"""Tests de durcissement de l'authentification.

Couvre deux failles à fort impact :
  * la rotation des refresh tokens n'était appliquée qu'en mémoire, donc
    contournable après un redémarrage ou depuis un autre worker ;
  * la latence de /signin révélait l'existence d'un compte.
"""

import statistics
import time

import pytest
from fastapi.testclient import TestClient

import tchuekam_backend.core.security as security_module
from tchuekam_backend.main import app

client = TestClient(app)

PASSWORD = "SecurePassword123!"


def _signup_signin(email: str) -> dict:
    client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "full_name": "T"},
    )
    res = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()


def _refresh(token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def _refresh_token_of(response) -> str:
    body = response.json()
    return body["data"]["refresh_token"] if "data" in body else body["refresh_token"]


def test_rotated_refresh_token_rejected_after_process_restart():
    """Le rejeu d'un refresh token consommé doit survivre au vidage du cache mémoire."""
    tokens = _signup_signin("rotate_restart@tchuekam.com")
    first = tokens["refresh_token"]

    rotated = _refresh(first)
    assert rotated.status_code == 200, rotated.text

    # Simule un redémarrage du processus / un second worker uvicorn :
    # la liste noire de JTI en mémoire est vide.
    security_module._REVOKED_JTI_BLACKLIST.clear()

    replayed = _refresh(first)
    assert replayed.status_code != 200, (
        "Rejeu accepte : un refresh token deja consomme reste valide apres redemarrage"
    )


def test_refresh_token_reuse_revokes_the_whole_session():
    """Le rejeu d'un ancien jeton est traité comme un vol : la session tombe."""
    tokens = _signup_signin("rotate_breach@tchuekam.com")
    first = tokens["refresh_token"]

    rotated = _refresh(first)
    assert rotated.status_code == 200
    current = _refresh_token_of(rotated)

    security_module._REVOKED_JTI_BLACKLIST.clear()
    assert _refresh(first).status_code != 200

    # Le jeton légitime en cours doit lui aussi être invalidé après détection.
    security_module._REVOKED_JTI_BLACKLIST.clear()
    assert _refresh(current).status_code != 200, (
        "La session n'a pas ete revoquee apres detection de rejeu"
    )


def test_legitimate_rotation_chain_still_works():
    """Une chaîne de rotations normale ne doit pas être cassée par le durcissement."""
    tokens = _signup_signin("rotate_happy@tchuekam.com")
    token = tokens["refresh_token"]
    for step in range(3):
        res = _refresh(token)
        assert res.status_code == 200, f"rotation {step} refusee: {res.text}"
        token = _refresh_token_of(res)


def test_signin_latency_does_not_reveal_account_existence():
    """La latence d'un echec ne doit pas separer comptes connus et inconnus."""
    n = 6
    for i in range(n):
        client.post(
            "/api/v1/auth/signup",
            json={"email": f"timing_real{i}@tchuekam.com", "password": PASSWORD},
        )

    known, unknown = [], []
    for i in range(n):
        # Une seule tentative par email : le limiteur anti-force-brute est
        # indexe par email et ne se declenche donc pas.
        t = time.perf_counter()
        r = client.post(
            "/api/v1/auth/signin",
            json={"email": f"timing_real{i}@tchuekam.com", "password": "WrongPassword123!"},
        )
        known.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 401

        t = time.perf_counter()
        r = client.post(
            "/api/v1/auth/signin",
            json={"email": f"timing_ghost{i}@tchuekam.com", "password": "WrongPassword123!"},
        )
        unknown.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 401

    m_known, m_unknown = statistics.median(known), statistics.median(unknown)
    slower, faster = max(m_known, m_unknown), max(min(m_known, m_unknown), 1e-6)
    assert slower / faster < 3.0, (
        f"Oracle temporel: comptes connus {m_known:.1f}ms vs inconnus {m_unknown:.1f}ms "
        f"(ratio {slower / faster:.1f}x)"
    )
