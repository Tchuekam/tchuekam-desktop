"""Shared runtime provider resolution for CLI, gateway, cron, and helpers."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from hermes_cli import auth as auth_mod
from agent.credential_pool import CredentialPool, PooledCredential, get_custom_provider_pool_key, load_pool
from hermes_cli.auth import (
    AuthError,
    DEFAULT_CODEX_BASE_URL,
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_XAI_OAUTH_BASE_URL,
    PROVIDER_REGISTRY,
    _agent_key_is_usable,
    format_auth_error,
    resolve_provider,
    resolve_nous_runtime_credentials,
    resolve_codex_runtime_credentials,
    resolve_xai_oauth_runtime_credentials,
    resolve_qwen_runtime_credentials,
    resolve_gemini_oauth_runtime_credentials,
    resolve_api_key_provider_credentials,
    resolve_external_process_provider_credentials,
    has_usable_secret,
)
from hermes_cli.config import get_compatible_custom_providers, load_config
from hermes_constants import OPENROUTER_BASE_URL
from utils import base_url_host_matches, base_url_hostname


def _normalize_custom_provider_name(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _loopback_hostname(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    return h in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _config_base_url_trustworthy_for_bare_custom(cfg_base_url: str, cfg_provider: str) -> bool:
    """Decide whether ``model.base_url`` may back bare ``custom`` runtime resolution.

    GitHub #14676: the model picker can select Custom while ``model.provider`` still reflects a
    previous provider. Reject non-loopback URLs unless the YAML provider is already ``custom``
    (or one of the local-server aliases that resolve to ``custom`` — ollama, vllm, llamacpp, …),
    so a stale OpenRouter/Z.ai base_url cannot hijack local ``custom`` sessions.
    """
    cfg_provider_norm = (cfg_provider or "").strip().lower()
    bu = (cfg_base_url or "").strip()
    if not bu:
        return False
    if cfg_provider_norm == "custom":
        return True
    # GitHub #27132: provider aliases that resolve to "custom" at runtime
    # (ollama, vllm, llamacpp, …) should be trusted the same way "custom"
    # is, otherwise a legit LAN/WireGuard ollama endpoint silently falls
    # through to OpenRouter.
    try:
        from hermes_cli.auth import resolve_provider as _resolve_provider

        if _resolve_provider(cfg_provider_norm) == "custom":
            return True
    except Exception:
        pass
    if base_url_host_matches(bu, "openrouter.ai"):
        return False
    return _loopback_hostname(base_url_hostname(bu))


def _detect_api_mode_for_url(base_url: str) -> Optional[str]:
    """Auto-detect api_mode from the resolved base URL.

    - Direct api.openai.com endpoints need the Responses API for GPT-5.x
      tool calls with reasoning (chat/completions returns 400).
    - Third-party Anthropic-compatible gateways (MiniMax, Zhipu GLM,
      LiteLLM proxies, etc.) conventionally expose the native Anthropic
      protocol under a ``/anthropic`` suffix — treat those as
      ``anthropic_messages`` transport instead of the default
      ``chat_completions``.
    - Kimi Code's ``api.kimi.com/coding`` endpoint also speaks the
      Anthropic Messages protocol (the /coding route accepts Claude
      Code's native request shape).
    """
    normalized = (base_url or "").strip().lower().rstrip("/")
    hostname = base_url_hostname(base_url)
    if hostname == "api.x.ai":
        return "codex_responses"
    if hostname == "api.openai.com":
        return "codex_responses"
    if normalized.endswith("/anthropic"):
        return "anthropic_messages"
    if hostname == "api.kimi.com" and "/coding" in normalized:
        return "anthropic_messages"
    return None


def _host_derived_api_key(base_url: str) -> str:
    """Look up `<VENDOR>_API_KEY` in the env, derived from the base URL host.

    Examples:
        https://api.deepseek.com/v1   → DEEPSEEK_API_KEY
        https://api.groq.com/openai/v1 → GROQ_API_KEY
        https://api.mistral.ai/v1     → MISTRAL_API_KEY
        https://generativelanguage.googleapis.com/v1beta/openai/ → GOOGLEAPIS_API_KEY

    Returns the env value (stripped) or "". Never returns env vars whose names
    are already explicitly checked elsewhere — those are handled by their own
    host-gated paths (OPENAI/OPENROUTER/OLLAMA).

    The vendor label is the *registrable* portion of the hostname: strip
    ``api.`` / ``www.`` prefixes, then take the second-to-last label
    (``api.deepseek.com`` → ``deepseek``). Falls back to "" for hostnames
    that don't yield a usable vendor label (IPs, loopback, single-label
    hosts).
    """
    hostname = base_url_hostname(base_url)
    if not hostname:
        return ""
    # Reject IPv4 / IPv6 / loopback — no meaningful vendor label.
    if any(ch.isdigit() for ch in hostname.split(".")[-1]):
        # Last label starts with a digit → likely IP. (TLDs are never numeric.)
        return ""
    if hostname in ("localhost",) or ":" in hostname:
        return ""
    labels = [lbl for lbl in hostname.split(".") if lbl]
    # Strip common API/CDN prefixes.
    while labels and labels[0] in ("api", "www"):
        labels.pop(0)
    if len(labels) < 2:
        return ""
    # Take the *registrable* label (second-to-last). For typical provider
    # hosts this is what users intuitively call "the vendor":
    #   deepseek.com               → labels[-2] = "deepseek"  ✓
    #   api.groq.com → groq.com    → labels[-2] = "groq"      ✓
    #   api.mistral.ai             → labels[-2] = "mistral"   ✓
    # Crucially, lookalike hosts pick the ATTACKER's label, not the spoofed
    # vendor:
    #   api.deepseek.com.attacker.test → labels[-2] = "attacker"
    # so DEEPSEEK_API_KEY stays put and the chain falls through to
    # no-key-required. This mirrors how `base_url_host_matches` resists the
    # same lookalike attack for explicit hosts.
    vendor = labels[-2]
    # Sanitize to env var charset: A-Z, 0-9, underscore.
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in vendor).upper()
    if not sanitized or not sanitized[0].isalpha():
        return ""
    # Don't re-derive env vars already handled by explicit host-gated paths.
    if sanitized in ("OPENAI", "OPENROUTER", "OLLAMA"):
        return ""
    env_name = f"{sanitized}_API_KEY"
    return (os.getenv(env_name, "") or "").strip()


def _auto_detect_local_model(base_url: str) -> str:
    """Query a local server for its model name when only one model is loaded."""
    if not base_url:
        return ""
    try:
        import requests
        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        resp = requests.get(url + "/models", timeout=5)
        if resp.ok:
            models = resp.json().get("data", [])
            if len(models) == 1:
                model_id = models[0].get("id", "")
                if model_id:
                    return model_id
    except Exception as exc:
        # Log instead of silently swallowing — aids debugging when
        # local model auto-detection fails unexpectedly.
        logger.debug("Auto-detect model from %s failed: %s", base_url, exc)
    return ""


def _get_model_config() -> Dict[str, Any]:
    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        cfg = dict(model_cfg)
        # Accept "model" as alias for "default" (users intuitively write model.model)
        if not cfg.get("default") and cfg.get("model"):
            cfg["default"] = cfg["model"]
        default = (cfg.get("default") or "").strip()
        base_url = (cfg.get("base_url") or "").strip()
        is_local = "localhost" in base_url or "127.0.0.1" in base_url
        is_fallback = not default
        if is_local and is_fallback and base_url:
            detected = _auto_detect_local_model(base_url)
            if detected:
                cfg["default"] = detected
        return cfg
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def _provider_supports_explicit_api_mode(provider: Optional[str], configured_provider: Optional[str] = None) -> bool:
    """Check whether a persisted api_mode should be honored for a given provider.

    Prevents stale api_mode from a previous provider leaking into a
    different one after a model/provider switch.  Only applies the
    persisted mode when the config's provider matches the runtime
    provider (or when no configured provider is recorded).
    """
    normalized_provider = (provider or "").strip().lower()
    normalized_configured = (configured_provider or "").strip().lower()
    if not normalized_configured:
        return True
    if normalized_provider == "custom":
        return normalized_configured == "custom" or normalized_configured.startswith("custom:")
    return normalized_configured == normalized_provider


def _copilot_runtime_api_mode(model_cfg: Dict[str, Any], api_key: str) -> str:
    configured_provider = str(model_cfg.get("provider") or "").strip().lower()
    configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
    if configured_mode and _provider_supports_explicit_api_mode("copilot", configured_provider):
        return configured_mode

    model_name = str(model_cfg.get("default") or "").strip()
    if not model_name:
        return "chat_completions"

    try:
        from hermes_cli.models import copilot_model_api_mode

        return copilot_model_api_mode(model_name, api_key=api_key)
    except Exception:
        return "chat_completions"


_VALID_API_MODES = {
    "chat_completions",
    "codex_responses",
    "anthropic_messages",
    "bedrock_converse",
    # Optional opt-in: hand the entire turn to a `codex app-server` subprocess
    # so terminal/file-ops/patching/sandboxing run inside Codex's own runtime
    # instead of Hermes' tool dispatch. Gated behind config key
    # `model.openai_runtime == "codex_app_server"` AND provider in
    # {"openai", "openai-codex"}. Default is unchanged.
    "codex_app_server",
}


def _parse_api_mode(raw: Any) -> Optional[str]:
    """Validate an api_mode value from config. Returns None if invalid."""
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in _VALID_API_MODES:
            return normalized
    return None


def _maybe_apply_codex_app_server_runtime(
    *,
    provider: str,
    api_mode: str,
    model_cfg: Optional[Dict[str, Any]],
) -> str:
    """Optional opt-in: rewrite api_mode → "codex_app_server" for OpenAI/Codex
    providers when the user has explicitly enabled that runtime via
    `model.openai_runtime: codex_app_server` in config.yaml.

    Default behavior is preserved: when the key is unset, "auto", or empty,
    this function is a no-op. Only providers in {"openai", "openai-codex"}
    are eligible — other providers (anthropic, openrouter, etc.) cannot be
    rerouted through codex.

    Returns the (possibly-rewritten) api_mode."""
    if not model_cfg:
        return api_mode
    if provider not in {"openai", "openai-codex"}:
        return api_mode
    runtime = str(model_cfg.get("openai_runtime") or "").strip().lower()
    if runtime == "codex_app_server":
        return "codex_app_server"
    return api_mode


def _resolve_runtime_from_pool_entry(
    *,
    provider: str,
    entry: PooledCredential,
    requested_provider: str,
    model_cfg: Optional[Dict[str, Any]] = None,
    pool: Optional[CredentialPool] = None,
    target_model: Optional[str] = None,
) -> Dict[str, Any]:
    model_cfg = model_cfg or _get_model_config()
    # When the caller is resolving for a specific target model (e.g. a /model
    # mid-session switch), prefer that over the persisted model.default. This
    # prevents api_mode being computed from a stale config default that no
    # longer matches the model actually being used — the bug that caused
    # opencode-zen /v1 to be stripped for chat_completions requests when
    # config.default was still a Claude model.
    effective_model = (target_model or model_cfg.get("default") or "")
    base_url = (getattr(entry, "runtime_base_url", None) or getattr(entry, "base_url", None) or "").rstrip("/")
    api_key = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "")
    api_mode = "chat_completions"
    if provider == "openai-codex":
        api_mode = "codex_responses"
        base_url = base_url or DEFAULT_CODEX_BASE_URL
    elif provider == "xai-oauth":
        api_mode = "codex_responses"
        base_url = base_url or DEFAULT_XAI_OAUTH_BASE_URL
    elif provider == "qwen-oauth":
        api_mode = "chat_completions"
        base_url = base_url or DEFAULT_QWEN_BASE_URL
    elif provider == "google-gemini-cli":
        api_mode = "chat_completions"
        base_url = base_url or "cloudcode-pa://google"
    elif provider == "minimax-oauth":
        # MiniMax OAuth tokens are valid only against the Anthropic Messages
        # compatible endpoint. Do not honor stale model.api_mode values from a
        # prior OpenAI-compatible provider, or the client will hit
        # /chat/completions under /anthropic and receive a bare nginx 404.
        api_mode = "anthropic_messages"
        pconfig = PROVIDER_REGISTRY.get(provider)
        base_url = base_url or (pconfig.inference_base_url if pconfig else "")
    elif provider == "anthropic":
        api_mode = "anthropic_messages"
        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
        cfg_base_url = ""
        if cfg_provider == "anthropic":
            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
        base_url = cfg_base_url or base_url or "https://api.anthropic.com"
    elif provider == "openrouter":
        base_url = base_url or OPENROUTER_BASE_URL
    elif provider == "xai":
        api_mode = "codex_responses"
    elif provider == "nous":
        api_mode = "chat_completions"
    elif provider == "copilot":
        api_mode = _copilot_runtime_api_mode(model_cfg, getattr(entry, "runtime_api_key", ""))
        base_url = base_url or PROVIDER_REGISTRY["copilot"].inference_base_url
    elif provider == "azure-foundry":
        # Azure Foundry: read api_mode and base_url from config
        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
        if cfg_provider == "azure-foundry":
            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
            if cfg_base_url:
                base_url = cfg_base_url
            configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
            if configured_mode:
                api_mode = configured_mode
        # Model-family inference for GPT-5.x / codex / o1-o4: Azure rejects
        # /chat/completions on these with 400 "operation unsupported" — see
        # azure_foundry_model_api_mode() for rationale.  Skip when the user
        # explicitly picked anthropic_messages (Anthropic-style endpoint).
        if effective_model and api_mode != "anthropic_messages":
            try:
                from hermes_cli.models import azure_foundry_model_api_mode

                inferred = azure_foundry_model_api_mode(effective_model)
            except Exception:
                inferred = None
            if inferred:
                api_mode = inferred
        # For Anthropic-style endpoints, strip /v1 suffix
        if api_mode == "anthropic_messages":
            base_url = re.sub(r"/v1/?$", "", base_url)
    else:
        configured_provider = str(model_cfg.get("provider") or "").strip().lower()
        # Honour model.base_url from config.yaml when the configured provider
        # matches this provider — same pattern as the Anthropic branch above.
        # Only override when the pool entry has no explicit base_url (i.e. it
        # fell back to the hardcoded default).  Env var overrides win (#6039).
        pconfig = PROVIDER_REGISTRY.get(provider)
        pool_url_is_default = pconfig and base_url.rstrip("/") == pconfig.inference_base_url.rstrip("/")
        if configured_provider == provider and pool_url_is_default:
            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
            if cfg_base_url:
                base_url = cfg_base_url
        configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
        if provider in {"opencode-zen", "opencode-go"}:
            # Re-derive api_mode from the effective model rather than the
            # persisted api_mode: the opencode providers serve both
            # anthropic_messages and chat_completions models, so the previous
            # session's mode must not leak across /model switches.
            # Refs #16878.
            from hermes_cli.models import opencode_model_api_mode
            api_mode = opencode_model_api_mode(provider, effective_model)
        elif configured_mode and _provider_supports_explicit_api_mode(provider, configured_provider):
            api_mode = configured_mode
        else:
            # Auto-detect Anthropic-compatible endpoints (/anthropic suffix,
            # Kimi /coding, api.openai.com → codex_responses, api.x.ai →
            # codex_responses).
            detected = _detect_api_mode_for_url(base_url)
            if detected:
                api_mode = detected

    # OpenCode base URLs end with /v1 for OpenAI-compatible models, but the
    # Anthropic SDK prepends its own /v1/messages to the base_url.  Strip the
    # trailing /v1 so the SDK constructs the correct path (e.g.
    # https://opencode.ai/zen/go/v1/messages instead of .../v1/v1/messages).
    if api_mode == "anthropic_messages" and provider in {"opencode-zen", "opencode-go"}:
        base_url = re.sub(r"/v1/?$", "", base_url)

    # Optional opt-in: route OpenAI/Codex turns through `codex app-server`.
    # Inert when `model.openai_runtime` is unset or "auto".
    api_mode = _maybe_apply_codex_app_server_runtime(
        provider=provider, api_mode=api_mode, model_cfg=model_cfg
    )

    return {
        "provider": provider,
        "api_mode": api_mode,
        "base_url": base_url,
        "api_key": api_key,
        "source": getattr(entry, "source", "pool"),
        "credential_pool": pool,
        "requested_provider": requested_provider,
    }


def resolve_requested_provider(requested: Optional[str] = None) -> str:
    """Resolve provider request from explicit arg, config, then env."""
    if requested and requested.strip():
        return requested.strip().lower()

    model_cfg = _get_model_config()
    cfg_provider = model_cfg.get("provider")
    if isinstance(cfg_provider, str) and cfg_provider.strip():
        return cfg_provider.strip().lower()

    # Prefer the persisted config selection over any stale shell/.env
    # provider override so chat uses the endpoint the user last saved.
    env_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip().lower()
    if env_provider:
        return env_provider

    return "auto"


def _try_resolve_from_custom_pool(
    base_url: str,
    provider_label: str,
    api_mode_override: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Check if a credential pool exists for a custom endpoint and return a runtime dict if so."""
    pool_key = get_custom_provider_pool_key(base_url, provider_name=provider_name)
    if not pool_key:
        return None
    try:
        pool = load_pool(pool_key)
        if not pool.has_credentials():
            return None
        entry = pool.select()
        if entry is None:
            return None
        pool_api_key = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "")
        if not pool_api_key:
            return None
        return {
            "provider": provider_label,
            "api_mode": api_mode_override or _detect_api_mode_for_url(base_url) or "chat_completions",
            "base_url": base_url,
            "api_key": pool_api_key,
            "source": f"pool:{pool_key}",
            "credential_pool": pool,
        }
    except Exception:
        return None


