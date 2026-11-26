"""Configuration gunicorn du backend SaaS TchueKAM.

Usage
-----
    gunicorn -c gunicorn.conf.py tchuekam_backend.main:app

Pourquoi gunicorn et pas uvicorn seul
-------------------------------------
``uvicorn`` sert un seul processus, donc un seul cœur : le reste de la machine
reste inutilisé, et un endpoint synchrone bloquant immobilise tout le service.
``gunicorn`` supervise N processus ``UvicornWorker``, redémarre un worker mort,
et draine les requêtes en vol lors d'un déploiement.

Le calcul à ne pas se tromper
-----------------------------
Chaque worker ouvre son *propre* pool SQLAlchemy. Le nombre total de
connexions ouvertes sur PostgreSQL est donc :

    (TCHUEKAM_DB_POOL_SIZE + TCHUEKAM_DB_MAX_OVERFLOW) × workers × instances

Ce total doit rester sous le ``max_connections`` du serveur, déduction faite de
ce que consomment les migrations, les sauvegardes et les sessions
d'administration. Avec les valeurs par défaut (10 + 10) et 4 workers, une
instance peut ouvrir 80 connexions : cela tient sous le ``max_connections``
de 100 des offres PostgreSQL d'entrée de gamme, mais *une seule instance*.
Pour passer à l'échelle horizontale, soit on augmente ``max_connections``,
soit on place PgBouncer en mode transaction devant la base. Le détail du
dimensionnement est dans ``docs/CAPACITY.md``.

Ce fichier journalise le total calculé au démarrage, précisément pour que
personne n'ait à refaire ce calcul de tête.
"""

from __future__ import annotations

import multiprocessing
import os
import shutil
import tempfile


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _default_workers() -> int:
    """Nombre de workers par défaut.

    ``2 × cœurs + 1`` est la formule usuelle de gunicorn pour des workers
    synchrones. Elle est ici volontairement *plafonnée* : au-delà, ce n'est
    plus le CPU qui limite mais le nombre de connexions PostgreSQL, et un
    worker supplémentaire réserve 20 connexions de plus sans servir davantage
    de trafic. On préfère donc ajouter des instances, chacune avec son pool.
    """
    cores = multiprocessing.cpu_count()
    return max(2, min(2 * cores + 1, 8))


# ── Réseau ──────────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# ── Workers ─────────────────────────────────────────────────────────────────
# ``WEB_CONCURRENCY`` est la variable que Heroku, Render et Railway
# renseignent eux-mêmes en fonction de la taille d'instance ; on la respecte.
workers = _int_env("WEB_CONCURRENCY", _default_workers())
worker_class = "uvicorn.workers.UvicornWorker"

# Pas d'option `threads` ici : elle ne s'applique qu'aux workers natifs de
# gunicorn (`gthread`) et `UvicornWorker` l'ignore silencieusement. La largeur
# du pool de threads qui exécute les endpoints `def` est celle du pool AnyIO,
# fixée depuis le processus par `core/concurrency.apply_thread_limit()` au
# démarrage de l'application. L'y régler ici donnerait l'illusion d'un réglage
# sans aucun effet — c'est précisément ce qui laissait 40 threads se disputer
# 20 connexions.
#
# Pour l'ajuster : TCHUEKAM_WORKER_THREADS (lu par core/concurrency.py).
_db_pool_total = _int_env("TCHUEKAM_DB_POOL_SIZE", 10) + _int_env("TCHUEKAM_DB_MAX_OVERFLOW", 10)

# ── Délais ──────────────────────────────────────────────────────────────────
# Un worker qui ne répond plus au maître pendant `timeout` est tué. La valeur
# par défaut de gunicorn (30 s) tue un worker en train de servir un
# téléversement lent ou une requête longue ; 60 s laisse de la marge tout en
# détectant un vrai blocage.
timeout = _int_env("TCHUEKAM_WORKER_TIMEOUT", 60)

# Délai accordé à un worker pour terminer ses requêtes en vol après un
# SIGTERM. Il doit être inférieur au délai d'arrêt de l'orchestrateur
# (`maxShutdownDelaySeconds` chez Render, `terminationGracePeriodSeconds` chez
# Kubernetes), sinon le worker est tué avant d'avoir fini de drainer.
graceful_timeout = _int_env("TCHUEKAM_GRACEFUL_TIMEOUT", 25)

# Garde la connexion ouverte entre deux requêtes du même client. Derrière un
# répartiteur qui réutilise ses connexions, cela évite une poignée de main TCP
# (et TLS) par requête.
keepalive = _int_env("TCHUEKAM_KEEPALIVE", 5)

