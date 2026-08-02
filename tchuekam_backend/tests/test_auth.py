"""
Tests unitaires et d'intégration pour le module d'Authentification.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_signup_and_signin_flow():
    # 1. SignUp
    signup_payload = {
        "email": "testuser@tchuekam.com",
        "password": "Password123!",
        "full_name": "Test User",
    }
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "testuser@tchuekam.com"
    assert "verification_token" in data

    # 2. Verify Email
    verify_token = data["verification_token"]
    res_v = client.get(f"/api/v1/auth/verify-email?token={verify_token}")
    assert res_v.status_code == 200

    # 3. SignIn
    signin_payload = {
        "email": "testuser@tchuekam.com",
        "password": "Password123!",
        "device_name": "Test Laptop",
    }
    res_s = client.post("/api/v1/auth/signin", json=signin_payload)
    assert res_s.status_code == 200
    token_data = res_s.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert "User" in token_data["roles"]


def test_refresh_token_rotation():
    client.post("/api/v1/auth/signup", json={"email": "refresh@tchuekam.com", "password": "Password123!"})
    res_s = client.post("/api/v1/auth/signin", json={"email": "refresh@tchuekam.com", "password": "Password123!"})
    tokens = res_s.json()

    res_r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res_r.status_code == 200
    new_tokens = res_r.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    res_invalid = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res_invalid.status_code == 401


def test_logout_and_revocation():
    client.post("/api/v1/auth/signup", json={"email": "logout@tchuekam.com", "password": "Password123!"})
    res_s = client.post("/api/v1/auth/signin", json={"email": "logout@tchuekam.com", "password": "Password123!"})
    access_token = res_s.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    res_l = client.post("/api/v1/auth/logout", headers=headers)
    assert res_l.status_code == 200

    res_me = client.get("/api/v1/users/me", headers=headers)
    assert res_me.status_code == 401
