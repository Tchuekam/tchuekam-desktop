#!/usr/bin/env python3
"""
AI Agent Runner with Tool Calling

This module provides a clean, standalone agent that can execute AI models
with tool calling capabilities. It handles the conversation loop, tool execution,
and response management.

Features:
- Automatic tool calling loop until completion
- Configurable model parameters
- Error handling and recovery
- Message history management
- Support for multiple model providers

Usage:
    from run_agent import AIAgent
    
    agent = AIAgent(base_url="http://localhost:30000/v1", model="claude-opus-4-20250514")
    response = agent.run_conversation("Tell me about the latest Python updates")
"""

# IMPORTANT: hermes_bootstrap must be the very first import — UTF-8 stdio
# on Windows.  No-op on POSIX.  See hermes_bootstrap.py for full rationale.
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    # Graceful fallback when hermes_bootstrap isn't registered in the venv
    # yet — happens during partial ``hermes update`` where git-reset landed
    # new code but ``uv pip install -e .`` didn't finish.  Missing bootstrap
    # means UTF-8 stdio setup is skipped on Windows; POSIX is unaffected.
    pass

import asyncio
import base64
import copy
import hashlib
import json
import logging
logger = logging.getLogger(__name__)
import os
import re
import sys
import tempfile
import time
import threading
import uuid
from typing import List, Dict, Any, Optional
# NOTE: `from openai import OpenAI` is deliberately NOT at module top — the
# SDK pulls ~240 ms of imports. We expose `OpenAI` as a thin proxy object
# that imports the SDK on first call/isinstance check. This preserves:
#   (a) the single in-module `OpenAI(**client_kwargs)` call site at
#       _create_openai_client, and
#   (b) `patch("run_agent.OpenAI", ...)` test patterns used by ~28 test files.
#
# NOTE: `fire` is ONLY used in the `__main__` block below (for running
# run_agent.py directly as a CLI) — it is NOT needed for library usage.
# It is imported there, not here, so that importing run_agent from a
# daemon thread (e.g. curator's forked review agent) never fails with
# ModuleNotFoundError on broken/partial installs where `fire` isn't present.
from datetime import datetime
from pathlib import Path

from hermes_constants import get_hermes_home

# OpenAI lazy proxy + safe stdio + proxy URL helpers — see agent/process_bootstrap.py.
# `OpenAI` is re-exported here so `patch("run_agent.OpenAI", ...)` in tests works.
# The other `# noqa: F401` re-exports below cover names accessed via
# `mock.patch("run_agent.<X>")`, `from run_agent import <X>` in production
# siblings, or the `_ra().<X>` indirection in agent/system_prompt.py — none
# of which ruff's in-module usage scan can see.
from agent.process_bootstrap import (
    OpenAI,  # noqa: F401  # re-exported for tests that mock.patch("run_agent.OpenAI")
    _SafeWriter,  # noqa: F401  # re-exported for tests that `from run_agent import _SafeWriter`
    _get_proxy_for_base_url,
)
from agent.iteration_budget import IterationBudget


from hermes_cli.env_loader import load_hermes_dotenv
from hermes_cli.timeouts import (
    get_provider_request_timeout,
    get_provider_stale_timeout,
)

_hermes_home = get_hermes_home()
_project_env = Path(__file__).parent / '.env'
_loaded_env_paths = load_hermes_dotenv(hermes_home=_hermes_home, project_env=_project_env)
if _loaded_env_paths:
    for _env_path in _loaded_env_paths:
        logger.info("Loaded environment variables from %s", _env_path)
else:
    logger.info("No .env file found. Using system environment variables.")


# Import our tool system
from model_tools import (
    get_tool_definitions,  # noqa: F401  # re-exported for tests that mock.patch("run_agent.get_tool_definitions")
    get_toolset_for_tool,
    handle_function_call,  # noqa: F401  # re-exported for tests that mock.patch("run_agent.handle_function_call")
    check_toolset_requirements,  # noqa: F401  # re-exported for tests that mock.patch("run_agent.check_toolset_requirements")
)
from tools.terminal_tool import cleanup_vm
from tools.interrupt import set_interrupt as _set_interrupt
from tools.browser_tool import cleanup_browser


# Agent internals extracted to agent/ package for modularity
from agent.memory_manager import sanitize_context
from agent.error_classifier import FailoverReason
from agent.redact import redact_sensitive_text
from agent.model_metadata import (
    estimate_request_tokens_rough,  # noqa: F401  # re-exported for tests that mock.patch("run_agent.estimate_request_tokens_rough")
    is_local_endpoint,
)
from agent.usage_pricing import normalize_usage
# Re-exported for tests that monkeypatch these symbols on run_agent.
from agent.context_compressor import ContextCompressor  # noqa: F401
from agent.retry_utils import jittered_backoff  # noqa: F401
from agent.prompt_builder import (  # noqa: F401  # re-exported via _ra() / mock.patch("run_agent.<name>") / from run_agent import <name>
    DEFAULT_AGENT_IDENTITY,
    build_skills_system_prompt,
    build_context_files_prompt,
    build_environment_hints,
    build_nous_subscription_prompt,
    load_soul_md,
)
from agent.process_bootstrap import _get_proxy_from_env  # noqa: F401
from agent.message_sanitization import (  # noqa: F401
    _SURROGATE_RE,
    _sanitize_surrogates,
    _sanitize_structure_surrogates,
    _sanitize_messages_surrogates,
    _escape_invalid_chars_in_json_strings,
    _repair_tool_call_arguments,
    _strip_non_ascii,
    _sanitize_messages_non_ascii,
    _sanitize_tools_non_ascii,
    _strip_images_from_messages,
    _sanitize_structure_non_ascii,
)
from agent.codex_responses_adapter import (
    _derive_responses_function_call_id as _codex_derive_responses_function_call_id,
    _deterministic_call_id as _codex_deterministic_call_id,
    _split_responses_tool_id as _codex_split_responses_tool_id,
    _summarize_user_message_for_log,  # noqa: F401  # re-exported for tests
)
from agent.tool_guardrails import (
    ToolGuardrailDecision,
    append_toolguard_guidance,
    toolguard_synthetic_result,
)
from agent.tool_result_classification import (
    FILE_MUTATING_TOOL_NAMES as _FILE_MUTATING_TOOLS,
    file_mutation_result_landed,
)
from agent.trajectory import (
    convert_scratchpad_to_think,
    save_trajectory as _save_trajectory_to_file,
)
from agent.tool_dispatch_helpers import (
    _should_parallelize_tool_batch,
    _is_destructive_command,  # noqa: F401  # re-exported for tests that access `run_agent._is_destructive_command`
    _extract_parallel_scope_path,  # noqa: F401  # re-exported for tests that `from run_agent import _extract_parallel_scope_path`
    _paths_overlap,  # noqa: F401  # re-exported for tests that `from run_agent import _paths_overlap`
    _is_multimodal_tool_result,
    _multimodal_text_summary,
    _append_subdir_hint_to_multimodal,  # noqa: F401  # re-exported for tests that `from run_agent import _append_subdir_hint_to_multimodal`
    _extract_file_mutation_targets,
    _extract_error_preview,
    _trajectory_normalize_msg,  # noqa: F401  # re-exported for tests that `from run_agent import _trajectory_normalize_msg`
)
from utils import atomic_json_write, base_url_host_matches, base_url_hostname



_MAX_TOOL_WORKERS = 8

# Guard so the OpenRouter metadata pre-warm thread is only spawned once per
# process, not once per AIAgent instantiation.  Without this, long-running
# gateway processes leak one OS thread per incoming message and eventually
# exhaust the system thread limit (RuntimeError: can't start new thread).
_openrouter_prewarm_done = threading.Event()

# =========================================================================
# Large tool result handler — save oversized output to temp file
# =========================================================================


# =========================================================================
# Qwen Portal headers — mimics QwenCode CLI for portal.qwen.ai compatibility.
# Extracted as a module-level helper so both __init__ and
# _apply_client_headers_for_base_url can share it.
# =========================================================================
_QWEN_CODE_VERSION = "0.14.1"


def _routermint_headers() -> dict:
    """Return the User-Agent RouterMint needs to avoid Cloudflare 1010 blocks."""
    from hermes_cli import __version__ as _HERMES_VERSION

    return {
        "User-Agent": f"HermesAgent/{_HERMES_VERSION}",
    }


def _pool_may_recover_from_rate_limit(
    pool, *, provider: str | None = None, base_url: str | None = None
) -> bool:
    """Decide whether to wait for credential-pool rotation instead of falling back.

    The existing pool-rotation path requires the pool to (1) exist and (2) have
    at least one entry not currently in exhaustion cooldown.  But rotation is
    only meaningful when the pool has more than one entry.

    With a single-credential pool (common for Gemini OAuth, Vertex service
    accounts, and any "one personal key" configuration), the primary entry
    just 429'd and there is nothing to rotate to.  Waiting for the pool
    cooldown to expire means retrying against the same exhausted quota — the
    daily-quota 429 will recur immediately, and the retry budget is burned.

    Additionally, Google CloudCode / Gemini CLI rate limits are ACCOUNT-level
    throttles — even a multi-entry pool shares the same quota window, so
    rotation won't recover.  Skip straight to the fallback for those (#13636).

    In those cases we must fall back to the configured ``fallback_model``
    instead.  Returns True only when rotation has somewhere to go.

    See issues #11314 and #13636.
    """
    if pool is None:
        return False
    if not pool.has_available():
        return False
    # CloudCode / Gemini CLI quotas are account-wide — all pool entries share
    # the same throttle window, so rotation can't recover.  Prefer fallback.
    if provider == "google-gemini-cli" or str(base_url or "").startswith("cloudcode-pa://"):
        return False
    return len(pool.entries()) > 1


def _qwen_portal_headers() -> dict:
    """Return default HTTP headers required by Qwen Portal API."""
    import platform as _plat

    _ua = f"QwenCode/{_QWEN_CODE_VERSION} ({_plat.system().lower()}; {_plat.machine()})"
    return {
        "User-Agent": _ua,
        "X-DashScope-CacheControl": "enable",
        "X-DashScope-UserAgent": _ua,
        "X-DashScope-AuthType": "qwen-oauth",
    }


