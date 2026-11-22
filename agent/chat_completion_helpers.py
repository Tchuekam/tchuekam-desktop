"""Helper functions for the chat-completions code path.

Extracted from :class:`AIAgent` for cleanliness — bodies of the
non-streaming API call, request kwargs builder, assistant-message
materializer, provider-fallback activator, max-iterations handler,
and per-turn resource cleanup.

Each function takes the parent ``AIAgent`` as its first argument
(``agent``).  :class:`AIAgent` keeps thin forwarder methods so call
sites unchanged.  Symbols that tests patch on ``run_agent`` (e.g.
``cleanup_vm`` / ``cleanup_browser`` in
``test_zombie_process_cleanup.py``) are resolved through
:func:`_ra` so the patch contract is preserved.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Optional

from hermes_cli.timeouts import get_provider_request_timeout, get_provider_stale_timeout
from hermes_constants import PARTIAL_STREAM_STUB_ID, FINISH_REASON_LENGTH
from agent.error_classifier import FailoverReason
from agent.model_metadata import is_local_endpoint
from agent.message_sanitization import (
    _sanitize_surrogates,
    _repair_tool_call_arguments,
)
from tools.terminal_tool import is_persistent_env
from utils import base_url_host_matches, base_url_hostname

logger = logging.getLogger(__name__)


def _ra():
    """Lazy ``run_agent`` reference.

    Used to honor test patches like
    ``patch("run_agent.cleanup_vm")`` / ``patch("run_agent.cleanup_browser")``
    that target symbols imported into ``run_agent``'s namespace.
    """
    import run_agent
    return run_agent


def estimate_request_context_tokens(api_payload: Any) -> int:
    """Estimate context/load tokens from an API payload, dict or messages list.

    The stale-call detectors historically assumed a Chat Completions request:
    they pulled ``api_kwargs["messages"]`` and ran a cheap char/4 estimate.
    Codex / Responses API requests carry the conversational payload in
    ``input`` (with additional load in ``instructions`` and ``tools``), so the
    legacy estimator reported ~0 tokens for every Codex turn and the
    context-tier scaling never fired.

    This helper handles both shapes:
      - bare list -> treat as Chat Completions ``messages``
      - dict with ``messages`` -> Chat Completions (+ ``tools`` if present)
      - dict with ``input`` -> Responses API (+ ``instructions``/``tools``)
      - any other dict -> fall back to summing string values
    """

    def _chars(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return len(value)
        return len(str(value))

    def _message_chars(messages: Any) -> int:
        if not isinstance(messages, list):
            return _chars(messages)
        return sum(_chars(item) for item in messages)

    if isinstance(api_payload, list):
        return _message_chars(api_payload) // 4

    if isinstance(api_payload, dict):
        messages = api_payload.get("messages")
        if isinstance(messages, list):
            total_chars = _message_chars(messages)
            if "tools" in api_payload:
                total_chars += _chars(api_payload.get("tools"))
            return total_chars // 4

        if "input" in api_payload:
            total_chars = (
                _chars(api_payload.get("input"))
                + _chars(api_payload.get("instructions"))
                + _chars(api_payload.get("tools"))
            )
            return total_chars // 4

        return sum(_chars(value) for value in api_payload.values()) // 4

    return _chars(api_payload) // 4


def _is_openai_codex_backend(agent) -> bool:
    base_url_lower = str(getattr(agent, "_base_url_lower", "") or "")
    base_url_hostname = str(getattr(agent, "_base_url_hostname", "") or "")
    return (
        getattr(agent, "provider", None) == "openai-codex"
        or (
            base_url_hostname == "chatgpt.com"
            and "/backend-api/codex" in base_url_lower
        )
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def interruptible_api_call(agent, api_kwargs: dict):
    """
    Run the API call in a background thread so the main conversation loop
    can detect interrupts without waiting for the full HTTP round-trip.

    Each worker thread gets its own OpenAI client instance. Interrupts only
    close that worker-local client, so retries and other requests never
    inherit a closed transport.

    Includes a stale-call detector: if no response arrives within the
    configured timeout, the connection is killed and an error raised so
    the main retry loop can try again with backoff / credential rotation /
    provider fallback.
    """
    result = {"response": None, "error": None}
    request_client_holder = {"client": None, "owner_tid": None}
    request_client_lock = threading.Lock()

    def _set_request_client(client):
        with request_client_lock:
            request_client_holder["client"] = client
            # #29507: stamp the owning thread so a stranger-thread interrupt
            # only shuts the connection down rather than racing the worker
            # for FD ownership during ``client.close()``.
            request_client_holder["owner_tid"] = threading.get_ident()
        return client

    def _close_request_client_once(reason: str) -> None:
        # #29507: dispatch on the calling thread.
        #
        # When ``_call`` (the worker) reaches its ``finally`` it owns the
        # close and we pop + fully close as before. When a *stranger* thread
        # (the interrupt-check loop, the stale-call detector) drives the
        # close, only shut the sockets down so the worker's blocked
        # ``recv``/``send`` unwinds with an ``EPIPE`` / EOF — and let the
        # worker close ``client`` from its own thread on its way out. That
        # avoids the FD-recycling race where the kernel reassigned a
        # just-closed TLS socket FD to ``kanban.db``, and the still-live SSL
        # BIO on the worker thread then wrote a 24-byte TLS application-data
        # record into the SQLite header (#29507).
        with request_client_lock:
            request_client = request_client_holder.get("client")
            owner_tid = request_client_holder.get("owner_tid")
            stranger_thread = (
                request_client is not None
                and owner_tid is not None
                and owner_tid != threading.get_ident()
            )
            if not stranger_thread:
                # Owning thread (or no recorded owner) → pop and fully close.
                request_client_holder["client"] = None
                request_client_holder["owner_tid"] = None
        if request_client is None:
            return
        if stranger_thread:
            agent._abort_request_openai_client(request_client, reason=reason)
        else:
            agent._close_request_openai_client(request_client, reason=reason)

    def _call():
        try:
            if agent.api_mode == "codex_responses":
                request_client = _set_request_client(
                    agent._create_request_openai_client(
                        reason="codex_stream_request",
                        api_kwargs=api_kwargs,
                    )
                )
                result["response"] = agent._run_codex_stream(
                    api_kwargs,
                    client=request_client,
                    on_first_delta=getattr(agent, "_codex_on_first_delta", None),
                )
            elif agent.api_mode == "anthropic_messages":
                result["response"] = agent._anthropic_messages_create(api_kwargs)
            elif agent.api_mode == "bedrock_converse":
                # Bedrock uses boto3 directly — no OpenAI client needed.
                # normalize_converse_response produces an OpenAI-compatible
                # SimpleNamespace so the rest of the agent loop can treat
                # bedrock responses like chat_completions responses.
                from agent.bedrock_adapter import (
                    _get_bedrock_runtime_client,
                    invalidate_runtime_client,
                    is_stale_connection_error,
                    normalize_converse_response,
                )
                region = api_kwargs.pop("__bedrock_region__", "us-east-1")
                api_kwargs.pop("__bedrock_converse__", None)
                client = _get_bedrock_runtime_client(region)
                try:
                    raw_response = client.converse(**api_kwargs)
                except Exception as _bedrock_exc:
                    # Evict the cached client on stale-connection failures
                    # so the outer retry loop builds a fresh client/pool.
                    if is_stale_connection_error(_bedrock_exc):
                        invalidate_runtime_client(region)
                    raise
                result["response"] = normalize_converse_response(raw_response)
            else:
                request_client = _set_request_client(
                    agent._create_request_openai_client(
                        reason="chat_completion_request",
                        api_kwargs=api_kwargs,
                    )
                )
                result["response"] = request_client.chat.completions.create(**api_kwargs)
        except Exception as e:
            result["error"] = e
        finally:
            _close_request_client_once("request_complete")

    # ── Stale-call timeout (mirrors streaming stale detector) ────────
    # Non-streaming calls return nothing until the full response is
    # ready.  Without this, a hung provider can block for the full
    # httpx timeout (default 1800s) with zero feedback.  The stale
    # detector kills the connection early so the main retry loop can
    # apply richer recovery (credential rotation, provider fallback).
    _stale_timeout = agent._compute_non_stream_stale_timeout(api_kwargs)

    # ── Codex Responses stream watchdogs ────────────────────────────────
    # The chatgpt.com/backend-api/codex endpoint has an intermittent failure
    # mode where it accepts the connection but never emits a single stream
    # event (observed directly: 0 events, no HTTP status, the socket just
    # hangs). A fresh reconnect succeeds in ~2s, but the wall-clock stale
    # timeout (often 180–900s) makes us wait minutes before retrying. While no
    # stream event has arrived yet we apply a much shorter TTFB cutoff so the
    # main retry loop can reconnect promptly. Large subscription-backed Codex
    # requests can legitimately spend tens of seconds in backend admission /
    # prompt prefill before the first SSE event, so the no-byte TTFB watchdog
    # is disabled for large chatgpt.com/backend-api/codex requests. A second
    # failure mode emits an opening SSE frame and then stalls forever in SSL
    # read; for that we watch the gap since the last Codex stream event. This
    # matches Codex CLI's stream_idle_timeout model: any valid SSE event is
    # activity. Operators can tune via HERMES_CODEX_TTFB_TIMEOUT_SECONDS and
    # HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS (0 disables each).
    _codex_watchdog_enabled = agent.api_mode == "codex_responses"
    _openai_codex_backend = _is_openai_codex_backend(agent)
    _est_tokens_for_codex_watchdog = estimate_request_context_tokens(api_kwargs)
    if _codex_watchdog_enabled and _openai_codex_backend:
        if _est_tokens_for_codex_watchdog > 100_000:
            _stale_timeout = max(_stale_timeout, 1200.0)
        elif _est_tokens_for_codex_watchdog > 50_000:
            _stale_timeout = max(_stale_timeout, 900.0)
        elif _est_tokens_for_codex_watchdog > 25_000:
            _stale_timeout = max(_stale_timeout, 600.0)

    if _est_tokens_for_codex_watchdog > 100_000:
        _codex_idle_timeout_default = 180.0
    elif _est_tokens_for_codex_watchdog > 50_000:
        _codex_idle_timeout_default = 120.0
    elif _est_tokens_for_codex_watchdog > 10_000:
        _codex_idle_timeout_default = 60.0
    else:
        _codex_idle_timeout_default = 12.0

    # No-byte TTFB cutoff. The OpenAI SDK's own streaming read timeout is far
    # longer (openai 2.x DEFAULT_TIMEOUT.read = 600s), so a tight 12s default
    # killed subscription-backed Codex requests mid-prefill before the backend
    # had a chance to emit its first SSE event. Default to 120s — long enough to
    # clear normal backend admission / prompt prefill, short enough to still
    # reconnect promptly when the socket is genuinely wedged. Set
    # HERMES_CODEX_TTFB_TIMEOUT_SECONDS=0 to disable this watchdog entirely.
    _ttfb_enabled = _codex_watchdog_enabled
    _ttfb_timeout = _env_float("HERMES_CODEX_TTFB_TIMEOUT_SECONDS", 120.0)
    if _ttfb_timeout <= 0:
        _ttfb_enabled = False
    elif _openai_codex_backend:
        _ttfb_disable_above = _env_float("HERMES_CODEX_TTFB_DISABLE_ABOVE_TOKENS", 25_000.0)
        _ttfb_strict = os.environ.get("HERMES_CODEX_TTFB_STRICT", "").strip().lower() in {
            "1", "true", "yes", "on"
        }
        if (
            not _ttfb_strict
            and _ttfb_disable_above > 0
            and _est_tokens_for_codex_watchdog >= _ttfb_disable_above
        ):
            _ttfb_enabled = False
            logger.info(
                "Disabling openai-codex no-byte TTFB watchdog for large request "
                "(context=~%s tokens >= %.0f). Waiting for backend response instead. "
                "Set HERMES_CODEX_TTFB_STRICT=1 to force early reconnects.",
                f"{_est_tokens_for_codex_watchdog:,}",
                _ttfb_disable_above,
            )
        else:
            _ttfb_cap = _env_float("HERMES_CODEX_TTFB_MAX_SECONDS", 120.0)
            if _ttfb_cap > 0 and _ttfb_timeout > _ttfb_cap:
                logger.info(
                    "Capping openai-codex no-byte TTFB timeout from %.0fs to %.0fs "
                    "(context=~%s tokens). Set HERMES_CODEX_TTFB_MAX_SECONDS to tune.",
                    _ttfb_timeout,
                    _ttfb_cap,
                    f"{_est_tokens_for_codex_watchdog:,}",
                )
                _ttfb_timeout = _ttfb_cap

    _codex_idle_enabled = _codex_watchdog_enabled
    _codex_idle_timeout = _env_float(
        "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS",
        _codex_idle_timeout_default,
    )
    if _codex_idle_timeout <= 0:
        _codex_idle_enabled = False

    if _codex_watchdog_enabled:
        # Reset before the worker starts so a marker left over from a previous
        # call on this agent can't be misread as first-byte for this one.
        agent._codex_stream_last_event_ts = None
        agent._codex_stream_last_progress_ts = None

    _call_start = time.time()
    agent._touch_activity("waiting for non-streaming API response")

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    _poll_count = 0
    while t.is_alive():
        t.join(timeout=0.3)
        _poll_count += 1

        # Touch activity every ~30s so the gateway's inactivity
        # monitor knows we're alive while waiting for the response.
        if _poll_count % 100 == 0:  # 100 × 0.3s = 30s
            _elapsed = time.time() - _call_start
            agent._touch_activity(
                f"waiting for non-streaming response ({int(_elapsed)}s elapsed)"
            )

        _elapsed = time.time() - _call_start

        # TTFB detector: the Codex stream has produced no event at all and
        # we're past the first-byte cutoff → the backend opened the
        # connection but isn't responding. Kill it so the retry loop can
        # reconnect (a fresh connection typically succeeds in seconds),
        # instead of waiting out the much longer wall-clock stale timeout.
        if (
            _ttfb_enabled
            and _elapsed > _ttfb_timeout
            and getattr(agent, "_codex_stream_last_event_ts", None) is None
        ):
            _silent_hint: Optional[str] = None
            _hint_fn = getattr(agent, "_codex_silent_hang_hint", None)
            if callable(_hint_fn):
                try:
                    _silent_hint = _hint_fn(model=api_kwargs.get("model"))
                except Exception:
                    _silent_hint = None
            logger.warning(
                "Codex stream produced no bytes within TTFB cutoff "
                "(%.0fs > %.0fs, model=%s). Backend accepted the connection "
                "but sent no stream events. Killing connection so the retry "
                "loop can reconnect.",
                _elapsed, _ttfb_timeout, api_kwargs.get("model", "unknown"),
            )
            if _silent_hint:
                agent._buffer_status(
                    f"⚠️ No first byte from provider in {int(_elapsed)}s "
                    f"(codex stream, model: {api_kwargs.get('model', 'unknown')}). "
                    f"Reconnecting. {_silent_hint}"
                )
            else:
                agent._buffer_status(
                    f"⚠️ No first byte from provider in {int(_elapsed)}s "
                    f"(codex stream, model: {api_kwargs.get('model', 'unknown')}). "
                    f"Reconnecting."
                )
            try:
                _close_request_client_once("codex_ttfb_kill")
            except Exception:
                pass
            agent._touch_activity(
                f"codex stream killed after {int(_elapsed)}s with no first byte"
            )
            # Wait briefly for the worker to notice the closed connection.
            t.join(timeout=2.0)
            if result["error"] is None and result["response"] is None:
                if _silent_hint:
                    result["error"] = TimeoutError(
                        f"Codex stream produced no bytes within {int(_elapsed)}s "
                        f"(TTFB threshold: {int(_ttfb_timeout)}s). {_silent_hint}"
                    )
                else:
                    result["error"] = TimeoutError(
                        f"Codex stream produced no bytes within {int(_elapsed)}s "
                        f"(TTFB threshold: {int(_ttfb_timeout)}s)"
                    )
            break

        # Stream-idle detector: the Codex backend emitted at least one SSE
        # frame, then stopped emitting events. Valid keepalive / in_progress
        # frames refresh _codex_stream_last_event_ts and should not be killed.
        _last_codex_event_ts = getattr(agent, "_codex_stream_last_event_ts", None)
        if (
            _codex_idle_enabled
            and _last_codex_event_ts is not None
            and (time.time() - _last_codex_event_ts) > _codex_idle_timeout
        ):
            _event_stale_elapsed = time.time() - _last_codex_event_ts
            logger.warning(
                "Codex stream produced no SSE events for %.0fs after first byte "
                "(threshold %.0fs, model=%s, context=~%s tokens). Killing "
                "connection so the retry loop can reconnect.",
                _event_stale_elapsed,
                _codex_idle_timeout,
                api_kwargs.get("model", "unknown"),
                f"{_est_tokens_for_codex_watchdog:,}",
            )
            agent._buffer_status(
                f"⚠️ Codex stream sent no events for {int(_event_stale_elapsed)}s "
                f"after first byte (model: {api_kwargs.get('model', 'unknown')}). "
                f"Reconnecting."
            )
            try:
                _close_request_client_once("codex_stream_idle_kill")
            except Exception:
                pass
            agent._touch_activity(
                f"codex stream killed after {int(_event_stale_elapsed)}s with no SSE events"
            )
            t.join(timeout=2.0)
            if result["error"] is None and result["response"] is None:
                result["error"] = TimeoutError(
                    f"Codex stream produced no SSE events for {int(_event_stale_elapsed)}s "
                    f"after first byte (threshold: {int(_codex_idle_timeout)}s)"
                )
            break

        # Stale-call detector: kill the connection if no response
        # arrives within the configured timeout.
        if _elapsed > _stale_timeout:
            _est_ctx = estimate_request_context_tokens(api_kwargs)
            _silent_hint: Optional[str] = None
            _hint_fn = getattr(agent, "_codex_silent_hang_hint", None)
            if callable(_hint_fn):
                try:
                    _silent_hint = _hint_fn(model=api_kwargs.get("model"))
                except Exception:
                    _silent_hint = None
            logger.warning(
                "Non-streaming API call stale for %.0fs (threshold %.0fs). "
                "model=%s context=~%s tokens. Killing connection.",
                _elapsed, _stale_timeout,
                api_kwargs.get("model", "unknown"), f"{_est_ctx:,}",
            )
            if _silent_hint:
                agent._buffer_status(
                    f"⚠️ No response from provider for {int(_elapsed)}s "
                    f"(non-streaming, model: {api_kwargs.get('model', 'unknown')}). "
                    f"{_silent_hint}"
                )
            else:
                agent._buffer_status(
                    f"⚠️ No response from provider for {int(_elapsed)}s "
                    f"(non-streaming, model: {api_kwargs.get('model', 'unknown')}). "
                    f"Aborting call."
                )
            try:
                if agent.api_mode == "anthropic_messages":
                    agent._anthropic_client.close()
                    agent._rebuild_anthropic_client()
                else:
                    _close_request_client_once("stale_call_kill")
            except Exception:
                pass
            agent._touch_activity(
                f"stale non-streaming call killed after {int(_elapsed)}s"
            )
            # Wait briefly for the thread to notice the closed connection.
            t.join(timeout=2.0)
            if result["error"] is None and result["response"] is None:
                if _silent_hint:
                    result["error"] = TimeoutError(
                        f"Non-streaming API call timed out after {int(_elapsed)}s "
                        f"with no response (threshold: {int(_stale_timeout)}s). "
                        f"{_silent_hint}"
                    )
                else:
                    result["error"] = TimeoutError(
                        f"Non-streaming API call timed out after {int(_elapsed)}s "
                        f"with no response (threshold: {int(_stale_timeout)}s)"
                    )
            break

        if agent._interrupt_requested:
            # Force-close the in-flight worker-local HTTP connection to stop
            # token generation without poisoning the shared client used to
            # seed future retries.
            try:
                if agent.api_mode == "anthropic_messages":
                    agent._anthropic_client.close()
                    agent._rebuild_anthropic_client()
                else:
                    _close_request_client_once("interrupt_abort")
            except Exception:
                pass
            raise InterruptedError("Agent interrupted during API call")
    if result["error"] is not None:
        raise result["error"]
    return result["response"]



_LOW_TPM_CORE_TOOLS = frozenset({
    "terminal",
    "read_file",
    "read_document",
    "write_file",
    "patch",
    "search_files",
    "web_search",
    "web_extract",
    "todo",
    "memory",
    "clarify",
    "execute_code",
    "delegate_task",
})


def _compact_payload_for_low_tpm(
    agent,
    api_messages: list,
    tools_for_api: list | None,
) -> tuple[list, list | None]:
    """Slim down verbose tool schemas and system prompt for low-TPM & local MbowaGPT providers."""
    provider = str(getattr(agent, "provider", "") or "").strip().lower()
    base_url = str(getattr(agent, "base_url", "") or "").strip().lower()

    if provider == "mbowagpt":
        try:
            from agent.connectivity import get_connectivity_monitor
            from agent.mbowagpt_router import (
                build_compact_local_system_prompt,
                filter_tools_for_local_runtime,
            )

            role_id = (
                getattr(agent, "_active_mbowagpt_role", None)
                or getattr(agent, "model", None)
                or "mbowagpt"
            )
            offline = get_connectivity_monitor().is_offline()
            compacted_tools = (
                filter_tools_for_local_runtime(
                    tools_for_api,
                    offline=offline,
                    role_id=role_id,
                    max_tools=8,
                )
                if isinstance(tools_for_api, list)
                else tools_for_api
            )
            local_sys = build_compact_local_system_prompt(
                role_id=role_id,
                offline=offline,
                platform=getattr(agent, "platform", None) or "desktop",
            )
            compacted_messages = api_messages
            if (
                isinstance(api_messages, list)
                and api_messages
                and isinstance(api_messages[0], dict)
                and api_messages[0].get("role") == "system"
            ):
                compacted_messages = [
                    {**api_messages[0], "content": local_sys},
                    *api_messages[1:],
                ]
            elif isinstance(api_messages, list):
                compacted_messages = [{"role": "system", "content": local_sys}, *api_messages]
            return compacted_messages, compacted_tools
        except Exception:
            pass

    force_compact = bool(getattr(agent, "_compact_payload_for_low_tpm", False))
    is_groq = provider == "groq" or "groq.com" in base_url
    if not (is_groq or force_compact):
        return api_messages, tools_for_api

    est_tokens = estimate_request_context_tokens(
        {"messages": api_messages, "tools": tools_for_api or []}
    )
    if not force_compact and est_tokens <= 5500:
        return api_messages, tools_for_api

    compacted_tools = tools_for_api
    if isinstance(tools_for_api, list) and tools_for_api:
        filtered = [
            t for t in tools_for_api
            if isinstance(t, dict)
            and ((t.get("function") or {}).get("name") in _LOW_TPM_CORE_TOOLS)
        ]
        if not filtered:
            filtered = tools_for_api[:8]
        slim_tools = []
        for t in filtered[:10]:
            fn = t.get("function")
            if not isinstance(fn, dict):
                slim_tools.append(t)
                continue
            desc = str(fn.get("description") or "").strip()
            first_line = desc.split("\n", 1)[0].split(". ", 1)[0][:100]
            params = fn.get("parameters")
            slim_params = params
            if isinstance(params, dict) and isinstance(params.get("properties"), dict):
                slim_props = {}
                for pk, pv in params["properties"].items():
                    if isinstance(pv, dict):
                        pv_copy = {k: v for k, v in pv.items() if k != "description"}
                        pdesc = str(pv.get("description") or "").strip()
                        if pdesc:
                            pv_copy["description"] = pdesc.split("\n", 1)[0][:60]
                        slim_props[pk] = pv_copy
                    else:
                        slim_props[pk] = pv
                slim_params = {**params, "properties": slim_props}
            slim_tools.append({
                **t,
                "function": {
                    **fn,
                    "description": first_line,
                    **({"parameters": slim_params} if slim_params is not None else {}),
                },
            })
        compacted_tools = slim_tools

    compacted_messages = api_messages
    max_sys_chars = 2800 if is_groq else 3600
    if (
        isinstance(api_messages, list)
        and api_messages
        and isinstance(api_messages[0], dict)
        and api_messages[0].get("role") == "system"
    ):
        sys_content = api_messages[0].get("content")
        if isinstance(sys_content, str) and len(sys_content) > max_sys_chars:
            compacted_messages = [
                {**api_messages[0], "content": sys_content[:max_sys_chars]},
                *api_messages[1:],
            ]

    return compacted_messages, compacted_tools


def build_api_kwargs(agent, api_messages: list) -> dict:
    """Build the keyword arguments dict for the active API mode."""
    api_messages, tools_for_api = _compact_payload_for_low_tpm(
        agent, api_messages, agent.tools
    )

    if agent.api_mode == "anthropic_messages":
        _transport = agent._get_transport()
        anthropic_messages = agent._prepare_anthropic_messages_for_api(api_messages)
        ctx_len = getattr(agent, "context_compressor", None)
        ctx_len = ctx_len.context_length if ctx_len else None
        ephemeral_out = getattr(agent, "_ephemeral_max_output_tokens", None)
        if ephemeral_out is not None:
            agent._ephemeral_max_output_tokens = None  # consume immediately
        return _transport.build_kwargs(
            model=agent.model,
            messages=anthropic_messages,
            tools=tools_for_api,
            max_tokens=ephemeral_out if ephemeral_out is not None else agent.max_tokens,
            reasoning_config=agent.reasoning_config,
            is_oauth=agent._is_anthropic_oauth,
            preserve_dots=agent._anthropic_preserve_dots(),
            context_length=ctx_len,
            base_url=getattr(agent, "_anthropic_base_url", None),
            fast_mode=(agent.request_overrides or {}).get("speed") == "fast",
            drop_context_1m_beta=bool(getattr(agent, "_oauth_1m_beta_disabled", False)),
        )

    # AWS Bedrock native Converse API — bypasses the OpenAI client entirely.
    # The adapter handles message/tool conversion and boto3 calls directly.
    if agent.api_mode == "bedrock_converse":
        _bt = agent._get_transport()
        region = getattr(agent, "_bedrock_region", None) or "us-east-1"
        guardrail = getattr(agent, "_bedrock_guardrail_config", None)
        return _bt.build_kwargs(
            model=agent.model,
            messages=api_messages,
            tools=tools_for_api,
            max_tokens=agent.max_tokens or 4096,
            region=region,
            guardrail_config=guardrail,
        )

    if agent.api_mode == "codex_responses":
        _ct = agent._get_transport()
        is_github_responses = (
            base_url_host_matches(agent.base_url, "models.github.ai")
            or base_url_host_matches(agent.base_url, "api.githubcopilot.com")
        )
        is_codex_backend = (
            agent.provider == "openai-codex"
            or (
                agent._base_url_hostname == "chatgpt.com"
                and "/backend-api/codex" in agent._base_url_lower
            )
        )
        is_xai_responses = agent.provider in {"xai", "xai-oauth"} or agent._base_url_hostname == "api.x.ai"
        _msgs_for_codex = agent._prepare_messages_for_non_vision_model(api_messages)

        # xAI's /responses endpoint rejects ``pattern`` and ``format`` keywords
        # in tool schemas (HTTP 400 "Invalid arguments passed to the model").
        # Most commonly hit when MCP-derived tools carry JSON Schema validation
        # keywords through. Strip them before building kwargs. See #27197.
        # It also rejects ``enum`` values containing ``/`` (HuggingFace IDs
        # like ``Qwen/Qwen3.5-0.8B`` shipped by MCP servers) — same 400 with
        # the same opaque message; strip those enums too.
        #
        # Deep-copy ``tools_for_api`` before sanitizing: the sanitizers
        # mutate in place (documented contract on ``strip_slash_enum`` /
        # ``strip_pattern_and_format``), and ``tools_for_api`` is a direct
        # reference to ``agent.tools``.  Without the copy, the first xAI
        # request permanently strips constraints from the shared per-agent
        # tool registry — every subsequent non-xAI call from the same
        # agent (auxiliary task routed to Anthropic, OpenRouter fallback,
        # main-model swap) sees the already-stripped schema.  See #27907.
        if is_xai_responses:
            try:
                import copy as _copy
                from tools.schema_sanitizer import (
                    strip_pattern_and_format,
                    strip_slash_enum,
                )
                tools_for_api = _copy.deepcopy(tools_for_api)
                tools_for_api, _ = strip_pattern_and_format(tools_for_api)
                tools_for_api, _ = strip_slash_enum(tools_for_api)
            except Exception as exc:
                logger.warning(
                    "%s⚠️ Failed to sanitize tool schemas for xAI: %s",
                    getattr(agent, "log_prefix", ""), exc,
                )

        return _ct.build_kwargs(
            model=agent.model,
            messages=_msgs_for_codex,
            tools=tools_for_api,
            reasoning_config=agent.reasoning_config,
            session_id=getattr(agent, "session_id", None),
            max_tokens=agent.max_tokens,
            timeout=agent._resolved_api_call_timeout(),
            request_overrides=agent.request_overrides,
            is_github_responses=is_github_responses,
            is_codex_backend=is_codex_backend,
            is_xai_responses=is_xai_responses,
            github_reasoning_extra=agent._github_models_reasoning_extra_body() if is_github_responses else None,
            replay_encrypted_reasoning=bool(
                getattr(agent, "_codex_reasoning_replay_enabled", True)
            ),
        )

    # ── chat_completions (default) ─────────────────────────────────────
    _ct = agent._get_transport()

    # Provider detection flags
    _is_qwen = agent._is_qwen_portal()
    _is_or = agent._is_openrouter_url()
    _is_gh = (
        base_url_host_matches(agent._base_url_lower, "models.github.ai")
        or base_url_host_matches(agent._base_url_lower, "api.githubcopilot.com")
    )
    _is_nous = "nousresearch" in agent._base_url_lower
    _is_nvidia = "integrate.api.nvidia.com" in agent._base_url_lower
    _is_kimi = (
        base_url_host_matches(agent.base_url, "api.kimi.com")
        or base_url_host_matches(agent.base_url, "moonshot.ai")
        or base_url_host_matches(agent.base_url, "moonshot.cn")
    )
    _is_tokenhub = base_url_host_matches(agent._base_url_lower, "tokenhub.tencentmaas.com")
    _is_lmstudio = (agent.provider or "").strip().lower() == "lmstudio"

    # Temperature: _fixed_temperature_for_model may return OMIT_TEMPERATURE
    # sentinel (temperature omitted entirely), a numeric override, or None.
    try:
        from agent.auxiliary_client import _fixed_temperature_for_model, OMIT_TEMPERATURE
        _ft = _fixed_temperature_for_model(agent.model, agent.base_url)
        _omit_temp = _ft is OMIT_TEMPERATURE
        _fixed_temp = _ft if not _omit_temp else None
    except Exception:
        _omit_temp = False
        _fixed_temp = None

    # Provider preferences (OpenRouter-style)
    _prefs: Dict[str, Any] = {}
    if agent.providers_allowed:
        _prefs["only"] = agent.providers_allowed
    if agent.providers_ignored:
        _prefs["ignore"] = agent.providers_ignored
    if agent.providers_order:
        _prefs["order"] = agent.providers_order
    if agent.provider_sort:
        _prefs["sort"] = agent.provider_sort
    if agent.provider_require_parameters:
        _prefs["require_parameters"] = True
    if agent.provider_data_collection:
        _prefs["data_collection"] = agent.provider_data_collection

    # Claude max-output override on aggregators
    _ant_max = None
    if (_is_or or _is_nous) and "claude" in (agent.model or "").lower():
        try:
            from agent.anthropic_adapter import _get_anthropic_max_output
            _ant_max = _get_anthropic_max_output(agent.model)
        except Exception:
            pass

    # Qwen session metadata
    _qwen_meta = None
    if _is_qwen:
        _qwen_meta = {
            "sessionId": agent.session_id or "hermes",
            "promptId": str(uuid.uuid4()),
        }

    # ── Provider profile path (registered providers) ───────────────────
    # Profiles handle per-provider quirks via hooks. When a profile is
    # found, delegate fully; otherwise fall through to the legacy flag path.
    try:
        from providers import get_provider_profile
        _profile = get_provider_profile(agent.provider)
    except Exception:
        _profile = None

    if _profile:
        _ephemeral_out = getattr(agent, "_ephemeral_max_output_tokens", None)
        if _ephemeral_out is not None:
            agent._ephemeral_max_output_tokens = None

        # Strip image parts for non-vision models that have provider profiles
        # (e.g. DeepSeek, Kimi). The legacy path below already does this, but
        # registered providers with profiles were bypassing the strip.
        api_messages = agent._prepare_messages_for_non_vision_model(api_messages)
        _wire_model = (
            getattr(agent, "_local_served_model", None) or agent.model
            if (agent.provider or "").strip().lower() == "mbowagpt"
            else agent.model
        )

        return _ct.build_kwargs(
            model=_wire_model,
            messages=api_messages,
            tools=tools_for_api,
            base_url=agent.base_url,
            timeout=agent._resolved_api_call_timeout(),
            max_tokens=agent.max_tokens,
            ephemeral_max_output_tokens=_ephemeral_out,
            max_tokens_param_fn=agent._max_tokens_param,
            reasoning_config=agent.reasoning_config,
            request_overrides=agent.request_overrides,
            session_id=getattr(agent, "session_id", None),
            provider_profile=_profile,
            ollama_num_ctx=agent._ollama_num_ctx,
            # Context forwarded to profile hooks:
            provider_preferences=_prefs or None,
            openrouter_min_coding_score=agent.openrouter_min_coding_score,
            anthropic_max_output=_ant_max,
            supports_reasoning=agent._supports_reasoning_extra_body(),
            qwen_session_metadata=_qwen_meta,
        )

    # ── Legacy flag path ────────────────────────────────────────────
    # Reached only when get_provider_profile() returns None — i.e. a
    # completely unknown provider not in providers/ registry.
    _ephemeral_out = getattr(agent, "_ephemeral_max_output_tokens", None)
    if _ephemeral_out is not None:
        agent._ephemeral_max_output_tokens = None

    # Strip image parts for non-vision models (no-op when vision-capable).
    _msgs_for_chat = agent._prepare_messages_for_non_vision_model(api_messages)
    _wire_model = (
        getattr(agent, "_local_served_model", None) or agent.model
        if (agent.provider or "").strip().lower() == "mbowagpt"
        else agent.model
    )

    return _ct.build_kwargs(
        model=_wire_model,
        messages=_msgs_for_chat,
        tools=tools_for_api,
        base_url=agent.base_url,
        timeout=agent._resolved_api_call_timeout(),
        max_tokens=agent.max_tokens,
        ephemeral_max_output_tokens=_ephemeral_out,
        max_tokens_param_fn=agent._max_tokens_param,
        reasoning_config=agent.reasoning_config,
        request_overrides=agent.request_overrides,
        session_id=getattr(agent, "session_id", None),
        model_lower=(_wire_model or "").lower(),
        is_openrouter=_is_or,
        is_nous=_is_nous,
        is_qwen_portal=_is_qwen,
        is_github_models=_is_gh,
        is_nvidia_nim=_is_nvidia,
        is_kimi=_is_kimi,
        is_tokenhub=_is_tokenhub,
        is_lmstudio=_is_lmstudio,
        is_custom_provider=agent.provider == "custom",
        ollama_num_ctx=agent._ollama_num_ctx,
        provider_preferences=_prefs or None,
        openrouter_min_coding_score=agent.openrouter_min_coding_score,
        qwen_prepare_fn=agent._qwen_prepare_chat_messages if _is_qwen else None,
        qwen_prepare_inplace_fn=agent._qwen_prepare_chat_messages_inplace if _is_qwen else None,
        qwen_session_metadata=_qwen_meta,
        fixed_temperature=_fixed_temp,
        omit_temperature=_omit_temp,
        supports_reasoning=agent._supports_reasoning_extra_body(),
        github_reasoning_extra=agent._github_models_reasoning_extra_body() if _is_gh else None,
        lmstudio_reasoning_options=agent._lmstudio_reasoning_options_cached() if _is_lmstudio else None,
        anthropic_max_output=_ant_max,
        provider_name=agent.provider,
    )



def build_assistant_message(agent, assistant_message, finish_reason: str) -> dict:
    """Build a normalized assistant message dict from an API response message.

    Handles reasoning extraction, reasoning_details, and optional tool_calls
    so both the tool-call path and the final-response path share one builder.
    """
    assistant_tool_calls = getattr(assistant_message, "tool_calls", None)
    reasoning_text = agent._extract_reasoning(assistant_message)
    _from_structured = bool(reasoning_text)

    # Fallback: extract inline <think> blocks from content when no structured
    # reasoning fields are present (some models/providers embed thinking
    # directly in the content rather than returning separate API fields).
    if not reasoning_text:
        content = assistant_message.content or ""
        think_blocks = re.findall(r'<think>(.*?)</think>', content, flags=re.DOTALL)
        if think_blocks:
            combined = "\n\n".join(b.strip() for b in think_blocks if b.strip())
            reasoning_text = combined or None

    if reasoning_text and agent.verbose_logging:
        logging.debug(f"Captured reasoning ({len(reasoning_text)} chars): {reasoning_text}")

    if reasoning_text and agent.reasoning_callback:
        # Skip callback when streaming is active — reasoning was already
        # displayed during the stream via one of two paths:
        #   (a) _fire_reasoning_delta (structured reasoning_content deltas)
        #   (b) _stream_delta tag extraction (<think>/<REASONING_SCRATCHPAD>)
        # When streaming is NOT active, always fire so non-streaming modes
        # (gateway, batch, quiet) still get reasoning.
        # Any reasoning that wasn't shown during streaming is caught by the
        # CLI post-response display fallback (cli.py _reasoning_shown_this_turn).
        if not agent.stream_delta_callback and not agent._stream_callback:
            try:
                agent.reasoning_callback(reasoning_text)
            except Exception:
                pass

    # Sanitize surrogates from API response — some models (e.g. Kimi/GLM via Ollama)
    # can return invalid surrogate code points that crash json.dumps() on persist.
    _raw_content = assistant_message.content or ""
    _san_content = _sanitize_surrogates(_raw_content)
    if reasoning_text:
        reasoning_text = _sanitize_surrogates(reasoning_text)

    # Strip inline reasoning tags (<think>…</think> etc.) from the stored
    # assistant content.  Reasoning was already captured into
    # ``reasoning_text`` above (either from structured fields or the
    # inline-block fallback), so the raw tags in content are redundant.
    # Leaving them in place caused reasoning to leak to messaging
    # platforms (#8878, #9568), inflate context on subsequent turns
    # (#9306 observed 16% content-size reduction on a real MiniMax
    # session), and pollute generated session titles.  One strip at the
    # storage boundary cleans content for every downstream consumer:
    # API replay, session transcript, gateway delivery, CLI display,
    # compression, title generation.
    if isinstance(_san_content, str) and _san_content:
        _san_content = agent._strip_think_blocks(_san_content).strip()

    # Defence-in-depth: redact credentials (PATs, API keys, Bearer tokens)
    # from assistant content BEFORE the message enters conversation history.
    # If the model accidentally inlines a secret in its natural-language
    # response, catch it here at the persistence boundary so it never
    # reaches state.db, session_*.json, gateway delivery, or compression.
    # Respects HERMES_REDACT_SECRETS via redact_sensitive_text — no-op
    # when disabled. (#19798)
    if isinstance(_san_content, str) and _san_content:
        from agent.redact import redact_sensitive_text
        _san_content = redact_sensitive_text(_san_content)

    msg = {
        "role": "assistant",
        "content": _san_content,
        "reasoning": reasoning_text,
        "finish_reason": finish_reason,
    }

    raw_reasoning_content = getattr(assistant_message, "reasoning_content", None)
    if raw_reasoning_content is None and hasattr(assistant_message, "model_extra"):
        model_extra = getattr(assistant_message, "model_extra", None) or {}
        if isinstance(model_extra, dict) and "reasoning_content" in model_extra:
            raw_reasoning_content = model_extra["reasoning_content"]
    if raw_reasoning_content is not None:
        msg["reasoning_content"] = _sanitize_surrogates(raw_reasoning_content)
    elif assistant_tool_calls and agent._needs_thinking_reasoning_pad():
        # DeepSeek v4 thinking mode and Kimi / Moonshot thinking mode
        # both require reasoning_content on every assistant tool-call
        # message. Without it, replaying the persisted message causes
        # HTTP 400 ("The reasoning_content in the thinking mode must
        # be passed back to the API"). Include streamed reasoning
        # text when captured; otherwise pad with a single space —
        # DeepSeek V4 Pro tightened validation and rejects empty
        # string ("The reasoning content in the thinking mode must
        # be passed back to the API"). A space satisfies non-empty
        # checks everywhere without leaking fabricated reasoning.
        # Refs #15250, #17400, #17341.
        msg["reasoning_content"] = reasoning_text or " "

    # Additive fallback (refs #16844, #16884). Streaming-only providers
    # (glm, MiniMax, gpt-5.x via aigw, Anthropic via openai-compat shims)
    # accumulate reasoning through ``delta.reasoning_content`` chunks
    # but never land it on the message object as a top-level attribute,
    # so neither branch above fires and the chain-of-thought is stored
    # only under the internal ``reasoning`` key. When the user later
    # replays that history through a DeepSeek-v4 / Kimi thinking model,
    # the missing ``reasoning_content`` causes HTTP 400 ("The
    # reasoning_content in the thinking mode must be passed back to the
    # API.").
    #
    # Promote the already-sanitized streamed ``reasoning_text`` to
    # ``reasoning_content`` at write time, but ONLY when no prior branch
    # already set it AND we actually captured reasoning text. This
    # preserves every existing behavior:
    #   - SDK-exposed ``reasoning_content`` (OpenAI/Moonshot/DeepSeek SDK)
    #     still wins.
    #   - DeepSeek tool-call ""-pad (#15250) still fires.
    #   - Non-thinking turns with no reasoning leave the field absent,
    #     so ``_copy_reasoning_content_for_api``'s cross-provider leak
    #     guard (#15748) and ``reasoning``→``reasoning_content``
    #     promotion tiers still apply at replay time.
    if "reasoning_content" not in msg and reasoning_text and not agent._provider_rejects_reasoning_content():
        msg["reasoning_content"] = reasoning_text

    if hasattr(assistant_message, 'reasoning_details') and assistant_message.reasoning_details:
        # Pass reasoning_details back unmodified so providers (OpenRouter,
        # Anthropic, OpenAI) can maintain reasoning continuity across turns.
        # Each provider may include opaque fields (signature, encrypted_content)
        # that must be preserved exactly.
        raw_details = assistant_message.reasoning_details
        preserved = []
        for d in raw_details:
            if isinstance(d, dict):
                preserved.append(d)
            elif hasattr(d, "__dict__"):
                preserved.append(d.__dict__)
            elif hasattr(d, "model_dump"):
                preserved.append(d.model_dump())
        if preserved:
            msg["reasoning_details"] = preserved

    # Codex Responses API: preserve encrypted reasoning items for
    # multi-turn continuity. These get replayed as input on the next turn.
    codex_items = getattr(assistant_message, "codex_reasoning_items", None)
    if codex_items:
        msg["codex_reasoning_items"] = codex_items

    # Codex Responses API: preserve exact assistant message items (with
    # id/phase) so follow-up turns can replay structured items instead of
    # flattening to plain text. This is required for prefix cache hits.
    codex_message_items = getattr(assistant_message, "codex_message_items", None)
    if codex_message_items:
        msg["codex_message_items"] = codex_message_items

    if assistant_tool_calls:
        tool_calls = []
        for tool_call in assistant_tool_calls:
            raw_id = getattr(tool_call, "id", None)
            call_id = getattr(tool_call, "call_id", None)
            if not isinstance(call_id, str) or not call_id.strip():
                embedded_call_id, _ = agent._split_responses_tool_id(raw_id)
                call_id = embedded_call_id
            if not isinstance(call_id, str) or not call_id.strip():
                if isinstance(raw_id, str) and raw_id.strip():
                    call_id = raw_id.strip()
                else:
                    _fn = getattr(tool_call, "function", None)
                    _fn_name = getattr(_fn, "name", "") if _fn else ""
                    _fn_args = getattr(_fn, "arguments", "{}") if _fn else "{}"
                    call_id = agent._deterministic_call_id(_fn_name, _fn_args, len(tool_calls))
            call_id = call_id.strip()

            response_item_id = getattr(tool_call, "response_item_id", None)
            if not isinstance(response_item_id, str) or not response_item_id.strip():
                _, embedded_response_item_id = agent._split_responses_tool_id(raw_id)
                response_item_id = embedded_response_item_id

            response_item_id = agent._derive_responses_function_call_id(
                call_id,
                response_item_id if isinstance(response_item_id, str) else None,
            )

            tc_dict = {
                "id": call_id,
                "call_id": call_id,
                "response_item_id": response_item_id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                },
            }
            # Defence-in-depth: redact credentials from tool call arguments
            # before they enter conversation history. Tool execution uses the
            # raw API response object, not this dict, so redacting the
            # persisted shape is safe and only affects storage. Catches the
            # case where a model accidentally inlines a secret into a tool
            # call (e.g. `terminal(command="curl -H 'Authorization: Bearer
            # sk-...'")`). (#19798)
            if isinstance(tc_dict["function"]["arguments"], str):
                from agent.redact import redact_sensitive_text
                tc_dict["function"]["arguments"] = redact_sensitive_text(
                    tc_dict["function"]["arguments"]
                )
            # Preserve extra_content (e.g. Gemini thought_signature) so it
            # is sent back on subsequent API calls.  Without this, Gemini 3
            # thinking models reject the request with a 400 error.
            extra = getattr(tool_call, "extra_content", None)
            if extra is not None:
                if hasattr(extra, "model_dump"):
                    extra = extra.model_dump()
                tc_dict["extra_content"] = extra
            tool_calls.append(tc_dict)
        msg["tool_calls"] = tool_calls

    return msg



def try_activate_fallback(agent, reason: "FailoverReason | None" = None) -> bool:
    """Switch to the next fallback model/provider in the chain.

    Called when the current model is failing after retries.  Swaps the
    OpenAI client, model slug, and provider in-place so the retry loop
    can continue with the new backend.  Advances through the chain on
    each call; returns False when exhausted.

    Uses the centralized provider router (resolve_provider_client) for
    auth resolution and client construction — no duplicated provider→key
    mappings.
    """
    if reason in {FailoverReason.rate_limit, FailoverReason.billing}:
        # Only start cooldown when leaving the primary provider.  If we're
        # already on a fallback and chain-switching, the primary wasn't the
        # source of the 429 so the cooldown should not be reset/extended.
        fallback_already_active = bool(getattr(agent, "_fallback_activated", False))
        current_provider = (getattr(agent, "provider", "") or "").strip().lower()
        primary_provider = ((agent._primary_runtime or {}).get("provider") or "").strip().lower()
        if (not fallback_already_active) or (primary_provider and current_provider == primary_provider):
            agent._rate_limited_until = time.monotonic() + 60
    if agent._fallback_index >= len(agent._fallback_chain):
        return False

    fb = agent._fallback_chain[agent._fallback_index]
    agent._fallback_index += 1
    fb_provider = (fb.get("provider") or "").strip().lower()
    fb_model = (fb.get("model") or "").strip()
    if not fb_provider or not fb_model:
        return agent._try_activate_fallback()  # skip invalid, try next

    # Skip entries that resolve to the current (provider, model) — falling
    # back to the same backend that just failed loops the failure. Compare
    # base_url too so two distinct custom_providers entries pointing at the
    # same shim/proxy URL also dedup. See issue #22548.
    current_provider = (getattr(agent, "provider", "") or "").strip().lower()
    current_model = (getattr(agent, "model", "") or "").strip()
    current_base_url = str(getattr(agent, "base_url", "") or "").rstrip("/").lower()
    fb_base_url_for_dedup = (fb.get("base_url") or "").strip().rstrip("/").lower()
    if fb_provider == current_provider and fb_model == current_model:
        logger.warning(
            "Fallback skip: chain entry %s/%s matches current provider/model",
            fb_provider, fb_model,
        )
        return agent._try_activate_fallback()
    if (
        fb_base_url_for_dedup
        and current_base_url
        and fb_base_url_for_dedup == current_base_url
        and fb_model == current_model
    ):
        logger.warning(
            "Fallback skip: chain entry base_url %s matches current backend",
            fb_base_url_for_dedup,
        )
        return agent._try_activate_fallback()

    # Use centralized router for client construction.
    # raw_codex=True because the main agent needs direct responses.stream()
    # access for Codex providers.
    try:
        from agent.auxiliary_client import resolve_provider_client
        # Pass base_url and api_key from fallback config so custom
        # endpoints (e.g. Ollama Cloud) resolve correctly instead of
        # falling through to OpenRouter defaults.
        fb_base_url_hint = (fb.get("base_url") or "").strip() or None
        fb_api_key_hint = (fb.get("api_key") or "").strip() or None
        if not fb_api_key_hint:
            # key_env and api_key_env are both documented aliases (see
            # _normalize_custom_provider_entry in hermes_cli/config.py).
            fb_key_env = (fb.get("key_env") or fb.get("api_key_env") or "").strip()
            if fb_key_env:
                fb_api_key_hint = os.getenv(fb_key_env, "").strip() or None
        # For Ollama Cloud endpoints, pull OLLAMA_API_KEY from env
        # when no explicit key is in the fallback config. Host match
        # (not substring) — see GHSA-76xc-57q6-vm5m.
        if fb_base_url_hint and base_url_host_matches(fb_base_url_hint, "ollama.com") and not fb_api_key_hint:
            fb_api_key_hint = os.getenv("OLLAMA_API_KEY") or None
        fb_client, _resolved_fb_model = resolve_provider_client(
            fb_provider, model=fb_model, raw_codex=True,
            explicit_base_url=fb_base_url_hint,
            explicit_api_key=fb_api_key_hint)
        if fb_client is None:
            logger.warning(
                "Fallback to %s failed: provider not configured",
                fb_provider)
            return agent._try_activate_fallback()  # try next in chain
        try:
            from hermes_cli.model_normalize import normalize_model_for_provider

            fb_model = normalize_model_for_provider(fb_model, fb_provider)
        except Exception as _norm_err:
            logger.warning(
                "Could not normalize fallback model %r for provider %r: %s",
                fb_model, fb_provider, _norm_err,
            )

        # Determine api_mode from provider / base URL / model
        fb_api_mode = "chat_completions"
        fb_base_url = str(fb_client.base_url)
        _fb_is_azure = agent._is_azure_openai_url(fb_base_url)
        if fb_provider == "openai-codex":
            fb_api_mode = "codex_responses"
        elif fb_provider == "anthropic" or fb_base_url.rstrip("/").lower().endswith("/anthropic"):
            fb_api_mode = "anthropic_messages"
        elif _fb_is_azure:
            # Azure OpenAI serves gpt-5.x on /chat/completions — does NOT
            # support the Responses API. Stay on chat_completions.
            fb_api_mode = "chat_completions"
        elif agent._is_direct_openai_url(fb_base_url):
            fb_api_mode = "codex_responses"
        elif agent._provider_model_requires_responses_api(
            fb_model,
            provider=fb_provider,
        ):
            # GPT-5.x models usually need Responses API, but keep
            # provider-specific exceptions like Copilot gpt-5-mini on
            # chat completions.
            fb_api_mode = "codex_responses"
        elif fb_provider == "bedrock" or (
            base_url_hostname(fb_base_url).startswith("bedrock-runtime.")
            and base_url_host_matches(fb_base_url, "amazonaws.com")
        ):
            fb_api_mode = "bedrock_converse"

        old_model = agent.model

        # Clear the per-config context_length override so the fallback
        # model's actual context window is resolved instead of inheriting
        # the stale value from the previous model.  See #22387.
        agent._config_context_length = None
        agent.model = fb_model
        agent.provider = fb_provider
        agent.base_url = fb_base_url
        agent.api_mode = fb_api_mode
        if hasattr(agent, "_transport_cache"):
            agent._transport_cache.clear()
        agent._fallback_activated = True

        # Clear the credential pool when the fallback provider doesn't match
        # the pool's provider.  The pool was seeded for the primary provider;
        # leaving it attached means downstream recovery (rate_limit / billing /
        # auth) calls ``_swap_credential`` with a primary entry which overwrites
        # the agent's ``base_url`` back to the primary's endpoint — every
        # fallback request then 404s against the wrong host.  See #33163.
        # When the fallback shares the pool's provider (e.g. both openrouter
        # entries with different routing) the pool is preserved.
        _existing_pool = getattr(agent, "_credential_pool", None)
        if _existing_pool is not None:
            if isinstance(getattr(agent, "_primary_runtime", None), dict):
                agent._primary_runtime.setdefault("credential_pool", _existing_pool)
            _pool_provider = (getattr(_existing_pool, "provider", "") or "").strip().lower()
            if _pool_provider and _pool_provider != fb_provider:
                logger.info(
                    "Fallback to %s/%s: clearing primary credential pool "
                    "(pool_provider=%s) to prevent cross-provider contamination",
                    fb_provider, fb_model, _pool_provider,
                )
                agent._credential_pool = None
        if getattr(agent, "_credential_pool", None) is None and not fb_api_key_hint:
            try:
                from agent.credential_pool import load_pool
                _fb_pool = load_pool(fb_provider)
                if (
                    _fb_pool is not None
                    and _fb_pool.has_credentials()
                    and len(getattr(_fb_pool, "entries", []) or []) > 1
                ):
