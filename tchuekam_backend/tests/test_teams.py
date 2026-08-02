"""
Tests unitaires et d'intégration pour le module des Équipes et Hiérarchies.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_team_hierarchy_and_members(db_session):
    client.post("/api/v1/auth/signup", json={"email": "teamlead@tchuekam.com", "password": "Password123!"})
    res_signin = client.post("/api/v1/auth/signin", json={"email": "teamlead@tchuekam.com", "password": "Password123!"})
    token = res_signin.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_org = client.post("/api/v1/organizations", json={"name": "Team Org", "slug": "team-org"}, headers=headers)
    org_id = res_org.json()["id"]
    org_headers = {**headers, "X-Organization-Id": org_id}

    # 1. Équipe Parente (Tech)
    res_parent = client.post("/api/v1/teams", json={"name": "Division Tech"}, headers=org_headers)
    assert res_parent.status_code == 201
    parent_id = res_parent.json()["id"]

    # 2. Équipe Enfant (Backend Agent)
    res_child = client.post("/api/v1/teams", json={"name": "Backend Team", "parent_team_id": parent_id}, headers=org_headers)
    assert res_child.status_code == 201
    assert res_child.json()["parent_team_id"] == parent_id

    # 3. Listing des équipes
    res_list = client.get("/api/v1/teams", headers=org_headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 2
