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

    def test_conversation_loop_fast_failover_on_503_overloaded(self):
        from types import SimpleNamespace
        from agent.auxiliary_client import clear_runtime_main
        from run_agent import AIAgent

        with (
            patch("run_agent.get_tool_definitions", return_value=[]),
            patch("run_agent.check_toolset_requirements", return_value={}),
            patch("run_agent.OpenAI"),
        ):
            agent = AIAgent(
                api_key="AIza_primary",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                provider="gemini",
                model="gemini-2.5-flash",
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
                fallback_model=[{"provider": "groq", "model": "llama-3.3-70b-versatile"}],
            )

        primary_err = Exception("Service Unavailable")
        primary_err.status_code = 503

        fb_client = MagicMock()
        fb_client.base_url = "https://api.groq.com/openai/v1"
        fb_client.api_key = "gsk_fb"
        fb_resp = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Fast fallback reply", tool_calls=None, reasoning=None))],
            usage=None,
            model="llama-3.3-70b-versatile",
        )
        fb_client.chat.completions.create.return_value = fb_resp

        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = primary_err
        agent._build_api_kwargs = lambda msgs, **kw: {"model": agent.model, "messages": msgs}
        agent._persist_session = lambda *a, **kw: None
        agent._save_trajectory = lambda *a, **kw: None
        agent._cleanup_task_resources = lambda *a, **kw: None
        agent._try_recover_primary_transport = MagicMock(return_value=False)

        try:
            with patch("agent.auxiliary_client.resolve_provider_client", return_value=(fb_client, "llama-3.3-70b-versatile")):
                result = agent.run_conversation("hello")

            assert result.get("completed") is True
            assert result.get("final_response") == "Fast fallback reply"
            assert agent.provider == "groq"
            assert agent.client.chat.completions.create.call_count == 1
            agent._try_recover_primary_transport.assert_not_called()
        finally:
            clear_runtime_main()


class TestVercelSplitOriginSupport:
    def test_public_showcase_allows_vercel_origin_ws_and_validate_without_token(self, monkeypatch):
        from starlette.websockets import WebSocketDisconnect
        from hermes_cli import web_server as ws

        monkeypatch.setattr(ws.app.state, "allow_public", True, raising=False)
        monkeypatch.setattr(ws.app.state, "auth_required", False, raising=False)
        monkeypatch.setattr(ws, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", True)
        with TestClient(ws.app) as client:
            # Provider credential probe (empty key validation) from *.vercel.app allowed without token
            resp = client.post(
                "/api/providers/validate",
                json={"key": "FAL_KEY", "value": ""},
                headers={"Origin": "https://tchuekam-agent.vercel.app"},
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is False

            # Untrusted external origin still fails _ws_auth_ok on /api/ws without token
            with pytest.raises(WebSocketDisconnect) as bad_ws:
                with client.websocket_connect(
                    "/api/ws",
                    headers={"Origin": "https://evil.example.com"},
                ):
                    pass
            assert bad_ws.value.code == 4401

            # Trusted Vercel origin passes _ws_auth_ok on /api/ws without token
            fake_ws = MagicMock()
            fake_ws.app = ws.app
            fake_ws.url.path = "/api/ws"
            fake_ws.query_params = {}
            fake_ws.headers = {"origin": "https://tchuekam-agent.vercel.app"}
            assert ws._ws_auth_ok(fake_ws) is True

            # /api/pty stays locked even for Vercel origin
            with pytest.raises(WebSocketDisconnect) as pty_ws:
                with client.websocket_connect(
                    f"/api/pty?token={ws._SESSION_TOKEN}",
                    headers={"Origin": "https://tchuekam-agent.vercel.app"},
                ):
                    pass
            assert pty_ws.value.code == 4403
