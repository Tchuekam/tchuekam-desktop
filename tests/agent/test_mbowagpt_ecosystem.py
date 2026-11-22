"""Tests for the MbowaGPT local intelligence ecosystem and reasoning_content bug fixes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_mbowagpt_specialist_routing_and_continuity():
    from agent.mbowagpt_router import classify_mbowagpt_route

    r_main = classify_mbowagpt_route("Hello, let's brainstorm marketing ideas for Q3")
    assert r_main.model_id == "mbowagpt"
    assert r_main.specialist_key == "main"

    r_cyber = classify_mbowagpt_route(
        "Debug this Python traceback in uvicorn and check TLS firewall ports"
    )
    assert r_cyber.model_id == "mbowagpt-cybertrunk"
    assert r_cyber.specialist_key == "cybertrunk"

    r_rel = classify_mbowagpt_route(
        "Create a step-by-step workflow checklist and automate the full deployment pipeline until everything passes"
    )
    assert r_rel.model_id == "mbowagpt-relentless"
    assert r_rel.specialist_key == "relentless"

    # Short follow-up preserves active specialist
    r_follow = classify_mbowagpt_route("try again", active_role="mbowagpt-cybertrunk")
    assert r_follow.model_id == "mbowagpt-cybertrunk"

    # Explicit specialist choice overrides heuristic
    r_explicit = classify_mbowagpt_route(
        "Say hello",
        requested_model="mbowagpt-relentless",
    )
    assert r_explicit.model_id == "mbowagpt-relentless"


def test_compact_local_prompt_and_offline_tool_filtering():
    from agent.mbowagpt_router import (
        build_compact_local_system_prompt,
        filter_tools_for_local_runtime,
    )

    prompt = build_compact_local_system_prompt("mbowagpt-cybertrunk", offline=True)
    assert "TchuekaM" in prompt
    assert "Hermes" not in prompt
    assert "OFFLINE" in prompt
    assert len(prompt) < 2500

    sample_tools = [
        {"type": "function", "function": {"name": "web_search", "description": "Search the web", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "browser_navigate", "description": "Browse web", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "read_document", "description": "Read PDF DOCX XLSX offline " * 20, "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path " * 20}}}}},
        {"type": "function", "function": {"name": "terminal", "description": "Run local shell commands", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "memory", "description": "Store persistent memory", "parameters": {"type": "object", "properties": {}}}},
    ]
    offline_filtered = filter_tools_for_local_runtime(
        sample_tools, offline=True, role_id="mbowagpt-cybertrunk", max_tools=5
    )
    names = [t["function"]["name"] for t in offline_filtered]
    assert "web_search" not in names
    assert "browser_navigate" not in names
    assert "read_document" in names
    assert "terminal" in names
    # Verify schema descriptions were compacted
    read_doc_schema = next(t for t in offline_filtered if t["function"]["name"] == "read_document")
    assert len(read_doc_schema["function"]["description"]) <= 165


def test_provider_rejects_reasoning_content_for_local_and_strict_providers():
    from agent.agent_runtime_helpers import provider_rejects_reasoning_content

    local_agent = SimpleNamespace(
        provider="mbowagpt",
        base_url="http://127.0.0.1:18080/v1",
        _needs_thinking_reasoning_pad=lambda: False,
    )
    assert provider_rejects_reasoning_content(local_agent) is True

    loopback_agent = SimpleNamespace(
        provider="custom",
        base_url="http://localhost:11434/v1",
        _needs_thinking_reasoning_pad=lambda: False,
    )
    assert provider_rejects_reasoning_content(loopback_agent) is True


def test_build_assistant_message_skips_reasoning_content_on_strict_providers():
    from agent.chat_completion_helpers import build_assistant_message

    agent = SimpleNamespace(
        verbose_logging=False,
        reasoning_callback=None,
        stream_delta_callback=None,
        _stream_callback=None,
        model="mbowagpt",
        provider="mbowagpt",
        _extract_reasoning=lambda m: "secret thought",
        _strip_think_blocks=lambda s: s,
        _provider_rejects_reasoning_content=lambda: True,
    )
    msg_obj = SimpleNamespace(content="Hello from TchuekaM", tool_calls=None)
    built = build_assistant_message(agent, msg_obj, "stop")
    assert built["role"] == "assistant"
    assert built["content"] == "Hello from TchuekaM"
    assert "reasoning_content" not in built
    assert built["reasoning"] == "secret thought"


def test_local_runtime_manager_discovers_temp_weights_and_binary(tmp_path, monkeypatch):
    from agent.local_runtime import LocalRuntimeManager

    local_dir = tmp_path / "local-ai"
    (local_dir / "runtime").mkdir(parents=True)
    (local_dir / "models").mkdir(parents=True)

    exe_name = "llama-server.exe" if __import__("os").name == "nt" else "llama-server"
    fake_exe = local_dir / "runtime" / exe_name
    fake_exe.write_bytes(b"MZ" + b"\x00" * 64)

    fake_gguf = local_dir / "models" / "Qwen3-1.7B-Q4_K_M.gguf"
    fake_gguf.write_bytes(b"GGUF" + b"\x00" * 1_500_000)

    monkeypatch.setenv("HERMES_LOCAL_AI_DIR", str(local_dir))
    mgr = LocalRuntimeManager()
    assert mgr.discover_binary() == fake_exe
    resolved = mgr.resolve_model_weights("mbowagpt")
    assert resolved == fake_gguf
    status = mgr.get_status()
    assert status["ready"] is True
    assert status["hardware"]["ram_gb"] > 0
