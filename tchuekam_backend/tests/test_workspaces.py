"""
Tests unitaires et d'intégration pour le module des Workspaces.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_workspace_lifecycle(db_session):
    # Setup
    client.post("/api/v1/auth/signup", json={"email": "wsuser@tchuekam.com", "password": "Password123!"})
    res_signin = client.post("/api/v1/auth/signin", json={"email": "wsuser@tchuekam.com", "password": "Password123!"})
    token = res_signin.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_org = client.post("/api/v1/organizations", json={"name": "Workspace Org", "slug": "ws-org"}, headers=headers)
    org_id = res_org.json()["id"]
    org_headers = {**headers, "X-Organization-Id": org_id}

    # 1. Création Workspace
    res_ws = client.post("/api/v1/workspaces", json={"name": "Ingénierie AI", "slug": "ai-engineering"}, headers=org_headers)
    assert res_ws.status_code == 201
    ws_data = res_ws.json()
    assert ws_data["name"] == "Ingénierie AI"
    ws_id = ws_data["id"]

    # 2. Listing Workspaces
    res_list = client.get("/api/v1/workspaces", headers=org_headers)
    assert res_list.status_code == 200
    workspaces = res_list.json()
    assert len(workspaces) >= 2  # Workspace 'Général' par défaut + 'Ingénierie AI'

    # 3. Mise à jour
    res_up = client.put(f"/api/v1/workspaces/{ws_id}", json={"description": "Projets LLM & Agents"}, headers=org_headers)
    assert res_up.status_code == 200
    assert res_up.json()["description"] == "Projets LLM & Agents"
