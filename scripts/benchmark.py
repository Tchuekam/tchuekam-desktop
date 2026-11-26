#!/usr/bin/env python
"""Banc de mesure de la plateforme TchueKAM.

Mesure ce qui décide du dimensionnement et de la qualité de service, et pas
des chiffres flatteurs :

``boot``
    Temps entre le lancement du processus et la première réponse de
    ``/readyz``. C'est ce qui conditionne la vitesse d'un déploiement, d'un
    redémarrage après incident et d'une montée en charge automatique.

``endpoints``
    Latence par endpoint à concurrence 1 (le coût propre de l'endpoint, sans
    file d'attente) puis à concurrence réaliste (le coût sous charge). Les
    deux ensemble disent si un endpoint est lent *ou* s'il attend.

``throughput``
    Balayage de concurrence jusqu'au plateau, et concurrence à laquelle le
    délestage commence. Un débit sans son plateau n'indique rien : il faut
    savoir si l'on mesure la capacité ou une file d'attente.

``memory``
    Empreinte résidente par worker, au repos et sous charge. C'est ce qui
    choisit la taille d'instance, et ce qui dit si l'OOM killer rôde.

``database``
    Plans d'exécution des requêtes du chemin critique sur un jeu de données
    réaliste, et détection des parcours séquentiels. Une base vide rend toute
    requête rapide ; les falaises de latence n'apparaissent qu'avec des
    lignes.

``startup``
    Temps d'import et de découverte d'outils de l'agent. C'est la latence que
    perçoit un utilisateur de la CLI à chaque invocation.

Usage
-----
    # Démarre un serveur, mesure tout, écrit le rapport
    python scripts/benchmark.py --json bench.json

    # Contre un serveur déjà lancé (ne mesure alors pas le démarrage)
    python scripts/benchmark.py --base-url http://127.0.0.1:8000

    # Un seul volet
    python scripts/benchmark.py --suite database
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

SUITES = ("boot", "endpoints", "throughput", "memory", "database", "startup")


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] * (1 - (rank - low)) + ordered[high] * (rank - low)


def http_get(url: str, headers: Optional[dict] = None, timeout: float = 30.0):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def host_facts() -> dict:
    """Contexte sans lequel les chiffres ne veulent rien dire."""
    facts = {"cpu_count": os.cpu_count()}
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    facts["memory_mb"] = int(line.split()[1]) // 1024
                    break
    except OSError:
        pass
    for key in ("WEB_CONCURRENCY", "TCHUEKAM_DB_POOL_SIZE", "TCHUEKAM_DB_MAX_OVERFLOW"):
        value = os.getenv(key, "").strip()
        if value:
            facts[key] = value
    return facts


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------


class ManagedServer:
    """Lance la vraie commande de production et attend la disponibilité."""

    def __init__(self, port: int):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.process: Optional[subprocess.Popen] = None
        self.log_path = REPO_ROOT / "benchmark-server.log"
        self._log_handle = None

    def start(self) -> float:
        """Démarre et retourne le temps jusqu'à la première disponibilité."""
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        env = {**os.environ, "PORT": str(self.port)}
        started = time.perf_counter()
        self.process = subprocess.Popen(
            [sys.executable, "-m", "gunicorn", "-c", "gunicorn.conf.py",
             "tchuekam_backend.main:app"],
            cwd=REPO_ROOT,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
        deadline = started + 120.0
        while time.perf_counter() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"le serveur s'est arrêté au démarrage ; voir {self.log_path}"
                )
            try:
                status, _ = http_get(f"{self.base_url}/readyz", timeout=2.0)
                if status == 200:
                    return time.perf_counter() - started
            except Exception:
                pass
            time.sleep(0.05)
        raise RuntimeError(f"le serveur n'est pas devenu disponible ; voir {self.log_path}")

    def worker_pids(self) -> List[int]:
        if self.process is None:
            return []
        try:
            out = subprocess.run(
                ["pgrep", "-P", str(self.process.pid)],
                capture_output=True, text=True, check=False,
            ).stdout
            return [int(p) for p in out.split()]
        except Exception:
            return []

    def stop(self) -> Optional[float]:
        """Arrête proprement et retourne la durée du drainage."""
        if self.process is None or self.process.poll() is not None:
            return None
        started = time.perf_counter()
        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        try:
            self.process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            return None
        finally:
            if self._log_handle:
                self._log_handle.close()
        return time.perf_counter() - started


# ---------------------------------------------------------------------------
# Jetons
# ---------------------------------------------------------------------------


