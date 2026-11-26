"""Gestionnaire d'accès et de sessions pour la base de données SQLAlchemy.

Dimensionnement du pool
-----------------------
Les valeurs par défaut de SQLAlchemy (``pool_size=5``, ``max_overflow=10``)
plafonnent un processus à 15 connexions. Les endpoints de ce backend sont
synchrones : FastAPI les exécute dans un pool de threads (40 threads par
défaut), et chacun réclame une connexion. Au-delà de 15 requêtes simultanées
par worker, les threads suivants attendent la disponibilité d'une connexion
pendant ``pool_timeout`` — 30 secondes par défaut — puis échouent. À mille
utilisateurs simultanés, c'est le premier mur rencontré.

Le dimensionnement est donc explicite et pilotable par variable
d'environnement, car le bon chiffre dépend de deux contraintes extérieures :

* ``max_connections`` du serveur PostgreSQL (souvent 100 sur les offres
  d'entrée de gamme), à partager entre *tous* les workers de *toutes* les
  instances, plus les migrations et les outils d'administration ;
* la largeur du pool de threads, qu'il est inutile de dépasser.

Règle de calcul : ``(pool_size + max_overflow) × workers × instances`` doit
rester sous le ``max_connections`` du serveur, marge de sécurité incluse. Voir
``docs/CAPACITY.md``.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from tchuekam_backend.core.config import _is_production, settings

logger = logging.getLogger("tchuekam_backend.database")

def _resolve_postgres_driver() -> Optional[str]:
    """Nom du pilote PostgreSQL réellement installé, ou ``None``.

    ``psycopg`` (v3) est préféré : c'est le pilote maintenu, et celui que
    SQLAlchemy 2.1 choisit par défaut. ``psycopg2`` reste accepté pour les
    déploiements qui l'ont déjà figé dans leur image.
    """
    for module_name, driver in (("psycopg", "psycopg"), ("psycopg2", "psycopg2")):
        try:
            __import__(module_name)
        except ImportError:
            continue
        return driver
    return None


def _normalise_database_url(raw: str) -> str:
    """Normalise l'URL de base, pilote PostgreSQL explicite inclus.

    Deux corrections sont appliquées :

    * ``postgres://`` — la forme historique distribuée par Heroku, Render et
      Railway — devient ``postgresql://``, seul préfixe que SQLAlchemy
      reconnaisse.
    * un ``postgresql://`` sans pilote reçoit un pilote explicite. SQLAlchemy
      2.0 résolvait cette forme vers ``psycopg2`` et 2.1 la résout vers
      ``psycopg`` (v3) : une URL nue dépend donc de la version de SQLAlchemy
      installée, et lève ``ModuleNotFoundError`` au démarrage dès que le
      pilote attendu n'est pas celui qui est présent. Nommer le pilote rend
      l'URL insensible à ce changement.
    """
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        driver = _resolve_postgres_driver()
        if driver is None:
            raise RuntimeError(
                "Aucun pilote PostgreSQL installé. Ajoutez `psycopg[binary]` "
                "(recommandé) ou `psycopg2-binary` aux dépendances du backend."
            )
        url = f"postgresql+{driver}://" + url[len("postgresql://"):]

    return url


_database_url = _normalise_database_url(settings.DATABASE_URL)

_IS_SQLITE = _database_url.startswith("sqlite")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _is_serverless() -> bool:
    """Vrai sous un hébergeur sans état persistant entre requêtes.

    Un pool n'a pas de sens quand le processus peut être gelé entre deux
    requêtes : les connexions qu'il garde ouvertes sont déjà mortes côté
    serveur au réveil, et chaque instance froide en accumule de nouvelles
    jusqu'à épuiser ``max_connections``.
    """
    return os.getenv("VERCEL", "").strip().lower() not in {"", "0", "false", "no"}


def pool_settings() -> dict:
    """Paramètres de pool effectifs (exposés pour ``/metrics`` et les tests)."""
    return {
        # 10 + 10 = 20 connexions par worker. Avec les 4 workers par défaut de
        # ``gunicorn.conf.py``, une instance ouvre au plus 80 connexions, ce
        # qui tient sous le ``max_connections`` de 100 des offres PostgreSQL
        # d'entrée de gamme. Les deux valeurs se dimensionnent ensemble : voir
        # ``docs/CAPACITY.md``.
        "pool_size": _int_env("TCHUEKAM_DB_POOL_SIZE", 10),
        "max_overflow": _int_env("TCHUEKAM_DB_MAX_OVERFLOW", 10),
        # 30 s par défaut chez SQLAlchemy : bien au-delà du budget d'une
        # requête HTTP. Une attente courte transforme une saturation en
        # erreur rapide et lisible, au lieu d'une file d'attente qui fait
        # expirer les clients et sature le pool de threads.
        "pool_timeout": _int_env("TCHUEKAM_DB_POOL_TIMEOUT", 10),
        # Les proxys (PgBouncer) et PostgreSQL ferment les connexions
        # inactives. Les recycler avant cette échéance évite de découvrir la
        # coupure en pleine requête.
        "pool_recycle": _int_env("TCHUEKAM_DB_POOL_RECYCLE", 1800),
    }


def _build_engine_kwargs() -> dict:
    connect_args: dict = {}
    engine_kwargs: dict = {
        # Vérifie la connexion avant de la prêter : sans cela, une connexion
        # coupée côté serveur fait échouer la requête qui la récupère.
        "pool_pre_ping": True,
    }

    if _IS_SQLITE:
        connect_args["check_same_thread"] = False
    else:
        # ``connect_timeout`` évite qu'un serveur injoignable bloque un thread
        # pour la durée du timeout TCP par défaut (plusieurs minutes).
        connect_args["connect_timeout"] = _int_env("TCHUEKAM_DB_CONNECT_TIMEOUT", 10)
        app_name = os.getenv("TCHUEKAM_DB_APP_NAME", "").strip() or "tchuekam-backend"
        # Identifie les connexions dans ``pg_stat_activity``, indispensable
        # pour attribuer une saturation au bon service.
        connect_args["application_name"] = app_name

    engine_kwargs["connect_args"] = connect_args

    if _is_serverless():
        engine_kwargs["poolclass"] = NullPool
    elif not _IS_SQLITE:
        # ``pool_size`` / ``max_overflow`` n'existent que sur ``QueuePool`` ;
        # les passer à ``NullPool`` lève un ``TypeError``. SQLite est exclu
        # parce qu'il sérialise les écritures de toute façon et qu'il est
        # refusé en production.
        engine_kwargs.update(pool_settings())

    return engine_kwargs


engine = create_engine(_database_url, **_build_engine_kwargs())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def new_session() -> Session:
    """Ouvre une session hors du cycle de vie d'une requête HTTP.

    Point de passage unique pour le code qui ne peut pas utiliser la
    dépendance ``get_db`` — le canal WebSocket, les tâches de fond. Il lit
    ``SessionLocal`` à l'appel, donc un test qui remplace ``SessionLocal``
    redirige aussi ces appelants.
    """
    return SessionLocal()


def _ensure_valid_prod_database() -> None:
    if (
        _is_production()
        and _IS_SQLITE
        and os.getenv("TCHUEKAM_ALLOW_SQLITE_IN_PROD", "").strip() != "1"
    ):
        raise RuntimeError(
            "SQLite n'est pas autorisé en production. Configurez TCHUEKAM_DATABASE_URL "
            "avec PostgreSQL (ou définissez TCHUEKAM_ALLOW_SQLITE_IN_PROD=1 explicitement)."
        )


def get_db() -> Generator[Session, None, None]:
    """Dépendance d'injection de session DB pour FastAPI."""
    _ensure_valid_prod_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def schema_is_managed_by_alembic() -> bool:
    """Vrai quand les migrations Alembic font autorité sur le schéma.

    ``create_all`` ne sait que créer ce qui manque : il n'applique aucune
    évolution (colonne ajoutée, type modifié, index renommé) sur une base déjà
    peuplée. Exécuté par N workers au démarrage, il déclenche en plus des
    courses sur ``CREATE TABLE``. En production, le schéma est donc appliqué
    par ``alembic upgrade head`` lors du déploiement, et le démarrage de
    l'application n'y touche pas.
    """
    override = os.getenv("TCHUEKAM_DB_AUTO_CREATE", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return False
    if override in {"0", "false", "no"}:
        return True
    return _is_production()


def init_db() -> None:
    """Prépare le schéma au démarrage.

    Hors production, crée les tables manquantes pour que ``pytest`` et un
    poste de développement fonctionnent sans étape supplémentaire. En
    production, ne fait que vérifier que le schéma a bien été migré : créer
    des tables depuis N workers concurrents est une course, et masquerait une
    migration oubliée.
    """
    _ensure_valid_prod_database()

    if not schema_is_managed_by_alembic():
        Base.metadata.create_all(bind=engine)
        return

    revision = current_schema_revision()
    if revision is None:
        raise RuntimeError(
            "Le schéma de base de données n'est pas initialisé : la table "
            "alembic_version est absente. Exécutez `alembic upgrade head` avant "
            "de démarrer l'application (ou définissez TCHUEKAM_DB_AUTO_CREATE=1 "
            "pour laisser l'application créer le schéma, ce qui est réservé au "
            "développement)."
        )
    logger.info("Schéma de base de données à la révision Alembic %s.", revision)


def current_schema_revision() -> Optional[str]:
    """Révision Alembic appliquée, ou ``None`` si la table est absente."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    except Exception:
        return None
    return str(row[0]) if row else None


#: Clé du verrou d'initialisation. Les verrous consultatifs PostgreSQL sont
#: indexés par entier 64 bits, pas par nom : la constante est donc tirée une
#: fois du nom logique et doit rester stable entre versions, sinon deux
#: déploiements successifs ne se verrouillent plus mutuellement.
_SEED_LOCK_KEY = 0x7C4_8E6A_2B51


@contextmanager
def exclusive_startup_lock(
    timeout_seconds: float = 30.0, poll_interval: float = 0.2
) -> Iterator[bool]:
    """Sérialise l'initialisation des données entre workers concurrents.

    Le semis RBAC est idempotent *par lecture puis écriture* : il cherche le
    rôle, et le crée s'il est absent. Exécuté simultanément par N workers au
    démarrage, deux d'entre eux ne trouvent rien, tentent la création, et le
    second heurte la contrainte d'unicité — ce qui fait échouer son démarrage.

    Le worker qui obtient le verrou effectue le semis. Les autres *attendent*
    sa libération avant de continuer : sans cette attente, ils commenceraient
    à servir du trafic alors que les rôles n'existent pas encore.

    Yields:
        True si ce processus détient le verrou et doit faire le travail.
        False s'il n'a pas pu l'obtenir dans le délai imparti — le travail est
        alors supposé fait (ou en cours) ailleurs.
    """
    if _IS_SQLITE or _is_serverless():
        # SQLite sert un seul processus en écriture, et un hébergeur sans état
        # n'exécute pas de phase de démarrage partagée : rien à sérialiser.
        yield True
        return

    conn = None
    acquired = False
    try:
        conn = engine.connect()
        deadline = time.monotonic() + timeout_seconds
        while True:
            row = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _SEED_LOCK_KEY}
            ).first()
            acquired = bool(row and row[0])
            if acquired or time.monotonic() >= deadline:
                break
            time.sleep(poll_interval)

        if not acquired:
            logger.info(
                "Verrou d'initialisation détenu par un autre worker ; semis ignoré."
            )
        yield acquired
    except Exception as exc:
        # Une base qui ne gère pas les verrous consultatifs (ou un pool
        # saturé) ne doit pas empêcher le démarrage : on repasse en mode « ce
        # worker fait le travail », qui est le comportement d'avant.
        logger.warning(
            "Verrou d'initialisation indisponible (%s) ; semis exécuté sans exclusion.",
            exc,
        )
        yield True
    finally:
        if conn is not None:
            if acquired:
                try:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": _SEED_LOCK_KEY}
                    )
                except Exception:
                    # Le verrou est attaché à la session : la fermeture de la
                    # connexion le relâche de toute façon.
                    logger.debug("Libération explicite du verrou échouée.", exc_info=True)
            conn.close()


def pool_status() -> dict:
    """Instantané du pool pour ``/metrics`` et ``/readyz``.

    ``checked_out`` proche de ``pool_size + max_overflow`` est le signe avancé
    d'une saturation : les requêtes suivantes attendront ``pool_timeout``.
    """
    pool: Any = engine.pool
    snapshot = {"impl": type(pool).__name__}
    for attr in ("size", "checkedin", "checkedout", "overflow"):
        getter = getattr(pool, attr, None)
        if callable(getter):
            try:
                snapshot[attr] = int(getter())
            except Exception:
                continue
    return snapshot


def check_connection() -> bool:
    """Exécute ``SELECT 1``. Utilisé par la sonde de disponibilité."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Vérification de connexion à la base échouée : %s", exc)
        return False
