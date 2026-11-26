#!/usr/bin/env python
"""Générateur de charge pour le backend SaaS TchueKAM.

Usage
-----
    # Palier réaliste : 1000 sessions simultanées avec temps de réflexion
    python scripts/loadtest.py --users 1000 --duration 60

    # Boucle fermée : 1000 requêtes en vol en permanence (point de saturation)
    python scripts/loadtest.py --users 1000 --duration 30 --think-time 0

    # Chemin de connexion seul, qui est volontairement coûteux (Argon2)
    python scripts/loadtest.py --scenario login --users 50 --duration 20

Ce que mesure l'outil
---------------------
Des percentiles de latence et un taux d'erreur par endpoint, plus l'état du
pool de connexions relevé pendant la course. Une moyenne ne dit rien d'utile
sur une file d'attente : c'est le p95 et le p99 qui révèlent la saturation,
parce qu'une moyenne reste basse tant que la majorité des requêtes passe.

« 1000 utilisateurs simultanés » : deux lectures
------------------------------------------------
* **Sessions simultanées** (défaut) — mille utilisateurs connectés qui
  agissent par intermittence. Avec un temps de réflexion de 3 s et 3 requêtes
  par action, cela représente de l'ordre de 300 à 1000 req/s. C'est la charge
  réelle d'un produit à mille utilisateurs actifs.
* **Requêtes simultanées** (``--think-time 0``) — mille requêtes en vol en
  permanence. Personne n'utilise un produit ainsi, mais c'est la borne haute
  qui montre où le système sature, et c'est la bonne mesure pour dimensionner.

Les deux sont mesurées, parce que confondre les deux conduit soit à
sous-dimensionner, soit à payer dix fois le nécessaire.

Préparation des jetons
----------------------
Les jetons sont forgés directement (``create_access_token`` + une ligne de
session), sans passer par ``/auth/signin``. Volontaire : Argon2id consomme
64 Mio et ~100 ms de CPU par vérification, donc mille connexions simultanées
mesureraient le coût d'Argon2 et non celui du chemin de requête en régime
établi. Le scénario ``login`` mesure ce chemin séparément.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


#: Domaine des comptes de charge.
#:
#: Un domaine ordinaire, et surtout pas un TLD réservé comme ``.local`` :
#: ``email-validator`` les refuse, et comme les schémas de réponse valident le
#: champ e-mail en *sortie*, chaque lecture de profil renverrait alors un 500
#: — on mesurerait la gestion d'erreur au lieu du chemin nominal.
_LOADTEST_DOMAIN = "loadtest.tchuekam.com"

#: Rôle attribué aux comptes de charge.
#:
#: « Support » porte ``audit.read``, ce qui fait passer ``/audit/logs`` par
#: ``require_permission`` avec une réponse 200. C'est le seul moyen d'inclure
#: le chemin RBAC — celui qui coûtait deux jointures par requête — dans la
#: mesure, plutôt que de mesurer un 403 renvoyé juste avant.
_LOADTEST_ROLE = "Support"

@dataclass
class Result:
    label: str
    status: int
    latency_ms: float
    error: Optional[str] = None


@dataclass
class Stats:
    results: List[Result] = field(default_factory=list)
    pool_samples: List[dict] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def wall_seconds(self) -> float:
        return max(1e-9, self.ended_at - self.started_at)


def percentile(values: List[float], pct: float) -> float:
    """Percentile par interpolation linéaire (méthode « inclusive »)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


# ---------------------------------------------------------------------------
# Préparation : utilisateurs et jetons
# ---------------------------------------------------------------------------