def mint_token() -> str:
    """Forge un jeton d'accès sans passer par /auth/signin.

    Argon2id coûte ~100 ms et 64 Mio par vérification : mesurer les endpoints
    de lecture à travers une vraie connexion mesurerait Argon2, pas eux.
    """
    import loadtest

    tokens = loadtest.provision_users(1)
    if not tokens:
        raise RuntimeError("impossible de préparer un utilisateur de mesure")
    return tokens[0][1]


# ---------------------------------------------------------------------------
# Volets
# ---------------------------------------------------------------------------


def suite_boot(port: int, repeats: int) -> dict:
    """Mesure le démarrage à froid, plusieurs fois.

    Une seule mesure n'est pas fiable : le premier démarrage paie les caches
    de page du système de fichiers et la compilation des bytecodes.
    """
    boots: List[float] = []
    drains: List[float] = []
    for _ in range(repeats):
        server = ManagedServer(port)
        boots.append(server.start())
        drain = server.stop()
        if drain is not None:
            drains.append(drain)
        time.sleep(1.0)
    return {
        "cold_boot_seconds": {
            "min": round(min(boots), 2),
            "median": round(statistics.median(boots), 2),
            "max": round(max(boots), 2),
            "samples": [round(b, 2) for b in boots],
        },
        "graceful_drain_seconds": {
            "median": round(statistics.median(drains), 2) if drains else None,
            "max": round(max(drains), 2) if drains else None,
        },
    }


#: Endpoints de lecture mesurés individuellement.
#:
#: Tous passent par l'authentification complète (session + utilisateur) ;
#: ``/audit/logs`` ajoute la résolution RBAC, et c'est le seul qui lit une
#: grande table.
_ENDPOINTS = (
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/users/me/devices"),
    ("GET", "/api/v1/organizations"),
    ("GET", "/api/v1/audit/logs?limit=20"),
    ("GET", "/api/v1/audit/logs?limit=100"),
    # Les deux sondes servent de référence basse : ``/health`` ne touche pas
    # la base, ``/readyz`` fait deux allers-retours SQL. L'écart entre elles et
    # les endpoints applicatifs situe le coût de l'accès aux données.
    ("GET", "/health"),
    ("GET", "/readyz"),
)
#: ``/api/v1/files`` est délibérément absent : le routeur n'expose que
#: ``/files/{file_id}``, donc ``GET /api/v1/files`` renvoie 404. Le mesurer
#: produirait une ligne à 0,5 ms qui se lit comme un endpoint rapide alors
#: qu'elle ne mesure que le chemin d'erreur.


def suite_endpoints(base_url: str, token: str, iterations: int) -> dict:
    """Latence par endpoint, un appel à la fois.

    À concurrence 1 il n'y a aucune file d'attente : ce qui est mesuré est le
    coût propre de l'endpoint. Comparé à la même mesure sous charge, l'écart
    révèle si un endpoint est intrinsèquement lent ou simplement en attente.
    """
    headers = {"Authorization": f"Bearer {token}"}
    results: Dict[str, dict] = {}
    for method, path in _ENDPOINTS:
        latencies: List[float] = []
        statuses: Dict[int, int] = {}
        # Deux appels à blanc : le premier paie le cache RBAC froid et
        # l'établissement de la connexion, et écraserait la médiane.
        for _ in range(2):
            http_get(f"{base_url}{path}", headers=headers)
        for _ in range(iterations):
            start = time.perf_counter()
            status, _ = http_get(f"{base_url}{path}", headers=headers)
            latencies.append((time.perf_counter() - start) * 1000)
            statuses[status] = statuses.get(status, 0) + 1
        results[f"{method} {path}"] = {
            "p50_ms": round(percentile(latencies, 50), 2),
            "p95_ms": round(percentile(latencies, 95), 2),
            "p99_ms": round(percentile(latencies, 99), 2),
            "status_codes": statuses,
        }
    return results


