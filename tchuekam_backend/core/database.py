"""
Gestionnaire d'accès et de sessions pour la base de données SQLAlchemy.
"""

import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool
from tchuekam_backend.core.config import _is_production, settings

_database_url = settings.DATABASE_URL.strip()
if _database_url.startswith("postgres://"):
    _database_url = "postgresql://" + _database_url[len("postgres://"):]

connect_args = {}
if _database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine_kwargs: dict = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}
if os.getenv("VERCEL", "").strip().lower() not in {"", "0", "false", "no"}:
    engine_kwargs["poolclass"] = NullPool

engine = create_engine(_database_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _ensure_valid_prod_database() -> None:
    if (
        _is_production()
        and _database_url.startswith("sqlite")
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


def init_db() -> None:
    """Initialise les tables de la base de données."""
    _ensure_valid_prod_database()
    Base.metadata.create_all(bind=engine)
