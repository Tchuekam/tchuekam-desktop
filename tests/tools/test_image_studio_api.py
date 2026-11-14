"""
HTTP-level tests for the Image Studio API, run against the REAL FastAPI app
(auth middleware included) and the real service/storage code.

MOCKED vs REAL (stated explicitly, per release policy):
  * REAL:   FastAPI app, session-token auth, job lifecycle, asset registry,
            workspace scoping, file materialization, palette extraction (Pillow).
  * MOCKED: only the *provider* (``FakeProvider``) — a deterministic stand-in
            for FAL/MuAPI so failure modes (error, timeout, empty result,
            cancel-in-flight) can be forced. These tests do NOT prove FAL.ai or
            MuAPI connectivity; see the release report for that.
"""

import base64
import io
import threading

import pytest
from fastapi.testclient import TestClient

import agent.image_studio_service as studio


@pytest.fixture()
def env(monkeypatch, tmp_path):
    cache = tmp_path / "cache" / "image_studio"
    (cache / "assets").mkdir(parents=True)
    monkeypatch.setattr(studio, "get_image_studio_dir", lambda: cache)
    monkeypatch.setattr(studio, "get_image_studio_assets_dir", lambda: cache / "assets")
    monkeypatch.setattr(studio, "_library_path", lambda: cache / "library.json")
    monkeypatch.setattr(studio, "_jobs_path", lambda: cache / "jobs.json")
    monkeypatch.setattr(studio, "_recovered", False)
    return cache


class FakeProvider:
    name = "fal"

    def __init__(self, result=None, exc=None, available=True, hook=None):
        self._result, self._exc, self._available, self._hook = result, exc, available, hook
        self.calls = 0

    def is_available(self):
        return self._available

    def default_model(self):
        return "fal-ai/flux-2/klein/9b"

    def generate(self, prompt, **kw):
        self.calls += 1
        if self._hook:
            self._hook()
        if self._exc:
            raise self._exc
        return self._result


OK = {"success": True, "image": "https://fal.media/files/x/out.png"}


@pytest.fixture()
def client(env, monkeypatch):
    from hermes_cli import web_server

    def use(provider):
        monkeypatch.setattr("agent.image_gen_registry.get_provider", lambda n: provider)
        monkeypatch.setattr("agent.image_gen_registry.get_active_provider", lambda: provider)
        monkeypatch.setattr("hermes_cli.plugins._ensure_plugins_discovered", lambda: None)

    c = TestClient(
        web_server.app,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {web_server._SESSION_TOKEN}"},
    )
    c.use = use
    return c


