"""Tests for offline detection, hybrid connectivity transitions, and seamless failover."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_is_network_error_distinguishes_transport_from_code_bugs():
    from agent.connectivity import is_network_error

    assert is_network_error(NameError("name 'foo' is not defined")) is False
    assert is_network_error(ValueError("HTTP 400 invalid argument")) is False
    assert is_network_error(ConnectionError("Connection aborted")) is True
    assert is_network_error(socket.gaierror("getaddrinfo failed")) is True
    assert is_network_error("httpx.ConnectError: [Errno 11001] getaddrinfo failed") is True


def test_connectivity_monitor_transitions_and_restore(monkeypatch):
    from agent.connectivity import ConnectivityMonitor

    mon = ConnectivityMonitor()
    mon._mode = "hybrid"
    events = []
    unsub = mon.subscribe(lambda snap: events.append(dict(snap)))

    monkeypatch.setenv("HERMES_OFFLINE_FORCE", "1")
    assert mon.probe(force=True) == "offline"
    assert mon.should_use_local_first() is True
    assert any(e["offline"] is True for e in events)

    # Restore connectivity
    monkeypatch.delenv("HERMES_OFFLINE_FORCE", raising=False)
    monkeypatch.setenv("HERMES_ONLINE_FORCE", "1")
    assert mon.probe(force=True) == "online"
    assert mon.should_use_local_first() is False
    assert mon.report_cloud_failure(ConnectionError("timeout"), provider="gemini") == "degraded"
    assert mon.report_cloud_success(provider="gemini") == "online"

    unsub()


def test_prepare_turn_intelligence_switches_offline_and_restores_online(monkeypatch):
    from agent.agent_runtime_helpers import prepare_turn_intelligence
    from agent.connectivity import get_connectivity_monitor
    from agent.local_runtime import LocalRuntimeEndpoint, get_local_runtime_manager

    mon = get_connectivity_monitor()
    orig_mode = mon.get_mode()
    mon.set_mode("hybrid", persist=False)

    fake_mgr = get_local_runtime_manager()
    monkeypatch.setattr(fake_mgr, "is_local_available", lambda: True)
    monkeypatch.setattr(
        fake_mgr,
        "ensure_started",
        lambda role_id="mbowagpt", **kw: LocalRuntimeEndpoint(
            base_url="http://127.0.0.1:18080/v1",
            api_key="local-mbowagpt",
            model_id=role_id,
            served_model="Qwen3-1.7B-Q4_K_M",
            weights_path="C:/models/Qwen3-1.7B-Q4_K_M.gguf",
            backend="llama-server",
            ctx_size=4096,
        ),
    )

    monkeypatch.setenv("HERMES_OFFLINE_FORCE", "1")
    mon.probe(force=True)

    emitted_status = []
    intel_events = []
    agent = SimpleNamespace(
        provider="gemini",
        model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="AIza-test",
        api_mode="chat_completions",
        _client_kwargs={"api_key": "AIza-test", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
        _use_prompt_caching=False,
        _use_native_cache_layout=False,
        _fallback_activated=False,
        _fallback_index=0,
        _primary_runtime=None,
        _transport_cache={},
        _offline_local_fallback_active=False,
        _sticky_fallback_active=False,
        _requested_mbowagpt_model=None,
        _active_mbowagpt_role=None,
        _active_mbowagpt_route=None,
        _local_served_model=None,
        client=MagicMock(),
        context_compressor=MagicMock(
            model="gemini-2.5-flash",
            base_url="https://generativelanguage.googleapis.com",
            api_key="AIza-test",
            provider="gemini",
            context_length=128000,
            threshold_tokens=96000,
        ),
        _create_openai_client=lambda kwargs, **kw: MagicMock(kwargs=kwargs),
        _emit_status=lambda msg: emitted_status.append(msg),
        intelligence_callback=lambda ev: intel_events.append(ev),
    )

    prepare_turn_intelligence(agent, "Check nginx logs and debug 502 error", [])
    assert agent.provider == "mbowagpt"
    assert agent.model == "mbowagpt-cybertrunk"
    assert agent._local_served_model == "Qwen3-1.7B-Q4_K_M"
    assert agent._offline_local_fallback_active is True
    assert intel_events and intel_events[-1]["tier"] == "local"

    # Now restore internet connectivity and verify seamless return to cloud
    monkeypatch.delenv("HERMES_OFFLINE_FORCE", raising=False)
    monkeypatch.setenv("HERMES_ONLINE_FORCE", "1")
    prepare_turn_intelligence(agent, "Now summarize online docs", [])
    assert agent.provider == "gemini"
    assert agent.model == "gemini-2.5-flash"
    assert agent._offline_local_fallback_active is False
    assert intel_events[-1]["tier"] == "cloud"

    mon.set_mode(orig_mode, persist=False)
    monkeypatch.delenv("HERMES_ONLINE_FORCE", raising=False)
