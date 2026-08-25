"""Tests d'autorisation (IDOR) pour le module de gestion de fichiers.

Ces tests prouvent qu'un utilisateur authentifié ne peut pas lire, télécharger
ou supprimer un fichier appartenant à un autre utilisateur.
"""

import io

from fastapi.testclient import TestClient

from tchuekam_backend.main import app

client = TestClient(app)


def _auth_headers(email: str) -> dict:
    password = "SecurePassword123!"
    client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": "Owner Test"},
    )
    res = client.post("/api/v1/auth/signin", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _upload(headers: dict, name: str, content: bytes) -> str:
    files = {"file": (name, io.BytesIO(content), "text/plain")}
    res = client.post("/api/v1/files/upload", headers=headers, files=files)
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


def test_other_user_cannot_read_file_metadata():
    victim = _auth_headers("idor_victim_meta@tchuekam.com")
    attacker = _auth_headers("idor_attacker_meta@tchuekam.com")
    file_id = _upload(victim, "secret.txt", b"donnees confidentielles")

    res = client.get(f"/api/v1/files/{file_id}", headers=attacker)
    assert res.status_code == 404, (
        f"IDOR: un autre utilisateur a lu les metadonnees du fichier ({res.status_code})"
    )


def test_other_user_cannot_download_file():
    victim = _auth_headers("idor_victim_dl@tchuekam.com")
    attacker = _auth_headers("idor_attacker_dl@tchuekam.com")
    secret = b"numero de carte bancaire 4111111111111111"
    file_id = _upload(victim, "secret.txt", secret)

    res = client.get(f"/api/v1/files/{file_id}/download", headers=attacker)
    assert res.status_code == 404, (
        f"IDOR: un autre utilisateur a telecharge le fichier ({res.status_code})"
    )
    assert secret not in res.content


def test_other_user_cannot_delete_file():
    victim = _auth_headers("idor_victim_del@tchuekam.com")
    attacker = _auth_headers("idor_attacker_del@tchuekam.com")
    file_id = _upload(victim, "secret.txt", b"donnees confidentielles")

    res = client.delete(f"/api/v1/files/{file_id}", headers=attacker)
    assert res.status_code == 404, (
        f"IDOR: un autre utilisateur a supprime le fichier ({res.status_code})"
    )

    # Le proprietaire doit toujours pouvoir acceder a son fichier.
    still_there = client.get(f"/api/v1/files/{file_id}", headers=victim)
    assert still_there.status_code == 200, "Le fichier de la victime a ete detruit"


def test_owner_retains_full_access():
    owner = _auth_headers("idor_owner_ok@tchuekam.com")
    content = b"mon propre fichier"
    file_id = _upload(owner, "mine.txt", content)

    assert client.get(f"/api/v1/files/{file_id}", headers=owner).status_code == 200
    dl = client.get(f"/api/v1/files/{file_id}/download", headers=owner)
    assert dl.status_code == 200 and dl.content == content
    assert client.delete(f"/api/v1/files/{file_id}", headers=owner).status_code == 200
