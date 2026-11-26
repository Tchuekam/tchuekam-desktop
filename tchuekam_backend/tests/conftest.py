"""
Pytest configuration and shared database fixtures for backend tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tchuekam_backend.core import database
from tchuekam_backend.core.database import Base, get_db
from tchuekam_backend.main import app

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Les chemins qui ne peuvent pas passer par la dépendance ``get_db`` — le canal
# WebSocket, qui doit relâcher sa connexion SQL avant d'entrer dans sa boucle
# de réception — ouvrent leur session via ``database.new_session()``. Sans ce
# remplacement, ils toucheraient la vraie base au lieu de celle des tests.
database.SessionLocal = TestingSessionLocal


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    from tchuekam_backend.services.rbac_service import RbacService
    rbac = RbacService(db)
    rbac.seed_default_roles_and_permissions()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
