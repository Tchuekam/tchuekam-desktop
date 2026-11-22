#!/usr/bin/env python3
"""
Text-to-Speech Tool Module

Built-in TTS providers:
- Edge TTS (default, free, no API key): Microsoft Edge neural voices
- ElevenLabs (premium): High-quality voices, needs ELEVENLABS_API_KEY
- OpenAI TTS: Good quality, needs OPENAI_API_KEY
- MiniMax TTS: High-quality with voice cloning, needs MINIMAX_API_KEY
- Mistral (Voxtral TTS): Multilingual, native Opus, needs MISTRAL_API_KEY
- Google Gemini TTS: Controllable, 30 prebuilt voices, needs GEMINI_API_KEY
- xAI TTS: Grok voices, uses xAI Grok OAuth credentials or XAI_API_KEY
- NeuTTS (local, free, no API key): On-device TTS via neutts
- KittenTTS (local, free, no API key): On-device 25MB model
- Piper (local, free, no API key): OHF-Voice/piper1-gpl neural VITS, 44 languages

Custom command providers:
- Users can declare any number of named providers with ``type: command``
  under ``tts.providers.<name>`` in ``~/.hermes/config.yaml``. Hermes
  writes the input text to a temp file and runs the configured shell
  command, which must produce the audio file at the expected path.
  See the Local Command section of ``website/docs/user-guide/features/tts.md``.

Output formats:
- Opus (.ogg) for Telegram voice bubbles (requires ffmpeg for Edge TTS)
- MP3 (.mp3) for everything else (CLI, Discord, WhatsApp)

Configuration is loaded from ~/.hermes/config.yaml under the 'tts:' key.
The user chooses the provider and voice; the model just sends text.

Usage:
    from tools.tts_tool import text_to_speech_tool, check_tts_requirements

    result = text_to_speech_tool(text="Hello world")
"""

import asyncio
import base64
import datetime
import json
import logging
import os
import queue
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable, Dict, Any, Optional
from urllib.parse import urljoin

from hermes_constants import display_hermes_home

logger = logging.getLogger(__name__)
def get_env_value(name, default=None):
    """Read env values through the live config module.

    Tests may monkeypatch and later restore ``hermes_cli.config.get_env_value``
    before this module is imported. Resolve the helper at call time so TTS does
    not keep a stale imported function for the rest of the test process.
    """
    try:
        from hermes_cli.config import get_env_value as _get_env_value
    except ImportError:
        return os.getenv(name, default)
    value = _get_env_value(name)
    return default if value is None else value
from tools.managed_tool_gateway import resolve_managed_tool_gateway
from tools.tool_backend_helpers import (
    managed_nous_tools_enabled,
    nous_tool_gateway_unavailable_message,
    prefers_gateway,
    resolve_openai_audio_api_key,
)
from tools.xai_http import hermes_xai_user_agent

# ---------------------------------------------------------------------------
# Lazy imports -- providers are imported only when actually used to avoid
# crashing in headless environments (SSH, Docker, WSL, no PortAudio).
# ---------------------------------------------------------------------------

def _import_edge_tts():
    """Lazy import edge_tts. Returns the module or raises ImportError."""
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("tts.edge", prompt=False)
    except ImportError:
        pass
    except Exception as e:
        raise ImportError(str(e))
    import edge_tts
    return edge_tts

def _edge_tts_usable_without_install() -> bool:
    """True if Edge TTS works now, or will be installed when speech is requested.

    ``check_tts_requirements`` is the ``text_to_speech`` tool's ``check_fn``, so
    it runs while the agent's tool list is built, on the first turn of a fresh
    install. It must never run pip: ``_import_edge_tts`` does, and that held the
    first message for ~45s. The install still happens, but at the point speech
    is actually generated (see ``_import_edge_tts`` callers), not here.
    """
    try:
        from tools.lazy_deps import _allow_lazy_installs, is_available
    except ImportError:
        # No lazy-install machinery: only an already-importable package counts.
        import importlib.util

        return importlib.util.find_spec("edge_tts") is not None
    return is_available("tts.edge") or _allow_lazy_installs()


def _import_elevenlabs():
    """Lazy import ElevenLabs client. Returns the class or raises ImportError.

    Calls :func:`tools.lazy_deps.ensure` first so the SDK gets installed on
    demand if the user picked ElevenLabs as their TTS provider but never ran
    the post-setup hook (e.g. enabled it by editing config.yaml directly).
    Raises ``ImportError`` on lazy-install failure so existing callers'
    error-handling paths keep working.
    """
    try:
        from tools.lazy_deps import FeatureUnavailable, ensure
        ensure("tts.elevenlabs", prompt=False)
    except ImportError:
        # lazy_deps module itself missing — fall through to the raw import
        # so older code paths still get a clean ImportError.
        pass
    except Exception as e:  # FeatureUnavailable or any unexpected error
        raise ImportError(str(e))
    from elevenlabs.client import ElevenLabs
    return ElevenLabs

def _import_openai_client():
    """Lazy import OpenAI client. Returns the class or raises ImportError."""
    from openai import OpenAI as OpenAIClient
    return OpenAIClient

def _import_mistral_client():
    """Lazy import Mistral client. Returns the class or raises ImportError.

    Calls :func:`tools.lazy_deps.ensure` first so the ``mistralai`` SDK gets
    installed on demand if the user picked Mistral as their STT/TTS provider
    but never ran the post-setup hook (e.g. enabled it by editing config.yaml
    directly). Mirrors the ElevenLabs lazy-import path.
    """
    try:
        from tools.lazy_deps import ensure
        ensure("tts.mistral", prompt=False)
    except ImportError:
        pass
    except Exception as e:  # FeatureUnavailable or any unexpected error
        raise ImportError(str(e))
    from mistralai.client import Mistral
    return Mistral

def _import_sounddevice():
    """Lazy import sounddevice. Returns the module or raises ImportError/OSError."""
    import sounddevice as sd
    return sd


