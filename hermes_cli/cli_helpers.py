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

# Canonical "put the terminal back" sequence, shared by every reset path.
# Lives here rather than in cli.py because cli.py imports from this module,
# and because the two copies had drifted: this module used to inline only the
# five mouse/focus codes, so the atexit path — the one that runs on Ctrl+C,
# SIGTERM and crashes, i.e. the whole point of #36823 — left the shell with a
# hidden cursor, stuck in the alt screen, with bracketed paste and kitty
# keyboard mode still enabled.
_TERMINAL_INPUT_MODE_RESET_SEQ = (
    "\x1b[?1006l"  # disable SGR mouse
    "\x1b[?1003l"  # disable any-motion tracking
    "\x1b[?1002l"  # disable button-motion tracking
    "\x1b[?1000l"  # disable click tracking
    "\x1b[?1004l"  # disable focus events
    "\x1b[?2004l"  # disable bracketed paste
    "\x1b[?1049l"  # leave alt screen (if stuck there)
    "\x1b[<u"      # pop kitty keyboard mode
    "\x1b[>4m"     # reset modifyOtherKeys
    "\x1b[0m"      # reset text attributes
    "\x1b[?25h"    # ensure cursor visible
)


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


def _set_active_agent_ref(agent: Any) -> None:
    """Register the live agent for atexit memory-provider shutdown.

    Must go through a setter: ``_run_cleanup`` below reads *this* module's
    ``_active_agent_ref``, and cli.py used to do ``global _active_agent_ref``
    in its own namespace, which left this one None forever. The effect was
    that on every CLI exit ``on_session_finalize`` fired with session_id=None
    and ``shutdown_memory_provider`` was never called at all — silently
    reintroducing #15165, the very bug tests/cli/test_cli_shutdown_memory_messages.py
    guards.
    """
    global _active_agent_ref
    _active_agent_ref = agent


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
    """Best-effort: put the terminal back the way the TUI found it (#36823).

    Called from ``_run_cleanup`` (atexit-registered plus the normal / EOF /
    interrupt exit paths), so it covers normal quit, Ctrl+C and SIGTERM/SIGHUP.
    ``kill -9`` is uncatchable and the kanban worker's ``os._exit(0)`` bypasses
    atexit; neither runs this, but both are non-TTY / non-TUI so there is
    nothing to reset.

    Gated on ``_tui_input_modes_active`` so one-shot non-TUI CLI runs (which
    share ``_run_cleanup`` via atexit) never emit these codes.

    Writes to the controlling terminal directly: by exit prompt_toolkit's own
    output is torn down, so ``sys.stdout`` is the real fd. Falls back to
    ``/dev/tty`` when stdout is redirected away from the terminal — the TUI may
    have been driving the tty while stdout went to a pipe, and resetting
    nowhere is what leaves the next shell with a hidden cursor.

    58464400e collapsed this to a bare five-code write on stdout, which dropped
    the flag clear, the /dev/tty fallback, and the guard around ``isatty()``
    (an OSError from a closed stdout escaped straight out of atexit).
    """
    global _tui_input_modes_active
    if not _tui_input_modes_active:
        return
    # About to disable the modes — clear the flag first so a re-armed
    # _run_cleanup (or a long-lived process that reuses it) doesn't re-emit
    # them, even if the writes below fail.
    _tui_input_modes_active = False
    # Prefer stdout when it's the terminal; otherwise reset on /dev/tty.
    try:
        stream = sys.stdout
        if stream is not None and stream.isatty():
            stream.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
            stream.flush()
            return
    except Exception:
        pass
    try:
        with open("/dev/tty", "w", encoding="ascii") as tty:
            tty.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
            tty.flush()
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