def _png_data_url(color=(200, 30, 30)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# --- auth ---------------------------------------------------------------------
def test_unauthenticated_requests_are_rejected(env):
    from hermes_cli import web_server

    anon = TestClient(web_server.app, base_url="http://127.0.0.1")
    assert anon.get("/api/images/library").status_code in (401, 403)
    assert anon.post("/api/images/generate", json={"prompt": "x"}).status_code in (401, 403)


# --- generation lifecycle -------------------------------------------------------
def test_generate_success_registers_asset_after_completion(client):
    client.use(FakeProvider(result=OK))
    r = client.post("/api/images/generate", json={"prompt": "a red fox", "clientRequestId": "r1"}).json()
    assert r["success"] and r["state"] == "COMPLETED"
    lib = client.get("/api/images/library").json()["items"]
    assert [a["id"] for a in lib] == [r["asset"]["id"]]
    assert lib[0]["jobId"] == r["jobId"]
    assert "localPath" not in lib[0]  # never leak server paths


def test_duplicate_request_id_does_not_generate_twice(client):
    p = FakeProvider(result=OK)
    client.use(p)
    a = client.post("/api/images/generate", json={"prompt": "fox", "clientRequestId": "same"}).json()
    b = client.post("/api/images/generate", json={"prompt": "fox", "clientRequestId": "same"}).json()
    assert p.calls == 1
    assert b["duplicate"] is True and b["jobId"] == a["jobId"]
    assert len(client.get("/api/images/library").json()["items"]) == 1


@pytest.mark.parametrize(
    "exc,etype",
    [
        (Exception("401 Unauthorized: bad key"), "auth_invalid_credentials"),
        (TimeoutError("read timed out"), "timeout"),
        (ConnectionError("dns failure"), "network_error"),
        (Exception("429 rate limit"), "quota_or_rate_limited"),
    ],
)
def test_provider_errors_are_normalized_and_leave_no_asset(client, exc, etype):
    client.use(FakeProvider(exc=exc))
    r = client.post("/api/images/generate", json={"prompt": "fox"}).json()
    assert r["success"] is False and r["error_type"] == etype and r["state"] == "FAILED"
    assert client.get("/api/images/library").json()["items"] == []
    assert client.get(f"/api/images/jobs/{r['jobId']}").json()["state"] == "FAILED"


def test_unconfigured_provider_fails_without_calling_it(client):
    p = FakeProvider(result=OK, available=False)
    client.use(p)
    r = client.post("/api/images/generate", json={"prompt": "fox"}).json()
    assert r["success"] is False and r["error_type"] == "auth_missing_credentials"
    assert p.calls == 0


def test_empty_provider_result_is_not_reported_as_success(client):
    client.use(FakeProvider(result={"success": True, "image": None}))
    r = client.post("/api/images/generate", json={"prompt": "fox"}).json()
    assert r["success"] is False and r["error_type"] == "empty_result"
    assert client.get("/api/images/library").json()["items"] == []


def test_cancel_during_flight_discards_result(client, env):
    holder = {}

    def cancel_midflight():
        job = studio._load_jobs_raw()[0]
        holder["id"] = job["id"]
        studio.cancel_job(job["id"])

    client.use(FakeProvider(result=OK, hook=cancel_midflight))
    r = client.post("/api/images/generate", json={"prompt": "fox"}).json()
    assert r["success"] is False and r["state"] == "CANCELLED"
    assert client.get("/api/images/library").json()["items"] == []


def test_storage_failure_is_reported_not_swallowed(client, monkeypatch):
    client.use(FakeProvider(result=OK))

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(studio, "_save_library_raw", boom)
    r = client.post("/api/images/generate", json={"prompt": "fox"}).json()
    assert r["success"] is False and r["error_type"] == "storage_failed"


def test_interrupted_job_is_failed_after_restart(env, monkeypatch):
    job, _ = studio.create_job("image", {"prompt": "x"})
    studio.update_job(job["id"], "VALIDATING")
    # simulate a new process: different boot id, recovery not yet run
    monkeypatch.setattr(studio, "_BOOT_ID", "new-process")
    monkeypatch.setattr(studio, "_recovered", False)
    got = studio.get_job(job["id"])
    assert got["state"] == "FAILED" and got["errorType"] == "interrupted"


def test_stale_job_times_out(env, monkeypatch):
    job, _ = studio.create_job("image", {"prompt": "x"})
    monkeypatch.setattr(studio, "JOB_TIMEOUT_S", -1)
    assert studio.get_job(job["id"])["errorType"] == "timeout"


def test_terminal_jobs_cannot_be_resurrected(env):
    job, _ = studio.create_job("image", {"prompt": "x"})
    studio.cancel_job(job["id"])
    assert studio.update_job(job["id"], "PROCESSING")["state"] == "CANCELLED"


# --- persistence & isolation ----------------------------------------------------
def test_assets_survive_a_process_restart(client, env, monkeypatch):
    client.use(FakeProvider(result=OK))
    asset = client.post("/api/images/generate", json={"prompt": "fox"}).json()["asset"]
    monkeypatch.setattr(studio, "_recovered", False)  # "restart": only disk remains
    items = client.get("/api/images/library").json()["items"]
    assert items and items[0]["id"] == asset["id"]


def test_workspace_isolation_over_http(client):
    client.use(FakeProvider(result=OK))
    a = client.post("/api/images/generate", json={"prompt": "secret", "workspaceId": "wsA"}).json()["asset"]
    assert client.get("/api/images/library", params={"workspaceId": "wsB"}).json()["items"] == []
    # omitting the workspace means "default", NOT "everything"
    assert client.get("/api/images/library").json()["items"] == []
    assert client.delete(f"/api/images/library/{a['id']}", params={"workspaceId": "wsB"}).status_code == 404
    assert client.delete(f"/api/images/library/{a['id']}").status_code == 404
    assert client.post(f"/api/images/assets/{a['id']}/materialize", params={"workspaceId": "wsB"}).status_code == 404
    assert client.get(f"/api/images/assets/{a['id']}/data", params={"workspaceId": "wsB"}).status_code == 404
    assert client.get(f"/api/images/jobs/{a['jobId']}", params={"workspaceId": "wsB"}).status_code == 404
    assert client.delete(f"/api/images/library/{a['id']}", params={"workspaceId": "wsA"}).status_code == 200


def test_cannot_overwrite_foreign_asset_id(client):
    body = {"id": "fixed", "url": "https://x/y.png", "prompt": "p", "workspaceId": "wsA"}
    assert client.post("/api/images/library", json=body).status_code == 200
    assert client.post("/api/images/library", json={**body, "workspaceId": "wsB"}).status_code == 409


def test_completed_asset_without_location_is_rejected(client):
    r = client.post("/api/images/library", json={"id": "e", "url": "", "prompt": "p"})
    assert r.status_code == 422


def test_client_cannot_inject_local_path(client):
    r = client.post(
        "/api/images/library",
        json={"id": "p1", "url": "https://x/y.png", "prompt": "p", "localPath": r"C:\Windows\win.ini"},
    ).json()
    assert r["item"]["hasLocalFile"] is False
    assert studio.get_asset("p1")["localPath"] in (None, "")


def test_delete_requires_existing_asset(client):
    assert client.delete("/api/images/library/nope").status_code == 404


# --- materialize (chat attachment) -----------------------------------------------
def test_materialize_writes_real_file_from_data_url(client, env):
    client.post("/api/images/library", json={"id": "m1", "url": _png_data_url(), "prompt": "p"})
    r = client.post("/api/images/assets/m1/materialize").json()
    assert r["success"]
    from pathlib import Path

    p = Path(r["path"])
    assert p.is_file() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert env / "assets" in p.parents
    data = client.get("/api/images/assets/m1/data").json()
    assert data["success"] and data["dataUrl"].startswith("data:image/png;base64,")


def test_materialize_blocks_unsafe_urls(client, monkeypatch):
    client.post("/api/images/library", json={"id": "ssrf", "url": "http://169.254.169.254/latest/meta-data", "prompt": "p"})
    r = client.post("/api/images/assets/ssrf/materialize")
    assert r.status_code == 502


def test_deleting_asset_removes_only_owned_cache_file(client, env, tmp_path):
    client.post("/api/images/library", json={"id": "d1", "url": _png_data_url(), "prompt": "p"})
    path = client.post("/api/images/assets/d1/materialize").json()["path"]
    outside = tmp_path / "keep.png"
    outside.write_bytes(b"x")
    studio._save_library_raw([{**studio.get_asset("d1"), "id": "d2", "localPath": str(outside)}] + studio._load_library_raw())
    assert client.delete("/api/images/library/d1").status_code == 200
    assert not __import__("os").path.exists(path)
    assert client.delete("/api/images/library/d2").status_code == 200
    assert outside.exists(), "files outside the studio cache must never be deleted"


# --- no fake analysis ------------------------------------------------------------
def test_color_analysis_is_computed_from_pixels(client):
    r = client.post("/api/images/analyze", json={"image": _png_data_url((255, 0, 0)), "mode": "color"}).json()
    assert r["success"] and r["colors"][0] == "#FF0000"


def test_describe_without_vision_is_honest_error_not_canned_text(client, monkeypatch):
    monkeypatch.setattr("tools.vision_tools.check_vision_requirements", lambda: False)
    r = client.post("/api/images/analyze", json={"image": _png_data_url(), "mode": "describe"}).json()
    assert r["success"] is False and r["error_type"] == "vision_unavailable"
    assert "result" not in r


def test_ocr_without_vision_never_returns_a_fake_invoice(client, monkeypatch):
    monkeypatch.setattr("tools.vision_tools.check_vision_requirements", lambda: False)
    r = client.post("/api/images/ocr", json={"image": _png_data_url()}).json()
    assert r["success"] is False and "INV-98124" not in str(r)


def test_vision_rejects_local_file_paths(client, monkeypatch):
    monkeypatch.setattr("tools.vision_tools.check_vision_requirements", lambda: True)
    r = client.post("/api/images/ocr", json={"image": r"C:\Users\victim\secret.png"}).json()
    assert r["success"] is False and r["error_type"] == "invalid_image"


def test_vision_uses_real_backend_when_available(client, monkeypatch):
    async def fake_vision(target, prompt):
        return '{"success": true, "analysis": "text found"}'

    monkeypatch.setattr("tools.vision_tools.check_vision_requirements", lambda: True)
    monkeypatch.setattr("tools.vision_tools.vision_analyze_tool", fake_vision)  # MOCKED vision model
    r = client.post("/api/images/ocr", json={"image": _png_data_url()}).json()
    assert r == {"success": True, "text": "text found"}


def test_concurrent_registrations_do_not_lose_assets(env):
    def reg(i):
        studio.register_asset(url=f"https://x/{i}.png", prompt=str(i), provider="fal", model="m")

    ts = [threading.Thread(target=reg, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(studio.list_assets(limit=100)) == 20