def _import_kittentts():
    """Lazy import KittenTTS. Returns the class or raises ImportError."""
    from kittentts import KittenTTS
    return KittenTTS


def _import_piper():
    """Lazy import Piper. Returns the PiperVoice class or raises ImportError.

    Piper is an optional, fully-local neural TTS engine (Home Assistant /
    Open Home Foundation). ``pip install piper-tts`` provides cross-platform
    wheels (Linux / macOS / Windows, x86_64 + ARM64) with embedded espeak-ng.
    Voice models (.onnx + .onnx.json) are downloaded on first use.
    """
    from piper import PiperVoice
    return PiperVoice


# ===========================================================================
# Defaults
# ===========================================================================
DEFAULT_PROVIDER = "edge"
DEFAULT_EDGE_VOICE = "en-US-AriaNeural"
DEFAULT_ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_ELEVENLABS_STREAMING_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini-tts"
DEFAULT_KITTENTTS_MODEL = "KittenML/kitten-tts-nano-0.8-int8"  # 25MB
DEFAULT_KITTENTTS_VOICE = "Jasper"
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"  # balanced size/quality
DEFAULT_OPENAI_VOICE = "alloy"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MINIMAX_MODEL = "speech-02-hd"
DEFAULT_MINIMAX_VOICE_ID = "English_expressive_narrator"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1/t2a_v2"
DEFAULT_MISTRAL_TTS_MODEL = "voxtral-mini-tts-2603"
DEFAULT_MISTRAL_TTS_VOICE_ID = "c69964a6-ab8b-4f8a-9465-ec0925096ec8"  # Paul - Neutral
DEFAULT_XAI_VOICE_ID = "eve"
DEFAULT_XAI_LANGUAGE = "en"
DEFAULT_XAI_SAMPLE_RATE = 24000
DEFAULT_XAI_BIT_RATE = 128000
DEFAULT_XAI_AUTO_SPEECH_TAGS = False
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_GEMINI_TTS_VOICE = "Kore"
DEFAULT_GEMINI_TTS_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# PCM output specs for Gemini TTS (fixed by the API)
GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_SAMPLE_WIDTH = 2  # 16-bit PCM (L16)

def _get_default_output_dir() -> str:
    from hermes_constants import get_hermes_dir
    return str(get_hermes_dir("cache/audio", "audio_cache"))

DEFAULT_OUTPUT_DIR = _get_default_output_dir()

# ---------------------------------------------------------------------------
# Per-provider input-character limits (from official provider docs).
# A single global cap was wrong: OpenAI is 4096, xAI is 15k, MiniMax is 10k,
# ElevenLabs is model-dependent (5k / 10k / 30k / 40k), Gemini caps at ~8k
# input tokens.  Users can override any of these via
# ``tts.<provider>.max_text_length`` in config.yaml.
# ---------------------------------------------------------------------------
PROVIDER_MAX_TEXT_LENGTH: Dict[str, int] = {
    "edge": 5000,         # edge-tts practical sync limit
    "openai": 4096,       # https://platform.openai.com/docs/guides/text-to-speech
    "xai": 15000,         # https://docs.x.ai/developers/model-capabilities/audio/text-to-speech
    "minimax": 10000,     # https://platform.minimax.io/docs/api-reference/speech-t2a-http (sync)
    "mistral": 4000,      # conservative; no published per-request cap
    "gemini": 5000,       # Gemini TTS caps at ~8k input tokens / ~655s audio
    "elevenlabs": 10000,  # fallback when model-aware lookup can't resolve (multilingual_v2)
    "neutts": 2000,       # local model, quality falls off on long text
    "kittentts": 2000,    # local 25MB model
    "piper": 5000,        # local VITS model, phoneme-based; practical cap
    "kokoro": 5000,       # local Kokoro-ONNX v1.0 neural voice engine
}

# ElevenLabs caps vary by model_id. https://elevenlabs.io/docs/overview/models
ELEVENLABS_MODEL_MAX_TEXT_LENGTH: Dict[str, int] = {
    "eleven_v3": 5000,
    "eleven_ttv_v3": 5000,
    "eleven_multilingual_v2": 10000,
    "eleven_multilingual_v1": 10000,
    "eleven_english_sts_v2": 10000,
    "eleven_english_sts_v1": 10000,
    "eleven_flash_v2": 30000,
    "eleven_flash_v2_5": 40000,
}

# Final fallback when provider isn't recognised at all.
FALLBACK_MAX_TEXT_LENGTH = 4000

# Back-compat alias. Prefer ``_resolve_max_text_length()`` for new code.
MAX_TEXT_LENGTH = FALLBACK_MAX_TEXT_LENGTH


def _resolve_max_text_length(
    provider: Optional[str],
    tts_config: Optional[Dict[str, Any]] = None,
) -> int:
    """Return the input-character cap for *provider*.

    Resolution order:
      1. ``tts.<provider>.max_text_length`` (user override in config.yaml)
      2. ``tts.providers.<provider>.max_text_length`` for user-declared
         command providers
      3. ElevenLabs model-aware table (keyed on configured ``model_id``)
      4. ``PROVIDER_MAX_TEXT_LENGTH`` default
      5. ``DEFAULT_COMMAND_TTS_MAX_TEXT_LENGTH`` when the provider is a
         command-type user provider without an explicit cap
      6. ``FALLBACK_MAX_TEXT_LENGTH`` (4000)

    Non-positive or non-integer overrides fall through to the default so a
    broken config can't accidentally disable truncation entirely.
    """
    if not provider:
        return FALLBACK_MAX_TEXT_LENGTH
    key = provider.lower().strip()
    cfg = tts_config or {}

    # Built-in-style override at tts.<provider>.max_text_length wins first,
    # matching historical behavior.
    prov_cfg = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
    override = prov_cfg.get("max_text_length") if prov_cfg else None
    if isinstance(override, bool):
        override = None
    if isinstance(override, int) and override > 0:
        return override

    if key == "elevenlabs":
        model_id = (prov_cfg or {}).get("model_id") or DEFAULT_ELEVENLABS_MODEL_ID
        mapped = ELEVENLABS_MODEL_MAX_TEXT_LENGTH.get(str(model_id).strip())
        if mapped:
            return mapped

    if key in PROVIDER_MAX_TEXT_LENGTH:
        return PROVIDER_MAX_TEXT_LENGTH[key]

    # User-declared command provider (under tts.providers.<name>)
    if key not in BUILTIN_TTS_PROVIDERS:
        named = _get_named_provider_config(cfg, key)
        if _is_command_provider_config(named):
            named_override = named.get("max_text_length")
            if isinstance(named_override, bool):
                named_override = None
            if isinstance(named_override, int) and named_override > 0:
                return named_override
            return DEFAULT_COMMAND_TTS_MAX_TEXT_LENGTH

    return FALLBACK_MAX_TEXT_LENGTH


