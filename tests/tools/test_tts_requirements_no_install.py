"""``check_tts_requirements`` must not install packages.

It is the ``text_to_speech`` tool's ``check_fn``, evaluated while the agent's
tool list is built on the first turn. When it ran ``pip install edge-tts`` the
first message of a fresh install waited ~45s. The install now happens only when
speech is actually generated.
"""

from unittest.mock import patch

import pytest

from tools import tts_tool


@pytest.fixture(autouse=True)
def no_other_providers(monkeypatch):
    """Take every non-Edge provider out of play so only the Edge path decides."""
    monkeypatch.setattr(tts_tool, "_has_any_command_tts_provider", lambda: False)


def test_requirements_check_never_runs_the_installer():
    """Edge TTS missing but installable: report available, do not call pip."""
    with (
        patch.object(tts_tool, "_import_edge_tts", side_effect=AssertionError("installer ran")),
        patch("tools.lazy_deps.is_available", return_value=False),
        patch("tools.lazy_deps._allow_lazy_installs", return_value=True),
        patch("tools.lazy_deps._venv_pip_install", side_effect=AssertionError("pip ran")),
    ):
        assert tts_tool.check_tts_requirements() is True


@pytest.mark.parametrize(
    "installed, lazy_allowed, expected",
    [
        (True, False, True),  # already installed: usable even if installs are off
        (False, True, True),  # missing but installable on first use
        (False, False, False),  # missing and installs disabled: not usable
    ],
)
def test_edge_tts_usable_without_install(installed, lazy_allowed, expected):
    with (
        patch("tools.lazy_deps.is_available", return_value=installed),
        patch("tools.lazy_deps._allow_lazy_installs", return_value=lazy_allowed),
    ):
        assert tts_tool._edge_tts_usable_without_install() is expected


def test_generating_speech_still_installs_on_demand():
    """The install is deferred, not removed: using Edge TTS still goes through it."""
    with patch("tools.lazy_deps.ensure") as ensure, patch.dict("sys.modules", {"edge_tts": object()}):
        tts_tool._import_edge_tts()
    ensure.assert_called_once_with("tts.edge", prompt=False)
