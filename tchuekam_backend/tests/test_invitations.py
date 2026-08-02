"""
Tests unitaires et d'intégration pour le flux d'Invitations et Onboarding.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_invitation_creation_and_acceptance(db_session):
    # Owner
    client.post("/api/v1/auth/signup", json={"email": "inviter@tchuekam.com", "password": "Password123!"})
    res_signin = client.post("/api/v1/auth/signin", json={"email": "inviter@tchuekam.com", "password": "Password123!"})
    token_inviter = res_signin.json()["access_token"]
    headers_inviter = {"Authorization": f"Bearer {token_inviter}"}

    res_org = client.post("/api/v1/organizations", json={"name": "Invited Org", "slug": "invited-org"}, headers=headers_inviter)
    org_id = res_org.json()["id"]
    org_headers = {**headers_inviter, "X-Organization-Id": org_id}

    # Invite
    client.post("/api/v1/auth/signup", json={"email": "invitee@tchuekam.com", "password": "Password123!"})
    res_signin_e = client.post("/api/v1/auth/signin", json={"email": "invitee@tchuekam.com", "password": "Password123!"})
    token_invitee = res_signin_e.json()["access_token"]
    headers_invitee = {"Authorization": f"Bearer {token_invitee}"}

    # 1. Envoi invitation
    res_inv = client.post("/api/v1/invitations", json={"email": "invitee@tchuekam.com", "role": "MEMBER"}, headers=org_headers)
    assert res_inv.status_code == 201
    inv_data = res_inv.json()
    raw_token = inv_data["token"]

    # 2. Acceptation invitation
    res_accept = client.post("/api/v1/invitations/accept", json={"token": raw_token}, headers=headers_invitee)
    assert res_accept.status_code == 200

    # 3. Vérifier accès à l'organisation acceptée
    res_my_orgs = client.get("/api/v1/organizations", headers=headers_invitee)
    assert res_my_orgs.status_code == 200
    org_slugs = [o["slug"] for o in res_my_orgs.json()]
    assert "invited-org" in org_slugs
