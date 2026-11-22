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
        assert ("groq", "openai/gpt-oss-120b") in providers
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


class TestMultiTurnStickyFallbackAndSanitization:
    def test_same_provider_gemini_fallback_included_when_primary_model_differs(
        self, clean_fallback_env, monkeypatch
    ):
        from hermes_cli.fallback_config import resolve_effective_fallback_chain

        monkeypatch.setenv("GEMINI_API_KEY", "AIza_test")
        monkeypatch.setenv("GROQ_API_KEYS", "gsk_1,gsk_2,gsk_3")

        chain = resolve_effective_fallback_chain(
            {},
            primary_provider="gemini",
            primary_model="gemini-3.6-flash",
        )
        providers = [(e["provider"], e["model"]) for e in chain]
        assert ("gemini", "gemini-2.5-flash") in providers
        assert ("groq", "openai/gpt-oss-120b") in providers
        assert ("groq", "qwen/qwen3.8-27b") in providers

    def test_multi_turn_gemini_to_groq_strips_reasoning_content_and_stays_sticky(self):
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
                model="gemini-3.6-flash",
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
                fallback_model=[{"provider": "groq", "model": "openai/gpt-oss-120b"}],
            )

        primary_client = MagicMock()
        err_503 = Exception("Gemini 503 overloaded")
        err_503.status_code = 503
        primary_client.chat.completions.create.side_effect = err_503

        sent_payloads = []
        groq_client = MagicMock()
        groq_client.base_url = "https://api.groq.com/openai/v1"
        groq_client.api_key = "gsk_working"

        def _groq_create(**kwargs):
            import copy
            sent_payloads.append(copy.deepcopy(kwargs.get("messages", [])))
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(
                            content=f"Groq turn {len(sent_payloads)} reply",
                            tool_calls=None,
                            reasoning="internal reasoning",
                            reasoning_content="internal reasoning",
                        ),
                    )
                ],
                usage=None,
                model="openai/gpt-oss-120b",
            )

        groq_client.chat.completions.create.side_effect = _groq_create
        agent.client = primary_client
        agent._persist_session = lambda *a, **kw: None
        agent._save_trajectory = lambda *a, **kw: None
        agent._cleanup_task_resources = lambda *a, **kw: None
        agent._try_recover_primary_transport = MagicMock(return_value=False)

        prior_history = [
            {"role": "user", "content": "Run a tool for me"},
            {
                "role": "assistant",
                "content": "",
                "reasoning": "Gemini thought",
                "reasoning_content": "Gemini thought",
                "reasoning_details": [{"type": "reasoning.summary", "summary": "Gemini thought"}],
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query":"test"}'},
                        "extra_content": {"google": {"thought_signature": "sig-abc"}},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "web_search", "content": '{"ok":true}'},
        ]

        try:
            with patch(
                "agent.auxiliary_client.resolve_provider_client",
                return_value=(groq_client, "openai/gpt-oss-120b"),
            ):
                turn1 = agent.run_conversation("First follow-up", conversation_history=prior_history)
                assert turn1.get("completed") is True
                assert turn1.get("final_response") == "Groq turn 1 reply"
                assert agent.provider == "groq"
                assert agent.model == "openai/gpt-oss-120b"
                assert getattr(agent, "_sticky_fallback_active", False) is True

                # Verify Groq payload had reasoning_content, reasoning_details, and extra_content stripped
                assistant_msgs = [m for m in sent_payloads[0] if m.get("role") == "assistant"]
                assert assistant_msgs
                for am in assistant_msgs:
                    assert "reasoning_content" not in am
                    assert "reasoning_details" not in am
                    for tc in am.get("tool_calls") or []:
                        assert "extra_content" not in tc

                # Turn 2: must stay sticky on the working Groq model without rotating back to broken Gemini
                primary_client.chat.completions.create.reset_mock()
                turn2 = agent.run_conversation(
                    "Second follow-up",
                    conversation_history=turn1["messages"],
                )
                assert turn2.get("completed") is True
                assert turn2.get("final_response") == "Groq turn 2 reply"
                assert agent.provider == "groq"
                assert agent.model == "openai/gpt-oss-120b"
                primary_client.chat.completions.create.assert_not_called()
        finally:
            clear_runtime_main()

    def test_gemini_native_coalesces_consecutive_tool_results_and_classifies_timeout(self):
        import httpx
        from agent.error_classifier import FailoverReason, classify_api_error
        from agent.gemini_native_adapter import GeminiNativeClient, build_gemini_request

        req = build_gemini_request(
            messages=[
                {"role": "user", "content": "Check two cities"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Yaounde"}'}},
                        {"id": "c2", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Douala"}'}},
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": '{"temp":28}'},
                {"role": "tool", "tool_call_id": "c2", "content": '{"temp":31}'},
            ],
            tools=[],
            tool_choice=None,
        )
        assert [c["role"] for c in req["contents"]] == ["user", "model", "user"]
        assert len(req["contents"][2]["parts"]) == 2

        class _TimeoutHTTP:
            def post(self, *a, **kw):
                raise httpx.ReadTimeout("timed out waiting for Gemini")

            def close(self):
                pass

        client = GeminiNativeClient(api_key="AIza-test", http_client=_TimeoutHTTP())
        with pytest.raises(Exception) as exc_info:
            client.chat.completions.create(
                model="gemini-3.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            )
        classified = classify_api_error(exc_info.value)
        assert classified.reason == FailoverReason.timeout

    def test_aiagent_exposes_provider_rejects_reasoning_content_and_strips_mbowagpt_prefill(self):
        from agent.agent_runtime_helpers import failover_to_local_mbowagpt
        from run_agent import AIAgent

        with (
            patch("run_agent.get_tool_definitions", return_value=[]),
            patch("run_agent.check_toolset_requirements", return_value={}),
            patch("run_agent.OpenAI"),
        ):
            agent = AIAgent(
                api_key="gsk_test",
                base_url="https://api.groq.com/openai/v1",
                provider="groq",
                model="openai/gpt-oss-120b",
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
            )

        assert agent._provider_rejects_reasoning_content() is True

        # Failing over to MbowaGPT must prune trailing _thinking_prefill assistant turns
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "", "_thinking_prefill": True},
        ]
        fake_mgr = MagicMock()
        fake_mgr.is_local_available.return_value = True
        fake_mgr.ensure_started.return_value = MagicMock(
            model_id="mbowagpt-fast",
            served_model="qwen3",
            base_url="http://127.0.0.1:18080/v1",
            api_key="local",
            ctx_size=8192,
        )
        with (
            patch("agent.local_runtime.get_local_runtime_manager", return_value=fake_mgr),
            patch.object(agent, "_create_openai_client", return_value=MagicMock()),
        ):
            assert failover_to_local_mbowagpt(agent, "Hello", msgs) is True
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_fetch_endpoint_model_metadata_short_circuits_when_offline(self, monkeypatch):
        from agent import model_metadata

        monkeypatch.setenv("HERMES_OFFLINE", "1")
        with patch.object(model_metadata.requests, "get") as mock_get:
            res = model_metadata.fetch_endpoint_model_metadata("https://api.example.com/v1")
        assert res == {}
        mock_get.assert_not_called()
