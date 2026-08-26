"""L'invitation doit être liée à l'adresse e-mail invitée.

Sans ce lien, quiconque met la main sur le jeton (e-mail transféré, boîte
partagée, journal, historique de navigation) peut le consommer depuis son
propre compte et obtenir le rôle prévu pour quelqu'un d'autre.
"""

from fastapi.testclient import TestClient

from tchuekam_backend.main import app

client = TestClient(app)

PASSWORD = "Password123!"


def _account(email: str) -> dict:
    client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    res = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _invite(org_headers: dict, email: str, role: str) -> str:
    res = client.post(
        "/api/v1/invitations", json={"email": email, "role": role}, headers=org_headers
    )
    assert res.status_code == 201, res.text
    return res.json()["token"]


def test_invitation_cannot_be_redeemed_by_a_different_account():
    owner = _account("bind_owner@tchuekam.com")
    res_org = client.post(
        "/api/v1/organizations",
        json={"name": "Bind Org", "slug": "bind-org"},
        headers=owner,
    )
    assert res_org.status_code == 201, res_org.text
    org_headers = {**owner, "X-Organization-Id": res_org.json()["id"]}

    _account("bind_victim@tchuekam.com")
    attacker = _account("bind_attacker@tchuekam.com")

    # Invitation ADMIN destinee a la victime, detournee par l'attaquant.
    token = _invite(org_headers, "bind_victim@tchuekam.com", "ADMIN")
    res = client.post("/api/v1/invitations/accept", json={"token": token}, headers=attacker)
    assert res.status_code != 200, (
        "Elevation de privileges: un compte tiers a consomme l'invitation d'autrui"
    )

    orgs = client.get("/api/v1/organizations", headers=attacker)
    assert "bind-org" not in [o["slug"] for o in orgs.json()], (
        "L'attaquant a rejoint l'organisation"
    )


def test_invited_recipient_can_still_accept():
    owner = _account("bind_owner2@tchuekam.com")
    res_org = client.post(
        "/api/v1/organizations",
        json={"name": "Bind Org 2", "slug": "bind-org-2"},
        headers=owner,
    )
    org_headers = {**owner, "X-Organization-Id": res_org.json()["id"]}

    invitee = _account("bind_invitee2@tchuekam.com")
    token = _invite(org_headers, "bind_invitee2@tchuekam.com", "MEMBER")

    res = client.post("/api/v1/invitations/accept", json={"token": token}, headers=invitee)
    assert res.status_code == 200, res.text
    orgs = client.get("/api/v1/organizations", headers=invitee)
    assert "bind-org-2" in [o["slug"] for o in orgs.json()]


def test_invitation_email_match_is_case_insensitive():
    owner = _account("bind_owner3@tchuekam.com")
    res_org = client.post(
        "/api/v1/organizations",
        json={"name": "Bind Org 3", "slug": "bind-org-3"},
        headers=owner,
    )
    org_headers = {**owner, "X-Organization-Id": res_org.json()["id"]}

    invitee = _account("bind_invitee3@tchuekam.com")
    token = _invite(org_headers, "BIND_Invitee3@Tchuekam.com", "MEMBER")

    res = client.post("/api/v1/invitations/accept", json={"token": token}, headers=invitee)
    assert res.status_code == 200, (
        f"La comparaison d'email doit ignorer la casse: {res.text}"
    )
