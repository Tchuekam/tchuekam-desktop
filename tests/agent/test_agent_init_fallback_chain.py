"""Regression tests: conversation_loop imports _resolve_auto_fallback_chain from agent.agent_init.

The helper used to be defined inside init_agent(), so the function-local import
on the rate-limit fallback path failed with ImportError instead of falling back.
"""
import pytest

_PROVIDER_KEY_VARS = (
    "GROQ_API_KEY",
    "GROQ_API_KEYS",
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEYS",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)


@pytest.fixture
def no_provider_keys(monkeypatch):
    for name in _PROVIDER_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("hermes_cli.config.load_env", lambda: {})


def test_import_from_agent_init_builds_chain_from_configured_keys(no_provider_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")

    from agent.agent_init import _resolve_auto_fallback_chain

    chain = _resolve_auto_fallback_chain("groq")

    assert [entry["provider"] for entry in chain] == ["openai-api", "deepseek"]


def test_primary_provider_is_left_out_of_the_chain(no_provider_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")

    from agent.agent_init import _resolve_auto_fallback_chain

    chain = _resolve_auto_fallback_chain("openai-api")

    assert [entry["provider"] for entry in chain] == ["deepseek"]
