"""Enterprise polish tests: fast fallback chain, aux cascade, non-blocking business AI, and showcase security."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def clean_fallback_env(monkeypatch):
    for var in (
        "HERMES_FALLBACK_PROVIDERS",
        "GROQ_API_KEY",
        "GROQ_API_KEYS",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEYS",
        "ANTHROPIC_TOKEN",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEYS",
        "OPENAI_API_KEY",
        "OPENAI_API_KEYS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEYS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("hermes_cli.config.load_env", lambda: {})


class TestResolveEffectiveFallbackChain:
    def test_merges_config_env_and_auto_providers(self, clean_fallback_env, monkeypatch):
        from hermes_cli.fallback_config import resolve_effective_fallback_chain

        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        monkeypatch.setenv("GEMINI_API_KEYS", "AIza_1,AIza_2")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("HERMES_FALLBACK_PROVIDERS", "deepseek:deepseek-chat")

        chain = resolve_effective_fallback_chain(
            {"fallback_providers": [{"provider": "openrouter", "model": "google/gemini-2.5-flash"}]},
            primary_provider="gemini",
            primary_model="gemini-2.5-flash",
        )

        providers = [(e["provider"], e["model"]) for e in chain]
        assert providers[0] == ("openrouter", "google/gemini-2.5-flash")
        assert ("deepseek", "deepseek-chat") in providers
        assert ("groq", "llama-3.3-70b-versatile") in providers
        assert ("anthropic", "claude-haiku-4-5-20251001") in providers
        assert all(p != "gemini" for p, _ in providers)


class TestAuxiliaryCascadeWithGroqAndGemini:
    def test_groq_has_default_aux_model_and_gemini_uses_ga_flash(self):
        from agent.auxiliary_client import _get_aux_model_for_provider

        assert _get_aux_model_for_provider("groq") == "llama-3.3-70b-versatile"
        assert _get_aux_model_for_provider("gemini") == "gemini-2.5-flash"

    def test_auto_call_cascades_across_multiple_fallbacks(self, clean_fallback_env):
        from agent.auxiliary_client import _reset_aux_unhealthy_cache, call_llm

        _reset_aux_unhealthy_cache()

        primary_client = MagicMock()
        err_429 = Exception("Rate limit reached")
        err_429.status_code = 429
        primary_client.chat.completions.create.side_effect = err_429
        primary_client.base_url = "https://generativelanguage.googleapis.com/v1beta"

        failing_fb = MagicMock()
        err_503 = Exception("Service Unavailable")
        err_503.status_code = 503
        failing_fb.chat.completions.create.side_effect = err_503
        failing_fb.base_url = "https://openrouter.ai/api/v1"

        succeeding_fb = MagicMock()
        succeeding_fb.base_url = "https://api.groq.com/openai/v1"
        succeeding_fb.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Groq responded fast"))]
        )

        def _fake_fallback(failed_provider, task=None, reason="error", skip_providers=None):
            skip = skip_providers or set()
            if "openrouter" not in skip:
                return failing_fb, "google/gemini-2.5-flash", "openrouter"
            if "groq" not in skip:
                return succeeding_fb, "llama-3.3-70b-versatile", "groq"
            return None, None, ""

        with (
            patch("agent.auxiliary_client._resolve_task_provider_model", return_value=("auto", "", None, None, None)),
            patch("agent.auxiliary_client._get_cached_client", return_value=(primary_client, "gemini-2.5-flash")),
            patch("agent.auxiliary_client._try_payment_fallback", side_effect=_fake_fallback),
        ):
            resp = call_llm(task="fast", messages=[{"role": "user", "content": "hi"}])

        assert resp.choices[0].message.content == "Groq responded fast"
        assert failing_fb.chat.completions.create.called
        assert succeeding_fb.chat.completions.create.called


class TestPublicShowcaseSecurityHardening:
    def _configure_public(self, monkeypatch, admin_key: str = ""):
        from hermes_cli import web_server as ws

        monkeypatch.setattr(ws.app.state, "allow_public", True, raising=False)
        monkeypatch.setattr(ws.app.state, "auth_required", False, raising=False)
        if admin_key:
            monkeypatch.setenv("HERMES_DASHBOARD_ADMIN_KEY", admin_key)
        else:
            monkeypatch.delenv("HERMES_DASHBOARD_ADMIN_KEY", raising=False)
        return ws

    def test_sensitive_routes_blocked_and_security_headers_present(self, monkeypatch):
        ws = self._configure_public(monkeypatch)
        headers = {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}

        with TestClient(ws.app) as client:
            for method, path, payload in [
                ("POST", "/api/env/reveal", {"key": "GEMINI_API_KEY"}),
                ("PUT", "/api/env", {"key": "FOO", "value": "BAR"}),
                ("DELETE", "/api/env", {"key": "FOO"}),
                ("PUT", "/api/config", {"config": {}}),
                ("GET", "/api/config/raw", None),
                ("PUT", "/api/config/raw", {"yaml_text": "a: 1"}),
                ("POST", "/api/model/set", {"scope": "main", "provider": "groq", "model": "x"}),
                ("GET", "/api/logs", None),
                ("POST", "/api/ops/dump", {}),
                ("GET", "/api/cron/jobs", None),
                ("GET", "/api/mcp/servers", None),
                ("GET", "/api/profiles", None),
                ("GET", "/api/webhooks", None),
                ("POST", "/api/gateway/restart", {}),
            ]:
                resp = client.request(method, path, json=payload, headers=headers)
                assert resp.status_code == 403, f"Expected 403 for {method} {path}, got {resp.status_code}"
                assert resp.headers.get("x-content-type-options") == "nosniff"
                assert resp.headers.get("x-frame-options") == "SAMEORIGIN"

            health = client.get("/health")
            assert health.status_code == 200
            assert health.headers.get("x-content-type-options") == "nosniff"

    def test_admin_key_allows_override_and_pty_closed_in_public_mode(self, monkeypatch):
        from starlette.websockets import WebSocketDisconnect

        ws = self._configure_public(monkeypatch, admin_key="super-secret-admin-key")
        with TestClient(ws.app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/api/pty?token={ws._SESSION_TOKEN}"):
                    pass
            assert exc_info.value.code == 4403

            admin_raw = client.get(
                "/api/config/raw",
                headers={
                    ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN,
                    "X-Hermes-Admin-Key": "super-secret-admin-key",
                },
            )
            assert admin_raw.status_code == 200
            assert "yaml" in admin_raw.json()

    def test_business_ai_falls_back_when_primary_errors(self, monkeypatch):
        ws = self._configure_public(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr("hermes_cli.config.load_env", lambda: {})

        calls: list[tuple] = []

        def _fake_call_llm(*, messages, task=None, provider=None, model=None, max_tokens=600, timeout=20.0):
            calls.append((task, provider, model))
            if provider is None:
                raise RuntimeError("Primary 500 error")
            return MagicMock(choices=[MagicMock(message=MagicMock(content="Polished executive text"))])

        with patch("agent.auxiliary_client.call_llm", side_effect=_fake_call_llm):
            with TestClient(ws.app) as client:
                resp = client.post(
                    "/api/business/ai",
                    json={"operation": "polish", "input": "Draft clause", "language": "en"},
                )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "output": "Polished executive text"}
        assert len(calls) >= 2

    def test_serve_index_omits_session_token_in_public_demo(self, monkeypatch):
        ws = self._configure_public(monkeypatch)
        with TestClient(ws.app) as client:
            resp = client.get("/")
        assert resp.status_code == 200
        assert "window.__HERMES_PUBLIC_DEMO__=true;" in resp.text
        assert "window.__HERMES_SESSION_TOKEN__" not in resp.text

    def test_status_strips_paths_and_pid_in_public_demo(self, monkeypatch):
        ws = self._configure_public(monkeypatch)
        headers = {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}
        with TestClient(ws.app) as client:
            resp = client.get("/api/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["hermes_home"] is None
        assert data["config_path"] is None
        assert data["env_path"] is None
        assert data["gateway_pid"] is None
        assert data["gateway_health_url"] is None

    def test_image_upload_rejects_invalid_magic_bytes_and_oversized(self, monkeypatch):
        import base64

        ws = self._configure_public(monkeypatch)
        headers = {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}
        ws._RATE_BUCKETS.clear()

        fake_png = base64.b64encode(b"this-is-plain-text-not-png").decode("ascii")
        oversized_b64 = "A" * (14 * 1024 * 1024)
        with TestClient(ws.app) as client:
            bad_magic = client.post(
                "/api/uploads/image",
                json={"data_url": f"data:image/png;base64,{fake_png}"},
                headers=headers,
            )
            assert bad_magic.status_code == 400

            too_big = client.post(
                "/api/uploads/image",
                json={"data_url": f"data:image/png;base64,{oversized_b64}"},
                headers=headers,
            )
            assert too_big.status_code == 413

    def test_business_ocr_rejects_oversized_upload(self, monkeypatch):
        ws = self._configure_public(monkeypatch)
        headers = {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}
        ws._RATE_BUCKETS.clear()

        oversized_b64 = "A" * (34 * 1024 * 1024)
        with TestClient(ws.app) as client:
            resp = client.post(
                "/api/business/ocr",
                json={
                    "data_url": f"data:application/pdf;base64,{oversized_b64}",
                    "file_name": "huge.pdf",
                    "mime_type": "application/pdf",
                },
                headers=headers,
            )
        assert resp.status_code == 413


class TestCredentialPoolAndFastLoopFailover:
    def test_multi_key_env_seeding_for_gemini_and_groq(self, clean_fallback_env, monkeypatch, tmp_path):
        from agent.credential_pool import load_pool

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("GEMINI_API_KEYS", "AIza_k1,AIza_k2,AIza_k3,AIza_k4")
        monkeypatch.setenv("GROQ_API_KEYS", "gsk_1,gsk_2,gsk_3")

        gemini_pool = load_pool("gemini")
        groq_pool = load_pool("groq")

        assert len(gemini_pool.entries()) == 4
        assert len(groq_pool.entries()) == 3

