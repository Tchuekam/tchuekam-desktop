"""Les jetons hors-bande ne doivent jamais fuiter dans une réponse HTTP en production.

Un jeton de réinitialisation renvoyé à l'appelant supprime la preuve de
possession de la boîte e-mail : un anonyme connaissant une adresse prenait le
contrôle du compte en trois requêtes.
"""

import os
import subprocess
import sys

from fastapi.testclient import TestClient

from tchuekam_backend.core.config import settings
from tchuekam_backend.main import app

client = TestClient(app)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASSWORD = "VictimSecret123!"


def test_forgot_password_response_is_identical_for_unknown_email():
    """La reponse ne doit pas reveler si l'adresse est enregistree."""
    client.post(
        "/api/v1/auth/signup",
        json={"email": "leak_known@tchuekam.com", "password": PASSWORD},
    )
    known = client.post(
        "/api/v1/auth/forgot-password", json={"email": "leak_known@tchuekam.com"}
    )
    unknown = client.post(
        "/api/v1/auth/forgot-password", json={"email": "leak_ghost@tchuekam.com"}
    )
    assert known.status_code == unknown.status_code
    assert known.json()["message"] == unknown.json()["message"], (
        "Oracle d'enumeration: /forgot-password distingue les adresses connues"
    )


def test_production_settings_withhold_sensitive_tokens():
    """En production, EXPOSE_SENSITIVE_TOKENS doit etre faux."""
    env = dict(os.environ)
    env["ENVIRONMENT"] = "production"
    env["TCHUEKAM_JWT_SECRET_KEY"] = "y" * 64
    proc = subprocess.run(
        [sys.executable, "-c",
         "from tchuekam_backend.core.config import settings; "
         "print('EXPOSE=', settings.EXPOSE_SENSITIVE_TOKENS)"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "EXPOSE= False" in proc.stdout, proc.stdout


def test_production_forgot_password_does_not_return_reset_token():
    """Bout en bout : en production le corps de reponse ne contient aucun jeton."""
    env = dict(os.environ)
    env["ENVIRONMENT"] = "production"
    env["TCHUEKAM_JWT_SECRET_KEY"] = "z" * 64
    script = """
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tchuekam_backend.core.database import Base, get_db
from tchuekam_backend.main import app
eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SL = sessionmaker(autocommit=False, autoflush=False, bind=eng)
def odb():
    d = SL()
    try: yield d
    finally: d.close()
app.dependency_overrides[get_db] = odb
Base.metadata.create_all(bind=eng)
db = SL()
from tchuekam_backend.services.rbac_service import RbacService
RbacService(db).seed_default_roles_and_permissions(); db.close()
c = TestClient(app)
c.post("/api/v1/auth/signup", json={"email": "prod@tchuekam.com", "password": "VictimSecret123!"})
signup = c.post("/api/v1/auth/signup", json={"email": "prod2@tchuekam.com", "password": "VictimSecret123!"})
forgot = c.post("/api/v1/auth/forgot-password", json={"email": "prod@tchuekam.com"})
print("SIGNUP_KEYS=", sorted(signup.json().keys()))
print("FORGOT_KEYS=", sorted(forgot.json().keys()))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "'reset_token'" not in proc.stdout, f"Jeton de reset expose: {proc.stdout}"
    assert "'verification_token'" not in proc.stdout, f"Jeton de verification expose: {proc.stdout}"


def test_development_still_exposes_tokens_for_integration():
    """Le confort de developpement reste disponible hors production."""
    assert settings.EXPOSE_SENSITIVE_TOKENS is True
    client.post(
        "/api/v1/auth/signup",
        json={"email": "dev_expose@tchuekam.com", "password": PASSWORD},
    )
    res = client.post(
        "/api/v1/auth/forgot-password", json={"email": "dev_expose@tchuekam.com"}
    )
    assert "reset_token" in res.json()
