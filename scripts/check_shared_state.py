#!/usr/bin/env python
"""Vérifie que l'état partagé l'est réellement, entre *processus* distincts.

Pourquoi un test pytest ne suffit pas
-------------------------------------
Les quotas de débit, la révocation de jetons et le cache RBAC doivent être
partagés par tous les workers. Un test exécuté dans un seul processus ne peut
pas distinguer « partagé via Redis » de « stocké dans un dictionnaire local » :
les deux passent. La seule vérification qui a du sens consiste à écrire depuis
un processus et à lire depuis un autre.

C'est exactement la régression que ce script attrape : un repli silencieux sur
l'implémentation mémoire (Redis non configuré, injoignable, ou un refactor qui
court-circuite le client) laisse l'application fonctionner en apparence, mais
multiplie le quota effectif par le nombre de workers et fait manquer les
révocations.

Sortie non nulle si l'état n'est pas partagé.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _writer(_: int) -> dict:
    """Consomme une partie d'un quota, révoque un jeton, écrit dans le cache."""
    from tchuekam_backend.core.cache import cache_service
    from tchuekam_backend.core.rate_limiter import rate_limiter
    from tchuekam_backend.core.security import revoke_jti

    rate_limiter.reset("xproc-check")
    consumed = [rate_limiter.is_allowed("xproc-check", 4, 60)[0] for _ in range(2)]
    revoke_jti("xproc-check-jti")
    cache_service.set("xproc-check:key", {"written_by": "writer"}, ttl_seconds=120)
    return {"consumed": consumed}


def _reader(_: int) -> dict:
    """Lit ce que l'autre processus a écrit."""
    from tchuekam_backend.core.cache import cache_service
    from tchuekam_backend.core.rate_limiter import rate_limiter
    from tchuekam_backend.core.security import is_jti_revoked

    return {
        # Le quota est de 4 et le writer en a consommé 2 : un quota partagé
        # n'en laisse que 2. Un quota local en laisserait 4.
        "remaining_allowed": [
            rate_limiter.is_allowed("xproc-check", 4, 60)[0] for _ in range(4)
        ],
        "sees_revocation": is_jti_revoked("xproc-check-jti"),
        "sees_cache": cache_service.get("xproc-check:key"),
    }


def main() -> int:
    from tchuekam_backend.core import redis_client

    if not redis_client.is_configured():
        print("ÉCHEC : REDIS_URL n'est pas configuré ; rien à vérifier.", file=sys.stderr)
        return 1

    health = redis_client.health()
    if not health.get("available"):
        print(f"ÉCHEC : Redis injoignable ({health}).", file=sys.stderr)
        return 1
    print(f"Redis joignable : {health}")

    # "spawn" : un fork hériterait les connexions Redis et SQLAlchemy du
    # parent, et le test passerait pour la mauvaise raison — les deux
    # « processus » partageraient la même socket.
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=1) as pool:
        written = pool.map(_writer, [0])[0]
    with ctx.Pool(processes=1) as pool:
        read = pool.map(_reader, [0])[0]

    print(f"Processus A : {written}")
    print(f"Processus B : {read}")

    failures = []

    if written["consumed"] != [True, True]:
        failures.append(f"le writer n'a pas consommé son quota : {written['consumed']}")

    allowed = read["remaining_allowed"]
    if allowed != [True, True, False, False]:
        failures.append(
            "quota NON partagé entre processus : le second processus a obtenu "
            f"{sum(allowed)} autorisations sur 4 au lieu de 2 — chaque worker "
            f"applique son propre quota ({allowed})"
        )

    if read["sees_revocation"] is not True:
        failures.append(
            "révocation de jeton NON partagée : un jeton révoqué sur un worker "
            "reste accepté par les autres"
        )

    if read["sees_cache"] != {"written_by": "writer"}:
        failures.append(
            "cache NON partagé : une invalidation sur un worker n'atteindrait "
            f"pas les autres (lu : {read['sees_cache']!r})"
        )

    if failures:
        print("\nÉCHEC :", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("\nOK : quota, révocation et cache sont partagés entre processus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