def _get_named_custom_provider(requested_provider: str) -> Optional[Dict[str, Any]]:
    requested_norm = _normalize_custom_provider_name(requested_provider or "")
    if not requested_norm or requested_norm == "custom":
        return None

    # Raw names should only map to custom providers when they are not already
    # valid built-in providers or aliases. Explicit menu keys like
    # ``custom:local`` always target the saved custom provider.
    if requested_norm == "auto":
        return None
    if not requested_norm.startswith("custom:"):
        try:
            canonical = auth_mod.resolve_provider(requested_norm)
        except AuthError:
            pass
        else:
            # A user-declared ``custom_providers`` entry whose name matches
            # only an *alias* (``kimi`` → built-in ``kimi-coding``) is the
            # user's intended target — alias rewriting would otherwise hijack
            # the request.  We only defer to the built-in when the raw name is
            # the canonical provider itself (``nous``, ``openrouter``, …) so
            # accidentally shadowing a canonical provider still resolves to
            # the built-in. See tests/hermes_cli/test_runtime_provider_resolution.py
            # ``test_named_custom_provider_does_not_shadow_builtin_provider``.
            if (canonical or "").strip().lower() == requested_norm:
                return None

    config = load_config()
    
    # First check providers: dict (new-style user-defined providers)
    providers = config.get("providers")
    if isinstance(providers, dict):
        for ep_name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            # Match exact name or normalized name
            name_norm = _normalize_custom_provider_name(ep_name)
            # Resolve the API key from the env var name stored in key_env
            key_env = str(entry.get("key_env", "") or "").strip()
            resolved_api_key = os.getenv(key_env, "").strip() if key_env else ""
            # Fall back to inline api_key when key_env is absent or unresolvable
            if not resolved_api_key:
                resolved_api_key = str(entry.get("api_key", "") or "").strip()

            if requested_norm in {ep_name, name_norm, f"custom:{name_norm}"}:
                # Found match by provider key
                base_url = entry.get("api") or entry.get("url") or entry.get("base_url") or ""
                if base_url:
                    result = {
                        "name": entry.get("name", ep_name),
                        "base_url": base_url.strip(),
                        "api_key": resolved_api_key,
                        "model": entry.get("default_model", ""),
                    }
                    extra_body = entry.get("extra_body")
                    if isinstance(extra_body, dict):
                        result["extra_body"] = dict(extra_body)
                    # The v11→v12 migration writes the API mode under the new
                    # ``transport`` field, but hand-edited configs may still
                    # use the legacy ``api_mode`` spelling.  Accept both —
                    # the runtime normaliser ``_normalize_custom_provider_entry``
                    # already does, so without this lift every migrated config
                    # silently downgrades codex_responses / anthropic_messages
                    # providers to chat_completions in the resolved runtime.
                    api_mode = _parse_api_mode(entry.get("api_mode") or entry.get("transport"))
                    if api_mode:
                        result["api_mode"] = api_mode
                    return result
            # Also check the 'name' field if present
            display_name = entry.get("name", "")
            if display_name:
                display_norm = _normalize_custom_provider_name(display_name)
                if requested_norm in {display_name, display_norm, f"custom:{display_norm}"}:
                    # Found match by display name
                    base_url = entry.get("api") or entry.get("url") or entry.get("base_url") or ""
                    if base_url:
                        result = {
                            "name": display_name,
                            "base_url": base_url.strip(),
                            "api_key": resolved_api_key,
                            "model": entry.get("default_model", ""),
                        }
                        extra_body = entry.get("extra_body")
                        if isinstance(extra_body, dict):
                            result["extra_body"] = dict(extra_body)
                        api_mode = _parse_api_mode(entry.get("api_mode") or entry.get("transport"))
                        if api_mode:
                            result["api_mode"] = api_mode
                        return result

    # Fall back to custom_providers: list (legacy format)
    custom_providers = config.get("custom_providers")
    if isinstance(custom_providers, dict):
        logger.warning(
            "custom_providers in config.yaml is a dict, not a list. "
            "Each entry must be prefixed with '-' in YAML. "
            "Run 'hermes doctor' for details."
        )
        return None

    custom_providers = get_compatible_custom_providers(config)
    if not custom_providers:
        return None

    for entry in custom_providers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        base_url = entry.get("base_url")
        if not isinstance(name, str) or not isinstance(base_url, str):
            continue
        name_norm = _normalize_custom_provider_name(name)
        menu_key = f"custom:{name_norm}"
        provider_key = str(entry.get("provider_key", "") or "").strip()
        provider_key_norm = _normalize_custom_provider_name(provider_key) if provider_key else ""
        provider_menu_key = f"custom:{provider_key_norm}" if provider_key_norm else ""
        if requested_norm not in {name_norm, menu_key, provider_key_norm, provider_menu_key}:
            continue
        result = {
            "name": name.strip(),
            "base_url": base_url.strip(),
            "api_key": str(entry.get("api_key", "") or "").strip(),
        }
        key_env = str(entry.get("key_env", "") or "").strip()
        if key_env:
            result["key_env"] = key_env
        if provider_key:
            result["provider_key"] = provider_key
        extra_body = entry.get("extra_body")
        if isinstance(extra_body, dict):
            result["extra_body"] = dict(extra_body)
        api_mode = _parse_api_mode(entry.get("api_mode"))
        if api_mode:
            result["api_mode"] = api_mode
        model_name = str(entry.get("model", "") or "").strip()
        if model_name:
            result["model"] = model_name
        return result

    return None