# ── Recyclage des workers ───────────────────────────────────────────────────
# Redémarre un worker après N requêtes : c'est le filet contre une fuite
# mémoire lente, qui autrement finit par faire tuer le processus par l'OOM
# killer au pire moment. Le `jitter` évite que tous les workers se recyclent
# en même temps et créent un trou de service.
max_requests = _int_env("TCHUEKAM_MAX_REQUESTS", 10_000)
max_requests_jitter = _int_env("TCHUEKAM_MAX_REQUESTS_JITTER", 1_000)

# ── Proxy ───────────────────────────────────────────────────────────────────
# En production l'application est derrière le répartiteur de l'hébergeur.
# `forwarded_allow_ips` indique de quelles adresses on accepte
# `X-Forwarded-For` / `X-Forwarded-Proto` ; uvicorn réécrit alors l'adresse du
# pair avec celle du vrai client, ce dont dépendent le quota par IP et
# l'émission de HSTS.
#
# `*` est le réglage adapté aux PaaS, où l'adresse interne du répartiteur
# n'est pas connue à l'avance et où seul ce répartiteur peut atteindre le
# conteneur. Sur une infrastructure dont le port est joignable autrement, il
# faut y mettre l'adresse du proxy : avec `*`, n'importe quel client pourrait
# usurper son adresse via `X-Forwarded-For`.
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")
proxy_allow_ips = forwarded_allow_ips

# ── Journalisation ──────────────────────────────────────────────────────────
accesslog = None  # ObservabilityMiddleware produit déjà le log d'accès.
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
capture_output = True

# ── Divers ──────────────────────────────────────────────────────────────────
preload_app = False
"""Volontairement désactivé.

``preload_app`` importe l'application avant le fork, ce qui économise de la
mémoire. Mais le moteur SQLAlchemy serait alors créé *avant* le fork, et ses
connexions héritées seraient partagées par tous les workers : deux processus
écrivant sur la même socket PostgreSQL produisent des erreurs de protocole
impossibles à diagnostiquer. Idem pour les connexions Redis.
"""

worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
"""Place les fichiers de pulsation des workers en mémoire partagée.

Sur un conteneur dont le système de fichiers est lent ou sur un disque réseau,
l'écriture de ces fichiers peut dépasser le délai de pulsation et faire tuer
des workers pourtant sains.
"""

_METRICS_DIR_ENV = "PROMETHEUS_MULTIPROC_DIR"


def on_starting(server) -> None:
    """Prépare le répertoire d'agrégation des métriques multiprocessus.

    Sans lui, un scrape de ``/metrics`` ne rapporte que les chiffres du worker
    qui a répondu, soit une fraction arbitraire du trafic (voir
    ``core/metrics.py``).
    """
    directory = os.getenv(_METRICS_DIR_ENV, "").strip()
    if not directory:
        directory = os.path.join(tempfile.gettempdir(), "tchuekam-metrics")
        os.environ[_METRICS_DIR_ENV] = directory

    # Purge au démarrage : les fichiers laissés par l'exécution précédente
    # seraient additionnés aux nouveaux, et les compteurs repartiraient d'un
    # total hérité d'avant le redéploiement.
    if os.path.isdir(directory):
        shutil.rmtree(directory, ignore_errors=True)
    os.makedirs(directory, exist_ok=True)

    total_connections = _db_pool_total * workers
    server.log.info(
        "TchueKAM API | workers=%s | connexions DB max pour cette instance = "
        "(%s par worker) × %s = %s — doit rester sous le max_connections de "
        "PostgreSQL",
        workers,
        _db_pool_total,
        workers,
        total_connections,
    )
    server.log.info("Métriques multiprocessus dans %s", os.environ[_METRICS_DIR_ENV])


def child_exit(server, worker) -> None:
    """Retire les échantillons du worker qui s'arrête.

    Les jauges d'un worker mort resteraient sinon dans le répertoire partagé
    et continueraient d'être additionnées : après quelques recyclages,
    « requêtes en cours » n'aurait plus aucun rapport avec la réalité.
    """
    try:
        from tchuekam_backend.core import metrics

        metrics.mark_worker_exit()
    except Exception:
        pass


def worker_abort(worker) -> None:
    """Journalise un worker tué pour dépassement de ``timeout``.

    C'est le symptôme le plus fréquent d'une saturation du pool de connexions
    (tous les threads attendent une connexion) et il mérite une ligne
    explicite, sinon le worker disparaît sans explication.
    """
    worker.log.error(
        "Worker %s tué après %ss sans réponse. Causes usuelles : pool de "
        "connexions saturé, requête SQL lente, ou appel bloquant dans la "
        "boucle d'événements. Voir /readyz et la métrique "
        "tchuekam_db_pool_connections.",
        worker.pid,
        timeout,
    )