def provision_users(count: int) -> List[Tuple[str, str]]:
    """Crée ``count`` utilisateurs et retourne des couples (user_id, jeton).

    Insère directement en base : à mille utilisateurs, passer par l'API
    d'inscription prendrait plusieurs minutes de hachage Argon2 avant même le
    début de la mesure.
    """
    from datetime import datetime, timedelta, timezone

    from tchuekam_backend.core.database import new_session
    from tchuekam_backend.core.security import create_access_token
    from tchuekam_backend.domain.models import Role, User, UserRole, UserSession
    from tchuekam_backend.services.rbac_service import RbacService

    db = new_session()
    tokens: List[Tuple[str, str]] = []
    try:
        RbacService(db).seed_default_roles_and_permissions()
        base_role = db.query(Role).filter(Role.name == _LOADTEST_ROLE).first()

        # Un seul hachage, réutilisé : ces comptes ne servent jamais à
        # vérifier un mot de passe dans ce scénario.
        shared_hash = "pbkdf2_sha256$120000$bG9hZHRlc3RzYWx0MTIzNA==$bG9hZHRlc3RrZXkxMjM0NTY3OA=="
        expires_at = datetime.now(timezone.utc) + timedelta(hours=6)

        existing = {
            u.email: u
            for u in db.query(User).filter(User.email.like(f"loadtest-%@{_LOADTEST_DOMAIN}")).all()
        }

        new_users = []
        for i in range(count):
            email = f"loadtest-{i}@{_LOADTEST_DOMAIN}"
            user = existing.get(email)
            if user is None:
                user = User(
                    email=email,
                    password_hash=shared_hash,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
                new_users.append(user)
        db.flush()

        for user in new_users:
            if base_role is not None:
                db.add(UserRole(user_id=user.id, role_id=base_role.id))
        db.commit()

        all_users = (
            db.query(User).filter(User.email.like(f"loadtest-%@{_LOADTEST_DOMAIN}")).limit(count).all()
        )

        for user in all_users:
            session = UserSession(
                user_id=user.id,
                refresh_token_hash="loadtest",
                device_name="loadtest",
                expires_at=expires_at,
                is_revoked=False,
            )
            db.add(session)
            db.flush()
            token = create_access_token(
                user_id=user.id,
                email=user.email,
                session_id=session.id,
                roles=[_LOADTEST_ROLE],
                expires_delta=timedelta(hours=6),
            )
            tokens.append((user.id, token))
        db.commit()
    finally:
        db.close()
    return tokens


def provision_login_accounts(count: int, password: str) -> List[str]:
    """Crée des comptes avec un vrai hachage, pour mesurer la connexion."""
    from tchuekam_backend.core.database import new_session
    from tchuekam_backend.core.security import hash_password
    from tchuekam_backend.domain.models import User

    db = new_session()
    emails: List[str] = []
    try:
        shared_hash = hash_password(password)
        for i in range(count):
            email = f"loadtest-login-{i}@{_LOADTEST_DOMAIN}"
            emails.append(email)
            if db.query(User).filter(User.email == email).first() is None:
                db.add(
                    User(
                        email=email,
                        password_hash=shared_hash,
                        is_active=True,
                        is_verified=True,
                    )
                )
        db.commit()
    finally:
        db.close()
    return emails


# ---------------------------------------------------------------------------
# Scénarios
# ---------------------------------------------------------------------------

#: Mélange de requêtes d'un utilisateur actif, avec leur poids relatif.
#:
#: Dominé par la lecture, comme tout tableau de bord : on consulte bien plus
#: souvent qu'on écrit. Chaque entrée passe par l'authentification complète
#: (session + utilisateur) ; ``/audit/logs`` ajoute la résolution RBAC.
_READ_MIX: Tuple[Tuple[str, str, int], ...] = (
    ("GET", "/api/v1/users/me", 4),
    ("GET", "/api/v1/organizations", 2),
    ("GET", "/api/v1/audit/logs?limit=20", 2),
    ("GET", "/api/v1/users/me/devices", 1),
)


def _weighted_mix() -> List[Tuple[str, str]]:
    expanded: List[Tuple[str, str]] = []
    for method, path, weight in _READ_MIX:
        expanded.extend([(method, path)] * weight)
    return expanded


async def user_session_worker(
    client,
    base_url: str,
    token: str,
    client_ip: str,
    stats: Stats,
    stop_at: float,
    think_time: float,
    mix: List[Tuple[str, str]],
) -> None:
    """Simule un utilisateur : des actions séparées par un temps de réflexion."""
    headers = {
        "Authorization": f"Bearer {token}",
        # Chaque utilisateur simulé porte sa propre adresse, comme en vrai :
        # mille utilisateurs ne partagent pas une IP. Cela exerce aussi le
        # quota par IP avec mille compartiments distincts dans Redis.
        "X-Forwarded-For": client_ip,
    }
    while time.perf_counter() < stop_at:
        method, path = random.choice(mix)
        started = time.perf_counter()
        try:
            response = await client.request(method, f"{base_url}{path}", headers=headers)
            stats.results.append(
                Result(path, response.status_code, (time.perf_counter() - started) * 1000)
            )
        except Exception as exc:
            stats.results.append(
                Result(path, 0, (time.perf_counter() - started) * 1000, type(exc).__name__)
            )
        if think_time > 0:
            # Temps de réflexion aléatoire : avec une valeur fixe, les mille
            # utilisateurs se synchronisent en vagues et la charge mesurée
            # n'a plus rien à voir avec un trafic réel.
            await asyncio.sleep(random.uniform(think_time * 0.5, think_time * 1.5))


async def login_worker(
    client,
    base_url: str,
    emails: List[str],
    password: str,
    client_ip: str,
    stats: Stats,
    stop_at: float,
) -> None:
    """Martèle ``/auth/signin``, le chemin coûteux en CPU et en mémoire."""
    headers = {"X-Forwarded-For": client_ip}
    while time.perf_counter() < stop_at:
        email = random.choice(emails)
        started = time.perf_counter()
        try:
            response = await client.post(
                f"{base_url}/api/v1/auth/signin",
                json={"email": email, "password": password},
                headers=headers,
            )
            stats.results.append(
                Result("/auth/signin", response.status_code, (time.perf_counter() - started) * 1000)
            )
        except Exception as exc:
            stats.results.append(
                Result("/auth/signin", 0, (time.perf_counter() - started) * 1000, type(exc).__name__)
            )


async def sample_pool(client, base_url: str, stats: Stats, stop_at: float) -> None:
    """Relève l'état du pool de connexions pendant la course.

    C'est ce relevé qui distingue « le système est lent » de « le système
    attend une connexion » : si ``checked_out`` plafonne à
    ``pool_size + max_overflow``, la latence vient de la file d'attente du
    pool et non du code applicatif.
    """
    while time.perf_counter() < stop_at:
        try:
            response = await client.get(f"{base_url}/readyz", timeout=5.0)
            payload = response.json()
            stats.pool_samples.append(
                {"at": time.perf_counter(), **payload.get("db_pool", {})}
            )
        except Exception:
            pass
        await asyncio.sleep(1.0)


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------


def report(stats: Stats, args) -> dict:
    latencies = [r.latency_ms for r in stats.results]
    by_status: Dict[int, int] = defaultdict(int)
    by_label: Dict[str, List[float]] = defaultdict(list)
    errors: Dict[str, int] = defaultdict(int)

    for r in stats.results:
        by_status[r.status] += 1
        by_label[r.label].append(r.latency_ms)
        if r.error:
            errors[r.error] += 1

    total = len(stats.results)
    # 2xx et 3xx sont des succès. 401/403/404 attendus d'un scénario sont
    # comptés à part : ce sont des réponses correctes, pas des défaillances.
    ok = sum(c for s, c in by_status.items() if 200 <= s < 400)
    throttled = by_status.get(429, 0)
    server_errors = sum(c for s, c in by_status.items() if s >= 500)
    transport_errors = by_status.get(0, 0)

    peak_checked_out = max(
        (s.get("checkedout", 0) for s in stats.pool_samples), default=0
    )

    summary = {
        "scenario": args.scenario,
        "concurrent_users": args.users,
        "think_time_seconds": args.think_time,
        "duration_seconds": round(stats.wall_seconds, 2),
        "requests": total,
        "throughput_rps": round(total / stats.wall_seconds, 1),
        "success": ok,
        "success_rate_pct": round(100.0 * ok / total, 2) if total else 0.0,
        "throttled_429": throttled,
        "server_errors_5xx": server_errors,
        "transport_errors": transport_errors,
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 1),
            "p95": round(percentile(latencies, 95), 1),
            "p99": round(percentile(latencies, 99), 1),
            "max": round(max(latencies), 1) if latencies else 0.0,
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        },
        "status_codes": dict(sorted(by_status.items())),
        "errors": dict(errors),
        "db_pool_peak_checked_out": peak_checked_out,
        "per_endpoint": {
            label: {
                "requests": len(values),
                "p50_ms": round(percentile(values, 50), 1),
                "p95_ms": round(percentile(values, 95), 1),
                "p99_ms": round(percentile(values, 99), 1),
            }
            for label, values in sorted(by_label.items())
        },
    }
    return summary