def _custom_provider_request_overrides(custom_provider: Dict[str, Any]) -> Dict[str, Any]:
    extra_body = custom_provider.get("extra_body")
    if not isinstance(extra_body, dict) or not extra_body:
        return {}
    return {"extra_body": dict(extra_body)}


def _resolve_named_custom_runtime(
    *,
    requested_provider: str,
    explicit_api_key: Optional[str] = None,
    explicit_base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    # Bare `provider="custom"` with an explicit base_url (e.g. propagated
    # from a `model_aliases:` direct-alias resolution) — build a runtime
    # directly so the alias's base_url actually takes effect.
    #
    # GitHub #27132: provider aliases that resolve to "custom" at runtime
    # (ollama, vllm, llamacpp, …) are treated identically here, so a YAML
    # `provider: ollama` with a LAN/WireGuard `base_url` doesn't silently
    # fall through to OpenRouter.
    requested_norm = (requested_provider or "").strip().lower()
    if requested_norm and requested_norm != "custom":
        try:
            from hermes_cli.auth import resolve_provider as _resolve_provider

            if _resolve_provider(requested_norm) == "custom":
                requested_norm = "custom"
        except Exception:
            pass
    if requested_norm == "custom" and explicit_base_url:
        base_url = explicit_base_url.strip().rstrip("/")
        # Check credential pool first — mirrors the named-custom-provider path
        # so bare `provider: custom` with a configured custom_providers entry
        # also gets its api_key from the pool instead of env var fallbacks.
        pool_result = _try_resolve_from_custom_pool(base_url, "custom", None)
        if pool_result:
            pool_result["source"] = "direct-alias"
            return pool_result
        _da_is_openai_url   = base_url_host_matches(base_url, "openai.com") or base_url_host_matches(base_url, "openai.azure.com")
        _da_is_openrouter   = base_url_host_matches(base_url, "openrouter.ai")
        api_key_candidates = [
            (explicit_api_key or "").strip(),
            # Gate env key fallbacks on authoritative hosts (#28660)
            (os.getenv("OPENAI_API_KEY", "").strip()     if _da_is_openai_url else ""),
            (os.getenv("OPENROUTER_API_KEY", "").strip() if _da_is_openrouter  else ""),
            # Bonus (#28660): derive `<VENDOR>_API_KEY` from the host so users
            # who set DEEPSEEK_API_KEY / GROQ_API_KEY / MISTRAL_API_KEY get the
            # intuitive match without configuring `custom_providers` first.
            _host_derived_api_key(base_url),
        ]
        api_key = next(
            (c for c in api_key_candidates if has_usable_secret(c)),
            "",
        ) or "no-key-required"
        return {
            "provider": "custom",
            "api_mode": _detect_api_mode_for_url(base_url) or "chat_completions",
            "base_url": base_url,
            "api_key": api_key,
            "source": "direct-alias",
            "requested_provider": requested_provider,
        }

    custom_provider = _get_named_custom_provider(requested_provider)
    if not custom_provider:
        return None

    base_url = (
        (explicit_base_url or "").strip()
        or custom_provider.get("base_url", "")
    ).rstrip("/")
    if not base_url:
        return None

    # Check if a credential pool exists for this custom endpoint
    pool_result = _try_resolve_from_custom_pool(base_url, "custom", custom_provider.get("api_mode"), provider_name=custom_provider.get("name"))
    if pool_result:
        # Propagate the model name even when using pooled credentials —
        # the pool doesn't know about the custom_providers model field.
        model_name = custom_provider.get("model")
        if model_name:
            pool_result["model"] = model_name
        request_overrides = _custom_provider_request_overrides(custom_provider)
        if request_overrides:
            pool_result["request_overrides"] = {
                **dict(pool_result.get("request_overrides") or {}),
                **request_overrides,
            }
        return pool_result

    _cp_is_openai_url   = base_url_host_matches(base_url, "openai.com") or base_url_host_matches(base_url, "openai.azure.com")
    _cp_is_openrouter   = base_url_host_matches(base_url, "openrouter.ai")
    api_key_candidates = [
        (explicit_api_key or "").strip(),
        str(custom_provider.get("api_key", "") or "").strip(),
        os.getenv(str(custom_provider.get("key_env", "") or "").strip(), "").strip(),
        # Gate provider env keys on their authoritative hosts — sending
        # OPENAI_API_KEY to a local-llm endpoint leaks credentials (#28660).
        (os.getenv("OPENAI_API_KEY", "").strip()     if _cp_is_openai_url  else ""),
        (os.getenv("OPENROUTER_API_KEY", "").strip() if _cp_is_openrouter  else ""),
        # Bonus (#28660): derive `<VENDOR>_API_KEY` from the host as a final
        # fallback when key_env wasn't set explicitly.
        _host_derived_api_key(base_url),
    ]
    api_key = next((candidate for candidate in api_key_candidates if has_usable_secret(candidate)), "")

    result = {
        "provider": "custom",
        "api_mode": custom_provider.get("api_mode")
        or _detect_api_mode_for_url(base_url)
        or "chat_completions",
        "base_url": base_url,
        "api_key": api_key or "no-key-required",
        "source": f"custom_provider:{custom_provider.get('name', requested_provider)}",
    }
    # Propagate the model name so callers can override self.model when the
    # provider name differs from the actual model string the API expects.
    if custom_provider.get("model"):
        result["model"] = custom_provider["model"]
    request_overrides = _custom_provider_request_overrides(custom_provider)
    if request_overrides:
        result["request_overrides"] = request_overrides
    return result


def _resolve_openrouter_runtime(
    *,
    requested_provider: str,
    explicit_api_key: Optional[str] = None,
    explicit_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    model_cfg = _get_model_config()
    cfg_base_url = model_cfg.get("base_url") if isinstance(model_cfg.get("base_url"), str) else ""
    cfg_provider = model_cfg.get("provider") if isinstance(model_cfg.get("provider"), str) else ""
    cfg_api_key = ""
    for k in ("api_key", "api"):
        v = model_cfg.get(k)
        if isinstance(v, str) and v.strip():
            cfg_api_key = v.strip()
            break
    requested_norm = (requested_provider or "").strip().lower()
    cfg_provider = cfg_provider.strip().lower()
    # GitHub #27132: provider aliases that resolve to "custom" (ollama,
    # vllm, llamacpp, …) follow the same base_url trust + routing rules
    # as a bare `provider: custom`. Normalising here keeps every check
    # below — `requested_norm == "custom"`, the trust check, the pool
    # gate up the stack — alias-aware without duplicating the alias map.
    if requested_norm and requested_norm != "custom":
        try:
            from hermes_cli.auth import resolve_provider as _resolve_provider

            if _resolve_provider(requested_norm) == "custom":
                requested_norm = "custom"
        except Exception:
            pass

    env_openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "").strip()
    env_custom_base_url = os.getenv("CUSTOM_BASE_URL", "").strip()

    # Use config base_url when available and the provider context matches.
    # OPENAI_BASE_URL env var is no longer consulted — config.yaml is
    # the single source of truth for endpoint URLs.
    use_config_base_url = False
    if cfg_base_url.strip() and not explicit_base_url:
        if requested_norm == "auto":
            if not cfg_provider or cfg_provider == "auto":
                use_config_base_url = True
        elif requested_norm == "custom" and _config_base_url_trustworthy_for_bare_custom(
            cfg_base_url, cfg_provider
        ):
            use_config_base_url = True

    base_url = (
        (explicit_base_url or "").strip()
        or env_custom_base_url
        or (cfg_base_url.strip() if use_config_base_url else "")
        or env_openrouter_base_url
        or OPENROUTER_BASE_URL
    ).rstrip("/")

    # Choose API key based on whether the resolved base_url targets OpenRouter.
    # When hitting OpenRouter, prefer OPENROUTER_API_KEY (issue #289).
    # When hitting a custom endpoint (e.g. Z.ai, local LLM), prefer
    # OPENAI_API_KEY so the OpenRouter key doesn't leak to an unrelated
    # provider (issues #420, #560).
    _is_openrouter_url = base_url_host_matches(base_url, "openrouter.ai")
    # Also treat explicitly-configured OpenRouter mirrors/proxies as OpenRouter
    # for key selection — if the user set OPENROUTER_BASE_URL or requested
    # provider=openrouter explicitly, OPENROUTER_API_KEY should still be used.
    _is_openrouter_context = _is_openrouter_url or (
        requested_norm == "openrouter"
        and (env_openrouter_base_url or base_url == env_openrouter_base_url)
        and base_url == (env_openrouter_base_url or "").rstrip("/")
    )
    if _is_openrouter_context:
        api_key_candidates = [
            explicit_api_key,
            os.getenv("OPENROUTER_API_KEY"),
            os.getenv("OPENAI_API_KEY"),
        ]
    else:
        # Custom endpoint: use api_key from config when using config base_url (#1760).
        # When the endpoint is Ollama Cloud, check OLLAMA_API_KEY — it's
        # the canonical env var for ollama.com authentication. Match on
        # HOST, not substring — a custom base_url whose path contains
        # "ollama.com" (e.g. http://127.0.0.1/ollama.com/v1) or whose
        # hostname is a look-alike (ollama.com.attacker.test) must not
        # receive the Ollama credential. See GHSA-76xc-57q6-vm5m.
        _is_ollama_url    = base_url_host_matches(base_url, "ollama.com")
        _is_openai_url    = base_url_host_matches(base_url, "openai.com")
        _is_openai_azure  = base_url_host_matches(base_url, "openai.azure.com")
        # Gate each provider key on its own host — sending OPENAI_API_KEY or
        # OPENROUTER_API_KEY to an unrelated custom endpoint (DeepSeek, Groq,
        # Mistral, …) leaks credentials and causes 401s (issue #28660).
        # Mirrors the OLLAMA_API_KEY host-gate added in GHSA-76xc-57q6-vm5m.
        api_key_candidates = [
            explicit_api_key,
            (cfg_api_key if use_config_base_url else ""),
            (os.getenv("OLLAMA_API_KEY")     if _is_ollama_url                       else ""),
            (os.getenv("OPENAI_API_KEY")     if (_is_openai_url or _is_openai_azure) else ""),
            (os.getenv("OPENROUTER_API_KEY") if _is_openrouter_url                   else ""),
            # Bonus (#28660): derive `<VENDOR>_API_KEY` from the host so users
            # who set DEEPSEEK_API_KEY / GROQ_API_KEY / MISTRAL_API_KEY get the
            # intuitive match. Helper returns "" for IPs/loopback and for env
            # vars already handled by the explicit host-gated paths above.
