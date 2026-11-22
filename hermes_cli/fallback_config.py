"""Helpers for reading the effective fallback provider chain from config."""

from __future__ import annotations

import json
import os
from typing import Any


_FAST_FALLBACK_PROVIDER_SPECS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("gemini", ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS"), "gemini-2.5-flash"),
    ("gemini", ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS"), "gemini-3.1-flash-lite"),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEYS"), "openai/gpt-oss-120b"),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEYS"), "qwen/qwen3.8-27b"),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEYS"), "openai/gpt-oss-20b"),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEYS"), "llama-3.1-8b-instant"),
    ("anthropic", ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "ANTHROPIC_TOKEN"), "claude-haiku-4-5-20251001"),
    ("openrouter", ("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"), "google/gemini-2.5-flash"),
    ("openai-api", ("OPENAI_API_KEY", "OPENAI_API_KEYS"), "gpt-4o-mini"),
    ("deepseek", ("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"), "deepseek-chat"),
)


def _normalized_base_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/")


def _iter_fallback_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        candidates = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []

    entries: list[dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        provider = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not provider or not model:
            continue

        normalized = dict(entry)
        normalized["provider"] = provider
        normalized["model"] = model

        base_url = _normalized_base_url(entry.get("base_url"))
        if base_url:
            normalized["base_url"] = base_url

        entries.append(normalized)
    return entries


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("provider") or "").strip().lower(),
        str(entry.get("model") or "").strip().lower(),
        _normalized_base_url(entry.get("base_url")).lower(),
    )


def get_fallback_chain(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the effective fallback chain merged across old and new config keys.

    ``fallback_providers`` remains the primary source of truth and keeps its
    order. Legacy ``fallback_model`` entries are appended afterwards unless
    they target the same provider/model/base_url route as an earlier entry.
    The returned list always contains fresh dict copies.
    """

    config = config or {}
    chain: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for key in ("fallback_providers", "fallback_model"):
        for entry in _iter_fallback_entries(config.get(key)):
            identity = _entry_identity(entry)
            if identity in seen:
                continue
            seen.add(identity)
            chain.append(entry)

    return chain


def _parse_env_fallback_entries() -> list[dict[str, Any]]:
    """Parse ``HERMES_FALLBACK_PROVIDERS`` from JSON or comma-separated specs."""
    raw = (os.getenv("HERMES_FALLBACK_PROVIDERS") or "").strip()
    if not raw:
        return []
    if raw.startswith("[") or raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return _iter_fallback_entries(parsed)

    entries: list[dict[str, Any]] = []
    for item in raw.split(","):
        spec = item.strip()
        if not spec or ":" not in spec:
            continue
        provider, model = spec.split(":", 1)
        provider = provider.strip()
        model = model.strip()
        if provider and model:
            entries.append({"provider": provider, "model": model})
    return entries


def resolve_effective_fallback_chain(
    config: dict[str, Any] | None = None,
    *,
    primary_provider: str | None = None,
    primary_model: str | None = None,
    include_local: bool = False,
) -> list[dict[str, Any]]:
    """Build the ordered fast fallback chain from config, env overrides, and live keys."""
    chain: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    norm_primary_provider = (primary_provider or "").strip().lower()
    norm_primary_model = (primary_model or "").strip().lower()

    def _append(entry: dict[str, Any]) -> None:
        identity = _entry_identity(entry)
        if identity in seen:
            return
        if (
            norm_primary_provider
            and identity[0] == norm_primary_provider
            and (not norm_primary_model or identity[1] == norm_primary_model)
        ):
            return
        seen.add(identity)
        chain.append(entry)

    for entry in get_fallback_chain(config):
        _append(entry)
    for entry in _parse_env_fallback_entries():
        _append(entry)

    try:
        from hermes_cli.config import load_env
        env_file = load_env()
    except Exception:
        env_file = {}

    def _has_env_key(var_name: str) -> bool:
        val = (os.getenv(var_name) or env_file.get(var_name) or "").strip()
        return bool(val)

    for provider_id, key_vars, default_model in _FAST_FALLBACK_PROVIDER_SPECS:
        if provider_id == norm_primary_provider and (
            not norm_primary_model
            or norm_primary_model == "gemini-2.5-flash"
            or default_model.strip().lower() == norm_primary_model
        ):
            continue
        if any(_has_env_key(var_name) for var_name in key_vars):
            _append({"provider": provider_id, "model": default_model})

    if include_local and norm_primary_provider != "mbowagpt":
        try:
            from agent.local_runtime import get_local_runtime_manager

            if get_local_runtime_manager().is_local_available():
                _append({"provider": "mbowagpt", "model": "mbowagpt-auto"})
        except Exception:
            pass

    return chain
