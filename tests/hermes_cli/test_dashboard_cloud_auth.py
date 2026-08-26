"""The dashboard must not disable authentication just because $PORT is set.

``PORT`` and ``RAILWAY_ENVIRONMENT`` describe how to *bind* (public host,
platform-assigned port). They previously also forced ``--insecure``, which
handed every PaaS deployment an unauthenticated dashboard on 0.0.0.0 and
bypassed the fail-closed OAuth gate in ``web_server.start_server``.
"""

import argparse
from unittest import mock

import pytest


def _args(**overrides):
    base = dict(
        host="127.0.0.1", port=None, no_open=True, tui=False, insecure=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _run_cmd_dashboard(args, env):
    """Invoke cmd_dashboard with start_server stubbed, returning its kwargs."""
    from hermes_cli import main as cli_main

    captured = {}

    def fake_start_server(**kwargs):
        captured.update(kwargs)

    with mock.patch.dict("os.environ", env, clear=False), \
         mock.patch("hermes_cli.web_server.start_server", fake_start_server), \
         mock.patch("hermes_cli.plugins.discover_plugins", lambda: None):
        cli_main.cmd_dashboard(args)
    return captured


@pytest.mark.parametrize(
    "env",
    [
        {"PORT": "8080"},
        {"RAILWAY_ENVIRONMENT": "production"},
        {"PORT": "8080", "RAILWAY_ENVIRONMENT": "production"},
    ],
)
def test_cloud_env_does_not_disable_authentication(env):
    captured = _run_cmd_dashboard(_args(), env)
    assert captured, "start_server was never called"
    assert captured["allow_public"] is False, (
        f"Auth disabled purely because of env {env}: allow_public="
        f"{captured['allow_public']}"
    )


def test_explicit_insecure_flag_is_still_honoured():
    captured = _run_cmd_dashboard(_args(insecure=True), {"PORT": "8080"})
    assert captured["allow_public"] is True


def test_cloud_env_still_controls_bind_host_and_port():
    """Le comportement de binding doit rester inchange."""
    captured = _run_cmd_dashboard(_args(), {"PORT": "8080"})
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8080
    assert captured["open_browser"] is False
