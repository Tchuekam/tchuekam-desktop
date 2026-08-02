"""
Tests unitaires et d'intégration pour le service OAuth2 extensible.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_oauth_authorization_urls():
    providers = ["google", "github", "apple", "microsoft", "facebook"]
    for provider in providers:
        res = client.get(f"/api/v1/oauth/{provider}/authorize?redirect_uri=http://localhost:3000/callback")
        assert res.status_code == 200
        data = res.json()
        assert "authorization_url" in data
        assert provider in data["authorization_url"].lower() or "accounts" in data["authorization_url"].lower() or "login" in data["authorization_url"].lower() or "apple" in data["authorization_url"].lower() or "facebook" in data["authorization_url"].lower()


def test_oauth_callback_flow():
    payload = {
        "code": "test_auth_code_123456",
        "device_name": "OAuth Test Device",
    }
    res = client.post("/api/v1/oauth/github/callback?redirect_uri=http://localhost:3000/callback", json=payload)
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert "User" in token_data["roles"]
