"""Un invitant ne doit pas pouvoir accorder un rôle supérieur au sien.

``add_org_member`` met à jour le rôle d'une adhésion existante. Un ADMIN qui
s'invite lui-même avec le rôle OWNER voit donc son adhésion promue : élévation
de privilèges verticale à l'intérieur de l'organisation.
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


def _my_role(headers: dict, slug: str):
    orgs = client.get("/api/v1/organizations", headers=headers).json()
    for o in orgs:
        if o["slug"] == slug:
            return o.get("role") or o.get("my_role")
    return None


def _setup_org_with_admin(slug: str):
    owner = _account(f"esc_owner_{slug}@tchuekam.com")
    res_org = client.post(
        "/api/v1/organizations", json={"name": slug, "slug": slug}, headers=owner
    )
    assert res_org.status_code == 201, res_org.text
    org_id = res_org.json()["id"]
    owner_org = {**owner, "X-Organization-Id": org_id}

    admin_email = f"esc_admin_{slug}@tchuekam.com"
    admin = _account(admin_email)
    inv = client.post(
        "/api/v1/invitations", json={"email": admin_email, "role": "ADMIN"},
        headers=owner_org,
    )
    assert inv.status_code == 201, inv.text
    accepted = client.post(
        "/api/v1/invitations/accept", json={"token": inv.json()["token"]}, headers=admin
    )
    assert accepted.status_code == 200, accepted.text
    return org_id, owner_org, admin, admin_email


def test_admin_cannot_self_promote_to_owner_via_invitation():
    slug = "esc-org"
    org_id, _owner_org, admin, admin_email = _setup_org_with_admin(slug)
    admin_org = {**admin, "X-Organization-Id": org_id}

    # L'ADMIN s'invite lui-meme avec le role OWNER.
    inv = client.post(
        "/api/v1/invitations", json={"email": admin_email, "role": "OWNER"},
        headers=admin_org,
    )
    if inv.status_code == 201:
        accepted = client.post(
            "/api/v1/invitations/accept",
            json={"token": inv.json()["token"]},
            headers=admin,
        )
        assert accepted.status_code != 200, (
            "Elevation verticale: un ADMIN s'est promu OWNER via une auto-invitation"
        )
    else:
        assert inv.status_code == 403, (
            f"L'invitation OWNER par un ADMIN doit etre refusee (403), recu {inv.status_code}"
        )

    assert _my_role(admin, slug) != "OWNER", "L'ADMIN detient desormais le role OWNER"


def test_owner_can_still_invite_an_owner():
    slug = "esc-org-ok"
    _org_id, owner_org, _admin, _e = _setup_org_with_admin(slug)
    new_owner_email = "esc_newowner@tchuekam.com"
    _account(new_owner_email)
    inv = client.post(
        "/api/v1/invitations", json={"email": new_owner_email, "role": "OWNER"},
        headers=owner_org,
    )
    assert inv.status_code == 201, f"Un OWNER doit pouvoir inviter un OWNER: {inv.text}"


def test_admin_can_still_invite_a_member():
    slug = "esc-org-mem"
    org_id, _owner_org, admin, _e = _setup_org_with_admin(slug)
    admin_org = {**admin, "X-Organization-Id": org_id}
    _account("esc_member@tchuekam.com")
    inv = client.post(
        "/api/v1/invitations", json={"email": "esc_member@tchuekam.com", "role": "MEMBER"},
        headers=admin_org,
    )
    assert inv.status_code == 201, f"Un ADMIN doit pouvoir inviter un MEMBER: {inv.text}"
