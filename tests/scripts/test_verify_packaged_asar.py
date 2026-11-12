"""Tests for the packaged-app check in scripts/verify_packaged_asar.py.

The v1.0.0 installer was a genuine 114 MB NSIS installer that installed
perfectly and then died before opening a window:

    A JavaScript error occurred in the main process
    Error: Cannot find module 'electron-updater'

npm workspaces had hoisted electron-updater to the repo root, so
electron-builder's ``node_modules/electron-updater/**`` glob -- resolved
relative to apps/desktop/ -- matched nothing. A glob matching nothing is not
an error, so every check upstream stayed green.

These tests pin both halves: a package missing a module it requires must fail,
and a package that ships one correctly must pass. The second half matters as
much as the first, because a check that reports problems that are not there is
a check people switch off.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

_MODULE_NAME = "_verify_packaged_asar_under_test"


def _load():
    spec = importlib.util.spec_from_file_location(
        _MODULE_NAME,
        Path(__file__).resolve().parents[2] / "scripts" / "verify_packaged_asar.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    return module


verifier = _load()


def write_asar(path: Path, files: dict[str, str]) -> None:
    """Build a real .asar containing ``files`` (relative path -> text)."""
    blob = bytearray()
    root: dict = {"files": {}}

    for rel, text in files.items():
        data = text.encode("utf-8")
        node = root
        parts = rel.split("/")
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        node["files"][parts[-1]] = {"offset": str(len(blob)), "size": len(data)}
        blob.extend(data)

    header = json.dumps(root).encode("utf-8")
    json_len = len(header)
    padding = (4 - json_len % 4) % 4
    # pickle(uint32 = 4) then pickle(header): size, json size, json length.
    path.write_bytes(
        struct.pack("<IIII", 4, json_len + padding + 8, json_len + padding + 4, json_len)
        + header
        + b"\0" * padding
        + bytes(blob)
    )


def package_json(main: str = "electron/main.cjs") -> str:
    return json.dumps({"name": "tchuekam", "main": main})


# --------------------------------------------------------------------------
# The crash that shipped
# --------------------------------------------------------------------------

def test_the_missing_module_that_shipped_is_caught(tmp_path):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('./auto-updater.cjs')\n",
            "electron/auto-updater.cjs": "const { autoUpdater } = require('electron-updater')\n",
        },
    )

    exit_code = verifier.main([str(asar)])

    assert exit_code == 1


def test_the_failure_names_the_module_and_the_file_that_needs_it(tmp_path, capsys):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "const u = require('electron-updater')\n",
        },
    )

    verifier.main([str(asar)])

    out = capsys.readouterr().out
    assert "electron-updater" in out
    assert "electron/main.cjs" in out


def test_a_package_with_no_modules_at_all_is_caught(tmp_path, capsys):
    # The shipped asar had zero node_modules entries.
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('electron-updater')\n",
        },
    )

    verifier.main([str(asar)])

    assert "*** none ***" in capsys.readouterr().out


# --------------------------------------------------------------------------
# A correctly packaged app must pass
# --------------------------------------------------------------------------

def test_a_bundled_module_satisfies_the_require(tmp_path):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('electron-updater')\n",
            "node_modules/electron-updater/package.json": '{"name":"electron-updater"}',
            "node_modules/electron-updater/out/main.js": "module.exports = {}\n",
        },
    )

    assert verifier.main([str(asar), "--expect", "electron-updater"]) == 0


def test_node_builtins_and_electron_need_nothing_bundled(tmp_path):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": (
                "const path = require('path')\n"
                "const fs = require('node:fs')\n"
                "const { app } = require('electron')\n"
            ),
        },
    )

    assert verifier.main([str(asar)]) == 0


def test_a_module_shipped_beside_the_asar_is_accepted(tmp_path):
    """node-pty is staged into resources/native-deps and loaded from there.

    Reporting it as missing would be wrong, and a check that cries wolf is one
    people learn to skip.
    """
    resources = tmp_path / "resources"
    resources.mkdir()
    asar = resources / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "let pty; try { pty = require('node-pty') } catch {}\n",
        },
    )
    staged = resources / "native-deps" / "node-pty"
    staged.mkdir(parents=True)
    (staged / "package.json").write_text('{"name":"node-pty"}')

    assert verifier.main([str(asar)]) == 0


def test_a_module_beside_the_asar_is_reported_as_such(tmp_path, capsys):
    resources = tmp_path / "resources"
    resources.mkdir()
    asar = resources / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('node-pty')\n",
        },
    )
    staged = resources / "native-deps" / "node-pty"
    staged.mkdir(parents=True)
    (staged / "package.json").write_text('{"name":"node-pty"}')

    verifier.main([str(asar)])

    assert "resources/native-deps" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Scope of the scan
# --------------------------------------------------------------------------

def test_relative_requires_that_point_nowhere_are_caught(tmp_path, capsys):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('./hardening.cjs')\n",
        },
    )

    exit_code = verifier.main([str(asar)])

    assert exit_code == 1
    assert "./hardening.cjs" in capsys.readouterr().out


def test_a_relative_require_that_resolves_passes(tmp_path):
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "require('./hardening.cjs')\n",
            "electron/hardening.cjs": "module.exports = {}\n",
        },
    )

    assert verifier.main([str(asar)]) == 0


def test_bundled_test_files_are_not_scanned(tmp_path):
    # Unit tests packaged by accident require devDependencies that are
    # legitimately absent from a production package.
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "const path = require('path')\n",
            "electron/hardening.test.cjs": "require('some-dev-only-harness')\n",
        },
    )

    assert verifier.main([str(asar)]) == 0


def test_expect_catches_a_module_no_source_names_literally(tmp_path, capsys):
    # A module reached only through a dynamic require still has to be shipped.
    asar = tmp_path / "app.asar"
    write_asar(
        asar,
        {
            "package.json": package_json(),
            "electron/main.cjs": "const name = 'electron-' + 'updater'; require(name)\n",
        },
    )

    exit_code = verifier.main([str(asar), "--expect", "electron-updater"])

    assert exit_code == 1
    assert "electron-updater" in capsys.readouterr().out


def test_a_missing_target_is_an_error_not_a_pass(tmp_path):
    assert verifier.main([str(tmp_path / "nope.asar")]) == 2


def test_a_package_with_no_main_process_sources_is_an_error(tmp_path):
    asar = tmp_path / "app.asar"
    write_asar(asar, {"package.json": package_json(), "dist/index.html": "<html></html>"})

    assert verifier.main([str(asar)]) == 2
