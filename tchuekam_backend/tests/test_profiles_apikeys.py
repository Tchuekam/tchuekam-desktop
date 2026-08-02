"""
Tests unitaires et d'intégration pour les Profils et Clés API.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_profile_management_and_api_keys(db_session):
    client.post("/api/v1/auth/signup", json={"email": "profuser@tchuekam.com", "password": "Password123!"})
    res_signin = client.post("/api/v1/auth/signin", json={"email": "profuser@tchuekam.com", "password": "Password123!"})
    token = res_signin.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_org = client.post("/api/v1/organizations", json={"name": "API Org", "slug": "api-org"}, headers=headers)
    org_id = res_org.json()["id"]
    org_headers = {**headers, "X-Organization-Id": org_id}

    # 1. Mise à jour du profil étendu
    res_prof = client.put("/api/v1/profiles/me", json={"username": "profuser", "language": "fr", "timezone": "Europe/Paris"}, headers=headers)
    assert res_prof.status_code == 200
    assert res_prof.json()["username"] == "profuser"

    # 2. Création Clé API
    res_key = client.post("/api/v1/api-keys", json={"name": "SDK Integration Key", "scopes": ["read", "write"]}, headers=org_headers)
    assert res_key.status_code == 201
    key_data = res_key.json()
    assert "raw_api_key" in key_data
    assert key_data["raw_api_key"].startswith("tk_live_")
    key_id = key_data["id"]

    # 3. Listing Clés API
    res_list = client.get("/api/v1/api-keys", headers=org_headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 4. Révocation Clé API
    res_del = client.delete(f"/api/v1/api-keys/{key_id}", headers=org_headers)
    assert res_del.status_code == 200
