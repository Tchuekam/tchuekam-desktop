"""Les fournisseurs OAuth simulés ne doivent pas être exploitables en production.

Un fournisseur simulé n'interroge jamais l'IdP : il dérive l'identité du
``code`` fourni par l'appelant. En production cela équivaut à un contournement
complet de l'authentification.
"""

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PROD_SCRIPT = """
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
c.post("/api/v1/auth/signup",
       json={"email": "user_abcdef@gmail.com", "password": "VictimSecret123!"})
r = c.post("/api/v1/oauth/google/callback", json={"code": "abcdefZZZZZZZZ"})
print("CALLBACK_STATUS=", r.status_code)
a = c.get("/api/v1/oauth/google/authorize?redirect_uri=http://x/cb&state=s")
print("AUTHORIZE_STATUS=", a.status_code)
"""


def _run_in_production(script: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ENVIRONMENT"] = "production"
    env["TCHUEKAM_JWT_SECRET_KEY"] = "q" * 64
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


def test_mock_oauth_callback_is_refused_in_production():
    proc = _run_in_production(_PROD_SCRIPT)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "CALLBACK_STATUS= 400" in proc.stdout, (
        f"Le callback OAuth simule a repondu autre chose qu'un refus: {proc.stdout}"
    )
    assert "AUTHORIZE_STATUS= 400" in proc.stdout, (
        f"L'URL d'autorisation simulee est encore servie: {proc.stdout}"
    )


def test_mock_providers_are_flagged_as_mock():
    from tchuekam_backend.services.oauth_service import (
        MockAppleOAuthProvider,
        MockFacebookOAuthProvider,
        MockGitHubOAuthProvider,
        MockGoogleOAuthProvider,
        MockMicrosoftOAuthProvider,
    )

    for cls in (
        MockGoogleOAuthProvider,
        MockGitHubOAuthProvider,
        MockAppleOAuthProvider,
        MockMicrosoftOAuthProvider,
        MockFacebookOAuthProvider,
    ):
        assert cls.is_mock is True, f"{cls.__name__} n'est pas marque comme simule"


def test_real_provider_would_still_work_in_production(db_session):
    """Un fournisseur reel enregistre doit rester utilisable en production."""
    from tchuekam_backend.services.oauth_service import BaseOAuthProvider, OAuthService

    class RealProvider(BaseOAuthProvider):
        name = "realidp"
        is_mock = False

        def get_authorization_url(self, redirect_uri: str, state: str) -> str:
            return f"https://idp.example.com/auth?state={state}"

        def get_user_info_from_code(self, code: str, redirect_uri: str):
            return {
                "provider_user_id": "real-123",
                "email": "real@example.com",
                "full_name": "Real User",
                "avatar_url": None,
            }

    service = OAuthService(db_session)
    service.register_provider(RealProvider())
    provider, error = service._resolve_provider("realidp")
    assert error is None and provider is not None