class _StreamErrorEvent(Exception):
    """Synthesized provider error surfaced from a Responses ``error`` SSE frame.

    Some Codex-style Responses backends (xAI for subscription/quota
    failures, custom relays under malformed-tool-call conditions) emit a
    standalone ``type=error`` frame instead of routing the failure
    through ``response.failed`` or returning an HTTP 4xx.  The fallback
    streaming path raises this exception so ``_summarize_api_error`` and
    ``_extract_api_error_context`` see a familiar ``.body`` /
    ``.status_code`` shape and the entitlement detector can match the
    underlying provider message ("do not have an active Grok
    subscription", etc.).
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        param: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.param = param
        self.status_code = status_code
        # OpenAI SDK-shaped body so _extract_api_error_context /
        # _summarize_api_error / classify_api_error all pick it up.
        self.body: Dict[str, Any] = {
            "error": {
                "message": message,
                "code": code,
                "param": param,
                "type": "error",
            }
        }


class AIAgent:
    """
    AI Agent with tool calling capabilities.

    This class manages the conversation flow, tool execution, and response handling
    for AI models that support function calling.
    """

    _TOOL_CALL_ARGUMENTS_CORRUPTION_MARKER = (
        "[hermes-agent: tool call arguments were corrupted in this session and "
        "have been dropped to keep the conversation alive. See issue #15236.]"
    )

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = value
        self._base_url_lower = value.lower() if value else ""
        self._base_url_hostname = base_url_hostname(value)

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        provider: str = None,
        api_mode: str = None,
        acp_command: str = None,
        acp_args: list[str] | None = None,
        command: str = None,
        args: list[str] | None = None,
        model: str = "",
        max_iterations: int = 90,  # Default tool-calling iterations (shared with subagents)
        tool_delay: float = 1.0,
        enabled_toolsets: List[str] = None,
        disabled_toolsets: List[str] = None,
        save_trajectories: bool = False,
        verbose_logging: bool = False,
        quiet_mode: bool = False,
        ephemeral_system_prompt: str = None,
        log_prefix_chars: int = 100,
        log_prefix: str = "",
        providers_allowed: List[str] = None,
        providers_ignored: List[str] = None,
        providers_order: List[str] = None,
        provider_sort: str = None,
        provider_require_parameters: bool = False,
        provider_data_collection: str = None,
        openrouter_min_coding_score: Optional[float] = None,
        session_id: str = None,
        tool_progress_callback: callable = None,
        tool_start_callback: callable = None,
        tool_complete_callback: callable = None,
        thinking_callback: callable = None,
        reasoning_callback: callable = None,
        clarify_callback: callable = None,
        step_callback: callable = None,
        stream_delta_callback: callable = None,
        interim_assistant_callback: callable = None,
        tool_gen_callback: callable = None,
        status_callback: callable = None,
        max_tokens: int = None,
        reasoning_config: Dict[str, Any] = None,
        service_tier: str = None,
        request_overrides: Dict[str, Any] = None,
        prefill_messages: List[Dict[str, Any]] = None,
        platform: str = None,
        user_id: str = None,
        user_id_alt: str = None,
        user_name: str = None,
        chat_id: str = None,
        chat_name: str = None,
        chat_type: str = None,
        thread_id: str = None,
        gateway_session_key: str = None,
        skip_context_files: bool = False,
        load_soul_identity: bool = False,
        skip_memory: bool = False,
        session_db=None,
        parent_session_id: str = None,
        iteration_budget: "IterationBudget" = None,
        fallback_model: Dict[str, Any] = None,
        credential_pool=None,
        checkpoints_enabled: bool = False,
        checkpoint_max_snapshots: int = 20,
        checkpoint_max_total_size_mb: int = 500,
        checkpoint_max_file_size_mb: int = 10,
        pass_session_id: bool = False,
    ):
        """Forwarder — see ``agent.agent_init.init_agent``."""
        from agent.agent_init import init_agent
        init_agent(
            self,
            base_url=base_url,
            api_key=api_key,
            provider=provider,
            api_mode=api_mode,
            acp_command=acp_command,
            acp_args=acp_args,
            command=command,
            args=args,
            model=model,
            max_iterations=max_iterations,
            tool_delay=tool_delay,
            enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets,
            save_trajectories=save_trajectories,
            verbose_logging=verbose_logging,
            quiet_mode=quiet_mode,
            ephemeral_system_prompt=ephemeral_system_prompt,
            log_prefix_chars=log_prefix_chars,
            log_prefix=log_prefix,
            providers_allowed=providers_allowed,
            providers_ignored=providers_ignored,
            providers_order=providers_order,
            provider_sort=provider_sort,
            provider_require_parameters=provider_require_parameters,
            provider_data_collection=provider_data_collection,
            openrouter_min_coding_score=openrouter_min_coding_score,
            session_id=session_id,
            tool_progress_callback=tool_progress_callback,
            tool_start_callback=tool_start_callback,
            tool_complete_callback=tool_complete_callback,
            thinking_callback=thinking_callback,
            reasoning_callback=reasoning_callback,
            clarify_callback=clarify_callback,
            step_callback=step_callback,
            stream_delta_callback=stream_delta_callback,
            interim_assistant_callback=interim_assistant_callback,
            tool_gen_callback=tool_gen_callback,
            status_callback=status_callback,
            max_tokens=max_tokens,
            reasoning_config=reasoning_config,
            service_tier=service_tier,
            request_overrides=request_overrides,
            prefill_messages=prefill_messages,
            platform=platform,
            user_id=user_id,
            user_id_alt=user_id_alt,
            user_name=user_name,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            thread_id=thread_id,
            gateway_session_key=gateway_session_key,
            skip_context_files=skip_context_files,
            load_soul_identity=load_soul_identity,
            skip_memory=skip_memory,
            session_db=session_db,
            parent_session_id=parent_session_id,
            iteration_budget=iteration_budget,
            fallback_model=fallback_model,
            credential_pool=credential_pool,
            checkpoints_enabled=checkpoints_enabled,
            checkpoint_max_snapshots=checkpoint_max_snapshots,
            checkpoint_max_total_size_mb=checkpoint_max_total_size_mb,
            checkpoint_max_file_size_mb=checkpoint_max_file_size_mb,
            pass_session_id=pass_session_id,
        )

    def _get_session_db_for_recall(self):
        """Return a SessionDB for recall, lazily creating it if an entrypoint forgot.

        Most frontends pass ``session_db`` into ``AIAgent`` explicitly, but recall
        is important enough that a missing constructor argument should degrade by
        opening the default state DB instead of making the advertised
        ``session_search`` tool unusable.
        """
        if self._session_db is not None:
            return self._session_db
        try:
            from hermes_state import SessionDB

            self._session_db = SessionDB()
            return self._session_db
        except Exception as exc:
            logger.debug("SessionDB unavailable for recall", exc_info=True)
            return None

    def _ensure_db_session(self) -> None:
        """Create session DB row on first use. Disables _session_db on failure."""
        if self._session_db_created or not self._session_db:
            return
        try:
            self._session_db.create_session(
                session_id=self.session_id,
                source=self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
                model=self.model,
                model_config=self._session_init_model_config,
                system_prompt=self._cached_system_prompt,
                user_id=None,
                parent_session_id=self._parent_session_id,
            )
            self._session_db_created = True
        except Exception as e:
            # Transient failure (e.g. SQLite lock). Keep _session_db alive —
            # _session_db_created stays False so next run_conversation() retries.
            logger.warning(
                "Session DB creation failed (will retry next turn): %s", e
            )

    def _transition_context_engine_session(
        self,
        *,
        old_session_id: Optional[str] = None,
        new_session_id: Optional[str] = None,
        previous_messages: Optional[list] = None,
        carry_over_context: bool = False,
        reset_engine: bool = True,
        **extra_context,
    ) -> None:
        """Notify the active context engine about a host session transition.

        Generic host-side lifecycle helper. The built-in compressor keeps its
        existing reset behavior; plugin engines that implement richer hooks
        (``on_session_end``, ``on_session_reset``, ``on_session_start``,
        ``carry_over_new_session_context``) can flush old-session state,
        reset runtime counters, bind to the new session, and optionally
        carry retained context forward.
        """
        engine = getattr(self, "context_compressor", None)
        if not engine:
            return

        if old_session_id and previous_messages is not None and hasattr(engine, "on_session_end"):
            try:
                engine.on_session_end(old_session_id, previous_messages)
            except Exception as exc:
                logger.debug("context engine on_session_end during transition: %s", exc)

        if reset_engine and hasattr(engine, "on_session_reset"):
            try:
                engine.on_session_reset()
            except Exception as exc:
                logger.debug("context engine on_session_reset during transition: %s", exc)

        should_start = bool(
            old_session_id
            or previous_messages is not None
            or carry_over_context
            or extra_context
        )
        target_session_id = new_session_id or getattr(self, "session_id", "") or ""
        if should_start and target_session_id and hasattr(engine, "on_session_start"):
            start_context = {
                "old_session_id": old_session_id,
                "carry_over_context": carry_over_context,
                "platform": getattr(self, "platform", None) or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
                "model": getattr(self, "model", ""),
                "context_length": getattr(engine, "context_length", None),
                "conversation_id": getattr(self, "_gateway_session_key", None),
            }
            start_context.update(extra_context)
            start_context = {k: v for k, v in start_context.items() if v not in (None, "")}
            try:
                engine.on_session_start(target_session_id, **start_context)
            except Exception as exc:
                logger.debug("context engine on_session_start during transition: %s", exc)

        if (
            carry_over_context
            and old_session_id
            and target_session_id
            and hasattr(engine, "carry_over_new_session_context")
        ):
            try:
                engine.carry_over_new_session_context(old_session_id, target_session_id)
            except Exception as exc:
                logger.debug("context engine carry_over_new_session_context during transition: %s", exc)

    def reset_session_state(
        self,
        previous_messages: Optional[list] = None,
        old_session_id: Optional[str] = None,
        carry_over_context: bool = False,
    ):
        """Reset all session-scoped token counters to 0 for a fresh session.
        
        This method encapsulates the reset logic for all session-level metrics
        including:
        - Token usage counters (input, output, total, prompt, completion)
        - Cache read/write tokens
        - API call count
        - Reasoning tokens
        - Estimated cost tracking
        - Context compressor internal counters
        
        The method safely handles optional attributes (e.g., context compressor)
        using ``hasattr`` checks.

        When ``previous_messages`` / ``old_session_id`` / ``carry_over_context``
        are provided, the active context engine is notified through the
        full transition lifecycle (``_transition_context_engine_session``)
        instead of a bare reset. Default callers pass nothing and keep the
        existing reset-only behavior.
        """
        # Token usage counters
        self.session_total_tokens = 0
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_cache_read_tokens = 0
        self.session_cache_write_tokens = 0
        self.session_reasoning_tokens = 0
        self.session_api_calls = 0
        self.session_estimated_cost_usd = 0.0
        self.session_cost_status = "unknown"
        self.session_cost_source = "none"
        
        # Turn counter (added after reset_session_state was first written — #2635)
        self._user_turn_count = 0

        # Context engine reset/transition (works for built-in compressor and plugins)
        self._transition_context_engine_session(
            old_session_id=old_session_id,
            new_session_id=getattr(self, "session_id", None),
            previous_messages=previous_messages,
            carry_over_context=carry_over_context,
            reset_engine=True,
        )

    def _ensure_lmstudio_runtime_loaded(self, config_context_length: Optional[int] = None) -> None:
        """
        Preload the LM Studio model with at least Hermes' minimum context.
        """
        if (self.provider or "").strip().lower() != "lmstudio":
            return
        try:
            from agent.model_metadata import MINIMUM_CONTEXT_LENGTH
            from hermes_cli.models import ensure_lmstudio_model_loaded
            if config_context_length is None:
                config_context_length = getattr(self, "_config_context_length", None)
            target_ctx = max(config_context_length or 0, MINIMUM_CONTEXT_LENGTH)
            loaded_ctx = ensure_lmstudio_model_loaded(
                self.model, self.base_url, getattr(self, "api_key", ""), target_ctx,
            )
            if loaded_ctx:
                # Push into the live compressor so the status bar reflects the
                # real loaded ctx the moment the load resolves, instead of
                # holding the previous model's value (or "ctx --") through the
                # next render tick.
                cc = getattr(self, "context_compressor", None)
                if cc is not None:
                    cc.update_model(
                        model=self.model,
                        context_length=loaded_ctx,
                        base_url=self.base_url,
                        api_key=getattr(self, "api_key", ""),
                        provider=self.provider,
                        api_mode=self.api_mode,
                    )
        except Exception as err:
            logger.debug("LM Studio preload skipped: %s", err)

    def switch_model(self, new_model, new_provider, api_key='', base_url='', api_mode=''):
        """Forwarder — see ``agent.agent_runtime_helpers.switch_model``."""
        from agent.agent_runtime_helpers import switch_model
        return switch_model(self, new_model, new_provider, api_key, base_url, api_mode)

    def _safe_print(self, *args, **kwargs):
        """Print that silently handles broken pipes / closed stdout.

        In headless environments (systemd, Docker, nohup) stdout may become
        unavailable mid-session.  A raw ``print()`` raises ``OSError`` which
        can crash cron jobs and lose completed work.

        Internally routes through ``self._print_fn`` (default: builtin
        ``print``) so callers such as the CLI can inject a renderer that
        handles ANSI escape sequences properly (e.g. prompt_toolkit's
        ``print_formatted_text(ANSI(...))``) without touching this method.
        """
        try:
            fn = self._print_fn or print
            fn(*args, **kwargs)
        except (OSError, ValueError):
            pass

    def _vprint(self, *args, force: bool = False, **kwargs):
        """Verbose print — suppressed when actively streaming tokens.

        Pass ``force=True`` for error/warning messages that should always be
        shown even during streaming playback (TTS or display).

        During tool execution (``_executing_tools`` is True), printing is
        allowed even with stream consumers registered because no tokens
        are being streamed at that point.

        After the main response has been delivered and the remaining tool
        calls are post-response housekeeping (``_mute_post_response``),
        all non-forced output is suppressed.

        ``suppress_status_output`` is a stricter CLI automation mode used by
        parseable single-query flows such as ``hermes chat -q``. In that mode,
        all status/diagnostic prints routed through ``_vprint`` are suppressed
        so stdout stays machine-readable.
        """
        if getattr(self, "suppress_status_output", False):
            return
        if not force and getattr(self, "_mute_post_response", False):
            return
        if not force and self._has_stream_consumers() and not self._executing_tools:
            return
        self._safe_print(*args, **kwargs)

    def _should_start_quiet_spinner(self) -> bool:
        """Return True when quiet-mode spinner output has a safe sink.

        In headless/stdio-protocol environments, a raw spinner with no custom
        ``_print_fn`` falls back to ``sys.stdout`` and can corrupt protocol
        streams such as ACP JSON-RPC. Allow quiet spinners only when either:
        - output is explicitly rerouted via ``_print_fn``; or
        - stdout is a real TTY.
        """
        if self._print_fn is not None:
            return True
        stream = getattr(sys, "stdout", None)
        if stream is None:
            return False
        try:
            return bool(stream.isatty())
        except (AttributeError, ValueError, OSError):
            return False

    def _should_emit_quiet_tool_messages(self) -> bool:
        """Return True when quiet-mode tool summaries should print directly.

        Quiet mode is used by both the interactive CLI and embedded/library
        callers. The CLI may still want compact progress hints when no callback
        owns rendering. Embedded/library callers, on the other hand, expect
        quiet mode to be truly silent.
        """
        return (
            self.quiet_mode
            and not self.tool_progress_callback
            and getattr(self, "platform", "") == "cli"
        )

    def _emit_status(self, message: str) -> None:
        """Emit a lifecycle status message to both CLI and gateway channels.

        CLI users see the message via ``_vprint(force=True)`` so it is always
        visible regardless of verbose/quiet mode.  Gateway consumers receive
        it through ``status_callback("lifecycle", ...)``.

        This helper never raises — exceptions are swallowed so it cannot
        interrupt the retry/fallback logic.
        """
        try:
            self._vprint(f"{self.log_prefix}{message}", force=True)
        except Exception:
            pass
        if self.status_callback:
            try:
                self.status_callback("lifecycle", message)
            except Exception:
                logger.debug("status_callback error in _emit_status", exc_info=True)

    def _emit_warning(self, message: str) -> None:
        """Emit a user-visible warning through the same status plumbing.

        Unlike debug logs, these warnings are meant for degraded side paths
        such as auxiliary compression or memory flushes where the main turn can
        continue but the user needs to know something important failed.
        """
        try:
            self._vprint(f"{self.log_prefix}{message}", force=True)
        except Exception:
            pass
        if self.status_callback:
            try:
                self.status_callback("warn", message)
            except Exception:
                logger.debug("status_callback error in _emit_warning", exc_info=True)

    # ── Buffered retry/fallback status ────────────────────────────────────
    # Retry and fallback chains were flooding the CLI/gateway with status
    # noise that users found confusing: a single transient 429 could produce
    # 10+ "Provider/Endpoint/Retrying in 5s..." lines before the request
    # eventually succeeded.  The buffered helpers below capture these
    # status messages instead of emitting them immediately.  They are
    # flushed (shown to the user) ONLY when every retry and fallback has
    # been exhausted; on success they are silently dropped.  Backend logs
    # (agent.log) are unaffected — every individual emission site still
    # writes to ``logger.warning`` / ``logger.info`` for diagnosis.

    def _buffer_status(self, message: str) -> None:
        """Buffer a retry/fallback status message.

        Stored as a (kind, text) tuple where ``kind`` is one of:
        - ``"status"``  -> replays via ``_emit_status``
        - ``"vprint"``  -> replays via ``_vprint(force=True)``
        - ``"warn"``    -> replays via ``_emit_warning``
        Used to defer noisy retry chatter until we know whether the
        turn ultimately recovered or failed.
        """
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf is None:
                buf = []
                self._retry_status_buffer = buf
            buf.append(("status", message))
        except Exception:
            # Never break the retry loop on a buffer hiccup.
            pass

    def _buffer_vprint(self, message: str) -> None:
        """Buffer a vprint(force=True) retry/fallback line."""
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf is None:
                buf = []
                self._retry_status_buffer = buf
            buf.append(("vprint", message))
        except Exception:
            pass

    def _clear_status_buffer(self) -> None:
        """Drop buffered retry messages — call on successful recovery."""
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf:
                buf.clear()
        except Exception:
            pass

    def _flush_status_buffer(self) -> None:
        """Emit buffered retry messages — call on terminal failure.

        Surfaces the full retry/fallback trace so the user can see what
        was tried before the turn gave up.
        """
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if not buf:
                return
            # Drain first so a callback exception doesn't double-emit.
            messages = list(buf)
            buf.clear()
            for kind, msg in messages:
                try:
                    if kind == "status":
                        self._emit_status(msg)
                    elif kind == "warn":
                        self._emit_warning(msg)
                    else:
                        self._vprint(f"{self.log_prefix}{msg}", force=True)
                except Exception:
                    pass
        except Exception:
            pass

    def _disable_codex_reasoning_replay(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """Disable Responses encrypted reasoning replay and strip cached state.

        Called from the conversation_loop retry path when the provider
        rejects a replayed ``codex_reasoning_items`` blob with HTTP 400
        ``invalid_encrypted_content``.  Sets ``self._codex_reasoning_replay_enabled``
        to ``False`` (consumed by ``codex_responses_adapter._chat_messages_to_responses_input``
        and ``transports/codex.py`` to drop ``reasoning.encrypted_content``
        from subsequent requests) and pops ``codex_reasoning_items`` from
        every assistant message in ``messages`` so they cannot be replayed
        again later in the session.

        Returns a small stats dict ``{"messages": int, "items": int}``
        counting what was stripped — purely for diagnostic logging.
        """
        stripped_messages = 0
        stripped_items = 0
        target_messages = messages if isinstance(messages, list) else []

        for msg in target_messages:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            items = msg.pop("codex_reasoning_items", None)
            if isinstance(items, list) and items:
                stripped_messages += 1
                stripped_items += len(items)

        self._codex_reasoning_replay_enabled = False
        return {"messages": stripped_messages, "items": stripped_items}

    # Stream-diagnostic class header preserved for backward compat —
    # actual list lives in ``agent.stream_diag.STREAM_DIAG_HEADERS``.
    from agent.stream_diag import STREAM_DIAG_HEADERS as _STREAM_DIAG_HEADERS  # noqa: E402

    @staticmethod
    def _stream_diag_init() -> Dict[str, Any]:
        """Forwarder — see ``agent.stream_diag.stream_diag_init``."""
        from agent.stream_diag import stream_diag_init
        return stream_diag_init()

    def _stream_diag_capture_response(
        self, diag: Dict[str, Any], http_response: Any
    ) -> None:
        """Forwarder — see ``agent.stream_diag.stream_diag_capture_response``."""
        from agent.stream_diag import stream_diag_capture_response
        stream_diag_capture_response(self, diag, http_response)

    @staticmethod
    def _flatten_exception_chain(error: BaseException) -> str:
        """Forwarder — see ``agent.stream_diag.flatten_exception_chain``."""
        from agent.stream_diag import flatten_exception_chain
        return flatten_exception_chain(error)

    def _is_provider_stream_parse_error(self, error: BaseException) -> bool:
        """Return True for malformed provider streaming data from SDK parsers.

        Some Anthropic-compatible streaming providers can send a malformed
        event-stream frame.  The Anthropic SDK surfaces that as a plain
        ``ValueError`` such as ``expected ident at line 1 column 149``.  That
        is provider wire-format trouble, not local request validation, so it
        should follow the same retry path as a truncated JSON body.
        """
        if getattr(self, "api_mode", None) != "anthropic_messages":
            return False
        if not isinstance(error, ValueError):
            return False
        if isinstance(error, (UnicodeEncodeError, json.JSONDecodeError)):
            return False
        message = str(error).strip().lower()
        return "expected ident at line" in message

    def _log_stream_retry(
        self,
        *,
        kind: str,
        error: BaseException,
        attempt: int,
        max_attempts: int,
        mid_tool_call: bool,
        diag: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Forwarder — see ``agent.stream_diag.log_stream_retry``."""
        from agent.stream_diag import log_stream_retry
        log_stream_retry(
            self, kind=kind, error=error, attempt=attempt,
            max_attempts=max_attempts, mid_tool_call=mid_tool_call, diag=diag,
        )

    def _emit_stream_drop(
        self,
        *,
        error: BaseException,
        attempt: int,
        max_attempts: int,
        mid_tool_call: bool,
        diag: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Forwarder — see ``agent.stream_diag.emit_stream_drop``."""
        from agent.stream_diag import emit_stream_drop
        emit_stream_drop(
            self, error=error, attempt=attempt, max_attempts=max_attempts,
            mid_tool_call=mid_tool_call, diag=diag,
        )

    def _emit_auxiliary_failure(self, task: str, exc: BaseException) -> None:
        """Surface a compact warning for failed auxiliary work."""
        try:
            detail = self._summarize_api_error(exc)
        except Exception:
            detail = str(exc)
        detail = (detail or exc.__class__.__name__).strip()
        if len(detail) > 220:
            detail = detail[:217].rstrip() + "..."
        self._emit_warning(f"⚠ Auxiliary {task} failed: {detail}")

    def _current_main_runtime(self) -> Dict[str, str]:
        """Return the live main runtime for session-scoped auxiliary routing."""
        return {
            "model": getattr(self, "model", "") or "",
            "provider": getattr(self, "provider", "") or "",
            "base_url": getattr(self, "base_url", "") or "",
            "api_key": getattr(self, "api_key", "") or "",
            "api_mode": getattr(self, "api_mode", "") or "",
        }

    def _check_compression_model_feasibility(self) -> None:
        """Forwarder — see ``agent.conversation_compression.check_compression_model_feasibility``."""
        from agent.conversation_compression import check_compression_model_feasibility
        check_compression_model_feasibility(self)

    def _replay_compression_warning(self) -> None:
        """Forwarder — see ``agent.conversation_compression.replay_compression_warning``."""
        from agent.conversation_compression import replay_compression_warning
        replay_compression_warning(self)

    def _is_direct_openai_url(self, base_url: str = None) -> bool:
        """Return True when a base URL targets OpenAI's native API."""
        if base_url is not None:
            hostname = base_url_hostname(base_url)
        else:
            hostname = getattr(self, "_base_url_hostname", "") or base_url_hostname(
                getattr(self, "_base_url_lower", "")
            )
        return hostname == "api.openai.com"

    def _is_azure_openai_url(self, base_url: str = None) -> bool:
        """Return True when a base URL targets Azure OpenAI.

        Azure OpenAI exposes an OpenAI-compatible endpoint at
        ``{resource}.openai.azure.com/openai/v1`` that accepts the
        standard ``openai`` Python client.  Unlike api.openai.com it
        does NOT support the Responses API — gpt-5.x models are served
        on the regular ``/chat/completions`` path — so routing decisions
        must treat Azure separately from direct OpenAI.
        """
        if base_url is not None:
            url = str(base_url).lower()
        else:
            url = getattr(self, "_base_url_lower", "") or ""
        return "openai.azure.com" in url

    def _is_github_copilot_url(self, base_url: str = None) -> bool:
        """Return True when a base URL targets GitHub Copilot's OpenAI-compatible API."""
        if base_url is not None:
            hostname = base_url_hostname(base_url)
        else:
            hostname = getattr(self, "_base_url_hostname", "") or base_url_hostname(
                getattr(self, "_base_url_lower", "")
            )
        return hostname == "api.githubcopilot.com"

    def _resolved_api_call_timeout(self) -> float:
        """Resolve the effective per-call request timeout in seconds.

        Priority:
          1. ``providers.<id>.models.<model>.timeout_seconds`` (per-model override)
          2. ``providers.<id>.request_timeout_seconds`` (provider-wide)
          3. ``HERMES_API_TIMEOUT`` env var (legacy escape hatch)
          4. 1800.0s default

        Used by OpenAI-wire chat completions (streaming and non-streaming) so
        the per-provider config knob wins over the 1800s default.  Without this
        helper, the hardcoded ``HERMES_API_TIMEOUT`` fallback would always be
        passed as a per-call ``timeout=`` kwarg, overriding the client-level
        timeout the AIAgent.__init__ path configured.
        """
        cfg = get_provider_request_timeout(self.provider, self.model)
        if cfg is not None:
            return cfg
        return float(os.getenv("HERMES_API_TIMEOUT", 1800.0))

    def _resolved_api_call_stale_timeout_base(self) -> tuple[float, bool]:
        """Resolve the base non-stream stale timeout and whether it is implicit.

        Priority:
          1. ``providers.<id>.models.<model>.stale_timeout_seconds``
          2. ``providers.<id>.stale_timeout_seconds``
          3. ``HERMES_API_CALL_STALE_TIMEOUT`` env var
          4. 90.0s default (time-to-first-byte for non-streaming / Codex
             internal-streaming requests; lowered from 300s in May 2026 so
             fallback providers kick in faster when upstream providers
             stall).  The detector still scales up for large contexts in
             ``_compute_non_stream_stale_timeout``.

        Returns ``(timeout_seconds, uses_implicit_default)`` so the caller can
        preserve legacy behaviors that only apply when the user has *not*
        explicitly configured a stale timeout, such as auto-disabling the
        detector for local endpoints.
        """
        cfg = get_provider_stale_timeout(self.provider, self.model)
        if cfg is not None:
            return cfg, False

        env_timeout = os.getenv("HERMES_API_CALL_STALE_TIMEOUT")
        if env_timeout is not None:
            return float(env_timeout), False

        return 90.0, True

    def _compute_non_stream_stale_timeout(self, api_payload: Any) -> float:
        """Compute the effective non-stream stale timeout for this request.

        Accepts either the full ``api_kwargs`` dict (Chat Completions or
        Responses API) or a legacy ``messages`` list.  Context-size scaling
        applies the same way to both shapes via
        :func:`agent.chat_completion_helpers.estimate_request_context_tokens`.
        """
        stale_base, uses_implicit_default = self._resolved_api_call_stale_timeout_base()
        base_url = getattr(self, "_base_url", None) or self.base_url or ""
        if uses_implicit_default and base_url and is_local_endpoint(base_url):
            return float("inf")

        from agent.chat_completion_helpers import estimate_request_context_tokens
        est_tokens = estimate_request_context_tokens(api_payload)
        if est_tokens > 100_000:
            return max(stale_base, 240.0)
        if est_tokens > 50_000:
            return max(stale_base, 150.0)
        return stale_base

    def _codex_silent_hang_hint(self, model: Optional[str] = None) -> Optional[str]:
        """Return an actionable hint when this request matches a known
        Codex silent-reject configuration, else ``None``.

        The ChatGPT Codex backend (``chatgpt.com/backend-api/codex``) has
        historically silently dropped certain model requests: the connection
        is accepted but no stream events are emitted and no error is raised.
        The stale-call detector ends the hang, but a generic "timed out"
        message gives the user no path forward.

        This helper substitutes an actionable hint into the stale-timeout
        warning when the request matches a known silent-reject pattern.
        Currently flagged: ``gpt-5.5`` family on the Codex backend.  See
        hermes-agent #21444 for the symptom history.  The upstream backend
        behavior has historically come and gone with ChatGPT entitlement
        changes — the heuristic stays in place as future-proofing even when
        the symptom is dormant.

        Does NOT fix the backend issue.  Only converts an opaque stale-timeout
        into actionable text so users learn the workaround in seconds rather
        than digging through logs.
        """
        if self.api_mode != "codex_responses":
            return None
        is_codex_backend = (
            self.provider == "openai-codex"
            or (
                getattr(self, "_base_url_hostname", "") == "chatgpt.com"
                and "/backend-api/codex" in (getattr(self, "_base_url_lower", "") or "")
            )
        )
        if not is_codex_backend:
            return None
        eff_model = (model if model is not None else self.model) or ""
        model_lower = eff_model.lower()
        # Match the gpt-5.5 family — bare ``gpt-5.5``, ``gpt-5.5-codex``,
        # vendor-prefixed variants like ``openai/gpt-5.5``, and any future
        # ``gpt-5.5-*`` SKU.  Anchor at a word boundary on either side so
        # unrelated tokens like ``gpt-5.50`` do not match.
        if not re.search(r"(?:^|[/\-_])gpt-5\.5(?:$|[\-_])", model_lower):
            return None
        return (
            f"Codex backend appears to be silently rejecting {eff_model!r} "
            "on chatgpt.com/backend-api/codex (no stream events, no error). "
            "This is a known backend-side pattern that has affected ChatGPT "
            "Plus accounts intermittently. "
            "Workaround: try `gpt-5.4` on the same OAuth profile, or `gpt-5.3-codex`, "
            "or switch to a different model/provider in your fallback chain. "
            "Some ChatGPT Codex accounts do not support `gpt-5.4-codex`. "
            "See hermes-agent#21444 for symptom history."
        )

    def _is_openrouter_url(self) -> bool:
        """Return True when the base URL targets OpenRouter."""
        return base_url_host_matches(self._base_url_lower, "openrouter.ai")

    def _anthropic_prompt_cache_policy(
        self,
        *,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        api_mode: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[bool, bool]:
        """Forwarder — see ``agent.agent_runtime_helpers.anthropic_prompt_cache_policy``."""
        from agent.agent_runtime_helpers import anthropic_prompt_cache_policy
        return anthropic_prompt_cache_policy(self, provider=provider, base_url=base_url, api_mode=api_mode, model=model)

    @staticmethod
    def _model_requires_responses_api(model: str) -> bool:
        """Return True for models that require the Responses API path.

        GPT-5.x models are rejected on /v1/chat/completions by both
        OpenAI and OpenRouter (error: ``unsupported_api_for_model``).
        Detect these so the correct api_mode is set regardless of
        which provider is serving the model.
        """
        m = model.lower()
        # Strip vendor prefix (e.g. "openai/gpt-5.4" → "gpt-5.4")
        if "/" in m:
            m = m.rsplit("/", 1)[-1]
        return m.startswith("gpt-5")

    @staticmethod
    def _provider_model_requires_responses_api(
        model: str,
        *,
        provider: Optional[str] = None,
    ) -> bool:
        """Return True when this provider/model pair should use Responses API."""
        normalized_provider = (provider or "").strip().lower()
        # Nous serves GPT-5.x models via its OpenAI-compatible chat
        # completions endpoint; its /v1/responses endpoint returns 404.
        if normalized_provider == "nous":
            return False
        if normalized_provider == "copilot":
            try:
                from hermes_cli.models import _should_use_copilot_responses_api
                return _should_use_copilot_responses_api(model)
            except Exception:
                # Fall back to the generic GPT-5 rule if Copilot-specific
                # logic is unavailable for any reason.
                pass
        return AIAgent._model_requires_responses_api(model)

    def _max_tokens_param(self, value: int) -> dict:
        """Return the correct max tokens kwarg for the current provider.

        OpenAI's newer models (gpt-4o, o-series, gpt-5+) require
        'max_completion_tokens'. Azure OpenAI also requires
        'max_completion_tokens' for gpt-5.x models served via the
        OpenAI-compatible endpoint. OpenRouter, local models, and older
        OpenAI models use 'max_tokens'.
        """
        if self._is_direct_openai_url() or self._is_azure_openai_url() or self._is_github_copilot_url():
            return {"max_completion_tokens": value}
        return {"max_tokens": value}

    @staticmethod
    def _requested_output_cap_from_api_kwargs(api_kwargs: Any) -> Optional[int]:
        """Extract the outgoing response token cap from a prepared request."""
        if not isinstance(api_kwargs, dict):
            return None
        for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
            raw = api_kwargs.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    def _has_content_after_think_block(self, content: str) -> bool:
        """
        Check if content has actual text after any reasoning/thinking blocks.

        This detects cases where the model only outputs reasoning but no actual
        response, which indicates an incomplete generation that should be retried.
        Must stay in sync with _strip_think_blocks() tag variants.

        Args:
            content: The assistant message content to check

        Returns:
            True if there's meaningful content after think blocks, False otherwise
        """
        if not content:
            return False

        # Remove all reasoning tag variants (must match _strip_think_blocks)
        cleaned = self._strip_think_blocks(content)

        # Check if there's any non-whitespace content remaining
        return bool(cleaned.strip())

    def _strip_think_blocks(self, content: str) -> str:
        """Forwarder — see ``agent.agent_runtime_helpers.strip_think_blocks``."""
        from agent.agent_runtime_helpers import strip_think_blocks
        return strip_think_blocks(self, content)

    @staticmethod
    def _has_natural_response_ending(content: str) -> bool:
        """Heuristic: does visible assistant text look intentionally finished?"""
        if not content:
            return False
        stripped = content.rstrip()
        if not stripped:
            return False
        if stripped.endswith("```"):
            return True
        if stripped.endswith('^'):
            return True
        last = stripped[-1]
        if last in '.!?:)"\']}。！？：）】」』》^':
            return True
        # Emoji ranges (Misc Symbols, Dingbats, Emoticons, Supplemental, etc.)
        if ord(last) >= 0x1F300:
            return True
        return False

    def _is_ollama_glm_backend(self) -> bool:
        """Detect the narrow backend family affected by Ollama/GLM stop misreports."""
        model_lower = (self.model or "").lower()
        provider_lower = (self.provider or "").lower()
        if "glm" not in model_lower and provider_lower != "zai":
            return False
        if "ollama" in self._base_url_lower or ":11434" in self._base_url_lower:
            return True
        return bool(self.base_url and is_local_endpoint(self.base_url))

    def _should_treat_stop_as_truncated(
        self,
        finish_reason: str,
        assistant_message,
        messages: Optional[list] = None,
    ) -> bool:
        """Detect conservative stop->length misreports for Ollama-hosted GLM models."""
        if finish_reason != "stop" or self.api_mode != "chat_completions":
            return False
        if not self._is_ollama_glm_backend():
            return False
        if not any(
            isinstance(msg, dict) and msg.get("role") == "tool"
            for msg in (messages or [])
        ):
            return False
        if assistant_message is None or getattr(assistant_message, "tool_calls", None):
            return False

        content = getattr(assistant_message, "content", None)
        if not isinstance(content, str):
            return False

        visible_text = self._strip_think_blocks(content).strip()
        if not visible_text:
            return False
        if len(visible_text) < 20 or not re.search(r"\s", visible_text):
            return False

        return not self._has_natural_response_ending(visible_text)

    def _looks_like_codex_intermediate_ack(
        self,
        user_message: str,
        assistant_content: str,
        messages: List[Dict[str, Any]],
    ) -> bool:
        """Forwarder — see ``agent.agent_runtime_helpers.looks_like_codex_intermediate_ack``."""
        from agent.agent_runtime_helpers import looks_like_codex_intermediate_ack
        return looks_like_codex_intermediate_ack(self, user_message, assistant_content, messages)

    def _extract_reasoning(self, assistant_message) -> Optional[str]:
        """Forwarder — see ``agent.agent_runtime_helpers.extract_reasoning``."""
        from agent.agent_runtime_helpers import extract_reasoning
        return extract_reasoning(self, assistant_message)

    def _cleanup_task_resources(self, task_id: str) -> None:
        """Forwarder — see ``agent.chat_completion_helpers.cleanup_task_resources``."""
        from agent.chat_completion_helpers import cleanup_task_resources
        return cleanup_task_resources(self, task_id)

    # ------------------------------------------------------------------
    # Background memory/skill review — prompts live in agent.background_review
    # ------------------------------------------------------------------
    from agent.background_review import (
        _MEMORY_REVIEW_PROMPT,
        _SKILL_REVIEW_PROMPT,
        _COMBINED_REVIEW_PROMPT,
    )

    @staticmethod
    def _summarize_background_review_actions(
        review_messages: List[Dict],
        prior_snapshot: List[Dict],
    ) -> List[str]:
        """Forwarder — see ``agent.background_review.summarize_background_review_actions``."""
        from agent.background_review import summarize_background_review_actions
        return summarize_background_review_actions(review_messages, prior_snapshot)

    def _spawn_background_review(
        self,
        messages_snapshot: List[Dict],
        review_memory: bool = False,
        review_skills: bool = False,
    ) -> None:
        """Spawn the background memory/skill review thread.

        Thin wrapper — the heavy lifting lives in
        ``agent.background_review.spawn_background_review_thread`` which
        returns the thread target.  ``threading.Thread`` is constructed
        here so existing tests that patch ``run_agent.threading.Thread``
        keep working.
        """
        from agent.background_review import spawn_background_review_thread
        target, _prompt = spawn_background_review_thread(
            self,
            messages_snapshot,
            review_memory=review_memory,
            review_skills=review_skills,
        )
        t = threading.Thread(target=target, daemon=True, name="bg-review")
        t.start()

    def _build_memory_write_metadata(
        self,
        *,
        write_origin: Optional[str] = None,
        execution_context: Optional[str] = None,
        task_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Forwarder — see ``agent.background_review.build_memory_write_metadata``."""
        from agent.background_review import build_memory_write_metadata
        return build_memory_write_metadata(
            self,
            write_origin=write_origin,
            execution_context=execution_context,
            task_id=task_id,
            tool_call_id=tool_call_id,
        )

    def _apply_persist_user_message_override(self, messages: List[Dict]) -> None:
        """Rewrite the current-turn user message before persistence/return.

        Some call paths need an API-only user-message variant without letting
        that synthetic text leak into persisted transcripts or resumed session
        history. When an override is configured for the active turn, mutate the
        in-memory messages list in place so both persistence and returned
        history stay clean.
        """
        idx = getattr(self, "_persist_user_message_idx", None)
        override = getattr(self, "_persist_user_message_override", None)
        if override is None or idx is None:
            return
        if 0 <= idx < len(messages):
            msg = messages[idx]
            if isinstance(msg, dict) and msg.get("role") == "user":
                msg["content"] = override

    def _persist_session(self, messages: List[Dict], conversation_history: List[Dict] = None):
        """Save session state to both JSON log and SQLite on any exit path.

        Ensures conversations are never lost, even on errors or early returns.
        """
        messages = self._drop_trailing_empty_response_scaffolding(messages)
        self._apply_persist_user_message_override(messages)
        self._session_messages = messages
        self._save_session_log(messages)
        self._flush_messages_to_session_db(messages, conversation_history)

    def _drop_trailing_empty_response_scaffolding(self, messages: List[Dict]) -> List[Dict]:
        """Remove private empty-response retry/failure scaffolding from transcript tails.

        Also rewinds past any trailing tool-result / assistant(tool_calls) pair
        that the failed iteration left hanging. Without this, the tail ends at
        a raw ``tool`` message and the next user turn lands as
        ``...tool, user, user`` — a protocol-invalid sequence that most
        providers silently reject (returns empty content), causing the
        empty-retry loop to fire forever. See #<TBD>.

        Mutates ``messages`` in place and returns it. In-place is the contract
        two of the three call sites rely on: both
        ``agent/conversation_loop.py`` sites discard the return value, so while
        this operated on a private ``list(messages)`` copy the scaffolding was
        never actually removed from the live transcript — leaving the sentinel
        in context for the next turn, which is the loop this exists to break.
        """
        # Pass 1: strip the flagged scaffolding messages themselves.
        dropped_scaffolding = False
        while (
            messages
            and isinstance(messages[-1], dict)
            and (
                messages[-1].get("_empty_recovery_synthetic")
                or messages[-1].get("_empty_terminal_sentinel")
            )
        ):
            messages.pop()
            dropped_scaffolding = True

        # Pass 2: if we stripped scaffolding, rewind through any trailing
        # tool-result messages plus the assistant(tool_calls) message that
        # produced them. This preserves role alternation so the next user
        # message follows a user or assistant message, not an orphan tool
        # result. Only runs when scaffolding was actually present — normal
        # conversation tails (real tool loops mid-progress) are untouched.
        if not dropped_scaffolding:
            return messages

        # Drop any trailing tool-result messages
        while (
            messages
            and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "tool"
        ):
            messages.pop()

        # Drop the assistant message that issued the tool calls, if the tail
        # now ends in an assistant-with-tool_calls (the pair that owned the
        # just-popped tool results). Without this, the tail is
        # ``assistant(tool_calls=...)`` with no tool answers, which some
        # providers also reject.
        if (
            messages
            and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "assistant"
            and messages[-1].get("tool_calls")
        ):
            messages.pop()

        return messages

    def _repair_message_sequence(self, messages: List[Dict]) -> int:
        """Forwarder — see ``agent.agent_runtime_helpers.repair_message_sequence``."""
        from agent.agent_runtime_helpers import repair_message_sequence
        return repair_message_sequence(self, messages)

    def _flush_messages_to_session_db(self, messages: List[Dict], conversation_history: List[Dict] = None):
        """Persist any un-flushed messages to the SQLite session store.

        Uses _last_flushed_db_idx to track which messages have already been
        written, so repeated calls (from multiple exit paths) only write
        truly new messages — preventing the duplicate-write bug (#860).
        """
        if not self._session_db:
            return
        self._apply_persist_user_message_override(messages)
        try:
            # Retry row creation if the earlier attempt failed transiently.
            if not self._session_db_created:
                self._ensure_db_session()
            start_idx = len(conversation_history) if conversation_history else 0
            flush_from = max(start_idx, self._last_flushed_db_idx)
            for idx in range(flush_from, len(messages)):
                msg = messages[idx]
                role = msg.get("role", "unknown")
                content = msg.get("content")
                # Persist multimodal tool results as their text summary only —
                # base64 images would bloat the session DB and aren't useful
                # for cross-session replay.
                if _is_multimodal_tool_result(content):
                    content = _multimodal_text_summary(content)
                elif isinstance(content, list):
                    # List of OpenAI-style content parts: strip images, keep text.
                    _txt = []
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            _txt.append(str(p.get("text", "")))
                        elif isinstance(p, dict) and p.get("type") in {"image", "image_url", "input_image"}:
                            _txt.append("[screenshot]")
                    content = "\n".join(_txt) if _txt else None
                tool_calls_data = None
                if hasattr(msg, "tool_calls") and isinstance(msg.tool_calls, list) and msg.tool_calls:
                    tool_calls_data = [
                        {"name": tc.function.name, "arguments": tc.function.arguments}
                        for tc in msg.tool_calls
                    ]
                elif isinstance(msg.get("tool_calls"), list):
                    tool_calls_data = msg["tool_calls"]
                self._session_db.append_message(
                    session_id=self.session_id,
                    role=role,
                    content=content,
                    tool_name=msg.get("tool_name"),
                    tool_calls=tool_calls_data,
                    tool_call_id=msg.get("tool_call_id"),
                    finish_reason=msg.get("finish_reason"),
                    reasoning=msg.get("reasoning") if role == "assistant" else None,
                    reasoning_content=msg.get("reasoning_content") if role == "assistant" else None,
                    reasoning_details=msg.get("reasoning_details") if role == "assistant" else None,
                    codex_reasoning_items=msg.get("codex_reasoning_items") if role == "assistant" else None,
                    codex_message_items=msg.get("codex_message_items") if role == "assistant" else None,
                )
                self._last_flushed_db_idx = idx + 1
        except Exception as e:
            logger.warning("Session DB append_message failed: %s", e)

    def _get_messages_up_to_last_assistant(self, messages: List[Dict]) -> List[Dict]:
        """
        Get messages up to (but not including) the last assistant turn.
        
        This is used when we need to "roll back" to the last successful point
        in the conversation, typically when the final assistant message is
        incomplete or malformed.
        
        Args:
            messages: Full message list
            
        Returns:
            Messages up to the last complete assistant turn (ending with user/tool message)
        """
        if not messages:
            return []
        
        # Find the index of the last assistant message
        last_assistant_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        
        if last_assistant_idx is None:
            # No assistant message found, return all messages
            return messages.copy()
        
        # Return everything up to (not including) the last assistant message
        return messages[:last_assistant_idx]

    def _format_tools_for_system_message(self) -> str:
        """Forwarder — see ``agent.system_prompt.format_tools_for_system_message``."""
        from agent.system_prompt import format_tools_for_system_message
        return format_tools_for_system_message(self)

    def _convert_to_trajectory_format(self, messages: List[Dict[str, Any]], user_query: str, completed: bool) -> List[Dict[str, Any]]:
        """Forwarder — see ``agent.agent_runtime_helpers.convert_to_trajectory_format``."""
        from agent.agent_runtime_helpers import convert_to_trajectory_format
        return convert_to_trajectory_format(self, messages, user_query, completed)

    def _save_trajectory(self, messages: List[Dict[str, Any]], user_query: str, completed: bool):
        """
        Save conversation trajectory to JSONL file.
        
        Args:
            messages (List[Dict]): Complete message history
            user_query (str): Original user query
            completed (bool): Whether the conversation completed successfully
        """
        if not self.save_trajectories:
            return
        
        trajectory = self._convert_to_trajectory_format(messages, user_query, completed)
        _save_trajectory_to_file(trajectory, self.model, completed)

    @staticmethod
    def _is_entitlement_failure(
        error_context: Optional[Dict[str, Any]],
        status_code: Optional[int],
    ) -> bool:
        """Detect subscription/entitlement 403s that masquerade as auth failures.

        Returned True only when the body text matches a known entitlement
        shape AND the status is 401/403.  Refreshing an OAuth token cannot
        fix an unsubscribed account, so callers should surface the error
        instead of looping the credential pool.

        Current matches:
          * xAI OAuth: "do not have an active Grok subscription" /
            "out of available resources" / "does not have permission" + "grok"

        Disambiguator for xAI (#29344): the same ``code`` text ("The caller
        does not have permission to execute the specified operation") is
        returned for BOTH an unsubscribed account AND a stale OAuth access
        token.  xAI ships an explicit signal in the ``error`` field that
        tells the two apart: a ``[WKE=unauthenticated:...]`` suffix (and/or
        the ``OAuth2 access token could not be validated`` phrasing) means
        the credentials failed validation — that's recoverable by refreshing
        the token, NOT by surfacing an entitlement message.  When either
        signal is present we return False eagerly so the credential-pool
        refresh path runs, letting long-running TUI sessions recover from
        stale tokens without an exit/reopen cycle.

        Extend here for new providers as we discover them (Anthropic's
        Claude Max OAuth entitlement errors look distinct enough today that
        the existing 1M-context-beta branch handles them; revisit if other
        subscription tiers start producing the same loop signature).
        """
        if status_code not in {401, 403, None}:
            return False
        if not isinstance(error_context, dict):
            return False
        # Build a single lowercase haystack covering every field shape the
        # body might land in.  ``_extract_api_error_context`` normalises to
        # ``message``/``reason``, but callers (and the test suite) may also
        # hand us the raw body with ``code``/``error`` keys; cover both so
        # the WKE disambiguator below fires regardless of entry point.
        message = str(error_context.get("message") or "").lower()
        reason = str(error_context.get("reason") or "").lower()
        code = str(error_context.get("code") or "").lower()
        err = str(error_context.get("error") or "").lower()
        haystack = f"{message} {reason} {code} {err}"
        if not haystack.strip():
            return False
        # xAI's authoritative disambiguator for "stale token" vs
        # "unsubscribed account".  Both conditions share the same
        # permission-denied ``code`` text; only one carries this suffix.
        # Bail out before the entitlement keyword checks so a stale OAuth
        # token routes through the credential-refresh path instead of the
        # surface-error-as-entitlement path.  See #29344 for the long-
        # running TUI failure mode this closes.
        if "[wke=unauthenticated:" in haystack:
            return False
        if "oauth2 access token could not be validated" in haystack:
            return False
        if "do not have an active grok subscription" in haystack:
            return True
        if "out of available resources" in haystack and "grok" in haystack:
            return True
        if "does not have permission" in haystack and "grok" in haystack:
            return True
        return False

    @staticmethod
    def _decorate_xai_entitlement_error(detail: str) -> str:
        """Append a neutral hint when xAI's OAuth surface returns the
        permission-denied 403.

        xAI's ``/v1/responses`` endpoint replies to several distinct failure
        modes with the SAME body::

            {"code": "The caller does not have permission to execute the
             specified operation", "error": "You have either run out of
             available resources or do not have an active Grok subscription.
             Manage subscriptions at https://grok.com/?_s=usage or subscribe
             at https://grok.com/supergrok"}

        That body covers several real causes we cannot distinguish without
        more info from xAI.  The most common (and least obvious) one is
        that **X Premium+ does NOT include API access** — only standalone
        SuperGrok subscribers can use Hermes against xai-oauth.  Lots of
        users see Grok in their X app, assume it works here too, and hit
        this 403 with no idea why.  Lead the hint with that.

        Other possible causes:
          * No Grok subscription at all
          * SuperGrok tier doesn't include the requested model (e.g.
            grok-4.3 may need a higher tier)
          * Monthly quota exhausted (the ``?_s=usage`` URL hints at this)

        Surface the raw xAI text verbatim and point at
        https://grok.com/?_s=usage where the user can see WHICH applies.

        Matched once per detail string — won't double-decorate if the
        upstream already concatenated the same text.
        """
        if not detail:
            return detail
        lower = detail.lower()
        is_entitlement = (
            "do not have an active grok subscription" in lower
            or ("out of available resources" in lower and "grok" in lower)
            or ("does not have permission" in lower and "grok" in lower)
        )
        if not is_entitlement:
            return detail
        hint = (
            " — xAI rejected this OAuth account. NOTE: X Premium+ does NOT "
            "include xAI API access — only standalone SuperGrok subscribers "
            "can use this provider. Other possible causes: no Grok "
            "subscription, your tier doesn't include this model, or your "
            "quota is exhausted. Check https://grok.com/?_s=usage to see "
            "which, or run `/model` to switch providers."
        )
        # Idempotency: detect prior decoration by a substring unique to the
        # hint (not present in xAI's own body text).
        if "X Premium+ does NOT include" in detail:
            return detail
        return f"{detail}{hint}"

    @staticmethod
    def _summarize_api_error(error: Exception) -> str:
        """Extract a human-readable one-liner from an API error.

        Handles Cloudflare HTML error pages (502, 503, etc.) by pulling the
        <title> tag instead of dumping raw HTML.  Falls back to a truncated
        str(error) for everything else.
        """
        raw = str(error)

        if (
            isinstance(error, ValueError)
            and "expected ident at line" in raw.lower()
        ):
            return f"Malformed provider streaming response: {raw[:300]}"

        # Cloudflare / proxy HTML pages: grab the <title> for a clean summary
        if "<!DOCTYPE" in raw or "<html" in raw:
            m = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.IGNORECASE)
            title = m.group(1).strip() if m else "HTML error page (title not found)"
            # Also grab Cloudflare Ray ID if present
            ray = re.search(r"Cloudflare Ray ID:\s*<strong[^>]*>([^<]+)</strong>", raw)
            ray_id = ray.group(1).strip() if ray else None
            status_code = getattr(error, "status_code", None)
            parts = []
            if status_code:
                parts.append(f"HTTP {status_code}")
            parts.append(title)
            if ray_id:
                parts.append(f"Ray {ray_id}")
            return " — ".join(parts)

        # JSON body errors from OpenAI/Anthropic SDKs
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
            if msg:
                status_code = getattr(error, "status_code", None)
                prefix = f"HTTP {status_code}: " if status_code else ""
                return AIAgent._decorate_xai_entitlement_error(f"{prefix}{msg[:300]}")

        # Fallback: truncate the raw string but give more room than 200 chars
        status_code = getattr(error, "status_code", None)
        prefix = f"HTTP {status_code}: " if status_code else ""
        return AIAgent._decorate_xai_entitlement_error(f"{prefix}{raw[:500]}")

    def _mask_api_key_for_logs(self, key: Any) -> Optional[str]:
        # Azure Foundry Entra ID bearer providers are callables — never
        # invoke them in log paths; identify the auth surface instead.
        if callable(key) and not isinstance(key, str):
            return "<entra-id-bearer>"
        if not key:
            return None
        if len(key) <= 12:
            return "***"
        return f"{key[:8]}...{key[-4:]}"

    def _clean_error_message(self, error_msg: str) -> str:
        """
        Clean up error messages for user display, removing HTML content and truncating.
        
        Args:
            error_msg: Raw error message from API or exception
            
        Returns:
            Clean, user-friendly error message
        """
        if not error_msg:
            return "Unknown error"
            
        # Remove HTML content (common with CloudFlare and gateway error pages)
        if error_msg.strip().startswith('<!DOCTYPE html') or '<html' in error_msg:
            return "Service temporarily unavailable (HTML error page returned)"
            
        # Remove newlines and excessive whitespace
        cleaned = ' '.join(error_msg.split())
        
        # Truncate if too long
        if len(cleaned) > 150:
            cleaned = cleaned[:150] + "..."
            
        return cleaned

    @staticmethod
    def _extract_api_error_context(error: Exception) -> Dict[str, Any]:
        """Forwarder — see ``agent.agent_runtime_helpers.extract_api_error_context``."""
        from agent.agent_runtime_helpers import extract_api_error_context
        return extract_api_error_context(error)

    def _usage_summary_for_api_request_hook(self, response: Any) -> Optional[Dict[str, Any]]:
        """Token buckets for ``post_api_request`` plugins (no raw ``response`` object)."""
        if response is None:
            return None
        raw_usage = getattr(response, "usage", None)
        if not raw_usage:
            return None
        from dataclasses import asdict

        cu = normalize_usage(raw_usage, provider=self.provider, api_mode=self.api_mode)
        summary = asdict(cu)
        summary.pop("raw_usage", None)
        summary["prompt_tokens"] = cu.prompt_tokens
        summary["total_tokens"] = cu.total_tokens
        return summary

    def _dump_api_request_debug(
        self,
        api_kwargs: Dict[str, Any],
        *,
        reason: str,
        error: Optional[Exception] = None,
    ) -> Optional[Path]:
        """Forwarder — see ``agent.agent_runtime_helpers.dump_api_request_debug``."""
        from agent.agent_runtime_helpers import dump_api_request_debug
        return dump_api_request_debug(self, api_kwargs, reason=reason, error=error)

    @staticmethod
    def _clean_session_content(content: str) -> str:
        """Convert REASONING_SCRATCHPAD to think tags and clean up whitespace."""
        if not content:
            return content
        content = convert_scratchpad_to_think(content)
        content = re.sub(r'\n+(<think>)', r'\n\1', content)
        content = re.sub(r'(</think>)\n+', r'\1\n', content)
        return content.strip()

    @staticmethod
    def _redact_message_content(content):
        """Apply secret redaction to message content (str or list-of-parts).

        Handles both plain-string content and the OpenAI/Anthropic multimodal
        shape where ``content`` is a list of ``{"type": "text", "text": ...}``
        / ``{"type": "image_url", ...}`` / ``{"type": "input_text", "content": ...}``
        parts. Image / binary parts are left untouched; only text fields are
        passed through ``redact_sensitive_text``.

        Respects ``HERMES_REDACT_SECRETS`` via ``redact_sensitive_text`` —
        when disabled the helper is effectively a no-op.
        """
        if content is None:
            return content
        if isinstance(content, str):
            return redact_sensitive_text(content)
        if isinstance(content, list):
            redacted = []
            for part in content:
                if isinstance(part, dict):
                    part = dict(part)
                    if isinstance(part.get("text"), str):
                        part["text"] = redact_sensitive_text(part["text"])
                    if isinstance(part.get("content"), str):
                        part["content"] = redact_sensitive_text(part["content"])
                redacted.append(part)
            return redacted
        return content

    def _save_session_log(self, messages: List[Dict[str, Any]] = None):
        """Optional per-session JSON snapshot writer.

        Gated by ``sessions.write_json_snapshots`` (default False).  state.db
        is the canonical message store; this writer exists only for users
        whose external tooling consumes ``~/.hermes/sessions/session_{sid}.json``
        directly.  When the flag is off this is a fast no-op.

        When enabled, rewrites the snapshot after every persistence point with
        the full message list (assistant content normalized via
        ``_clean_session_content`` to convert REASONING_SCRATCHPAD to think
        tags).  The truncation guard ("don't overwrite a larger log with
        fewer messages") is preserved so resume + branch don't clobber a
        fuller existing snapshot.
        """
        if not getattr(self, "_session_json_enabled", False):
            return
        messages = messages or self._session_messages
        if not messages:
            return

        # Re-derive the target path each call so /branch and /compress
        # session-id changes land in the right file without any re-point
        # bookkeeping at the call sites.
        try:
            log_file = self.logs_dir / f"session_{self.session_id}.json"
        except Exception:
            return

        try:
            cleaned = []
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("content"):
                    msg = dict(msg)
                    msg["content"] = self._clean_session_content(msg["content"])
                # Defence-in-depth: redact credentials from every message
                # content before persistence. Catches PATs / API keys / Bearer
                # tokens that may have leaked into assistant responses, tool
                # output, or user paste. Respects HERMES_REDACT_SECRETS via
                # redact_sensitive_text — no-op when disabled. (#19798, #19845)
                if "content" in msg:
                    msg = dict(msg)
                    msg["content"] = self._redact_message_content(msg.get("content"))
                cleaned.append(msg)

            # Guard: never overwrite a larger session log with fewer messages.
            # Protects against data loss when a resumed agent starts with
            # partial history and would otherwise clobber the full JSON log.
            if log_file.exists():
                try:
                    existing = json.loads(log_file.read_text(encoding="utf-8"))
                    existing_count = existing.get("message_count", len(existing.get("messages", [])))
                    if existing_count > len(cleaned):
                        logging.debug(
                            "Skipping session log overwrite: existing has %d messages, current has %d",
                            existing_count, len(cleaned),
                        )
                        return
                except Exception:
                    pass  # corrupted existing file — allow the overwrite

            entry = {
                "session_id": self.session_id,
                "model": self.model,
                "base_url": self.base_url,
                "platform": self.platform,
                "session_start": self.session_start.isoformat(),
                "last_updated": datetime.now().isoformat(),
                "system_prompt": redact_sensitive_text(self._cached_system_prompt or ""),
                "tools": self.tools or [],
                "message_count": len(cleaned),
                "messages": cleaned,
            }

            atomic_json_write(
                log_file,
                entry,
                indent=2,
                default=str,
            )

        except Exception as e:
            if self.verbose_logging:
                logging.warning(f"Failed to save session log: {e}")


    def interrupt(self, message: str = None) -> None:
        """
        Request the agent to interrupt its current tool-calling loop.
        
        Call this from another thread (e.g., input handler, message receiver)
        to gracefully stop the agent and process a new message.
        
        Also signals long-running tool executions (e.g. terminal commands)
        to terminate early, so the agent can respond immediately.
        
        Args:
            message: Optional new message that triggered the interrupt.
                     If provided, the agent will include this in its response context.
        
        Example (CLI):
            # In a separate input thread:
            if user_typed_something:
                agent.interrupt(user_input)
        
        Example (Messaging):
            # When new message arrives for active session:
            if session_has_running_agent:
                running_agent.interrupt(new_message.text)
        """
        self._interrupt_requested = True
        self._interrupt_message = message
        # Signal all tools to abort any in-flight operations immediately.
        # Scope the interrupt to this agent's execution thread so other
        # agents running in the same process (gateway) are not affected.
        if self._execution_thread_id is not None:
            _set_interrupt(True, self._execution_thread_id)
            self._interrupt_thread_signal_pending = False
        else:
            # The interrupt arrived before run_conversation() finished
            # binding the agent to its execution thread. Defer the tool-level
            # interrupt signal until startup completes instead of targeting
            # the caller thread by mistake.
            self._interrupt_thread_signal_pending = True
        # Fan out to concurrent-tool worker threads.  Those workers run tools
        # on their own tids (ThreadPoolExecutor workers), so `is_interrupted()`
        # inside a tool only sees an interrupt when their specific tid is in
        # the `_interrupted_threads` set.  Without this propagation, an
        # already-running concurrent tool (e.g. a terminal command hung on
        # network I/O) never notices the interrupt and has to run to its own
        # timeout.  See `_run_tool` for the matching entry/exit bookkeeping.
        # `getattr` fallback covers test stubs that build AIAgent via
        # object.__new__ and skip __init__.
        _tracker = getattr(self, "_tool_worker_threads", None)
        _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
        if _tracker is not None and _tracker_lock is not None:
            with _tracker_lock:
                _worker_tids = list(_tracker)
            for _wtid in _worker_tids:
                try:
                    _set_interrupt(True, _wtid)
                except Exception:
                    pass
        # Propagate interrupt to any running child agents (subagent delegation)
        with self._active_children_lock:
            children_copy = list(self._active_children)
        for child in children_copy:
            try:
                child.interrupt(message)
            except Exception as e:
                logger.debug("Failed to propagate interrupt to child agent: %s", e)
        if not self.quiet_mode:
            print("\n⚡ Interrupt requested" + (f": '{message[:40]}...'" if message and len(message) > 40 else f": '{message}'" if message else ""))

    def clear_interrupt(self) -> None:
        """Clear any pending interrupt request and the per-thread tool interrupt signal."""
        self._interrupt_requested = False
        self._interrupt_message = None
        self._interrupt_thread_signal_pending = False
        if self._execution_thread_id is not None:
            _set_interrupt(False, self._execution_thread_id)
        # Also clear any concurrent-tool worker thread bits.  Tracked
        # workers normally clear their own bit on exit, but an explicit
        # clear here guarantees no stale interrupt can survive a turn
        # boundary and fire on a subsequent, unrelated tool call that
        # happens to get scheduled onto the same recycled worker tid.
        # `getattr` fallback covers test stubs that build AIAgent via
        # object.__new__ and skip __init__.
        _tracker = getattr(self, "_tool_worker_threads", None)
        _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
        if _tracker is not None and _tracker_lock is not None:
            with _tracker_lock:
                _worker_tids = list(_tracker)
            for _wtid in _worker_tids:
                try:
                    _set_interrupt(False, _wtid)
                except Exception:
                    pass
        # A hard interrupt supersedes any pending /steer — the steer was
        # meant for the agent's next tool-call iteration, which will no
        # longer happen. Drop it instead of surprising the user with a
        # late injection on the post-interrupt turn.
        _steer_lock = getattr(self, "_pending_steer_lock", None)
        if _steer_lock is not None:
            with _steer_lock:
                self._pending_steer = None

    def steer(self, text: str) -> bool:
        """
        Inject a user message into the next tool result without interrupting.

        Unlike interrupt(), this does NOT stop the current tool call. The
        text is stashed and the agent loop appends it to the LAST tool
        result's content once the current tool batch finishes. The model
        sees the steer as part of the tool output on its next iteration.

        Thread-safe: callable from gateway/CLI/TUI threads. Multiple calls
        before the drain point concatenate with newlines.

        Args:
            text: The user text to inject. Empty strings are ignored.

        Returns:
            True if the steer was accepted, False if the text was empty.
        """
        if not text or not text.strip():
            return False
        cleaned = text.strip()
        _lock = getattr(self, "_pending_steer_lock", None)
        if _lock is None:
            # Test stubs that built AIAgent via object.__new__ skip __init__.
            # Fall back to direct attribute set; no concurrent callers expected
            # in those stubs.
            existing = getattr(self, "_pending_steer", None)
            self._pending_steer = (existing + "\n" + cleaned) if existing else cleaned
            return True
        with _lock:
            if self._pending_steer:
                self._pending_steer = self._pending_steer + "\n" + cleaned
            else:
                self._pending_steer = cleaned
        return True

    def _drain_pending_steer(self) -> Optional[str]:
        """Return the pending steer text (if any) and clear the slot.

        Safe to call from the agent execution thread after appending tool
        results. Returns None when no steer is pending.
        """
        _lock = getattr(self, "_pending_steer_lock", None)
        if _lock is None:
            text = getattr(self, "_pending_steer", None)
            self._pending_steer = None
            return text
        with _lock:
            text = self._pending_steer
            self._pending_steer = None
        return text

    def _record_file_mutation_result(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        is_error: bool,
    ) -> None:
        """Record a ``write_file`` / ``patch`` outcome for the turn-end verifier.

        On failure, store ``{path: {error_preview, tool}}`` entries.  On
        success, remove any prior failure entries for the same paths (the
        model recovered within the turn).  Silently no-ops if the per-turn
        state dict hasn't been initialised yet (e.g. a tool dispatched
        outside ``run_conversation``).
        """
        if tool_name not in _FILE_MUTATING_TOOLS:
            return
        state = getattr(self, "_turn_failed_file_mutations", None)
        if state is None:
            return
        targets = _extract_file_mutation_targets(tool_name, args)
        if not targets:
            return
        landed = file_mutation_result_landed(tool_name, result)
        if is_error and not landed:
            preview = _extract_error_preview(result)
            for path in targets:
                # Keep the FIRST error we saw for a given path unless we
                # later see success.  A repeated failure with a different
                # message shouldn't silently overwrite the original.
                if path not in state:
                    state[path] = {
                        "tool": tool_name,
                        "error_preview": preview,
                    }
        else:
            for path in targets:
                state.pop(path, None)

    def _file_mutation_verifier_enabled(self) -> bool:
        """Check whether the per-turn file-mutation verifier footer is on.

        Config path: ``display.file_mutation_verifier`` (bool, default True).
        ``HERMES_FILE_MUTATION_VERIFIER`` env var overrides config.  Exposed
        as a method so tests can patch a single seam without reaching into
        the private ``_turn_failed_file_mutations`` state dict.
        """
        try:
            import os as _os
            env = _os.environ.get("HERMES_FILE_MUTATION_VERIFIER")
            if env is not None:
                return env.strip().lower() not in {"0", "false", "no", "off"}
            # Read from the persisted config.yaml so gateway and CLI share
            # the same setting.  Import lazily to avoid a startup-time cycle.
            try:
                from hermes_cli.config import load_config as _load_config
                _cfg = _load_config() or {}
            except Exception:
                _cfg = {}
            _display = _cfg.get("display") if isinstance(_cfg, dict) else None
            if isinstance(_display, dict) and "file_mutation_verifier" in _display:
                return bool(_display.get("file_mutation_verifier"))
        except Exception:
            pass
        return True  # safe default: verifier on

    # Bare absolute / home / Windows-drive file paths in a footer line.
    # Anchors mirror the gateway's ``extract_local_files`` bare-path
    # detector so that anything the gateway WOULD auto-attach is wrapped
    # in inline-code backticks here first (the extractor skips paths inside
    # `code` spans).  Defense-in-depth: even if a future error message
    # echoes a credential path (config.yaml, .env, auth.json) into the
    # user-facing footer, it can never be matched as a deliverable bare
    # path and silently uploaded to a messaging channel (#35584).
    _FOOTER_PATH_RE = re.compile(
        r"(?<![/:\w.`])(?:~/|/|[A-Za-z]:[/\\])(?:[\w.\-]+[/\\])*[\w.\-]+\.[\w]+",
    )

    @classmethod
    def _neutralize_footer_paths(cls, text: str) -> str:
        """Wrap bare file paths in backticks so they aren't auto-delivered.

        The gateway's ``extract_local_files`` scans response text for bare
        absolute/home paths ending in a deliverable extension and uploads
        any that exist on disk as native attachments — but it explicitly
        skips paths inside inline-code (`` `...` ``) spans.  Backticking
        every path the footer renders defeats that auto-detection while
        keeping the path fully human-readable.  Paths already wrapped in a
        backtick (the negative lookbehind excludes a preceding `` ` ``) are
        left untouched so we never double-wrap.
        """
        if not text:
            return text
        return cls._FOOTER_PATH_RE.sub(lambda m: f"`{m.group(0)}`", text)

    @classmethod
    def _format_file_mutation_failure_footer(cls, failed: Dict[str, Dict[str, Any]]) -> str:
        """Render the per-turn failed-mutation dict as a user-facing footer.

        Displays up to 10 paths with their first error preview, then a
        count of any additional failures.  Returns an empty string when
        the dict is empty so callers can concatenate unconditionally.

        Every file path that reaches the user-facing text — both the bullet
        path and any path echoed inside the tool's error preview — is
        backtick-wrapped via ``_neutralize_footer_paths`` so the gateway's
        bare-path media extractor can never auto-attach a protected file
        (e.g. ``~/.hermes/config.yaml``) to a messaging channel (#35584).
        """
        if not failed:
            return ""
        lines = [
            "⚠️ File-mutation verifier: "
            f"{len(failed)} file(s) were NOT modified this turn despite any "
            "wording above that may suggest otherwise. Run `git status` or "
            "`read_file` to confirm."
        ]
        shown = 0
        for path, info in failed.items():
            if shown >= 10:
                break
            preview = (info.get("error_preview") or "").strip()
            tool = info.get("tool") or "patch"
            if preview:
                lines.append(f"  • `{path}` — [{tool}] {preview}")
            else:
                lines.append(f"  • `{path}` — [{tool}] failed")
            shown += 1
        remaining = len(failed) - shown
        if remaining > 0:
            lines.append(f"  • … and {remaining} more")
        # Neutralize any path the preview text echoed (the bullet path is
        # already backticked above; the lookbehind keeps it from being
        # double-wrapped).
        return cls._neutralize_footer_paths("\n".join(lines))

    def _turn_completion_explainer_enabled(self) -> bool:
        """Check whether the end-of-turn completion explainer footer is on.

        Config path: ``display.turn_completion_explainer`` (bool, default
        True).  ``HERMES_TURN_COMPLETION_EXPLAINER`` env var overrides
        config.  Exposed as a method so tests can patch a single seam,
        mirroring ``_file_mutation_verifier_enabled``.
        """
        try:
            import os as _os
            env = _os.environ.get("HERMES_TURN_COMPLETION_EXPLAINER")
            if env is not None:
                return env.strip().lower() not in {"0", "false", "no", "off"}
            # Read from the persisted config.yaml so gateway and CLI share
            # the same setting.  Import lazily to avoid a startup-time cycle.
            try:
                from hermes_cli.config import load_config as _load_config
                _cfg = _load_config() or {}
            except Exception:
                _cfg = {}
            _display = _cfg.get("display") if isinstance(_cfg, dict) else None
            if isinstance(_display, dict) and "turn_completion_explainer" in _display:
                return bool(_display.get("turn_completion_explainer"))
        except Exception:
            pass
        return True  # safe default: explainer on

    @staticmethod
    def _format_turn_completion_explanation(turn_exit_reason: str) -> str:
        """Render a user-facing explanation for an abnormal turn ending.

        Maps the internal ``turn_exit_reason`` to a short, actionable
        message so a turn that produced no usable assistant reply (empty
        content after retries, a partial/truncated stream, a still-pending
        tool result, or an iteration/budget limit) is never silent from
        the UI's perspective — the symptom users report in #34452.

        Returns an empty string for reasons that are NOT abnormal (e.g.
        a normal ``text_response(...)`` exit), so callers can concatenate
        or substitute unconditionally without warning on healthy turns
        like a terse ``Done.``.
        """
        if not turn_exit_reason:
            return ""
        reason = str(turn_exit_reason)

        # Normal completion — stay quiet.  ``text_response(...)`` is the
        # healthy terminal; anything that produced a real reply is fine.
        if reason.startswith("text_response"):
            return ""

        prefix = "⚠️ No reply: "
        if reason == "empty_response_exhausted":
            return (
                prefix
                + "the model returned empty content after retries and any "
                "fallback providers. Try `continue`, switch model/provider, "
                "or inspect the tool output above."
            )
        if reason == "all_retries_exhausted_no_response":
            return (
                prefix
                + "all API retries were exhausted before a response was "
                "produced (provider errors / rate limits). Try `continue` "
                "or switch provider."
            )
        if reason == "partial_stream_recovery":
            return (
                prefix
                + "streaming stopped early and only a partial response was "
                "recovered. Send `continue` to resume from where it stopped."
            )
        if reason == "fallback_prior_turn_content":
            return (
                prefix
                + "no new content was produced this turn; showing recovered "
                "prior context. Send `continue` to retry."
            )
        if reason == "interrupted_during_api_call":
            return (
                prefix
                + "the request was interrupted mid-call before a reply was "
                "received. Send `continue` to retry."
            )
        if reason == "budget_exhausted":
            return (
                prefix
                + "the per-turn iteration/cost budget was exhausted before a "
                "final answer. Send `continue` to keep going."
            )
        if reason == "ollama_runtime_context_too_small":
            return (
                prefix
                + "the local model's context window was too small to finish. "
                "Increase the context size or use a larger model."
            )
        if reason.startswith("max_iterations_reached"):
            return (
                prefix
                + "the maximum tool-iteration limit was reached before a "
                "final answer. Send `continue` to keep going, or raise "
                "`max_iterations`."
            )
        if reason.startswith("error_near_max_iterations"):
            return (
                prefix
                + "an error occurred near the iteration limit before a final "
                "answer. Check the tool output above, then send `continue`."
            )
        if reason == "pending_tool_result":
            return (
                prefix
                + "the turn stopped while a tool result was still pending and "
                "the model produced no follow-up text. Send `continue` to "
                "let it summarize."
            )
        # Unknown/diagnostic-only reasons (e.g. "unknown", guardrail_halt
        # which already surfaces its own message) — don't second-guess.
        return ""

    def _apply_pending_steer_to_tool_results(self, messages: list, num_tool_msgs: int) -> None:
        """Forwarder — see ``agent.agent_runtime_helpers.apply_pending_steer_to_tool_results``."""
        from agent.agent_runtime_helpers import apply_pending_steer_to_tool_results
        return apply_pending_steer_to_tool_results(self, messages, num_tool_msgs)

    def _touch_activity(self, desc: str) -> None:
        """Update the last-activity timestamp and description (thread-safe).

        Also bridges to the kanban board's heartbeat fields when this
        process is a dispatcher-spawned worker (HERMES_KANBAN_TASK set),
        so the dispatcher watchdog doesn't reclaim an actively-running
        worker as stale (#31752). Bridge is rate-limited (60s) and
        best-effort — it never raises into the agent loop.
        """
        self._last_activity_ts = time.time()
        self._last_activity_desc = desc
        if os.environ.get("HERMES_KANBAN_TASK"):
            try:
                from tools.kanban_tools import heartbeat_current_worker_from_env
                heartbeat_current_worker_from_env()
            except Exception:
                # Never let the bridge break the agent loop.  The function
                # already swallows exceptions internally; this outer guard
                # covers import-time failures (kanban_tools unavailable,
                # etc.) on niche deployment surfaces.
                pass

    def _capture_rate_limits(self, http_response: Any) -> None:
        """Parse x-ratelimit-* headers from an HTTP response and cache the state.

        Called after each streaming API call.  The httpx Response object is
        available on the OpenAI SDK Stream via ``stream.response``.
        """
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        try:
            from agent.rate_limit_tracker import parse_rate_limit_headers
            state = parse_rate_limit_headers(headers, provider=self.provider)
            if state is not None:
                self._rate_limit_state = state
        except Exception:
            pass  # Never let header parsing break the agent loop

    def get_rate_limit_state(self):
