"""Regression tests for GitHub #36823 — the TUI must reset terminal input
modes on exit so focus-reporting / mouse-tracking escape sequences don't leak
into the next shell session sharing the tab.

prompt_toolkit restores these on a clean teardown, but Ctrl+C, SIGTERM/SIGHUP
and crashes can bypass its unwind. ``_run_cleanup`` (the once-only cleanup that
runs on every catchable exit path, including ``atexit``) now emits the disable
sequence as its first step via ``_reset_terminal_input_modes_on_exit`` — gated
on ``_tui_input_modes_active`` so non-TUI one-shot CLI runs (which share
``_run_cleanup`` via ``atexit``) don't emit codes for modes they never set.
"""

import unittest
from unittest.mock import mock_open, patch


def _import_helpers():
    """Return the module that owns the reset flag, sequence and cleanup.

    These used to live in cli.py; 58464400e moved them to
    hermes_cli.cli_helpers. Patching them on ``cli`` is a no-op — the
    functions read cli_helpers' own module globals — so the tests have to
    target the owning module. ``cli`` is still imported first so the module
    graph matches a real CLI startup.
    """
    import hermes_cli.config as config_mod

    if not hasattr(config_mod, "save_env_value_secure"):
        config_mod.save_env_value_secure = lambda key, value: {
            "success": True,
            "stored_as": key,
            "validated": False,
        }

    import cli  # noqa: F401 — import side effects mirror real startup
    import hermes_cli.cli_helpers as helpers_mod

    return helpers_mod


class _FakeStream:
    def __init__(self, isatty: bool = True):
        self._isatty = isatty
        self.written: list[str] = []
        self.flushed = 0

    def isatty(self) -> bool:
        return self._isatty

    def write(self, s: str) -> int:
        self.written.append(s)
        return len(s)

    def flush(self) -> None:
        self.flushed += 1


class TestResetTerminalInputModes(unittest.TestCase):
    def test_emits_reset_seq_on_tty_when_tui_ran(self):
        helpers_mod = _import_helpers()
        fake = _FakeStream(isatty=True)
        with (
            patch.object(helpers_mod, "_tui_input_modes_active", True),
            patch.object(helpers_mod.sys, "stdout", fake),
        ):
            helpers_mod._reset_terminal_input_modes_on_exit()

        written = "".join(fake.written)
        self.assertEqual(written, helpers_mod._TERMINAL_INPUT_MODE_RESET_SEQ)
        self.assertGreaterEqual(fake.flushed, 1)
        # The focus-reporting disable is the specific leak the issue reports.
        self.assertIn("\x1b[?1004l", written)

    def test_noop_when_tui_never_ran(self):
        """Non-TUI one-shot CLI runs share _run_cleanup via atexit — they must
        not emit terminal escape codes they never needed (review finding #1)."""
        helpers_mod = _import_helpers()
        fake = _FakeStream(isatty=True)
        with (
            patch.object(helpers_mod, "_tui_input_modes_active", False),
            patch.object(helpers_mod.sys, "stdout", fake),
            # Guard: must not touch the real /dev/tty either.
            patch("builtins.open", mock_open()) as m_open,
        ):
            helpers_mod._reset_terminal_input_modes_on_exit()

        self.assertEqual(fake.written, [])
        m_open.assert_not_called()

    def test_noop_when_not_a_tty_and_no_dev_tty(self):
        """stdout redirected and /dev/tty unavailable → nothing written, no raise."""
        helpers_mod = _import_helpers()
        fake = _FakeStream(isatty=False)
        with (
            patch.object(helpers_mod, "_tui_input_modes_active", True),
            patch.object(helpers_mod.sys, "stdout", fake),
            patch("builtins.open", side_effect=OSError("no /dev/tty")),
        ):
            helpers_mod._reset_terminal_input_modes_on_exit()

        self.assertEqual(fake.written, [], "must not pollute the redirected stream")

    def test_falls_back_to_dev_tty_when_stdout_redirected(self):
        """When stdout isn't the terminal, reset via /dev/tty (issue's own
        suggestion) so a TUI that drove /dev/tty still gets cleaned up."""
        helpers_mod = _import_helpers()
        fake = _FakeStream(isatty=False)
        m_open = mock_open()
        with (
            patch.object(helpers_mod, "_tui_input_modes_active", True),
            patch.object(helpers_mod.sys, "stdout", fake),
            patch("builtins.open", m_open),
        ):
            helpers_mod._reset_terminal_input_modes_on_exit()

        self.assertEqual(fake.written, [])
        m_open.assert_called_once_with("/dev/tty", "w", encoding="ascii")
        m_open().write.assert_called_once_with(helpers_mod._TERMINAL_INPUT_MODE_RESET_SEQ)

    def test_swallows_stdout_errors(self):
        helpers_mod = _import_helpers()

        class _Boom:
            def isatty(self):
                raise OSError("stdout closed")

        with (
            patch.object(helpers_mod, "_tui_input_modes_active", True),
            patch.object(helpers_mod.sys, "stdout", _Boom()),
            patch("builtins.open", side_effect=OSError("no /dev/tty")),
        ):
            # Cleanup runs at process teardown — it must never raise.
            helpers_mod._reset_terminal_input_modes_on_exit()

    def test_mark_tui_input_modes_active_sets_flag(self):
        helpers_mod = _import_helpers()
        original = helpers_mod._tui_input_modes_active
        helpers_mod._tui_input_modes_active = False
        try:
            helpers_mod._mark_tui_input_modes_active()
            self.assertTrue(helpers_mod._tui_input_modes_active)
        finally:
            helpers_mod._tui_input_modes_active = original

    def test_flag_cleared_after_reset(self):
        """Once the modes are disabled they are no longer active — the flag must
        flip back so a re-armed cleanup doesn't re-emit the sequence."""
        helpers_mod = _import_helpers()
        fake = _FakeStream(isatty=True)
        original = helpers_mod._tui_input_modes_active
        helpers_mod._tui_input_modes_active = True
        try:
            with patch.object(helpers_mod.sys, "stdout", fake):
                helpers_mod._reset_terminal_input_modes_on_exit()
            self.assertIn("\x1b[?1004l", "".join(fake.written))
            self.assertFalse(
                helpers_mod._tui_input_modes_active, "flag must clear after reset"
            )
        finally:
            helpers_mod._tui_input_modes_active = original


