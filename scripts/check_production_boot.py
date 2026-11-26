#!/usr/bin/env python
"""Vérifie que le serveur de production démarre et sert réellement.

Pourquoi
--------
Les tests passent sous ``TestClient``, qui appelle l'application ASGI en
mémoire : il ne lance ni gunicorn, ni plusieurs workers, ni le cycle de vie
complet. Toute une classe de pannes n'est donc visible qu'ici :

* une commande de démarrage qui ne lance pas la bonne application (le dépôt
  démarrait le tableau de bord mono-utilisateur à la place de l'API) ;
* un échec de démarrage propre à la production — secret JWT manquant, schéma
  non migré, pilote PostgreSQL absent ;
* une course entre workers pendant le semis au démarrage ;
* une agrégation de métriques qui ne rapporte qu'un worker sur N ;
* une sonde de disponibilité qui répond 200 avant que le service soit prêt.

Ce script lance la vraie commande de production, attend la disponibilité, puis
vérifie les propriétés qu'un déploiement doit garantir.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PORT = os.getenv("PORT", "8111")
BASE = f"http://127.0.0.1:{PORT}"
BOOT_TIMEOUT_SECONDS = 90.0


def get(path: str, timeout: float = 10.0):
    """Retourne (status, corps, en-têtes) sans lever sur une erreur HTTP."""
    request = urllib.request.Request(f"{BASE}{path}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


def wait_until_ready(process: subprocess.Popen) -> bool:
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            status, _, _ = get("/readyz", timeout=3.0)
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def main() -> int:
    failures: list[str] = []

    print("Application des migrations...")
    migrate = subprocess.run(
        [sys.executable, "scripts/db_migrate.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if migrate.returncode != 0:
        print(migrate.stdout, migrate.stderr, file=sys.stderr)
        print("ÉCHEC : les migrations n'ont pas abouti.", file=sys.stderr)
        return 1

    log_path = REPO_ROOT / "gunicorn-boot-check.log"
    # encoding explicite : les lignes de log applicatives contiennent des
    # accents, et le mode texte sans encodage suit la locale du système
    # (cp1252 sur une installation Windows anglophone), ce qui les corrompt
    # à l'écriture puis fait échouer la relecture.
    log_handle = log_path.open("w", encoding="utf-8")
    print(f"Démarrage de gunicorn sur le port {PORT}...")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "-c",
            "gunicorn.conf.py",
            "tchuekam_backend.main:app",
        ],
        cwd=REPO_ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        # Groupe de processus propre, pour terminer le maître *et* ses workers.
        start_new_session=True,
    )

    try:
        if not wait_until_ready(process):
            log_handle.flush()
            print(log_path.read_text(encoding="utf-8")[-4000:], file=sys.stderr)
            print("ÉCHEC : le serveur n'est pas devenu disponible.", file=sys.stderr)
            return 1
        print("Serveur disponible.")

        # --- Disponibilité ------------------------------------------------
        status, body, _ = get("/readyz")
        payload = json.loads(body)
        print(f"/readyz -> {status} {payload.get('status')}")
        if payload.get("database") != "up":
            failures.append(f"/readyz ne voit pas la base : {payload.get('database')}")
        if not payload.get("schema_revision"):
            failures.append("/readyz ne rapporte aucune révision de schéma")
        if not payload.get("redis", {}).get("available"):
            failures.append(f"/readyz ne voit pas Redis : {payload.get('redis')}")

        # --- Vivacité -----------------------------------------------------
        status, body, _ = get("/livez")
        if status != 200:
            failures.append(f"/livez a répondu {status}")

        # --- Documentation interactive désactivée en production -----------
        for path in ("/docs", "/redoc", "/api/v1/openapi.json"):
            status, _, _ = get(path)
            if status != 404:
                failures.append(
                    f"{path} a répondu {status} en production : la documentation "
                    "expose toutes les routes et tous les schémas à un appelant "
                    "non authentifié"
                )

        # --- En-têtes de sécurité et identifiant de requête ---------------
        status, _, headers = get("/api/v1/health")
        lowered = {k.lower(): v for k, v in headers.items()}
        for header in (
            "x-content-type-options",
            "x-frame-options",
            "content-security-policy",
            "referrer-policy",
            "x-request-id",
        ):
            if header not in lowered:
                failures.append(f"en-tête absent de la réponse : {header}")

        # --- Enveloppe d'erreur -------------------------------------------
        status, body, _ = get("/api/v1/users/me")
        if status != 401:
            failures.append(f"une requête non authentifiée a répondu {status} au lieu de 401")
        else:
            error = json.loads(body).get("error", {})
            if not error.get("request_id"):
                failures.append("l'enveloppe d'erreur ne porte pas d'identifiant de requête")

        # --- Agrégation des métriques entre workers -----------------------
        # On force du trafic pour que chaque worker en voie, puis on vérifie
        # que le scrape totalise bien l'ensemble. Sans le mode multiprocessus,
        # il ne rapporterait que le worker ayant servi le scrape.
        probes = 60
        for _ in range(probes):
            get("/api/v1/users/me", timeout=5.0)
        status, body, _ = get("/metrics")
        if status != 200:
            failures.append(f"/metrics a répondu {status}")
        else:
            counted = sum(
                float(m.group(1))
                for m in re.finditer(r"^tchuekam_http_requests_total\{[^}]*\} ([0-9.e+]+)$", body, re.M)
            )
            workers = int(os.getenv("WEB_CONCURRENCY", "2"))
            print(f"/metrics totalise {counted:.0f} requêtes pour {probes} émises")
            # Une marge basse généreuse : le but est de distinguer « total »
            # de « un worker sur N », pas de compter à l'unité.
            if counted < probes * 0.8:
                failures.append(
                    f"/metrics ne rapporte que {counted:.0f} requêtes sur ~{probes} : "
                    f"l'agrégation multiprocessus ne fonctionne pas (PROMETHEUS_MULTIPROC_DIR), "
                    f"donc le scrape ne voit qu'un worker sur {workers}"
                )
            if "tchuekam_db_pool_connections" not in body:
                failures.append("/metrics n'expose pas l'état du pool de connexions")

        # --- Aucune 5xx pendant le contrôle -------------------------------
        log_handle.flush()
        log_text = log_path.read_text(encoding="utf-8")
        server_errors = len(re.findall(r'"status":5\d\d', log_text))
        if server_errors:
            failures.append(f"{server_errors} réponse(s) 5xx pendant le contrôle")
        if "QueuePool limit" in log_text:
            failures.append("saturation du pool de connexions pendant le contrôle")

        # --- Posture de démarrage journalisée -----------------------------
        # Si cette ligne manque, c'est que la journalisation n'est pas
        # configurée et que tout ce qui est émis en INFO est perdu.
        if "Démarrage" not in log_text:
            failures.append(
                "aucune ligne de posture au démarrage dans les logs : la "
                "journalisation n'est pas configurée et les niveaux INFO sont perdus"
            )

        # --- Arrêt propre --------------------------------------------------
        print("Test de l'arrêt propre...")
        started = time.monotonic()
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=40)
        except subprocess.TimeoutExpired:
            failures.append("le serveur n'a pas terminé dans les 40 s après SIGTERM")
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            print(f"Arrêt en {time.monotonic() - started:.1f}s")

    finally:
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        log_handle.close()

    if failures:
        print("\nÉCHEC :", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(f"\nJournal : {log_path}", file=sys.stderr)
        return 1

    print("\nOK : le serveur de production démarre, sert, mesure et s'arrête proprement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
