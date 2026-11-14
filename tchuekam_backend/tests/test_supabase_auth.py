"""
Tests d'intégration pour l'authentification JWT Supabase ES256 et la synchronisation SaaS.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from tchuekam_backend.core.supabase_auth import get_supabase_issuer
from tchuekam_backend.main import app

client = TestClient(app)


def _generate_es256_token(email: str, sub: str, expired: bool = False, issuer: str | None = None):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(minutes=30)
    payload = {
        "sub": sub,
        "email": email,
        "aud": "authenticated",
        "iss": issuer or get_supabase_issuer(),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "session_id": "sb-sess-123",
        "user_metadata": {
            "full_name": "Supabase Architect",
            "username": "sb_architect",
        },
    }
    token = jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test-kid"})
    return token, public_key


def test_supabase_es256_token_auto_provisions_and_authenticates():
    token, public_key = _generate_es256_token(
        email="new.architect@tchuekam.com",
        sub="11111111-2222-3333-4444-555555555555",
    )

    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _tok: SimpleNamespace(key=public_key)
    )
    with patch("tchuekam_backend.core.supabase_auth._get_jwks_client", return_value=fake_client):
        res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "new.architect@tchuekam.com"
    assert body["id"] == "11111111-2222-3333-4444-555555555555"


def test_supabase_expired_and_wrong_issuer_tokens_rejected():
    expired_token, expired_pub = _generate_es256_token(
        email="expired@tchuekam.com",
        sub="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        expired=True,
    )
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _tok: SimpleNamespace(key=expired_pub)
    )
    with patch("tchuekam_backend.core.supabase_auth._get_jwks_client", return_value=fake_client):
        res_exp = client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {expired_token}"}
        )
    assert res_exp.status_code == 401

    wrong_iss_token, _ = _generate_es256_token(
        email="evil@example.com",
        sub="99999999-8888-7777-6666-555555555555",
        issuer="https://evil.example.com/auth/v1",
    )
    res_iss = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {wrong_iss_token}"}
    )
    assert res_iss.status_code == 401


def test_supabase_passwordless_user_lifecycle_and_hermes_passthrough():
    from hermes_cli.dashboard_auth.public_paths import allows_saas_api_passthrough

    assert allows_saas_api_passthrough("/api/v1/health", "") is True
    assert allows_saas_api_passthrough("/api/v1/auth/signin", "") is True
    assert allows_saas_api_passthrough("/api/v1/users/me", "Bearer sb-jwt") is True
    assert allows_saas_api_passthrough("/api/v1/users/me", "") is False
    assert allows_saas_api_passthrough("/api/v1/biocompute/status", "Bearer sb-jwt") is False
    assert allows_saas_api_passthrough("/api/config", "Bearer sb-jwt") is False

    token, public_key = _generate_es256_token(
        email="lifecycle.user@tchuekam.com",
        sub="22222222-3333-4444-5555-666666666666",
    )
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _tok: SimpleNamespace(key=public_key)
    )
    with patch("tchuekam_backend.core.supabase_auth._get_jwks_client", return_value=fake_client):
        res_pwd = client.post(
            "/api/v1/users/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "OldPassword1!", "new_password": "NewPassword2!"},
        )
        assert res_pwd.status_code == 400

        res_logout = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_logout.status_code == 200


def test_supabase_concurrent_first_login_integrity_error_recovers():
    from sqlalchemy.exc import IntegrityError
    from tchuekam_backend.core.database import get_db
    from tchuekam_backend.core.supabase_auth import get_or_provision_supabase_user, get_supabase_issuer

    sub = "33333333-4444-5555-6666-777777777777"
    email = "race.user@tchuekam.com"
    payload = {
        "sub": sub,
        "email": email,
        "iss": get_supabase_issuer(),
        "user_metadata": {"full_name": "Race User", "username": "race_user"},
    }
    db_gen1 = app.dependency_overrides[get_db]()
    db_gen2 = app.dependency_overrides[get_db]()
    db1 = next(db_gen1)
    db2 = next(db_gen2)
    try:
        first_user, _, _ = get_or_provision_supabase_user(db1, payload)
        # Simulate another worker seeing user=None before db1 commits, then hitting IntegrityError
        orig_commit = db2.commit
        call_state = {"raised": False}

        def fail_once_commit():
            if not call_state["raised"]:
                call_state["raised"] = True
                raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
            return orig_commit()

        with patch("tchuekam_backend.repositories.user_repository.UserRepository.get_by_id", side_effect=[None, first_user]), \
             patch("tchuekam_backend.repositories.user_repository.UserRepository.get_by_email", side_effect=[None, first_user]), \
             patch.object(db2, "commit", side_effect=fail_once_commit):
            recovered_user, _, _ = get_or_provision_supabase_user(db2, payload)
        assert recovered_user.id == first_user.id
        assert recovered_user.email == email
    finally:
        db1.close()
        db2.close()
