"""
BioCompute playground endpoints, exercised against the backend's own dependency
set (requirements-backend.txt). These routes import scikit-learn / scipy at call
time, so a deploy missing them starts fine and then answers 500.
"""

import pytest
from fastapi.testclient import TestClient

from tchuekam_backend.main import app

client = TestClient(app)

PLAYGROUND_BACKENDS = ["tiny_cnn", "digital_reservoir", "biocompute_simulator", "finalspark"]


def test_status_online():
    response = client.get("/api/v1/biocompute/status")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


@pytest.mark.parametrize("backend", PLAYGROUND_BACKENDS)
def test_experiment_run_succeeds_for_every_backend(backend):
    """Every backend the playground offers must answer, not 500."""
    response = client.post(
        "/api/v1/biocompute/experiment/run",
        data={"backend": backend, "dataset": "MNIST"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["backend"] == backend
    assert body["prediction"]


@pytest.mark.timeout(120)
def test_exp001_benchmark_runs():
    response = client.get("/api/v1/biocompute/benchmark/exp001")
    assert response.status_code == 200, response.text
    assert response.json()["n_classes"] >= 2