async def run(args, _return_raw: bool = False, _prepared=None):
    import httpx

    stats = Stats()
    base_url = args.base_url.rstrip("/")
    password = "LoadTestPassword123!"

    # En mode multi-processus, la préparation est faite une seule fois par le
    # parent et transmise ici. Laisser chaque shard préparer de son côté
    # relancerait le semis RBAC en parallèle, et deux processus qui sèment en
    # même temps violent la contrainte d'unicité sur ``role_permissions`` —
    # c'est précisément la course que ``exclusive_startup_lock`` évite côté
    # application.
    if _prepared is not None:
        tokens = _prepared.get("tokens") or []
        emails = _prepared.get("emails") or []
    elif args.scenario == "login":
        print(f"Préparation de {args.users} comptes de connexion...", file=sys.stderr)
        emails = await asyncio.to_thread(provision_login_accounts, args.users, password)
        print("Prêt.", file=sys.stderr)
    else:
        print(f"Préparation de {args.users} utilisateurs et jetons...", file=sys.stderr)
        tokens = await asyncio.to_thread(provision_users, args.users)
        if len(tokens) < args.users:
            print(
                f"ATTENTION : {len(tokens)} jetons pour {args.users} demandés.",
                file=sys.stderr,
            )
        print("Prêt.", file=sys.stderr)

    # Le pool de connexions HTTP doit pouvoir porter toutes les requêtes en
    # vol : s'il est plus étroit que la concurrence demandée, c'est le client
    # qui met en file d'attente et la latence mesurée est celle du client, pas
    # celle du serveur.
    limits = httpx.Limits(
        max_connections=args.users + 50,
        max_keepalive_connections=args.users + 50,
    )
    timeout = httpx.Timeout(args.timeout, connect=10.0)

    mix = _weighted_mix()

    async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=False) as client:
        stats.started_at = time.perf_counter()
        stop_at = stats.started_at + args.duration

        workers = [asyncio.create_task(sample_pool(client, base_url, stats, stop_at))]

        for i in range(args.users):
            # Adresses simulées réparties sur plusieurs /16, pour ne pas faire
            # tomber mille utilisateurs dans le même compartiment de quota.
            client_ip = f"10.{(i // 65536) % 256}.{(i // 256) % 256}.{i % 256}"
            if args.scenario == "login":
                workers.append(
                    asyncio.create_task(
                        login_worker(
                            client, base_url, emails, password, client_ip, stats, stop_at
                        )
                    )
                )
            else:
                _user_id, token = tokens[i % len(tokens)]
                workers.append(
                    asyncio.create_task(
                        user_session_worker(
                            client,
                            base_url,
                            token,
                            client_ip,
                            stats,
                            stop_at,
                            args.think_time,
                            mix,
                        )
                    )
                )

        await asyncio.gather(*workers, return_exceptions=True)
        stats.ended_at = time.perf_counter()

    # Les shards renvoient leurs mesures brutes ; c'est le parent qui
    # agrège, sinon chaque shard produirait des percentiles sur sa seule
    # part et ils ne seraient pas moyennables.
    if _return_raw:
        return stats
    return report(stats, args)


