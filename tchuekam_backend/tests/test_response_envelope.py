"""
Tests d'intégration pour la validation du format standard des réponses (Success & Error Envelopes).
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app

client = TestClient(app)


def test_health_check_standard_envelope():
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert json_data["message"] == "Service opérationnel."
    assert "data" in json_data
    assert json_data["data"]["status"] == "healthy"


def test_validation_error_standard_envelope():
    # Envoi d'un payload invalide (email incorrect, mot de passe trop court)
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "invalid-email-address", "password": "123"},
    )
    assert response.status_code == 422
    json_data = response.json()
    assert json_data["success"] is False
    assert "error" in json_data
    assert json_data["error"]["code"] == "VALIDATION_ERROR"
    assert json_data["error"]["message"] == "Erreur de validation de la requête."
    assert isinstance(json_data["error"]["details"], list)
    assert len(json_data["error"]["details"]) > 0


def test_not_found_standard_envelope():
    response = client.get("/api/v1/non-existent-endpoint")
    assert response.status_code == 404
    json_data = response.json()
    assert json_data["success"] is False
    assert json_data["error"]["code"] == "NOT_FOUND"