class TestRunCleanupWiring(unittest.TestCase):
    """_run_cleanup must call the reset, as its first step, on every invocation
    — even if a later cleanup step raises."""

    def _run_cleanup_isolated(self, helpers_mod, **extra_patches):
        """Invoke _run_cleanup with heavy/real teardown steps stubbed out so the
        test is hermetic (review finding #5)."""
        original_done = helpers_mod._cleanup_done
        helpers_mod._cleanup_done = False
        patches = {
            "_cleanup_all_terminals": lambda: None,
            "_cleanup_all_browsers": lambda: None,
        }
        try:
            with (
                patch.object(
                    helpers_mod, "_reset_terminal_input_modes_on_exit"
                ) as mock_reset,
                patch.object(
                    helpers_mod, "_cleanup_all_terminals", patches["_cleanup_all_terminals"]
                ),
                patch.object(
                    helpers_mod, "_cleanup_all_browsers", patches["_cleanup_all_browsers"]
                ),
                patch("tools.mcp_tool.shutdown_mcp_servers", lambda *a, **k: None),
                patch(
                    "agent.auxiliary_client.shutdown_cached_clients",
                    lambda *a, **k: None,
                ),
                patch("hermes_cli.plugins.invoke_hook", lambda *a, **k: None),
            ):
                if extra_patches.get("terminals_raise"):
                    with patch.object(
                        helpers_mod,
                        "_cleanup_all_terminals",
                        side_effect=RuntimeError("boom"),
                    ):
                        helpers_mod._run_cleanup()
                else:
                    helpers_mod._run_cleanup()
                return mock_reset
        finally:
            helpers_mod._cleanup_done = original_done

    def test_run_cleanup_calls_reset(self):
        helpers_mod = _import_helpers()
        mock_reset = self._run_cleanup_isolated(helpers_mod)
        mock_reset.assert_called_once()

    def test_reset_runs_even_when_a_cleanup_step_raises(self):
        """The reset is the first step, so a failing teardown step can't skip
        it — covering the Ctrl+C / crash paths the issue is about."""
        helpers_mod = _import_helpers()
        mock_reset = self._run_cleanup_isolated(helpers_mod, terminals_raise=True)
        mock_reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