# ===========================================================================
# Config loader -- reads tts: section from ~/.hermes/config.yaml
# ===========================================================================
def _load_tts_config() -> Dict[str, Any]:
    """
    Load TTS configuration from ~/.hermes/config.yaml.

    Returns a dict with provider settings. Falls back to defaults
    for any missing fields.
    """
    try:
        from hermes_cli.config import load_config
        config = load_config()
        return config.get("tts", {})
    except ImportError:
        logger.debug("hermes_cli.config not available, using default TTS config")
        return {}
    except Exception as e:
        logger.warning("Failed to load TTS config: %s", e, exc_info=True)
        return {}


def _get_provider(tts_config: Dict[str, Any]) -> str:
    """Get the configured TTS provider name."""
    return (tts_config.get("provider") or DEFAULT_PROVIDER).lower().strip()


# ===========================================================================
# Custom command providers (type: command under tts.providers.<name>)
# ===========================================================================
#
# Users can declare any number of command-type providers alongside the
# built-ins so they can plug any local CLI (Piper, VoxCPM, Kokoro CLIs,
# custom voice-cloning scripts, etc.) into Hermes without any Python code
# changes. The config shape is::
#
#     tts:
#       provider: piper-en
#       providers:
#         piper-en:
#           type: command
#           command: "piper -m ~/model.onnx -f {output_path} < {input_path}"
#           output_format: wav
#
# Hermes writes the input text to a temp UTF-8 file, runs the command with
# placeholder substitution, and reads the audio file the command wrote to
# ``{output_path}``. Supported placeholders: ``{input_path}``,
# ``{text_path}`` (alias for input_path), ``{output_path}``, ``{format}``,
# ``{voice}``, ``{model}``, ``{speed}``. Use ``{{`` / ``}}`` for literal braces.
#
# Built-in provider names always win over an entry with the same name under
# ``tts.providers``, so user config can't silently shadow ``edge`` etc.
#
# Placeholder values are shell-quoted for their surrounding context
# (bare / single / double quote), so paths with spaces work transparently.

# Built-in provider names. Any ``tts.provider`` value NOT in this set is
# interpreted as a reference to ``tts.providers.<name>``.
BUILTIN_TTS_PROVIDERS = frozenset({
    "edge",
    "elevenlabs",
    "openai",
    "minimax",
    "xai",
    "mistral",
    "gemini",
    "neutts",
    "kittentts",
    "piper",
    "kokoro",
})

DEFAULT_COMMAND_TTS_TIMEOUT_SECONDS = 120
DEFAULT_COMMAND_TTS_OUTPUT_FORMAT = "mp3"
COMMAND_TTS_OUTPUT_FORMATS = frozenset({"mp3", "wav", "ogg", "flac"})
DEFAULT_COMMAND_TTS_MAX_TEXT_LENGTH = 5000


