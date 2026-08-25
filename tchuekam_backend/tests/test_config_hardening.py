"""Tests de durcissement de la configuration : CORS et secret JWT.

Ces tests protègent contre deux régressions à fort impact :
  * une origine arbitraire recevant ``Access-Control-Allow-Credentials: true`` ;
  * un secret JWT de repli codé en dur utilisé en production.
"""

import importlib
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from tchuekam_backend.core import config as config_module
from tchuekam_backend.main import app

client = TestClient(app)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_arbitrary_origin_is_not_granted_credentialed_cors():
    res = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert res.status_code == 200
    acao = res.headers.get("access-control-allow-origin")
    acac = res.headers.get("access-control-allow-credentials")
    assert acao != "https://evil.example.com", (
        "CORS: une origine arbitraire a ete reflechie dans Access-Control-Allow-Origin"
    )
    assert not (acao == "*" and acac == "true"), (
        "CORS: joker combine avec allow_credentials"
    )


def test_preflight_from_arbitrary_origin_is_not_authorized():
    res = client.options(
        "/api/v1/auth/signin",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_allowed_origins_never_defaults_to_wildcard():
    assert "*" not in config_module.settings.ALLOWED_ORIGINS


def test_no_hardcoded_jwt_secret_fallback_in_source():
    """Le secret de repli historique ne doit plus exister dans le code source."""
    path = os.path.join(REPO_ROOT, "tchuekam_backend", "core", "config.py")
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    assert "tchuekam_super_secret_jwt_key" not in source


def test_production_without_jwt_secret_fails_closed():
    """Sans TCHUEKAM_JWT_SECRET_KEY, un demarrage en production doit echouer."""
    env = dict(os.environ)
    env["ENVIRONMENT"] = "production"
    env.pop("TCHUEKAM_JWT_SECRET_KEY", None)
    proc = subprocess.run(
        [sys.executable, "-c", "import tchuekam_backend.core.config"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0, (
        "Le backend a demarre en production sans secret JWT explicite"
    )
    assert "TCHUEKAM_JWT_SECRET_KEY" in (proc.stderr + proc.stdout)


def test_production_with_explicit_jwt_secret_boots():
    env = dict(os.environ)
    env["ENVIRONMENT"] = "production"
    env["TCHUEKAM_JWT_SECRET_KEY"] = "x" * 64
    proc = subprocess.run(
        [sys.executable, "-c",
         "from tchuekam_backend.core.config import settings; print(settings.JWT_SECRET_KEY[:4])"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "xxxx" in proc.stdout


def test_development_generates_ephemeral_secret_not_constant():
    """Deux demarrages en developpement ne doivent pas partager le meme secret."""
    env = dict(os.environ)
    env["ENVIRONMENT"] = "development"
    env.pop("TCHUEKAM_JWT_SECRET_KEY", None)
    code = "from tchuekam_backend.core.config import settings; print(settings.JWT_SECRET_KEY)"
    first = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                           capture_output=True, text=True, timeout=120)
    second = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                            capture_output=True, text=True, timeout=120)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout.strip() and first.stdout.strip() != second.stdout.strip()
