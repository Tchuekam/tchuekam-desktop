"""Implementation of :meth:`AIAgent.__init__` — extracted as a module function.

``AIAgent.__init__`` is one of the longest methods in the codebase (60+
parameters, ~1,400 lines of attribute initialization, provider
auto-detection, credential resolution, context-engine bootstrap, etc.).
Keeping it in ``run_agent.py`` bloats that file with code that's mostly
"setup state, then forget".

After this extraction the body lives here as ``init_agent(agent, ...)``
and :meth:`AIAgent.__init__` is a thin wrapper that calls
``init_agent(self, ...)``.  All imports the body needs at module-load
time are listed below; the body also performs many lazy imports inside
its own scope that come along unchanged.

Symbols that tests patch on ``run_agent.*`` (``OpenAI``, ``cleanup_vm``,
etc.) are resolved through :func:`_ra` so the patch contract is
preserved.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlunparse

from agent.context_compressor import ContextCompressor
from agent.iteration_budget import IterationBudget
from agent.memory_manager import StreamingContextScrubber
from agent.model_metadata import (
    MINIMUM_CONTEXT_LENGTH,
    fetch_model_metadata,
    is_local_endpoint,
    query_ollama_num_ctx,
)
from agent.process_bootstrap import _install_safe_stdio
from agent.subdirectory_hints import SubdirectoryHintTracker
from agent.think_scrubber import StreamingThinkScrubber
from agent.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
    ToolGuardrailDecision,
)
from hermes_cli.config import cfg_get
from hermes_cli.timeouts import get_provider_request_timeout
from hermes_constants import get_hermes_home
from utils import base_url_host_matches

# Use the same logger name as run_agent so tests patching ``run_agent.logger``
# capture our warnings.  (run_agent.py also does
# ``logger = logging.getLogger(__name__)``, which resolves to "run_agent"
# from inside that module.)
logger = logging.getLogger("run_agent")


def _ra():
    """Lazy reference to ``run_agent`` so callers can patch
    ``run_agent.OpenAI`` / ``run_agent.cleanup_vm`` / ... and have those
    patches reach this code path.
    """
    import run_agent
    return run_agent


def _normalized_custom_base_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/")


def _custom_provider_model_matches(agent_model: str, entry: Dict[str, Any]) -> bool:
    provider_model = str(entry.get("model", "") or "").strip().lower()
    if not provider_model:
        return True
    return provider_model == str(agent_model or "").strip().lower()


def _custom_provider_extra_body_for_agent(
    *,
    provider: str,
    model: str,
    base_url: str,
    custom_providers: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if (provider or "").strip().lower() != "custom":
        return None

    target_url = _normalized_custom_base_url(base_url)
    if not target_url:
        return None

    fallback: Optional[Dict[str, Any]] = None
    for entry in custom_providers or []:
        if not isinstance(entry, dict):
            continue
        if _normalized_custom_base_url(entry.get("base_url")) != target_url:
            continue
        extra_body = entry.get("extra_body")
        if not isinstance(extra_body, dict) or not extra_body:
            continue
        provider_model = str(entry.get("model", "") or "").strip()
        if provider_model:
            if _custom_provider_model_matches(model, entry):
                return dict(extra_body)
        elif fallback is None:
            fallback = dict(extra_body)

    return fallback


def _merge_custom_provider_extra_body(agent, custom_providers: List[Dict[str, Any]]) -> None:
    extra_body = _custom_provider_extra_body_for_agent(
        provider=agent.provider,
        model=agent.model,
        base_url=agent.base_url,
        custom_providers=custom_providers,
    )
    if not extra_body:
        return

    overrides = dict(getattr(agent, "request_overrides", {}) or {})
    merged_extra_body = dict(extra_body)
    existing_extra_body = overrides.get("extra_body")
    if isinstance(existing_extra_body, dict):
        merged_extra_body.update(existing_extra_body)
    overrides["extra_body"] = merged_extra_body
    agent.request_overrides = overrides


def _resolve_auto_fallback_chain(
    primary_provider: str,
    primary_model: str = "",
) -> List[Dict[str, str]]:
    """Build an emergency fallback provider chain from the configured env keys.

    Module scope is load-bearing: agent/conversation_loop.py imports this by
    name when a rate limit arrives and no fallback chain was configured. It
    used to be nested inside init_agent(), where it was both unreachable from
    outside and never called locally — so that import raised ImportError on
    the first 429 and took the whole turn down instead of failing over.
    """
    try:
        from hermes_cli.fallback_config import resolve_effective_fallback_chain
        resolved = resolve_effective_fallback_chain(
            primary_provider=primary_provider,
            primary_model=primary_model,
        )
        if resolved:
            return resolved
    except Exception:
        pass

    try:
        from hermes_cli.config import load_env
        env = load_env()
    except Exception:
        env = {}

    def _has_key(key_name: str) -> bool:
        val = env.get(key_name) or os.environ.get(key_name) or ""
        return bool(val.strip())

    primary = (primary_provider or "").strip().lower()
    chain: List[Dict[str, str]] = []

    # 1. Groq (Fast & generous rate limits)
    if primary != "groq" and (_has_key("GROQ_API_KEY") or _has_key("GROQ_API_KEYS")):
        chain.append({"provider": "groq", "model": "openai/gpt-oss-120b"})
        chain.append({"provider": "groq", "model": "qwen/qwen3.8-27b"})
        chain.append({"provider": "groq", "model": "llama-3.3-70b-versatile"})

    # 2. OpenRouter
    if primary != "openrouter" and (_has_key("OPENROUTER_API_KEY") or _has_key("OPENROUTER_API_KEYS")):
        chain.append({"provider": "openrouter", "model": "google/gemini-2.5-flash"})

    # 3. Google Gemini
    if primary not in {"gemini", "google-gemini-cli"} and (
        _has_key("GOOGLE_API_KEY") or _has_key("GEMINI_API_KEY") or _has_key("GEMINI_API_KEYS")
    ):
        chain.append({"provider": "gemini", "model": "gemini-2.5-flash"})

    # 4. OpenAI
    if primary != "openai-api" and (_has_key("OPENAI_API_KEY") or _has_key("OPENAI_API_KEYS")):
        chain.append({"provider": "openai-api", "model": "gpt-4o-mini"})

    # 5. DeepSeek
    if primary != "deepseek" and (_has_key("DEEPSEEK_API_KEY") or _has_key("DEEPSEEK_API_KEYS")):
        chain.append({"provider": "deepseek", "model": "deepseek-chat"})

    return chain


def init_agent(
    agent,
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
    """
    Initialize the AI Agent.

    Args:
        base_url (str): Base URL for the model API (optional)
        api_key (str): API key for authentication (optional, uses env var if not provided)
        provider (str): Provider identifier (optional; used for telemetry/routing hints)
        api_mode (str): API mode override: "chat_completions" or "codex_responses"
        model (str): Model name to use (default: "anthropic/claude-opus-4.6")
        max_iterations (int): Maximum number of tool calling iterations (default: 90)
        tool_delay (float): Delay between tool calls in seconds (default: 1.0)
        enabled_toolsets (List[str]): Only enable tools from these toolsets (optional)
        disabled_toolsets (List[str]): Disable tools from these toolsets (optional)
        save_trajectories (bool): Whether to save conversation trajectories to JSONL files (default: False)
        verbose_logging (bool): Enable verbose logging for debugging (default: False)
        quiet_mode (bool): Suppress progress output for clean CLI experience (default: False)
        ephemeral_system_prompt (str): System prompt used during agent execution but NOT saved to trajectories (optional)
        log_prefix_chars (int): Number of characters to show in log previews for tool calls/responses (default: 100)
        log_prefix (str): Prefix to add to all log messages for identification in parallel processing (default: "")
        providers_allowed (List[str]): OpenRouter providers to allow (optional)
        providers_ignored (List[str]): OpenRouter providers to ignore (optional)
        providers_order (List[str]): OpenRouter providers to try in order (optional)
        provider_sort (str): Sort providers by price/throughput/latency (optional)
        openrouter_min_coding_score (float): Coding-score floor (0.0-1.0) for the
            openrouter/pareto-code router. Only applied when model == "openrouter/pareto-code".
            None or empty = let OpenRouter pick the strongest available coder.
        session_id (str): Pre-generated session ID for logging (optional, auto-generated if not provided)
        tool_progress_callback (callable): Callback function(tool_name, args_preview) for progress notifications
        clarify_callback (callable): Callback function(question, choices) -> str for interactive user questions.
            Provided by the platform layer (CLI or gateway). If None, the clarify tool returns an error.
        max_tokens (int): Maximum tokens for model responses (optional, uses model default if not set)
        reasoning_config (Dict): OpenRouter reasoning configuration override (e.g. {"effort": "none"} to disable thinking).
            If None, defaults to {"enabled": True, "effort": "medium"} for OpenRouter. Set to disable/customize reasoning.
        prefill_messages (List[Dict]): Messages to prepend to conversation history as prefilled context.
            Useful for injecting a few-shot example or priming the model's response style.
            Example: [{"role": "user", "content": "Hi!"}, {"role": "assistant", "content": "Hello!"}]
            NOTE: Anthropic Sonnet 4.6+ and Opus 4.6+ reject a conversation that ends on an
            assistant-role message (400 error).  For those models use structured outputs or
            output_config.format instead of a trailing-assistant prefill.
        platform (str): The interface platform the user is on (e.g. "cli", "telegram", "discord", "whatsapp").
            Used to inject platform-specific formatting hints into the system prompt.
        skip_context_files (bool): If True, skip auto-injection of SOUL.md, AGENTS.md, and .cursorrules
            into the system prompt. Use this for batch processing and data generation to avoid
            polluting trajectories with user-specific persona or project instructions.
        load_soul_identity (bool): If True, still use ~/.hermes/SOUL.md as the primary
            identity even when skip_context_files=True. Project context files from the cwd
            remain skipped.
    """
    _install_safe_stdio()

    agent.model = model
    agent.max_iterations = max_iterations
    # Shared iteration budget — parent creates, children inherit.
    # Consumed by every LLM turn across parent + all subagents.
    agent.iteration_budget = iteration_budget or IterationBudget(max_iterations)
    agent.tool_delay = tool_delay
    agent.save_trajectories = save_trajectories
    agent.verbose_logging = verbose_logging
    agent.quiet_mode = quiet_mode
    agent.ephemeral_system_prompt = ephemeral_system_prompt
    agent.platform = platform  # "cli", "telegram", "discord", "whatsapp", etc.
    agent._user_id = user_id  # Platform user identifier (gateway sessions)
    agent._user_id_alt = user_id_alt  # Optional stable alternate platform identifier
    agent._user_name = user_name
    agent._chat_id = chat_id
    agent._chat_name = chat_name
    agent._chat_type = chat_type
    agent._thread_id = thread_id
    agent._gateway_session_key = gateway_session_key  # Stable per-chat key (e.g. agent:main:telegram:dm:123)
    # Pluggable print function — CLI replaces this with _cprint so that
    # raw ANSI status lines are routed through prompt_toolkit's renderer
    # instead of going directly to stdout where patch_stdout's StdoutProxy
    # would mangle the escape sequences.  None = use builtins.print.
    agent._print_fn = None
    agent.background_review_callback = None  # Optional sync callback for gateway delivery
    agent.skip_context_files = skip_context_files
    agent.load_soul_identity = load_soul_identity
    agent.pass_session_id = pass_session_id
    agent._credential_pool = credential_pool
    agent.log_prefix_chars = log_prefix_chars
    agent.log_prefix = f"{log_prefix} " if log_prefix else ""
    # Store effective base URL for feature detection (prompt caching, reasoning, etc.)
    agent.base_url = base_url or ""
    provider_name = provider.strip().lower() if isinstance(provider, str) and provider.strip() else None
    agent.provider = provider_name or ""
    if agent.provider == "mbowagpt" or str(model or "").strip().lower().startswith("mbowagpt"):
        agent._requested_mbowagpt_model = (model or "").strip() or "mbowagpt-auto"
    else:
        agent._requested_mbowagpt_model = None
    agent._active_mbowagpt_role = None
    agent._active_mbowagpt_route = None
    agent._local_served_model = None
    agent._offline_local_fallback_active = False
    agent.intelligence_callback = None
    agent.acp_command = acp_command or command
    agent.acp_args = list(acp_args or args or [])
    if api_mode in {"chat_completions", "codex_responses", "anthropic_messages", "bedrock_converse", "codex_app_server"}:
        agent.api_mode = api_mode
    elif agent.provider == "openai-codex":
        agent.api_mode = "codex_responses"
    elif agent.provider in {"xai", "xai-oauth"}:
        agent.api_mode = "codex_responses"
    elif (provider_name is None) and (
        agent._base_url_hostname == "chatgpt.com"
        and "/backend-api/codex" in agent._base_url_lower
    ):
        agent.api_mode = "codex_responses"
        agent.provider = "openai-codex"
    elif (provider_name is None) and agent._base_url_hostname == "api.x.ai":
        agent.api_mode = "codex_responses"
        agent.provider = "xai"
    elif agent.provider == "anthropic" or (provider_name is None and agent._base_url_hostname == "api.anthropic.com"):
        agent.api_mode = "anthropic_messages"
        agent.provider = "anthropic"
    elif agent._base_url_lower.rstrip("/").endswith("/anthropic"):
        # Third-party Anthropic-compatible endpoints (e.g. MiniMax, DashScope)
        # use a URL convention ending in /anthropic. Auto-detect these so the
        # Anthropic Messages API adapter is used instead of chat completions.
        agent.api_mode = "anthropic_messages"
    elif agent.provider == "bedrock" or (
        agent._base_url_hostname.startswith("bedrock-runtime.")
        and base_url_host_matches(agent._base_url_lower, "amazonaws.com")
    ):
        # AWS Bedrock — auto-detect from provider name or base URL
        # (bedrock-runtime.<region>.amazonaws.com).
        agent.api_mode = "bedrock_converse"
    else:
        agent.api_mode = "chat_completions"

    # Eagerly warm the transport cache so import errors surface at init,
    # not mid-conversation.  Also validates the api_mode is registered.
    try:
        agent._get_transport()
    except Exception:
        pass  # Non-fatal — transport may not exist for all modes yet

    try:
        from hermes_cli.model_normalize import (
            _AGGREGATOR_PROVIDERS,
            normalize_model_for_provider,
        )

        if agent.provider not in _AGGREGATOR_PROVIDERS:
            agent.model = normalize_model_for_provider(agent.model, agent.provider)
    except Exception:
        pass

    # GPT-5.x models usually require the Responses API path, but some
    # providers have exceptions (for example Copilot's gpt-5-mini still
    # uses chat completions). Also auto-upgrade for direct OpenAI URLs
    # (api.openai.com) since all newer tool-calling models prefer
    # Responses there. ACP runtimes are excluded: CopilotACPClient
    # handles its own routing and does not implement the Responses API
    # surface.
    # When api_mode was explicitly provided, respect it — the user
    # knows what their endpoint supports (#10473).
    # Exception: Azure OpenAI serves gpt-5.x on /chat/completions and
    # does NOT support the Responses API — skip the upgrade for Azure
    # (openai.azure.com), even though it looks OpenAI-compatible.
    if (
        api_mode is None
        and agent.api_mode == "chat_completions"
        and agent.provider != "copilot-acp"
        and not str(agent.base_url or "").lower().startswith("acp://copilot")
        and not str(agent.base_url or "").lower().startswith("acp+tcp://")
        and not agent._is_azure_openai_url()
        and (
            agent._is_direct_openai_url()
            or agent._provider_model_requires_responses_api(
                agent.model,
                provider=agent.provider,
            )
        )
    ):
        agent.api_mode = "codex_responses"
        # Invalidate the eager-warmed transport cache — api_mode changed
        # from chat_completions to codex_responses after the warm at __init__.
        if hasattr(agent, "_transport_cache"):
            agent._transport_cache.clear()

    # Pre-warm OpenRouter model metadata cache in a background thread.
    # fetch_model_metadata() is cached for 1 hour; this avoids a blocking
    # HTTP request on the first API response when pricing is estimated.
    # Use a process-level Event so this thread is only spawned once — a new
    # AIAgent is created for every gateway request, so without the guard
    # each message leaks one OS thread and the process eventually exhausts
    # the system thread limit (RuntimeError: can't start new thread).
    if (agent.provider == "openrouter" or agent._is_openrouter_url()) and \
            not _ra()._openrouter_prewarm_done.is_set():
        _ra()._openrouter_prewarm_done.set()
        threading.Thread(
            target=fetch_model_metadata,
            daemon=True,
            name="openrouter-prewarm",
        ).start()

    agent.tool_progress_callback = tool_progress_callback
    agent.tool_start_callback = tool_start_callback
    agent.tool_complete_callback = tool_complete_callback
    agent.suppress_status_output = False
    agent.thinking_callback = thinking_callback
    agent.reasoning_callback = reasoning_callback
    agent.clarify_callback = clarify_callback
    agent.step_callback = step_callback
    agent.stream_delta_callback = stream_delta_callback
    agent.interim_assistant_callback = interim_assistant_callback
    agent.status_callback = status_callback
    agent.tool_gen_callback = tool_gen_callback

    
    # Tool execution state — allows _vprint during tool execution
    # even when stream consumers are registered (no tokens streaming then)
    agent._executing_tools = False
    agent._tool_guardrails = ToolCallGuardrailController()
    agent._tool_guardrail_halt_decision: ToolGuardrailDecision | None = None

    # Interrupt mechanism for breaking out of tool loops
    agent._interrupt_requested = False
    agent._interrupt_message = None  # Optional message that triggered interrupt
    agent._execution_thread_id: int | None = None  # Set at run_conversation() start
    agent._interrupt_thread_signal_pending = False
    agent._client_lock = threading.RLock()

    # /steer mechanism — inject a user note into the next tool result
    # without interrupting the agent. Unlike interrupt(), steer() does
    # NOT set _interrupt_requested; it waits for the current tool batch
    # to finish naturally, then the drain hook appends the text to the
    # last tool result's content so the model sees it on its next
    # iteration. Message-role alternation is preserved (we modify an
    # existing tool message rather than inserting a new user turn).
    agent._pending_steer: Optional[str] = None
    agent._pending_steer_lock = threading.Lock()

    # Concurrent-tool worker thread tracking.  `_execute_tool_calls_concurrent`
    # runs each tool on its own ThreadPoolExecutor worker — those worker
    # threads have tids distinct from `_execution_thread_id`, so
    # `_set_interrupt(True, _execution_thread_id)` alone does NOT cause
    # `is_interrupted()` inside the worker to return True.  Track the
    # workers here so `interrupt()` / `clear_interrupt()` can fan out to
    # their tids explicitly.
    agent._tool_worker_threads: set[int] = set()
    agent._tool_worker_threads_lock = threading.Lock()
    
    # Subagent delegation state
    agent._delegate_depth = 0        # 0 = top-level agent, incremented for children
    agent._active_children = []      # Running child AIAgents (for interrupt propagation)
    agent._active_children_lock = threading.Lock()
    
    # Store OpenRouter provider preferences
    agent.providers_allowed = providers_allowed
    agent.providers_ignored = providers_ignored
    agent.providers_order = providers_order
    agent.provider_sort = provider_sort
    agent.provider_require_parameters = provider_require_parameters
    agent.provider_data_collection = provider_data_collection
    agent.openrouter_min_coding_score = openrouter_min_coding_score

    # Store toolset filtering options
    agent.enabled_toolsets = enabled_toolsets
    agent.disabled_toolsets = disabled_toolsets
    
    # Model response configuration
    agent.max_tokens = max_tokens  # None = use model default
    agent.reasoning_config = reasoning_config  # None = use default (medium for OpenRouter)
    agent.service_tier = service_tier
    agent.request_overrides = dict(request_overrides or {})
    agent.prefill_messages = prefill_messages or []  # Prefilled conversation turns
    agent._force_ascii_payload = False
    
    # Anthropic prompt caching: auto-enabled for Claude models on native
    # Anthropic, OpenRouter, and third-party gateways that speak the
    # Anthropic protocol (``api_mode == 'anthropic_messages'``). Reduces
    # input costs by ~75% on multi-turn conversations. Uses system_and_3
    # strategy (4 breakpoints). See ``_anthropic_prompt_cache_policy``
    # for the layout-vs-transport decision.
    agent._use_prompt_caching, agent._use_native_cache_layout = (
        agent._anthropic_prompt_cache_policy()
    )
    # Anthropic supports "5m" (default) and "1h" cache TTL tiers. Read from
    # config.yaml under prompt_caching.cache_ttl; unknown values keep "5m".
    # 1h tier costs 2x on write vs 1.25x for 5m, but amortizes across long
    # sessions with >5-minute pauses between turns (#14971).
    agent._cache_ttl = "5m"
    try:
        from hermes_cli.config import load_config as _load_pc_cfg

        _pc_cfg = _load_pc_cfg().get("prompt_caching", {}) or {}
        _ttl = _pc_cfg.get("cache_ttl", "5m")
        if _ttl in {"5m", "1h"}:
            agent._cache_ttl = _ttl
    except Exception:
        pass

    # Iteration budget: the LLM is only notified when it actually exhausts
    # the iteration budget (api_call_count >= max_iterations).  At that
    # point we inject ONE message, allow one final API call, and if the
    # model doesn't produce a text response, force a user-message asking
    # it to summarise.  No intermediate pressure warnings — they caused
    # models to "give up" prematurely on complex tasks (#7915).
    agent._budget_exhausted_injected = False
    agent._budget_grace_call = False

    # Activity tracking — updated on each API call, tool execution, and
    # stream chunk.  Used by the gateway timeout handler to report what the
    # agent was doing when it was killed, and by the "still working"
    # notifications to show progress.
    agent._last_activity_ts: float = time.time()
    agent._last_activity_desc: str = "initializing"
    agent._current_tool: str | None = None
    agent._api_call_count: int = 0

    # Rate limit tracking — updated from x-ratelimit-* response headers
    # after each API call.  Accessed by /usage slash command.
    agent._rate_limit_state: Optional["RateLimitState"] = None

    # OpenRouter response cache hit counter — incremented when
    # X-OpenRouter-Cache-Status: HIT is seen in streaming response headers.
    agent._or_cache_hits: int = 0

    # Centralized logging — agent.log (INFO+) and errors.log (WARNING+)
    # both live under ~/.hermes/logs/.  Idempotent, so gateway mode
    # (which creates a new AIAgent per message) won't duplicate handlers.
    from hermes_logging import setup_logging, setup_verbose_logging
    setup_logging(hermes_home=_ra()._hermes_home)

    if agent.verbose_logging:
        setup_verbose_logging()
        _ra().logger.info("Verbose logging enabled (third-party library logs suppressed)")
    elif agent.quiet_mode:
        # In quiet mode (CLI default), keep console output clean —
        # but DO NOT raise per-logger levels. Doing so prevents the
        # root logger's file handlers (agent.log, errors.log) from
        # ever seeing the records, because Python checks
        # logger.isEnabledFor() before handler propagation. We rely
        # on the fact that hermes_logging.setup_logging() does not
        # install a console StreamHandler in quiet mode — so INFO
        # records flow to the file handlers but never reach a
        # console. Any future noise reduction belongs at the
        # handler level inside hermes_logging.py, not here.
        pass
    
    # Internal stream callback (set during streaming TTS).
    # Initialized here so _vprint can reference it before run_conversation.
    agent._stream_callback = None
    # Deferred paragraph break flag — set after tool iterations so a
    # single "\n\n" is prepended to the next real text delta.
    agent._stream_needs_break = False
    # Stateful scrubber for <memory-context> spans split across stream
    # deltas (#5719).  sanitize_context() alone can't survive chunk
    # boundaries because the block regex needs both tags in one string.
    agent._stream_context_scrubber = StreamingContextScrubber()
    # Stateful scrubber for reasoning/thinking tags in streamed deltas
    # (#17924).  Replaces the per-delta _strip_think_blocks regex that
    # destroyed downstream state (e.g. MiniMax-M2.7 streaming
    # '<think>' as delta1 and 'Let me check' as delta2 — the regex
    # erased delta1, so downstream state machines never learned a
    # block was open and leaked delta2 as content).
    agent._stream_think_scrubber = StreamingThinkScrubber()
    # Visible assistant text already delivered through live token callbacks
    # during the current model response. Used to avoid re-sending the same
    # commentary when the provider later returns it as a completed interim
    # assistant message.
    agent._current_streamed_assistant_text = ""

    # Optional current-turn user-message override used when the API-facing
    # user message intentionally differs from the persisted transcript
    # (e.g. CLI voice mode adds a temporary prefix for the live call only).
    agent._persist_user_message_idx = None
    agent._persist_user_message_override = None

    # Cache anthropic image-to-text fallbacks per image payload/URL so a
    # single tool loop does not repeatedly re-run auxiliary vision on the
    # same image history.
    agent._anthropic_image_fallback_cache: Dict[str, str] = {}

    # Initialize LLM client via centralized provider router.
    # The router handles auth resolution, base URL, headers, and
    # Codex/Anthropic wrapping for all known providers.
    # raw_codex=True because the main agent needs direct responses.stream()
    # access for Codex Responses API streaming.
    agent._anthropic_client = None
    agent._is_anthropic_oauth = False

    # Resolve per-provider / per-model request timeout once up front so
    # every client construction path below (Anthropic native, OpenAI-wire,
    # router-based implicit auth) can apply it consistently.  Bedrock
    # Claude uses its own timeout path and is not covered here.
    _provider_timeout = get_provider_request_timeout(agent.provider, agent.model)

    if agent.api_mode == "anthropic_messages":
        from agent.anthropic_adapter import build_anthropic_client, resolve_anthropic_token
        # Bedrock + Claude → use AnthropicBedrock SDK for full feature parity
        # (prompt caching, thinking budgets, adaptive thinking).
        _is_bedrock_anthropic = agent.provider == "bedrock"
        if _is_bedrock_anthropic:
            from agent.anthropic_adapter import build_anthropic_bedrock_client
            _region_match = re.search(r"bedrock-runtime\.([a-z0-9-]+)\.", base_url or "")
            _br_region = _region_match.group(1) if _region_match else "us-east-1"
            agent._bedrock_region = _br_region
            agent._anthropic_client = build_anthropic_bedrock_client(_br_region)
            agent._anthropic_api_key = "aws-sdk"
            agent._anthropic_base_url = base_url
            agent._is_anthropic_oauth = False
            agent.api_key = "aws-sdk"
            agent.client = None
            agent._client_kwargs = {}
            if not agent.quiet_mode:
                print(f"🤖 AI Agent initialized with model: {agent.model} (AWS Bedrock + AnthropicBedrock SDK, {_br_region})")
        else:
            # Only fall back to ANTHROPIC_TOKEN when the provider is actually Anthropic.
            # Other anthropic_messages providers (MiniMax, Alibaba, etc.) must use their own API key.
            # Falling back would send Anthropic credentials to third-party endpoints (Fixes #1739, #minimax-401).
            _is_native_anthropic = agent.provider == "anthropic"
            effective_key = (api_key or resolve_anthropic_token() or "") if _is_native_anthropic else (api_key or "")

            # MiniMax OAuth issues short-lived (~15-min) access tokens. The
            # Anthropic SDK caches ``api_key`` as a static string at client
            # construction time, so a session that resolves the bearer once
            # at startup will keep sending the same token until MiniMax
            # returns 401 mid-session. Swap the static string for a callable
            # token provider — ``build_anthropic_client`` recognizes the
            # callable and installs an httpx event hook that mints a fresh
            # bearer per outbound request (re-reading auth.json so a refresh
            # persisted by another process is visible immediately).
            # The cached refresh path is a no-op when the token still has
            # ``MINIMAX_OAUTH_REFRESH_SKEW_SECONDS`` of life left, so steady-
            # state cost is one file read + one timestamp compare per request.
            if agent.provider == "minimax-oauth" and isinstance(effective_key, str) and effective_key:
                try:
                    from hermes_cli.auth import build_minimax_oauth_token_provider
                    effective_key = build_minimax_oauth_token_provider()
                except Exception as _mm_exc:  # noqa: BLE001 — never block startup on this
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "MiniMax OAuth: failed to install per-request token provider "
                        "(%s); falling back to static bearer that will expire ~15min in.",
                        _mm_exc,
                    )

            agent.api_key = effective_key
            agent._anthropic_api_key = effective_key
            agent._anthropic_base_url = base_url
            # Only mark the session as OAuth-authenticated when the token
            # genuinely belongs to native Anthropic.  Third-party providers
            # (MiniMax, Kimi, GLM, LiteLLM proxies) that accept the
            # Anthropic protocol must never trip OAuth code paths — doing
            # so injects Claude-Code identity headers and system prompts
            # that cause 401/403 on their endpoints.  Guards #1739 and
            # the third-party identity-injection bug.
            from agent.anthropic_adapter import _is_oauth_token as _is_oat
            agent._is_anthropic_oauth = _is_oat(effective_key) if (_is_native_anthropic and isinstance(effective_key, str)) else False
            agent._anthropic_client = build_anthropic_client(effective_key, base_url, timeout=_provider_timeout)
            # No OpenAI client needed for Anthropic mode
            agent.client = None
            agent._client_kwargs = {}
            if not agent.quiet_mode:
                print(f"🤖 AI Agent initialized with model: {agent.model} (Anthropic native)")
                # ``effective_key`` may be a callable Entra ID bearer
                # provider for Azure Foundry anthropic_messages mode.
                # The Anthropic adapter installs an httpx event hook
                # that mints a fresh JWT per request — we never
                # invoke or inspect the callable in the banner.
                from agent.azure_identity_adapter import is_token_provider

                if is_token_provider(effective_key):
                    print("🔑 Using credentials: Microsoft Entra ID")
                elif isinstance(effective_key, str) and len(effective_key) > 12:
                    print(f"🔑 Using token: {effective_key[:8]}...{effective_key[-4:]}")
    elif agent.api_mode == "bedrock_converse":
        # AWS Bedrock — uses boto3 directly, no OpenAI client needed.
        # Region is extracted from the base_url or defaults to us-east-1.
        _region_match = re.search(r"bedrock-runtime\.([a-z0-9-]+)\.", base_url or "")
        agent._bedrock_region = _region_match.group(1) if _region_match else "us-east-1"
        # Guardrail config — read from config.yaml at init time.
        agent._bedrock_guardrail_config = None
        try:
            from hermes_cli.config import load_config as _load_br_cfg
            _gr = _load_br_cfg().get("bedrock", {}).get("guardrail", {})
            if _gr.get("guardrail_identifier") and _gr.get("guardrail_version"):
                agent._bedrock_guardrail_config = {
                    "guardrailIdentifier": _gr["guardrail_identifier"],
                    "guardrailVersion": _gr["guardrail_version"],
                }
                if _gr.get("stream_processing_mode"):
                    agent._bedrock_guardrail_config["streamProcessingMode"] = _gr["stream_processing_mode"]
                if _gr.get("trace"):
                    agent._bedrock_guardrail_config["trace"] = _gr["trace"]
        except Exception:
            pass
        agent.client = None
        agent._client_kwargs = {}
        if not agent.quiet_mode:
            _gr_label = " + Guardrails" if agent._bedrock_guardrail_config else ""
            print(f"🤖 AI Agent initialized with model: {agent.model} (AWS Bedrock, {agent._bedrock_region}{_gr_label})")
    else:
        if api_key and base_url:
            # Explicit credentials from CLI/gateway — construct directly.
            # The runtime provider resolver already handled auth for us.
            # Extract query params (e.g. Azure api-version) from base_url
            # and pass via default_query to prevent loss during SDK URL
            # joining (httpx drops query string when joining paths).
            _parsed_url = urlparse(base_url)
            if _parsed_url.query:
                _clean_url = urlunparse(_parsed_url._replace(query=""))
                _query_params = {
                    k: v[0] for k, v in parse_qs(_parsed_url.query).items()
                }
                client_kwargs = {
                    "api_key": api_key,
                    "base_url": _clean_url,
                    "default_query": _query_params,
                }
            else:
                client_kwargs = {"api_key": api_key, "base_url": base_url}
            if _provider_timeout is not None:
                client_kwargs["timeout"] = _provider_timeout
            if agent.provider == "copilot-acp":
                client_kwargs["command"] = agent.acp_command
                client_kwargs["args"] = agent.acp_args
            effective_base = base_url
            if base_url_host_matches(effective_base, "openrouter.ai"):
                from agent.auxiliary_client import build_or_headers
                client_kwargs["default_headers"] = build_or_headers()
            elif base_url_host_matches(effective_base, "integrate.api.nvidia.com"):
                from agent.auxiliary_client import build_nvidia_nim_headers
                client_kwargs["default_headers"] = build_nvidia_nim_headers(effective_base)
            elif base_url_host_matches(effective_base, "api.routermint.com"):
                client_kwargs["default_headers"] = _ra()._routermint_headers()
            elif base_url_host_matches(effective_base, "api.githubcopilot.com"):
                from hermes_cli.models import copilot_default_headers

                client_kwargs["default_headers"] = copilot_default_headers()
            elif base_url_host_matches(effective_base, "api.kimi.com"):
                client_kwargs["default_headers"] = {
                    "User-Agent": "claude-code/0.1.0",
                }
            elif base_url_host_matches(effective_base, "portal.qwen.ai"):
                client_kwargs["default_headers"] = _ra()._qwen_portal_headers()
            elif base_url_host_matches(effective_base, "chatgpt.com"):
                from agent.auxiliary_client import _codex_cloudflare_headers
                client_kwargs["default_headers"] = _codex_cloudflare_headers(api_key)
            elif "default_headers" not in client_kwargs:
                # Fall back to profile.default_headers for providers that
                # declare custom headers (e.g. Kimi User-Agent on non-kimi.com
                # endpoints).
                try:
                    from providers import get_provider_profile as _gpf
                    _ph = _gpf(agent.provider)
                    if _ph and _ph.default_headers:
                        client_kwargs["default_headers"] = dict(_ph.default_headers)
                except Exception:
                    pass
        else:
            # No explicit creds — use the centralized provider router
            from agent.auxiliary_client import resolve_provider_client
            _routed_client, _ = resolve_provider_client(
                agent.provider or "auto", model=agent.model, raw_codex=True)
            if _routed_client is not None:
                client_kwargs = {
                    "api_key": _routed_client.api_key,
                    "base_url": str(_routed_client.base_url),
                }
                if _provider_timeout is not None:
                    client_kwargs["timeout"] = _provider_timeout
                # Preserve provider-specific headers the router set.  The
                # OpenAI SDK stores caller-provided default_headers in
                # _custom_headers; older/mocked clients may expose
                # _default_headers instead.
                _routed_headers = getattr(_routed_client, "_custom_headers", None)
                if not _routed_headers:
                    _routed_headers = getattr(_routed_client, "_default_headers", None)
                if _routed_headers:
                    client_kwargs["default_headers"] = dict(_routed_headers)
            else:
                # When the user explicitly chose a non-OpenRouter provider
                # but no credentials were found, fail fast with a clear
                # message instead of silently routing through OpenRouter.
                _explicit = (agent.provider or "").strip().lower()
                if _explicit and _explicit not in {"auto", "openrouter", "custom"}:
                    # Look up the actual env var name from the provider
                    # config — some providers use non-standard names
                    # (e.g. alibaba → DASHSCOPE_API_KEY, not ALIBABA_API_KEY).
                    _env_hint = f"{_explicit.upper()}_API_KEY"
                    try:
                        from hermes_cli.auth import PROVIDER_REGISTRY
                        _pcfg = PROVIDER_REGISTRY.get(_explicit)
                        if _pcfg and _pcfg.api_key_env_vars:
                            _env_hint = _pcfg.api_key_env_vars[0]
                    except Exception:
                        pass
                    # --- Init-time fallback (#17929) ---
                    _fb_entries = []
                    if isinstance(fallback_model, list):
                        _fb_entries = [
                            f for f in fallback_model
                            if isinstance(f, dict) and f.get("provider") and f.get("model")
                        ]
                    elif isinstance(fallback_model, dict) and fallback_model.get("provider") and fallback_model.get("model"):
                        _fb_entries = [fallback_model]
                    _fb_resolved = False
                    for _fb in _fb_entries:
                        _fb_explicit_key = (_fb.get("api_key") or "").strip() or None
                        if not _fb_explicit_key:
                            _fb_key_env = (_fb.get("key_env") or _fb.get("api_key_env") or "").strip()
                            if _fb_key_env:
                                _fb_explicit_key = os.getenv(_fb_key_env, "").strip() or None
                        _fb_client, _fb_model = resolve_provider_client(
                            _fb["provider"], model=_fb["model"], raw_codex=True,
                            explicit_base_url=_fb.get("base_url"),
                            explicit_api_key=_fb_explicit_key,
                        )
