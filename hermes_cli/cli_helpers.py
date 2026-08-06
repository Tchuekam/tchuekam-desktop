"""
CLI Process, Environment, and Cleanup Utilities for Hermes CLI.
"""

import os
import sys
import logging
from typing import Any

logger = logging.getLogger(__name__)

_cleanup_done = False
_active_agent_ref = None
_deferred_agent_startup_done = False
_tui_input_modes_active = False


def _sync_process_session_id(session_id: str) -> None:
    """Keep process-local session-id consumers aligned after CLI switches."""
    from gateway.session_context import set_current_session_id
    set_current_session_id(session_id)


def get_job(*args, **kwargs):
    from cron import get_job as _get_job
    return _get_job(*args, **kwargs)


def _cleanup_all_terminals(*args, **kwargs):
    from tools.terminal_tool import cleanup_all_environments
    return cleanup_all_environments(*args, **kwargs)


def set_sudo_password_callback(*args, **kwargs):
    from tools.terminal_tool import set_sudo_password_callback as _set_sudo_password_callback
    return _set_sudo_password_callback(*args, **kwargs)


def set_approval_callback(*args, **kwargs):
    from tools.terminal_tool import set_approval_callback as _set_approval_callback
    return _set_approval_callback(*args, **kwargs)


def set_secret_capture_callback(*args, **kwargs):
    from tools.skills_tool import set_secret_capture_callback as _set_secret_capture_callback
    return _set_secret_capture_callback(*args, **kwargs)


def _cleanup_all_browsers(*args, **kwargs):
    from tools.browser_tool import _emergency_cleanup_all_sessions
    return _emergency_cleanup_all_sessions(*args, **kwargs)


def _mark_tui_input_modes_active() -> None:
    """Record that the TUI app started, so _run_cleanup resets input modes."""
    global _tui_input_modes_active
    _tui_input_modes_active = True


def _prepare_deferred_agent_startup() -> None:
    """Run Termux-deferred agent discovery before the first real agent turn."""
    global _deferred_agent_startup_done
    if _deferred_agent_startup_done:
        return
    if os.environ.get("HERMES_DEFER_AGENT_STARTUP") != "1":
        return
    _deferred_agent_startup_done = True
    _accept_hooks = os.environ.get("HERMES_ACCEPT_HOOKS", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        from hermes_cli.plugins import discover_plugins
        discover_plugins()
    except Exception:
        logger.warning(
            "plugin discovery failed at deferred CLI startup",
            exc_info=True,
        )
    try:
        from hermes_cli.mcp_startup import start_background_mcp_discovery
        start_background_mcp_discovery(
            logger=logger,
            thread_name="termux-cli-mcp-discovery",
        )
    except Exception:
        logger.debug(
            "MCP tool discovery failed at deferred CLI startup",
            exc_info=True,
        )
    try:
        from agent.shell_hooks import register_from_config
        from hermes_cli.config import load_config
        register_from_config(load_config(), accept_hooks=_accept_hooks)
    except Exception:
        logger.debug(
            "shell-hook registration failed at deferred CLI startup",
            exc_info=True,
        )


def _reset_terminal_input_modes_on_exit() -> None:
    """Best-effort: disable focus reporting + mouse tracking on TUI exit."""
    global _tui_input_modes_active
    if not _tui_input_modes_active:
        return
    if not sys.stdout or not getattr(sys.stdout, "isatty", lambda: False)():
        return
    try:
        sys.stdout.write("\x1b[?1004l\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l")
        sys.stdout.flush()
    except Exception:
        pass


def _run_cleanup():
    """Run resource cleanup exactly once."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    _reset_terminal_input_modes_on_exit()

    try:
        _cleanup_all_terminals()
    except Exception:
        pass
    try:
        _cleanup_all_browsers()
    except Exception:
        pass
    try:
        from tools.mcp_tool import shutdown_mcp_servers
        shutdown_mcp_servers()
    except Exception:
        pass
    try:
        from agent.auxiliary_client import shutdown_cached_clients
        shutdown_cached_clients()
    except Exception:
        pass
    try:
        from hermes_cli.plugins import invoke_hook as _invoke_hook
        _invoke_hook("on_session_finalize", session_id=_active_agent_ref.session_id if _active_agent_ref else None, platform="cli")
    except Exception:
        pass
    try:
        if _active_agent_ref and hasattr(_active_agent_ref, 'shutdown_memory_provider'):
            _session_msgs = getattr(_active_agent_ref, '_session_messages', None)
            if isinstance(_session_msgs, list):
                _active_agent_ref.shutdown_memory_provider(_session_msgs)
            else:
                _active_agent_ref.shutdown_memory_provider()
    except Exception:
        pass