def _shard_entrypoint(payload: dict) -> List[Tuple[str, int, float, Optional[str]]]:
    """Exécute une part de la charge dans un processus séparé.

    Retourne des tuples et non des ``Result`` : le passage entre processus
    passe par un pickle, et des types natifs évitent d'exiger que la classe
    soit importable à l'identique côté enfant.
    """
    args = argparse.Namespace(**payload["args"])
    args.users = payload["users"]
    summary_stats = asyncio.run(
        run(args, _return_raw=True, _prepared=payload["prepared"])
    )
    return [(r.label, r.status, r.latency_ms, r.error) for r in summary_stats.results]


def run_sharded(args) -> dict:
    """Répartit la charge sur plusieurs processus et fusionne les mesures.

    Un seul processus Python ne suffit pas à générer la charge : le GIL limite
    la boucle asyncio du client à un cœur, et au-delà de quelques centaines de
    connexions c'est *le client* qui sature. On mesure alors sa latence à lui.
    Le symptôme est non ambigu — latence élevée alors que le serveur montre un
    processeur inactif et aucune requête SQL en cours.
    """
    import multiprocessing

    shards = args.processes
    per_shard = args.users // shards
    remainder = args.users % shards
    sizes = [per_shard + (1 if i < remainder else 0) for i in range(shards)]
    sizes = [s for s in sizes if s > 0]

    serialisable = {k: v for k, v in vars(args).items()}

    # Préparation unique, dans le parent, puis découpage par shard. Voir le
    # commentaire dans ``run`` sur la course du semis RBAC.
    if args.scenario == "login":
        print(f"Préparation de {args.users} comptes de connexion...", file=sys.stderr)
        emails = provision_login_accounts(args.users, "LoadTestPassword123!")
        prepared_shards = [{"emails": emails, "tokens": []} for _ in sizes]
    else:
        print(f"Préparation de {args.users} utilisateurs et jetons...", file=sys.stderr)
        tokens = provision_users(args.users)
        if len(tokens) < args.users:
            print(
                f"ATTENTION : {len(tokens)} jetons pour {args.users} demandés.",
                file=sys.stderr,
            )
        prepared_shards = []
        cursor = 0
        for size in sizes:
            slice_ = tokens[cursor : cursor + size]
            # Un shard sans jeton ne pourrait rien émettre ; on recycle depuis
            # le début plutôt que de le laisser inerte.
            prepared_shards.append({"tokens": slice_ or tokens, "emails": []})
            cursor += size
    print("Prêt.", file=sys.stderr)

    payloads = [
        {"args": serialisable, "users": size, "prepared": prepared}
        for size, prepared in zip(sizes, prepared_shards)
    ]

    print(
        f"Charge répartie sur {len(sizes)} processus : {sizes} utilisateurs.",
        file=sys.stderr,
    )

    started = time.perf_counter()
    # "spawn" plutôt que "fork" : le processus parent a déjà ouvert des
    # connexions SQLAlchemy pendant la préparation, et un fork les ferait
    # partager par plusieurs processus — deux processus écrivant sur la même
    # socket PostgreSQL produisent des erreurs de protocole.
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=len(sizes)) as pool:
        shard_results = pool.map(_shard_entrypoint, payloads)
    ended = time.perf_counter()

    merged = Stats(started_at=started, ended_at=ended)
    for shard in shard_results:
        for label, status, latency_ms, error in shard:
            merged.results.append(Result(label, status, latency_ms, error))

    return report(merged, args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("LOADTEST_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--processes",
        type=int,
        default=1,
        help=(
            "Processus générateurs. Au-delà de ~200 connexions simultanées, un "
            "seul processus Python sature un cœur et devient le goulot mesuré."
        ),
    )
    parser.add_argument("--users", type=int, default=1000, help="Sessions simultanées.")
    parser.add_argument("--duration", type=float, default=60.0, help="Durée en secondes.")
    parser.add_argument(
        "--think-time",
        type=float,
        default=3.0,
        help="Secondes entre deux actions d'un même utilisateur. 0 = boucle fermée.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Délai par requête.")
    parser.add_argument(
        "--scenario",
        choices=("read", "login"),
        default="read",
        help="'read' : mélange de lectures authentifiées. 'login' : /auth/signin seul.",
    )
    parser.add_argument("--json", default="", help="Écrit le rapport JSON dans ce fichier.")
    args = parser.parse_args()

    if args.processes > 1:
        summary = run_sharded(args)
    else:
        summary = asyncio.run(run(args))
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json:
        Path(args.json).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
