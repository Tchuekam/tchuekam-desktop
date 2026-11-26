"""Métriques Prometheus du backend.

Agrégation multi-workers
------------------------
``prometheus_client`` tient ses compteurs en mémoire de processus. Sous
gunicorn, chaque scrape de ``/metrics`` est servi par *un* worker tiré au
hasard : les chiffres rapportés sont alors ceux de ce seul worker, soit une
fraction arbitraire du trafic réel. Un taux d'erreur calculé là-dessus est
faux, et une alerte bâtie dessus ne déclenche pas.

La bibliothèque résout ce problème avec son mode multiprocessus : chaque
worker écrit ses échantillons dans des fichiers mappés en mémoire d'un
répertoire partagé, et le scrape les agrège. Il faut pour cela que
``PROMETHEUS_MULTIPROC_DIR`` soit défini *avant* l'import de la
bibliothèque — c'est le rôle du hook ``post_fork`` dans ``gunicorn.conf.py``.

Ce module détecte le mode actif et expose ``render_latest()`` qui fait ce
qu'il faut dans les deux cas.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger("tchuekam_backend.metrics")

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        multiprocess,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - dépendance optionnelle
    _PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"


def is_available() -> bool:
    return _PROMETHEUS_AVAILABLE


def multiproc_dir() -> Optional[str]:
    """Répertoire d'agrégation multiprocessus, s'il est configuré."""
    for key in ("PROMETHEUS_MULTIPROC_DIR", "prometheus_multiproc_dir"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return None


#: Bornes du histogramme de latence, en secondes.
#:
#: Choisies autour du budget visé pour une requête d'API (quelques dizaines de
#: millisecondes) et étendues jusqu'à 10 s pour rendre visibles les attentes
#: sur le pool de connexions, dont le délai par défaut est de 10 s. Les bornes
#: par défaut de la bibliothèque s'arrêtent à 10 s mais sont trop grossières
#: en dessous de 100 ms, là où vit l'essentiel du trafic.
_LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0,
)

if _PROMETHEUS_AVAILABLE:
    REQUEST_COUNT = Counter(
        "tchuekam_http_requests_total",
        "Nombre de requêtes HTTP servies.",
        ["method", "path", "status"],
    )
    REQUEST_LATENCY = Histogram(
        "tchuekam_http_request_duration_seconds",
        "Latence des requêtes HTTP.",
        ["method", "path"],
        buckets=_LATENCY_BUCKETS,
    )
    REQUESTS_IN_FLIGHT = Gauge(
        "tchuekam_http_requests_in_flight",
        "Requêtes HTTP en cours de traitement.",
        multiprocess_mode="livesum",
    )
    RATE_LIMIT_REJECTED = Counter(
        "tchuekam_rate_limit_rejected_total",
        "Requêtes refusées par le limiteur de débit.",
        ["scope"],
    )
    DB_POOL = Gauge(
        "tchuekam_db_pool_connections",
        "Connexions du pool SQLAlchemy par état.",
        ["state"],
        multiprocess_mode="livemostrecent",
    )
    WS_CONNECTIONS = Gauge(
        "tchuekam_websocket_connections",
        "Connexions WebSocket ouvertes sur ce processus.",
        multiprocess_mode="livesum",
    )
    REDIS_UP = Gauge(
        "tchuekam_redis_up",
        "1 si le backplane Redis répond, 0 sinon.",
        multiprocess_mode="livemostrecent",
    )
else:  # pragma: no cover
    REQUEST_COUNT = REQUEST_LATENCY = REQUESTS_IN_FLIGHT = None
    RATE_LIMIT_REJECTED = DB_POOL = WS_CONNECTIONS = REDIS_UP = None


def observe_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)


def note_rate_limit_rejection(scope: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        RATE_LIMIT_REJECTED.labels(scope=scope).inc()


def refresh_runtime_gauges() -> None:
    """Rafraîchit les jauges échantillonnées au moment du scrape.

    Le pool de connexions, le nombre de sockets et l'état de Redis sont des
    états instantanés : les publier en continu n'apporterait rien, on les lit
    donc quand on nous les demande.
    """
    if not _PROMETHEUS_AVAILABLE:
        return

    try:
        from tchuekam_backend.core.database import pool_status

        snapshot = pool_status()
        for state, key in (
            ("checked_out", "checkedout"),
            ("checked_in", "checkedin"),
            ("size", "size"),
            ("overflow", "overflow"),
        ):
            if key in snapshot:
                DB_POOL.labels(state=state).set(snapshot[key])
    except Exception:
        logger.debug("Lecture de l'état du pool impossible.", exc_info=True)

    try:
        from tchuekam_backend.api.ws.notifications import ws_manager

        WS_CONNECTIONS.set(ws_manager.total_connections())
    except Exception:
        logger.debug("Lecture du compteur WebSocket impossible.", exc_info=True)

    try:
        from tchuekam_backend.core import redis_client

        if redis_client.is_configured():
            REDIS_UP.set(1 if redis_client.health().get("available") else 0)
        else:
            REDIS_UP.set(0)
    except Exception:
        logger.debug("Lecture de l'état Redis impossible.", exc_info=True)


def render_latest() -> Tuple[bytes, str]:
    """Rend l'exposition Prometheus, agrégée entre workers si configuré."""
    if not _PROMETHEUS_AVAILABLE:
        return b"", CONTENT_TYPE_LATEST

    refresh_runtime_gauges()

    directory = multiproc_dir()
    if directory:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST

    return generate_latest(), CONTENT_TYPE_LATEST


def mark_worker_exit() -> None:
    """Purge les échantillons du worker qui s'arrête.

    Sans cela, les jauges d'un worker mort restent dans le répertoire partagé
    et continuent d'être additionnées par le scrape : après quelques
    redéploiements, « requêtes en cours » et « sockets ouvertes » n'ont plus
    aucun rapport avec la réalité. Appelé depuis le hook ``child_exit`` de
    gunicorn.
    """
    if not _PROMETHEUS_AVAILABLE or not multiproc_dir():
        return
    try:
        multiprocess.mark_process_dead(os.getpid())
    except Exception:
        logger.debug("Purge des métriques du worker impossible.", exc_info=True)