def suite_throughput(base_url: str, levels: List[int], duration: float, processes: int) -> dict:
    """Balaye la concurrence pour trouver le plateau et le début du délestage."""
    import asyncio

    import loadtest

    rows = []
    for users in levels:
        args = argparse.Namespace(
            base_url=base_url, users=users, duration=duration, think_time=0.0,
            timeout=30.0, scenario="read", json="", processes=min(processes, max(1, users // 25) or 1),
        )
        summary = (
            loadtest.run_sharded(args)
            if args.processes > 1
            else asyncio.run(loadtest.run(args))
        )
        # ``loadtest.report`` indexe ``status_codes`` par entier. Appelé
        # directement, on reçoit donc des clés ``int`` ; après un aller-retour
        # JSON (comme en ligne de commande) elles deviennent des chaînes. On
        # normalise, sinon le code ne fonctionne que dans un des deux cas.
        codes = {int(k): v for k, v in summary["status_codes"].items()}
        rows.append({
            "concurrency": users,
            "rps": summary["throughput_rps"],
            "p50_ms": summary["latency_ms"]["p50"],
            "p95_ms": summary["latency_ms"]["p95"],
            "p99_ms": summary["latency_ms"]["p99"],
            "success_pct": summary["success_rate_pct"],
            "shed_503": codes.get(503, 0),
            "errors_5xx": sum(v for k, v in codes.items() if 500 <= k < 600 and k != 503),
            # Statut 0 = échec de transport (le client a abandonné). À part,
            # car ce n'est pas une réponse du serveur.
            "transport_errors": codes.get(0, 0),
        })

    served = [r for r in rows if r["errors_5xx"] == 0]
    plateau = max(served, key=lambda r: r["rps"]) if served else None
    first_shed = next((r for r in rows if r["shed_503"] > 0), None)

    return {
        "sweep": rows,
        "plateau_rps": plateau["rps"] if plateau else None,
        "plateau_at_concurrency": plateau["concurrency"] if plateau else None,
        "shedding_begins_at_concurrency": first_shed["concurrency"] if first_shed else None,
        # Zéro 5xx sur tout le balayage est le critère qui compte : il dit que
        # la surcharge se traduit en délestage propre et non en erreurs.
        "any_server_errors": any(r["errors_5xx"] > 0 for r in rows),
    }


def _rss_mb(pid: int) -> Optional[float]:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def suite_memory(server: Optional[ManagedServer], base_url: str, token: str) -> dict:
    """Empreinte résidente par worker, au repos puis après du trafic."""
    if server is None:
        return {"skipped": "mesure possible uniquement sur un serveur lancé par le banc"}

    pids = server.worker_pids()
    idle = [m for m in (_rss_mb(p) for p in pids) if m is not None]

    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(400):
        http_get(f"{base_url}/api/v1/users/me", headers=headers)

    loaded = [m for m in (_rss_mb(p) for p in pids) if m is not None]

    return {
        "workers": len(pids),
        "rss_idle_mb": {"per_worker_median": round(statistics.median(idle), 1) if idle else None,
                        "total": round(sum(idle), 1) if idle else None},
        "rss_after_traffic_mb": {"per_worker_median": round(statistics.median(loaded), 1) if loaded else None,
                                 "total": round(sum(loaded), 1) if loaded else None},
        # Le pire cas de hachage de mot de passe s'ajoute à cette empreinte :
        # slots x memory_cost, réservés simultanément (voir core/security.py).
        "password_hashing_worst_case_mb": _hashing_worst_case_mb(),
    }


def _hashing_worst_case_mb() -> Optional[float]:
    try:
        from tchuekam_backend.core.security import hashing_capacity

        return round(hashing_capacity()["max_resident_kib"] / 1024, 1)
    except Exception:
        return None


#: Requêtes du chemin critique, telles que l'application les émet.
#:
#: Les clés sont passées en paramètres liés, et non via une sous-requête
#: ``(SELECT ... LIMIT 1)``. Une sous-requête ajoute au plan un parcours
#: séquentiel qui appartient au banc et non à l'application : il rendrait la
#: détection d'index manquant inexploitable, puisque chaque plan contiendrait
#: un ``Seq Scan`` parasite.
_HOT_QUERIES = (
    ("auth: session by primary key",
     "SELECT * FROM sessions WHERE id = :session_id"),
    ("auth: user by primary key",
     "SELECT * FROM users WHERE id = :user_id"),
    ("signin: user by email",
     "SELECT * FROM users WHERE email = :email"),
    ("rbac: roles of a user",
     "SELECT roles.* FROM roles JOIN user_roles ON user_roles.role_id = roles.id "
     "WHERE user_roles.user_id = :user_id"),
    ("rbac: permissions of a user",
     "SELECT permissions.* FROM permissions "
     "JOIN role_permissions ON role_permissions.permission_id = permissions.id "
     "JOIN roles ON roles.id = role_permissions.role_id "
     "JOIN user_roles ON user_roles.role_id = roles.id "
     "WHERE user_roles.user_id = :user_id"),
    ("devices: active sessions of a user",
     "SELECT * FROM sessions WHERE user_id = :user_id AND is_revoked = false"),
    ("refresh: session by refresh token hash",
     "SELECT * FROM sessions WHERE refresh_token_hash = :refresh_hash"),
    ("organizations: memberships of a user",
     "SELECT * FROM organization_memberships WHERE user_id = :user_id AND status = 'ACTIVE'"),
    ("audit: first page",
     "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100 OFFSET 0"),
)

#: Décalages de pagination mesurés. OFFSET lit puis jette toutes les lignes
#: sautées : le coût croît linéairement avec le décalage, et la mesure sert à
#: établir à partir de quel volume la pagination devient le poste dominant.
_OFFSET_LEVELS = (0, 1_000, 10_000, 40_000)

#: En dessous de ce nombre de lignes, un parcours séquentiel est le plan
#: optimal et non un défaut : la table tient dans quelques pages et un
#: index coûterait plus cher à parcourir.
_SEQ_SCAN_ROW_THRESHOLD = 1_000


def suite_database() -> dict:
    """Plans d'exécution du chemin critique, et coût de la pagination."""
    from sqlalchemy import text

    from tchuekam_backend.core.database import _IS_SQLITE, engine

    if _IS_SQLITE:
        return {"skipped": "EXPLAIN ANALYZE requiert PostgreSQL"}

    out: dict = {"table_sizes": {}, "hot_queries": [], "offset_scaling": []}

    with engine.connect() as conn:
        for table in ("users", "sessions", "audit_logs", "organizations",
                      "organization_memberships", "user_roles", "role_permissions"):
            try:
                out["table_sizes"][table] = conn.execute(
                    text(f"SELECT count(*) FROM {table}")
                ).scalar()
            except Exception:
                continue

        # Clés réelles, lues une fois, puis liées aux requêtes mesurées.
        keys = {
            "user_id": conn.execute(text("SELECT id FROM users LIMIT 1")).scalar(),
            "email": conn.execute(text("SELECT email FROM users LIMIT 1")).scalar(),
            "session_id": conn.execute(text("SELECT id FROM sessions LIMIT 1")).scalar(),
            "refresh_hash": conn.execute(
                text("SELECT refresh_token_hash FROM sessions LIMIT 1")
            ).scalar(),
        }
        if keys["user_id"] is None:
            return {"skipped": "base vide : les plans ne seraient pas représentatifs"}

        for label, sql in _HOT_QUERIES:
            try:
                plan = "\n".join(
                    row[0] for row in conn.execute(
                        text(f"EXPLAIN (ANALYZE, COSTS OFF) {sql}"), keys
                    )
                )
            except Exception as exc:
                out["hot_queries"].append({"query": label, "error": str(exc)[:160]})
                continue

            exec_match = re.search(r"Execution Time: ([0-9.]+) ms", plan)
            # Un parcours séquentiel dans le plan d'une requête du chemin
            # critique peut signaler un index manquant : son coût croît avec la
            # table, donc il tient tant que les données sont rares et
            # s'effondre en production.
            #
            # Mais seulement au-delà d'une certaine taille. Sur une table de
            # quelques lignes qui tient dans une page — ici `roles`,
            # `permissions`, `role_permissions` — le parcours séquentiel est le
            # *bon* plan, et le planificateur le choisit à raison. Les signaler
            # noierait le signal utile sous des faux positifs permanents.
            scans = sorted(set(re.findall(r"Seq Scan on (\w+)", plan)))
            significant = [
                t for t in scans
                if out["table_sizes"].get(t, 0) >= _SEQ_SCAN_ROW_THRESHOLD
            ]
            out["hot_queries"].append({
                "query": label,
                "execution_ms": float(exec_match.group(1)) if exec_match else None,
                "seq_scans": scans,
                "seq_scans_on_large_tables": significant,
                "uses_index": "Index Scan" in plan or "Index Only Scan" in plan or "Bitmap Index Scan" in plan,
            })

        for offset in _OFFSET_LEVELS:
            try:
                plan = "\n".join(
                    row[0] for row in conn.execute(
                        text("EXPLAIN (ANALYZE, COSTS OFF) SELECT * FROM audit_logs "
                             f"ORDER BY created_at DESC LIMIT 100 OFFSET {offset}")
                    )
                )
            except Exception:
                continue
            exec_match = re.search(r"Execution Time: ([0-9.]+) ms", plan)
            # Le noeud qui lit réellement les lignes est celui sous le
            # ``Limit`` : c'est son compte de lignes qui montre le travail
            # jeté par OFFSET, pas celui du ``Limit`` (toujours égal à LIMIT).
            #
            # Le libellé dépend des options : « actual rows=N » avec TIMING
            # OFF, « actual time=a..b rows=N » sinon. Les deux sont acceptés.
            rows_match = re.search(
                r"(?:Index Scan|Index Only Scan|Seq Scan|Sort)[^\n]*?"
                r"actual (?:time=[0-9.]+\.\.[0-9.]+ )?rows=(\d+)",
                plan,
            )
            out["offset_scaling"].append({
                "offset": offset,
                "execution_ms": float(exec_match.group(1)) if exec_match else None,
                "rows_scanned": int(rows_match.group(1)) if rows_match else None,
            })

    # Les clés étant liées en paramètres, tout ``Seq Scan`` restant vient
    # bien du chemin applicatif et signale un index manquant.
    # Le verdict : une requête du chemin critique qui parcourt séquentiellement
    # une table de taille non triviale. C'est le seul motif qui demande une
    # action (ajouter un index), et il doit ressortir seul.
    out["needs_an_index"] = [
        {"query": q["query"], "tables": q["seq_scans_on_large_tables"]}
        for q in out["hot_queries"]
        if q.get("seq_scans_on_large_tables")
    ]
    return out


def suite_startup() -> dict:
    """Temps d'import de l'agent et du backend, mesuré en sous-processus.

    Un import n'a lieu qu'une fois par processus : le mesurer dans le
    processus courant renverrait zéro au second appel. C'est la latence
    perçue à chaque invocation de la CLI.
    """
    targets = {
        "backend_app": "import tchuekam_backend.main",
        "agent_tools": "import model_tools",
        "agent_core": "import run_agent",
        "cli": "import cli",
    }
    out = {}
    for label, statement in targets.items():
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, "-c", statement],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
            )
            elapsed = (time.perf_counter() - started) * 1000
            if completed.returncode != 0:
                out[label] = {"error": (completed.stderr or "").strip().splitlines()[-1][:160]}
                break
            samples.append(elapsed)
        else:
            out[label] = {"median_ms": round(statistics.median(samples), 1),
                          "min_ms": round(min(samples), 1)}
    return out


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="", help="Serveur déjà lancé. Sinon le banc en démarre un.")
    parser.add_argument("--port", type=int, default=8120)
    parser.add_argument("--suite", action="append", choices=SUITES, default=None,
                        help="Volet à exécuter (répétable). Par défaut : tous.")
    parser.add_argument("--quick", action="store_true", help="Durées réduites.")
    parser.add_argument("--json", default="", help="Écrit le rapport JSON ici.")
    args = parser.parse_args()

    suites = args.suite or list(SUITES)
    quick = args.quick

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": host_facts(),
        "suites": {},
    }

    server: Optional[ManagedServer] = None
    base_url = args.base_url.rstrip("/")

    try:
        if "boot" in suites and not base_url:
            print("== boot ==", file=sys.stderr)
            report["suites"]["boot"] = suite_boot(args.port, repeats=2 if quick else 3)

        needs_server = any(s in suites for s in ("endpoints", "throughput", "memory"))
        if needs_server and not base_url:
            server = ManagedServer(args.port)
            boot_seconds = server.start()
            report["suites"].setdefault("boot", {}).setdefault(
                "cold_boot_seconds", {}
            ).setdefault("last_run", round(boot_seconds, 2))
            base_url = server.base_url

        token = ""
        if any(s in suites for s in ("endpoints", "throughput", "memory")):
            token = mint_token()

        if "endpoints" in suites:
            print("== endpoints ==", file=sys.stderr)
            report["suites"]["endpoints"] = suite_endpoints(
                base_url, token, iterations=30 if quick else 100
            )

        if "throughput" in suites:
            print("== throughput ==", file=sys.stderr)
            levels = [25, 100, 200] if quick else [25, 50, 100, 200, 400]
            report["suites"]["throughput"] = suite_throughput(
                base_url, levels, duration=8.0 if quick else 15.0, processes=4
            )

        if "memory" in suites:
            print("== memory ==", file=sys.stderr)
            report["suites"]["memory"] = suite_memory(server, base_url, token)

        if "database" in suites:
            print("== database ==", file=sys.stderr)
            report["suites"]["database"] = suite_database()

        if "startup" in suites:
            print("== startup ==", file=sys.stderr)
            report["suites"]["startup"] = suite_startup()

    finally:
        if server is not None:
            drain = server.stop()
            if drain is not None:
                report["suites"].setdefault("boot", {})["graceful_drain_seconds_last"] = round(drain, 2)

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json:
        Path(args.json).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
