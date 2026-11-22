"""Regression tests for SaaS backend web security hardening."""

from __future__ import annotations

import io
import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tchuekam_backend.main import app

client = TestClient(app)


def _signup_and_login(email: str, password: str = "SecurePassword123!") -> tuple[str, str]:
    client.post("/api/v1/auth/signup", json={"email": email, "password": password, "full_name": "Sec User"})
    res = client.post("/api/v1/auth/signin", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()
    return data["user_id"], data["access_token"]


def test_security_alerts_ws_rejects_unauth_and_cross_user():
    user_a_id, token_a = _signup_and_login("ws_user_a@tchuekam.com")
    user_b_id, _token_b = _signup_and_login("ws_user_b@tchuekam.com")

    with pytest.raises(WebSocketDisconnect) as exc_unauth:
        with client.websocket_connect(f"/api/v1/ws/security-alerts/{user_a_id}"):
            pass
    assert exc_unauth.value.code == 4401

    with pytest.raises(WebSocketDisconnect) as exc_cross:
        with client.websocket_connect(f"/api/v1/ws/security-alerts/{user_b_id}?token={token_a}"):
            pass
    assert exc_cross.value.code == 4403

    with client.websocket_connect(f"/api/v1/ws/security-alerts/{user_a_id}?token={token_a}") as ws:
        ws.send_text("ping")
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "PONG"
        assert msg["payload"] == "ping"


def test_cross_tenant_api_key_revoke_returns_404():
    _ua, tok_a = _signup_and_login("idor_key_a@tchuekam.com")
    _ub, tok_b = _signup_and_login("idor_key_b@tchuekam.com")
    headers_a = {"Authorization": f"Bearer {tok_a}"}
    headers_b = {"Authorization": f"Bearer {tok_b}"}

    org_a = client.post("/api/v1/organizations", json={"name": "Tenant Key A", "slug": "tenant-key-a"}, headers=headers_a).json()["id"]
    org_b = client.post("/api/v1/organizations", json={"name": "Tenant Key B", "slug": "tenant-key-b"}, headers=headers_b).json()["id"]

    key_a = client.post(
        "/api/v1/api-keys",
        json={"name": "Key A", "scopes": ["read"]},
        headers={**headers_a, "X-Organization-Id": org_a},
    )
    assert key_a.status_code == 201
    key_a_id = key_a.json()["id"]

    cross_del = client.delete(
        f"/api/v1/api-keys/{key_a_id}",
        headers={**headers_b, "X-Organization-Id": org_b},
    )
    assert cross_del.status_code == 404

    still_exists = client.get("/api/v1/api-keys", headers={**headers_a, "X-Organization-Id": org_a}).json()
    assert any(k["id"] == key_a_id for k in still_exists)


def test_cross_tenant_workspace_update_returns_404():
    _ua, tok_a = _signup_and_login("idor_ws_a@tchuekam.com")
    _ub, tok_b = _signup_and_login("idor_ws_b@tchuekam.com")
    headers_a = {"Authorization": f"Bearer {tok_a}"}
    headers_b = {"Authorization": f"Bearer {tok_b}"}

    org_a = client.post("/api/v1/organizations", json={"name": "Tenant WS A", "slug": "tenant-ws-a"}, headers=headers_a).json()["id"]
    org_b = client.post("/api/v1/organizations", json={"name": "Tenant WS B", "slug": "tenant-ws-b"}, headers=headers_b).json()["id"]

    ws_a = client.post(
        "/api/v1/workspaces",
        json={"name": "Org A Secret WS", "slug": "org-a-secret"},
        headers={**headers_a, "X-Organization-Id": org_a},
    )
    assert ws_a.status_code == 201
    ws_a_id = ws_a.json()["id"]

    cross_put = client.put(
        f"/api/v1/workspaces/{ws_a_id}",
        json={"name": "Hijacked"},
        headers={**headers_b, "X-Organization-Id": org_b},
    )
    assert cross_put.status_code == 404

    listing = client.get("/api/v1/workspaces", headers={**headers_a, "X-Organization-Id": org_a}).json()
    target = [w for w in listing if w["id"] == ws_a_id][0]
    assert target["name"] == "Org A Secret WS"


def test_supabase_user_provisioning_tuple_order_and_unverified_default(db_session):
    from tchuekam_backend.core.supabase_auth import get_or_provision_supabase_user, get_supabase_issuer

    user, jti, session_id = get_or_provision_supabase_user(
        db_session,
        {
            "sub": "99999999-1111-2222-3333-444444444444",
            "email": "unverified.sb@tchuekam.com",
            "iss": get_supabase_issuer(),
            "session_id": "sb-sess-tuple",
            "jti": "sb-jti-tuple",
            "user_metadata": {"email_verified": True, "username": "unverified_sb"},
        },
    )
    assert user.email == "unverified.sb@tchuekam.com"
    assert user.is_verified is False
    assert jti == "sb-jti-tuple"
    assert session_id == "sb-sess-tuple"


def test_file_upload_omits_storage_path_and_blocks_oversized(monkeypatch):
    _u, token = _signup_and_login("file_sec@tchuekam.com")
    headers = {"Authorization": f"Bearer {token}"}

    ok_res = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert ok_res.status_code == 201
    assert "storage_path" not in ok_res.json()["data"]

    monkeypatch.setattr("tchuekam_backend.core.config.settings.MAX_UPLOAD_SIZE_BYTES", 16)
    big_res = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": ("too_big.txt", io.BytesIO(b"A" * 32), "text/plain")},
    )
    assert big_res.status_code == 400
    assert big_res.json()["error"]["code"] == "FILE_UPLOAD_ERROR"


def test_biocompute_rejects_oversized_upload():
    oversized = b"X" * (2 * 1024 * 1024 + 1)
    res = client.post(
        "/api/v1/biocompute/experiment/run",
        data={"backend": "biocompute_simulator", "dataset": "MNIST"},
        files={"file": ("huge.png", io.BytesIO(oversized), "image/png")},
    )
    assert res.status_code == 413
