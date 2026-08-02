"""
Tests unitaires et d'intégration pour le module des Organisations et le Multi-Tenancy.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_organization_crud_and_archiving(db_session):
    # 1. Inscription utilisateur
    res_signup = client.post("/api/v1/auth/signup", json={"email": "orgowner@tchuekam.com", "password": "Password123!"})
    res_signin = client.post("/api/v1/auth/signin", json={"email": "orgowner@tchuekam.com", "password": "Password123!"})
    token = res_signin.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Création d'une organisation
    res_org = client.post("/api/v1/organizations", json={"name": "TchueKAM Corp", "slug": "tchuekam-corp"}, headers=headers)
    assert res_org.status_code == 201
    org_data = res_org.json()
    assert org_data["name"] == "TchueKAM Corp"
    assert org_data["slug"] == "tchuekam-corp"
    org_id = org_data["id"]

    # 3. Récupération de l'organisation courante
    org_headers = {**headers, "X-Organization-Id": org_id}
    res_curr = client.get("/api/v1/organizations/current", headers=org_headers)
    assert res_curr.status_code == 200
    assert res_curr.json()["id"] == org_id

    # 4. Mise à jour de l'organisation
    res_update = client.put("/api/v1/organizations/current", json={"name": "TchueKAM Enterprise"}, headers=org_headers)
    assert res_update.status_code == 200
    assert res_update.json()["name"] == "TchueKAM Enterprise"

    # 5. Archivage
    res_archive = client.post("/api/v1/organizations/current/archive", headers=org_headers)
    assert res_archive.status_code == 200
