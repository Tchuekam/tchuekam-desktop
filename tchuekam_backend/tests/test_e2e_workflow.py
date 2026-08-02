"""
Phase 5 — Test de Validation End-to-End (E2E Workflow) pour TchueKAM Backend.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app
from tchuekam_backend.services.rbac_service import RbacService

client = TestClient(app)


def test_full_end_to_end_user_workflow(db_session):
    # 1. Inscription du Propriétaire (Owner)
    res_signup = client.post("/api/v1/auth/signup", json={
        "email": "e2e_owner@tchuekam.com",
        "password": "E2E_Password123!",
        "full_name": "E2E Owner",
    })
    assert res_signup.status_code == 201
    owner_verify_token = res_signup.json()["verification_token"]
    owner_user_id = res_signup.json()["user_id"]

    # Attribution du rôle système Admin au Propriétaire avant connexion pour intégration du rôle au JWT
    rbac_service = RbacService(db_session)
    admin_role = rbac_service.rbac_repo.get_role_by_name("Admin")
    rbac_service.assign_user_roles(owner_user_id, [admin_role.id])

    # Validation email
    res_v = client.get(f"/api/v1/auth/verify-email?token={owner_verify_token}")
    assert res_v.status_code == 200

    # 2. Connexion (SignIn) -> Émet un JWT contenant le rôle Admin
    res_login = client.post("/api/v1/auth/signin", json={
        "email": "e2e_owner@tchuekam.com",
        "password": "E2E_Password123!",
        "device_name": "E2E Workstation",
    })
    assert res_login.status_code == 200
    owner_token = res_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 3. Créer une Organisation
    res_org = client.post("/api/v1/organizations", json={
        "name": "E2E Enterprise",
        "slug": "e2e-enterprise",
    }, headers=owner_headers)
    assert res_org.status_code == 201
    org_id = res_org.json()["id"]
    org_headers = {**owner_headers, "X-Organization-Id": org_id}

    # 4. Créer un Workspace dans l'Organisation
    res_ws = client.post("/api/v1/workspaces", json={
        "name": "E2E Production Workspace",
        "slug": "e2e-prod",
        "description": "Workspace principal E2E",
    }, headers=org_headers)
    assert res_ws.status_code == 201
    ws_id = res_ws.json()["id"]

    # 5. Inviter un nouvel utilisateur (Developer)
    res_inv = client.post("/api/v1/invitations", json={
        "email": "e2e_dev@tchuekam.com",
        "role": "MEMBER",
        "workspace_id": ws_id,
    }, headers=org_headers)
    assert res_inv.status_code == 201
    inv_token = res_inv.json()["token"]

    # 6. Le nouvel utilisateur s'inscrit, se connecte et accepte l'invitation
    client.post("/api/v1/auth/signup", json={
        "email": "e2e_dev@tchuekam.com",
        "password": "Dev_Password123!",
        "full_name": "E2E Dev",
    })
    res_dev_login = client.post("/api/v1/auth/signin", json={
        "email": "e2e_dev@tchuekam.com",
        "password": "Dev_Password123!",
    })
    dev_token = res_dev_login.json()["access_token"]
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    res_accept = client.post("/api/v1/invitations/accept", json={"token": inv_token}, headers=dev_headers)
    assert res_accept.status_code == 200

    # 7. Créer une Équipe dans l'Organisation et ajouter le membre
    res_team = client.post("/api/v1/teams", json={
        "name": "E2E Core Team",
        "workspace_id": ws_id,
    }, headers=org_headers)
    assert res_team.status_code == 201
    team_id = res_team.json()["id"]

    dev_user_id = res_dev_login.json()["user_id"]
    res_add_member = client.post(f"/api/v1/teams/{team_id}/members", json={
        "user_id": dev_user_id,
        "role": "MEMBER",
    }, headers=org_headers)
    assert res_add_member.status_code == 200

    # 8. Générer une Clé API
    res_key = client.post("/api/v1/api-keys", json={
        "name": "E2E Integration Key",
        "scopes": ["read", "write"],
    }, headers=org_headers)
    assert res_key.status_code == 201
    assert res_key.json()["raw_api_key"].startswith("tk_live_")

    # 9. Consulter les logs d'audit de l'Organisation (Autorisé car rôle Admin présent dans le JWT)
    res_audit = client.get("/api/v1/audit/logs", headers=org_headers)
    assert res_audit.status_code == 200
    logs = res_audit.json()
    assert len(logs) > 0

    # 10. Déconnexion (Logout) et Re-connexion (SignIn)
    res_logout = client.post("/api/v1/auth/logout", headers=owner_headers)
    assert res_logout.status_code == 200

    res_relogin = client.post("/api/v1/auth/signin", json={
        "email": "e2e_owner@tchuekam.com",
        "password": "E2E_Password123!",
    })
    assert res_relogin.status_code == 200
    new_token = res_relogin.json()["access_token"]

    # 11. Vérification de l'intégrité des données après re-connexion
    new_headers = {"Authorization": f"Bearer {new_token}", "X-Organization-Id": org_id}
    res_check_org = client.get("/api/v1/organizations/current", headers=new_headers)
    assert res_check_org.status_code == 200
    assert res_check_org.json()["name"] == "E2E Enterprise"
