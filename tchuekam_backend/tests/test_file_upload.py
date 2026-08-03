"""
Tests d'intégration pour le module de téléversement sécurisé de fichiers.
"""

import io
from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def get_auth_headers():
    # Inscription et connexion d'un utilisateur de test pour obtenir un token
    email = "filetestuser@tchuekam.com"
    password = "SecurePassword123!"
    client.post("/api/v1/auth/signup", json={"email": email, "password": password, "full_name": "File Test"})
    signin_res = client.post("/api/v1/auth/signin", json={"email": email, "password": password})
    token = signin_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_file_upload_and_download_flow():
    headers = get_auth_headers()
    
    # 1. Upload un fichier valide (text/plain)
    file_content = b"Ceci est un fichier texte de test pour la securite TchueKAM."
    files = {"file": ("test_document.txt", io.BytesIO(file_content), "text/plain")}
    
    upload_res = client.post("/api/v1/files/upload", headers=headers, files=files)
    assert upload_res.status_code == 201
    upload_json = upload_res.json()
    assert upload_json["success"] is True
    file_id = upload_json["data"]["id"]
    assert upload_json["data"]["original_filename"] == "test_document.txt"
    assert upload_json["data"]["mime_type"] == "text/plain"

    # 2. Get file metadata
    meta_res = client.get(f"/api/v1/files/{file_id}", headers=headers)
    assert meta_res.status_code == 200
    assert meta_res.json()["data"]["id"] == file_id

    # 3. Download file
    download_res = client.get(f"/api/v1/files/{file_id}/download", headers=headers)
    assert download_res.status_code == 200
    assert download_res.content == file_content

    # 4. Delete file
    del_res = client.delete(f"/api/v1/files/{file_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_file_upload_blacklisted_extension_rejection():
    headers = get_auth_headers()
    
    # Upload d'un fichier exécutable interdit (.exe)
    file_content = b"echo 'malicious payload'"
    files = {"file": ("malware.exe", io.BytesIO(file_content), "text/plain")}
    
    upload_res = client.post("/api/v1/files/upload", headers=headers, files=files)
    assert upload_res.status_code == 400
    json_res = upload_res.json()
    assert json_res["success"] is False
    assert json_res["error"]["code"] == "FILE_UPLOAD_ERROR"
    assert "n'est pas autorisée" in json_res["error"]["message"]
