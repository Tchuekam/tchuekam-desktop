"""
Tests de pénétration et validation de l'isolation Multi-Tenant stricte.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_multi_tenant_strict_data_isolation(db_session):
    # Tenant A
    client.post("/api/v1/auth/signup", json={"email": "tenantA@tchuekam.com", "password": "Password123!"})
    res_a = client.post("/api/v1/auth/signin", json={"email": "tenantA@tchuekam.com", "password": "Password123!"})
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_org_a = client.post("/api/v1/organizations", json={"name": "Org A", "slug": "org-a"}, headers=headers_a)
    org_a_id = res_org_a.json()["id"]

    # Tenant B
    client.post("/api/v1/auth/signup", json={"email": "tenantB@tchuekam.com", "password": "Password123!"})
    res_b = client.post("/api/v1/auth/signin", json={"email": "tenantB@tchuekam.com", "password": "Password123!"})
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res_org_b = client.post("/api/v1/organizations", json={"name": "Org B", "slug": "org-b"}, headers=headers_b)
    org_b_id = res_org_b.json()["id"]

    # 1. Tentative de Tenant B d'accéder à Org A en fournissant X-Organization-Id de Org A -> DOIT ÊTRE BLOQUÉ (403 Forbidden)
    malicious_headers = {**headers_b, "X-Organization-Id": org_a_id}
    res_attack = client.get("/api/v1/organizations/current", headers=malicious_headers)
    assert res_attack.status_code == 403
    json_data = res_attack.json()
    err_msg = json_data.get("error", {}).get("message") or json_data.get("detail", "")
    assert "Accès refusé" in err_msg

    # 2. Tentative de Tenant B de lister les membres de Org A -> BLOQUÉ (403 Forbidden)
    res_attack_members = client.get("/api/v1/organizations/current/members", headers=malicious_headers)
    assert res_attack_members.status_code == 403

    # 3. Tentative de Tenant B de créer un workspace dans Org A -> BLOQUÉ (403 Forbidden)
    res_attack_ws = client.post("/api/v1/workspaces", json={"name": "Rogue WS"}, headers=malicious_headers)
    assert res_attack_ws.status_code == 403