def _get_provider_section(tts_config: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Return a provider config block if it's a dict, else an empty dict."""
    if not isinstance(tts_config, dict):
        return {}
    section = tts_config.get(name)
    return section if isinstance(section, dict) else {}


def _get_named_provider_config(
    tts_config: Dict[str, Any],
    name: str,
) -> Dict[str, Any]:
    """Return the config dict for a user-declared provider.

    Looks up ``tts.providers.<name>`` first (the canonical location), and
    falls back to ``tts.<name>`` so users who followed the built-in layout
    still work. Returns an empty dict when the provider is not declared.
    """
    providers = _get_provider_section(tts_config, "providers")
    section = providers.get(name) if isinstance(providers, dict) else None
    if isinstance(section, dict):
        return section
    # Back-compat: allow ``tts.<name>`` for user-declared providers too,
    # but only when the name is not a built-in (so a user's ``tts.openai``
    # block still means the OpenAI provider, not a custom command).
    if name.lower() not in BUILTIN_TTS_PROVIDERS:
        legacy = _get_provider_section(tts_config, name)
        if legacy:
            return legacy
    return {}


def _is_command_provider_config(config: Dict[str, Any]) -> bool:
    """Return True when *config* declares a command-type provider."""
    if not isinstance(config, dict):
        return False
    ptype = str(config.get("type") or "").strip().lower()
    if ptype and ptype != "command":
        return False
    command = config.get("command")
    return isinstance(command, str) and bool(command.strip())


def _resolve_command_provider_config(
    provider: str,
    tts_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the provider config if *provider* resolves to a command type.

    Built-in provider names are rejected (they have native handlers).
    Returns None when the name is a built-in, unknown, or not a command
    type.
    """
    if not provider:
        return None
    key = provider.lower().strip()
    if key in BUILTIN_TTS_PROVIDERS:
        return None
    config = _get_named_provider_config(tts_config, key)
    if _is_command_provider_config(config):
        return config
    return None


def _dispatch_to_plugin_provider(
    text: str,
    output_path: str,
    provider: str,
    tts_config: Dict[str, Any],
) -> Optional[str]:
    """Route the call to a plugin-registered TTS provider, or return None.

    Returns the path to the written audio file on dispatch, or ``None``
    to fall through to the next resolution layer (built-in dispatch or
    Edge TTS default).

    Resolution invariants enforced here (matches issue #30398):

    1. Built-in provider names short-circuit — never reach the plugin
       registry. The caller is responsible for the elif chain that
       handles ``edge``/``openai``/etc.; this function explicitly
       rejects those names defensively.
    2. Command-type providers declared under
       ``tts.providers.<name>: type: command`` (PR #17843) win over a
       plugin with the same name. The caller passes us only when its
       own command-provider check returned None — we re-verify here so
       a refactor of the caller can't silently break the invariant.
    3. Plugin dispatch fires only when ``provider`` matches a registered
       :class:`TTSProvider` whose ``name`` equals the configured value.
       Unknown names return None (caller falls through to Edge default).

    Plugin exceptions are caught and re-raised — the outer
    ``text_to_speech_tool`` try/except converts them to the standard
    error envelope, matching how command-provider failures surface.
    """
    if not provider:
        return None
    key = provider.lower().strip()
    if key in BUILTIN_TTS_PROVIDERS:
        return None
    # Defense in depth: command-provider check should already have
    # short-circuited the caller. If a same-name command config exists,
    # bail so the command path wins.
    if _is_command_provider_config(_get_named_provider_config(tts_config, key)):
        return None
    try:
        from agent.tts_registry import get_provider
        from hermes_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        plugin_provider = get_provider(key)
        if plugin_provider is None:
            # Long-lived sessions may have discovered plugins before the
            # bundled backend was patched in or before config changed.
            # Retry once with a forced refresh before surfacing fall-
            # through. Mirrors the image_gen / browser dispatcher
            # recovery pattern.
            _ensure_plugins_discovered(force=True)
            plugin_provider = get_provider(key)
    except Exception as exc:  # noqa: BLE001 — discovery failure is non-fatal
        logger.debug("tts plugin dispatch skipped (discovery failed): %s", exc)
        return None
    if plugin_provider is None:
        return None

    # Resolve voice / model / format from tts_config — providers should
    # treat all of these as optional and fall back to their own defaults
    # when None is passed (matches the ABC contract documented on
    # ``TTSProvider.synthesize``).
    voice = tts_config.get("voice") if isinstance(tts_config, dict) else None
    model = tts_config.get("model") if isinstance(tts_config, dict) else None
    speed = tts_config.get("speed") if isinstance(tts_config, dict) else None
    fmt = (
        tts_config.get("output_format", DEFAULT_COMMAND_TTS_OUTPUT_FORMAT)
        if isinstance(tts_config, dict)
        else DEFAULT_COMMAND_TTS_OUTPUT_FORMAT
    )

    logger.info(
        "Generating speech with plugin TTS provider '%s'...", key,
    )
    written = plugin_provider.synthesize(
        text,
        output_path,
        voice=voice if isinstance(voice, str) and voice else None,
        model=model if isinstance(model, str) and model else None,
        speed=float(speed) if isinstance(speed, (int, float)) else None,
        format=str(fmt).lower() if fmt else "mp3",
    )
    # Provider contract: returns the (possibly rewritten) output path.
    # Defensive against a provider returning None or a non-string —
    # fall back to the caller's expected output_path.
    return written if isinstance(written, str) and written else output_path


def _plugin_provider_is_voice_compatible(provider: str) -> bool:
    """Return True when the registered plugin provider opts into voice
    bubble delivery via its ``voice_compatible`` property.

    Defensive: any registry or property access failure means False
    (matches the safe default for the command-provider path).
    """
    if not provider:
        return False
    key = provider.lower().strip()
    if key in BUILTIN_TTS_PROVIDERS:
        return False
    try:
        from agent.tts_registry import get_provider

        plugin_provider = get_provider(key)
        if plugin_provider is None:
            return False
        return bool(plugin_provider.voice_compatible)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "tts plugin voice_compatible check failed for '%s': %s", key, exc,
        )
        return False


def _iter_command_providers(tts_config: Dict[str, Any]):
    """Yield (name, config) pairs for every declared command-type provider."""
    if not isinstance(tts_config, dict):
        return
    providers = _get_provider_section(tts_config, "providers")
    for name, cfg in (providers or {}).items():
        if isinstance(name, str) and name.lower() not in BUILTIN_TTS_PROVIDERS:
            if _is_command_provider_config(cfg):
                yield name, cfg


def _get_command_tts_timeout(config: Dict[str, Any]) -> float:
    """Return timeout in seconds, falling back when invalid."""
    raw = config.get("timeout", config.get("timeout_seconds", DEFAULT_COMMAND_TTS_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_COMMAND_TTS_TIMEOUT_SECONDS)
    if value <= 0:
        return float(DEFAULT_COMMAND_TTS_TIMEOUT_SECONDS)
    return value


def _get_command_tts_output_format(
    config: Dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    """Return the validated output format (mp3/wav/ogg/flac)."""
    if output_path:
        suffix = Path(output_path).suffix.lower().strip().lstrip(".")
        if suffix in COMMAND_TTS_OUTPUT_FORMATS:
            return suffix
    raw = (
        config.get("format")
        or config.get("output_format")
        or DEFAULT_COMMAND_TTS_OUTPUT_FORMAT
    )
    fmt = str(raw).lower().strip().lstrip(".")
    return fmt if fmt in COMMAND_TTS_OUTPUT_FORMATS else DEFAULT_COMMAND_TTS_OUTPUT_FORMAT


def _is_command_tts_voice_compatible(config: Dict[str, Any]) -> bool:
    """Return True only when the user explicitly opted in to voice delivery."""
    value = config.get("voice_compatible", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _shell_quote_context(command_template: str, position: int) -> Optional[str]:
    """Return the shell quote character active right before *position*.

    Returns ``"'"`` / ``'"'`` when inside a single- / double-quoted region
    of the template, ``None`` for bare context.
    """
    quote: Optional[str] = None
    escaped = False
    i = 0
    while i < position:
        char = command_template[i]
        if quote == "'":
            if char == "'":
                quote = None
        elif quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif char == "'":
            quote = "'"
        elif char == '"':
            quote = '"'
        elif char == "\\":
            i += 1
        i += 1
    return quote


def _quote_command_tts_placeholder(value: str, quote_context: Optional[str]) -> str:
    """Quote a placeholder value for its position in a shell command template."""
    if quote_context == "'":
        return value.replace("'", r"'\''")
    if quote_context == '"':
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', r'\"')
            .replace("$", r"\$")
            .replace("`", r"\`")
        )
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


def _render_command_tts_template(
    command_template: str,
    placeholders: Dict[str, str],
) -> str:
    """Replace supported placeholders while preserving ``{{`` / ``}}``."""
    names = "|".join(re.escape(name) for name in placeholders)
    pattern = re.compile(
        rf"(?<!\$)(?:\{{\{{(?P<double>{names})\}}\}}|\{{(?P<single>{names})\}})"
    )
    replacements: list[tuple[str, str]] = []

    def replace_match(match: re.Match[str]) -> str:
        name = match.group("double") or match.group("single")
        token = f"__HERMES_TTS_PLACEHOLDER_{len(replacements)}__"
        replacements.append((
            token,
            _quote_command_tts_placeholder(
                placeholders[name],
                _shell_quote_context(command_template, match.start()),
            ),
        ))
        return token

    rendered = pattern.sub(replace_match, command_template)
    rendered = rendered.replace("{{", "{").replace("}}", "}")
    for token, value in replacements:
        rendered = rendered.replace(token, value)
    return rendered


def _terminate_command_tts_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort termination of a shell process and all of its children."""
    if proc.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            proc.kill()
        return

    import psutil
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
    except psutil.NoSuchProcess:
        return
    except Exception:
        proc.terminate()

    try:
        proc.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        return
    except Exception:
        proc.kill()


def _run_command_tts(command: str, timeout: float) -> subprocess.CompletedProcess:
    """Run a command-provider shell command with process-tree timeout cleanup."""
    popen_kwargs: Dict[str, Any] = {
        "shell": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_command_tts_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except Exception:
            stdout = getattr(exc, "output", None)
            stderr = getattr(exc, "stderr", None)
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=stdout,
            stderr=stderr,
        ) from exc

    if proc.returncode:
        raise subprocess.CalledProcessError(
            proc.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def _configured_command_tts_output_path(path: Path, config: Dict[str, Any]) -> Path:
    """Return an output path whose extension matches the provider's output_format."""
    fmt = _get_command_tts_output_format(config)
    return path.with_suffix(f".{fmt}")


def _generate_command_tts(
    text: str,
    output_path: str,
    provider_name: str,
    config: Dict[str, Any],
    tts_config: Dict[str, Any],
) -> str:
    """Generate speech by running a user-configured shell command.

    Returns the absolute path of the audio file the command wrote.
    Raises ``ValueError`` when the provider config is invalid, and
    ``RuntimeError`` for timeouts / non-zero exits / empty output.
    """
    command_template = str(config.get("command") or "").strip()
    if not command_template:
        raise ValueError(
            f"tts.providers.{provider_name}.command is not configured"
        )

    output = Path(output_path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    timeout = _get_command_tts_timeout(config)
    output_format = _get_command_tts_output_format(config, str(output))
    speed = config.get("speed", tts_config.get("speed", ""))

    with tempfile.TemporaryDirectory() as tmpdir:
        text_path = Path(tmpdir) / "input.txt"
        text_path.write_text(text, encoding="utf-8")

        placeholders = {
            "input_path": str(text_path),
            "text_path": str(text_path),
            "output_path": str(output),
            "format": output_format,
            "voice": str(config.get("voice", "")),
            "model": str(config.get("model", "")),
            "speed": str(speed),
        }
        command = _render_command_tts_template(command_template, placeholders)

        try:
            _run_command_tts(command, timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"TTS provider '{provider_name}' timed out after {timeout:g}s"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail_parts = []
            if exc.stderr:
                detail_parts.append(f"stderr: {exc.stderr.strip()}")
            if exc.stdout:
                detail_parts.append(f"stdout: {exc.stdout.strip()}")
            detail = "; ".join(detail_parts) or "no command output"
            raise RuntimeError(
                f"TTS provider '{provider_name}' exited with code "
                f"{exc.returncode}: {detail}"
            ) from exc

    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError(
            f"TTS provider '{provider_name}' produced no output at {output}"
        )
    return str(output)


def _has_any_command_tts_provider(tts_config: Optional[Dict[str, Any]] = None) -> bool:
    """Return True when any command-type TTS provider is configured."""
    if tts_config is None:
        tts_config = _load_tts_config()
    for _name, _cfg in _iter_command_providers(tts_config):
        return True
    return False


# ===========================================================================
# ffmpeg Opus conversion (Edge TTS MP3 -> OGG Opus for Telegram)
# ===========================================================================
def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


def _convert_to_opus(mp3_path: str) -> Optional[str]:
    """
    Convert an MP3 file to OGG Opus format for Telegram voice bubbles.

    Args:
        mp3_path: Path to the input MP3 file.

    Returns:
        Path to the .ogg file, or None if conversion fails.
    """
    if not _has_ffmpeg():
        return None

    ogg_path = mp3_path.rsplit(".", 1)[0] + ".ogg"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", mp3_path, "-acodec", "libopus",
             "-ac", "1", "-b:a", "64k", "-vbr", "off", ogg_path, "-y"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed with return code %d: %s", 
                          result.returncode, result.stderr.decode('utf-8', errors='ignore')[:200])
            return None
        if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
            return ogg_path
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg OGG conversion timed out after 30s")
    except FileNotFoundError:
        logger.warning("ffmpeg not found in PATH")
    except Exception as e:
        logger.warning("ffmpeg OGG conversion failed: %s", e, exc_info=True)
    return None


# ===========================================================================
# Provider: Edge TTS (free)
# ===========================================================================
async def _generate_edge_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using Edge TTS.

    Args:
        text: Text to convert.
        output_path: Where to save the MP3 file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    _edge_tts = _import_edge_tts()
    edge_config = tts_config.get("edge", {})
    voice = edge_config.get("voice", DEFAULT_EDGE_VOICE)
    speed = float(edge_config.get("speed", tts_config.get("speed", 1.0)))

    kwargs = {"voice": voice}
    if speed != 1.0:
        pct = round((speed - 1.0) * 100)
        kwargs["rate"] = f"{pct:+d}%"

    try:
        communicate = _edge_tts.Communicate(text, **kwargs)
        await communicate.save(output_path)
        return output_path
    except Exception as first_exc:
        # Attempt clock-skew DRM recovery if edge_tts exposes DRM.handle_client_response_error
        drm_cls = getattr(getattr(_edge_tts, "drm", None), "DRM", None)
        if drm_cls is None:
            try:
                from edge_tts.drm import DRM as drm_cls
            except Exception:
                drm_cls = None
        if drm_cls is not None and hasattr(drm_cls, "handle_client_response_error"):
            try:
                drm_cls.handle_client_response_error(first_exc)
            except Exception:
                pass
        # Single bounded retry for clock-skew or transient WebSocket errors
        try:
            await asyncio.sleep(0.15)
            communicate_retry = _edge_tts.Communicate(text, **kwargs)
            await communicate_retry.save(output_path)
            return output_path
        except Exception:
            raise first_exc


_ORIG_GENERATE_EDGE_TTS = _generate_edge_tts


# ===========================================================================
# Provider: ElevenLabs (premium)
# ===========================================================================
def _generate_elevenlabs(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using ElevenLabs.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key = (get_env_value("ELEVENLABS_API_KEY") or "")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not set. Get one at https://elevenlabs.io/")

    el_config = tts_config.get("elevenlabs", {})
    voice_id = el_config.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
    model_id = el_config.get("model_id", DEFAULT_ELEVENLABS_MODEL_ID)

    # Determine output format based on file extension
    if output_path.endswith(".ogg"):
        output_format = "opus_48000_64"
    else:
        output_format = "mp3_44100_128"

    ElevenLabs = _import_elevenlabs()
    client = ElevenLabs(api_key=api_key)
    audio_generator = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )

    # audio_generator yields chunks -- write them all
    with open(output_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    return output_path


# ===========================================================================
# Provider: OpenAI TTS
# ===========================================================================
def _generate_openai_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using OpenAI TTS.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key, base_url = _resolve_openai_audio_client_config()

    oai_config = tts_config.get("openai", {})
    model = oai_config.get("model", DEFAULT_OPENAI_MODEL)
    voice = oai_config.get("voice", DEFAULT_OPENAI_VOICE)
    base_url = oai_config.get("base_url", base_url)
    speed = float(oai_config.get("speed", tts_config.get("speed", 1.0)))

    # Determine response format from extension
    if output_path.endswith(".ogg"):
        response_format = "opus"
    else:
        response_format = "mp3"

    OpenAIClient = _import_openai_client()
    client = OpenAIClient(api_key=api_key, base_url=base_url)
    try:
        create_kwargs = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": response_format,
            "extra_headers": {"x-idempotency-key": str(uuid.uuid4())},
        }
        if speed != 1.0:
            create_kwargs["speed"] = max(0.25, min(4.0, speed))
        response = client.audio.speech.create(**create_kwargs)

        response.stream_to_file(output_path)
        return output_path
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


# ===========================================================================
# Provider: xAI TTS
# ===========================================================================
_XAI_INLINE_SPEECH_TAGS = (
    "pause",
    "long-pause",
    "hum-tune",
    "laugh",
    "chuckle",
    "giggle",
    "cry",
    "tsk",
    "tongue-click",
    "lip-smack",
    "breath",
    "inhale",
    "exhale",
    "sigh",
)
_XAI_WRAPPING_SPEECH_TAGS = (
    "soft",
    "whisper",
    "loud",
    "build-intensity",
    "decrease-intensity",
    "higher-pitch",
    "lower-pitch",
    "slow",
    "fast",
    "sing-song",
    "singing",
    "laugh-speak",
    "emphasis",
)
_XAI_SPEECH_TAG_RE = re.compile(
    r"(\[(?:" + "|".join(_XAI_INLINE_SPEECH_TAGS) + r")\]|</?(?:" + "|".join(_XAI_WRAPPING_SPEECH_TAGS) + r")>)",
    flags=re.IGNORECASE,
)
_XAI_FIRST_SENTENCE_RE = re.compile(r"^(.{12,120}?[.!?…])\s+(?=\S)", flags=re.DOTALL)


def _xai_bool_config(value: Any, default: bool = False) -> bool:
    """Coerce common YAML/env bool spellings without treating random strings as true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return default


def _apply_xai_auto_speech_tags(text: str) -> str:
    """Add light xAI speech tags for more natural voice-mode replies.

    The transform is intentionally conservative: it only inserts pauses. It
    never fabricates laughter or whispering, and it leaves explicit user/model
    speech tags untouched.
    """
    clean = text.strip()
    if not clean or _XAI_SPEECH_TAG_RE.search(clean):
        return text

    clean = re.sub(r"\n\s*\n+", " [pause] ", clean)
    clean = re.sub(r"\s*\n\s*", " ", clean)
    if not _XAI_SPEECH_TAG_RE.search(clean):
        clean = _XAI_FIRST_SENTENCE_RE.sub(r"\1 [pause] ", clean, count=1)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean


def _generate_xai_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using xAI TTS.

    xAI exposes a dedicated /v1/tts endpoint instead of the OpenAI audio.speech
    API shape, so this is implemented as a separate backend.
    """
    import requests

    from tools.xai_http import resolve_xai_http_credentials

    creds = resolve_xai_http_credentials()
    api_key = str(creds.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("No xAI credentials found. Configure xAI OAuth in `hermes model` or set XAI_API_KEY.")

    xai_config = tts_config.get("xai", {})
    voice_id = str(xai_config.get("voice_id", DEFAULT_XAI_VOICE_ID)).strip() or DEFAULT_XAI_VOICE_ID
    language = str(xai_config.get("language", DEFAULT_XAI_LANGUAGE)).strip() or DEFAULT_XAI_LANGUAGE
    sample_rate = int(xai_config.get("sample_rate", DEFAULT_XAI_SAMPLE_RATE))
    bit_rate = int(xai_config.get("bit_rate", DEFAULT_XAI_BIT_RATE))
    auto_speech_tags = _xai_bool_config(
        xai_config.get("auto_speech_tags", xai_config.get("speech_tags")),
        DEFAULT_XAI_AUTO_SPEECH_TAGS,
    )
    if auto_speech_tags:
        text = _apply_xai_auto_speech_tags(text)
    base_url = str(
        xai_config.get("base_url")
        or creds.get("base_url")
        or get_env_value("XAI_BASE_URL")
        or DEFAULT_XAI_BASE_URL
    ).strip().rstrip("/")

    # Match the documented minimal POST /v1/tts shape by default. Only send
    # output_format when Hermes actually needs a non-default format/override.
    codec = "wav" if output_path.endswith(".wav") else "mp3"
    payload: Dict[str, Any] = {
        "text": text,
        "voice_id": voice_id,
        "language": language,
    }
    if (
        codec != "mp3"
        or sample_rate != DEFAULT_XAI_SAMPLE_RATE
        or (codec == "mp3" and bit_rate != DEFAULT_XAI_BIT_RATE)
    ):
        output_format: Dict[str, Any] = {"codec": codec}
        if sample_rate:
            output_format["sample_rate"] = sample_rate
        if codec == "mp3" and bit_rate:
            output_format["bit_rate"] = bit_rate
        payload["output_format"] = output_format

    response = requests.post(
        f"{base_url}/tts",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": hermes_xai_user_agent(),
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    return output_path


# ===========================================================================
# Provider: MiniMax TTS
# ===========================================================================
def _generate_minimax_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using MiniMax TTS API.

    Supports two endpoints:
    - v1/text_to_speech: simple payload, returns raw audio (Content-Type: audio/mpeg)
    - v1/t2a_v2: nested voice_setting/audio_setting, returns JSON with hex-encoded audio

    Args:
        text: Text to convert (max 10,000 characters).
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    import requests

    api_key = (get_env_value("MINIMAX_API_KEY") or "")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set. Get one at https://platform.minimax.io/")

    mm_config = tts_config.get("minimax", {})
    model = mm_config.get("model", DEFAULT_MINIMAX_MODEL)
    voice_id = mm_config.get("voice_id", DEFAULT_MINIMAX_VOICE_ID)
    base_url = mm_config.get("base_url", DEFAULT_MINIMAX_BASE_URL)
    speed = mm_config.get("speed", 1.0)
    vol = mm_config.get("vol", 1.0)
    pitch = mm_config.get("pitch", 0)
    emotion = mm_config.get("emotion", "neutral")
    sample_rate = mm_config.get("sample_rate", 32000)
    bitrate = mm_config.get("bitrate", 128000)

    # MiniMax accounts scope TTS requests by GroupId.  When present, the docs
    # show it as a ?GroupId=<id> query param on the t2a_v2 URL.  Accept it
    # from config or from the MINIMAX_GROUP_ID env var; only attach when the
    # URL doesn't already carry one.
    group_id = (
        str(mm_config.get("group_id") or "").strip()
        or (get_env_value("MINIMAX_GROUP_ID") or "").strip()
    )
    if group_id and "GroupId=" not in base_url:
        sep = "&" if "?" in base_url else "?"
        base_url = f"{base_url}{sep}GroupId={group_id}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Detect endpoint from URL
    is_t2a_v2 = "t2a_v2" in base_url

    if is_t2a_v2:
        # t2a_v2 endpoint: nested voice_setting/audio_setting structure
        payload = {
            "model": model,
            "text": text,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
                "emotion": emotion,
            },
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": "mp3",
                "channel": 1,
            },
        }
    else:
        # text_to_speech endpoint: flat payload
        payload = {
            "model": model,
            "text": text,
            "voice_id": voice_id,
        }

    response = requests.post(base_url, json=payload, headers=headers, timeout=60)

    if is_t2a_v2:
        # t2a_v2 returns JSON with hex-encoded audio
        result = response.json()
        base_resp = result.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)

        if status_code != 0:
            status_msg = base_resp.get("status_msg", "unknown error")
            raise RuntimeError(f"MiniMax TTS API error (code {status_code}): {status_msg}")

        hex_audio = result.get("data", {}).get("audio", "")
        if not hex_audio:
            raise RuntimeError("MiniMax TTS returned empty audio data")

        audio_bytes = bytes.fromhex(hex_audio)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return output_path

    else:
        # text_to_speech returns raw audio directly
        content_type = response.headers.get("Content-Type", "")

        if "audio/" in content_type:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path

        # Fallback: try parsing as JSON
        try:
            result = response.json()
            base_resp = result.get("base_resp", {})
            status_code = base_resp.get("status_code", -1)
            if status_code != 0:
                status_msg = base_resp.get("status_msg", "unknown error")
                raise RuntimeError(f"MiniMax TTS API error (code {status_code}): {status_msg}")
        except Exception:
            response.raise_for_status()
            raise RuntimeError(
                f"MiniMax TTS returned unexpected Content-Type '{content_type}' "
                f"({len(response.content)} bytes)"
            )

        raise RuntimeError("MiniMax TTS returned no audio data")


# ===========================================================================
# Provider: Mistral (Voxtral TTS)
# ===========================================================================
def _generate_mistral_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate audio using Mistral Voxtral TTS API.

    The API returns base64-encoded audio; this function decodes it
    and writes the raw bytes to *output_path*.
    Supports native Opus output for Telegram voice bubbles.
    """
    api_key = (get_env_value("MISTRAL_API_KEY") or "")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set. Get one at https://console.mistral.ai/")

    mi_config = tts_config.get("mistral", {})
    model = mi_config.get("model", DEFAULT_MISTRAL_TTS_MODEL)
    voice_id = mi_config.get("voice_id") or DEFAULT_MISTRAL_TTS_VOICE_ID

    if output_path.endswith(".ogg"):
        response_format = "opus"
    elif output_path.endswith(".wav"):
        response_format = "wav"
    elif output_path.endswith(".flac"):
        response_format = "flac"
    else:
        response_format = "mp3"

    Mistral = _import_mistral_client()
    try:
        with Mistral(api_key=api_key) as client:
            response = client.audio.speech.complete(
                model=model,
                input=text,
                voice_id=voice_id,
                response_format=response_format,
            )
            audio_bytes = base64.b64decode(response.audio_data)
    except ValueError:
        raise
    except Exception as e:
        logger.error("Mistral TTS failed: %s", e, exc_info=True)
        raise RuntimeError(f"Mistral TTS failed: {type(e).__name__}") from e

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    return output_path


# ===========================================================================
# Provider: Google Gemini TTS
# ===========================================================================
def _wrap_pcm_as_wav(
    pcm_bytes: bytes,
    sample_rate: int = GEMINI_TTS_SAMPLE_RATE,
    channels: int = GEMINI_TTS_CHANNELS,
    sample_width: int = GEMINI_TTS_SAMPLE_WIDTH,
) -> bytes:
    """Wrap raw signed-little-endian PCM with a standard WAV RIFF header.

    Gemini TTS returns audio/L16;codec=pcm;rate=24000 -- raw PCM samples with
    no container. We add a minimal WAV header so the file is playable and
    ffmpeg can re-encode it to MP3/Opus downstream.
    """
    import struct

    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(pcm_bytes)
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,             # fmt chunk size (PCM)
        1,              # audio format (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
    )
    data_chunk_header = struct.pack("<4sI", b"data", data_size)
    riff_size = 4 + len(fmt_chunk) + len(data_chunk_header) + data_size
    riff_header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return riff_header + fmt_chunk + data_chunk_header + pcm_bytes


def _generate_gemini_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate audio using Google Gemini TTS.

    Gemini's generateContent endpoint with responseModalities=["AUDIO"] returns
    raw 24kHz mono 16-bit PCM (L16) as base64. We wrap it with a WAV RIFF
    header to produce a playable file, then ffmpeg-convert to MP3 / Opus if
    the caller requested those formats (same pattern as NeuTTS).

    Args:
        text: Text to convert (prompt-style; supports inline direction like
              "Say cheerfully:" and audio tags like [whispers]).
        output_path: Where to save the audio file (.wav, .mp3, or .ogg).
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    import requests

    api_key = (get_env_value("GEMINI_API_KEY") or get_env_value("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Get one at https://aistudio.google.com/app/apikey"
        )

    gemini_config = tts_config.get("gemini", {})
    model = str(gemini_config.get("model", DEFAULT_GEMINI_TTS_MODEL)).strip() or DEFAULT_GEMINI_TTS_MODEL
    voice = str(gemini_config.get("voice", DEFAULT_GEMINI_TTS_VOICE)).strip() or DEFAULT_GEMINI_TTS_VOICE
    base_url = str(
        gemini_config.get("base_url")
        or get_env_value("GEMINI_BASE_URL")
        or DEFAULT_GEMINI_TTS_BASE_URL
    ).strip().rstrip("/")

    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                },
            },
        },
    }

    endpoint = f"{base_url}/models/{model}:generateContent"
    response = requests.post(
        endpoint,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if response.status_code != 200:
        # Surface the API error message when present
        try:
            err = response.json().get("error", {})
            detail = err.get("message") or response.text[:300]
        except Exception:
            detail = response.text[:300]
        raise RuntimeError(
            f"Gemini TTS API error (HTTP {response.status_code}): {detail}"
        )

    try:
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        audio_part = next((p for p in parts if "inlineData" in p or "inline_data" in p), None)
        if audio_part is None:
            raise RuntimeError("Gemini TTS response contained no audio data")
        inline = audio_part.get("inlineData") or audio_part.get("inline_data") or {}
        audio_b64 = inline.get("data", "")
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Gemini TTS response was malformed: {e}") from e

    if not audio_b64:
        raise RuntimeError("Gemini TTS returned empty audio data")

    pcm_bytes = base64.b64decode(audio_b64)
    wav_bytes = _wrap_pcm_as_wav(pcm_bytes)

    # Fast path: caller wants WAV directly, just write.
    if output_path.lower().endswith(".wav"):
        with open(output_path, "wb") as f:
            f.write(wav_bytes)
        return output_path

    # Otherwise write WAV to a temp file and ffmpeg-convert to the target
    # format (.mp3 or .ogg). If ffmpeg is missing, fall back to renaming the
    # WAV -- this matches the NeuTTS behavior and keeps the tool usable on
    # systems without ffmpeg (audio still plays, just with a misleading
    # extension).
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        wav_path = tmp.name

    try:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            # For .ogg output, force libopus encoding (Telegram voice bubbles
            # require Opus specifically; ffmpeg's default for .ogg is Vorbis).
            if output_path.lower().endswith(".ogg"):
                cmd = [
                    ffmpeg, "-i", wav_path,
                    "-acodec", "libopus", "-ac", "1",
                    "-b:a", "64k", "-vbr", "off",
                    "-y", "-loglevel", "error",
                    output_path,
                ]
            else:
                cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="ignore")[:300]
                raise RuntimeError(f"ffmpeg conversion failed: {stderr}")
        else:
            logger.warning(
                "ffmpeg not found; writing raw WAV to %s (extension may be misleading)",
                output_path,
            )
            shutil.copyfile(wav_path, output_path)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass

    return output_path


# ===========================================================================
# NeuTTS (local, on-device TTS via neutts_cli)
# ===========================================================================

def _check_neutts_available() -> bool:
    """Check if the neutts engine is importable (installed locally)."""
    try:
        import importlib.util
        return importlib.util.find_spec("neutts") is not None
    except Exception:
