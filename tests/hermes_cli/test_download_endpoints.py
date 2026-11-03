"""Tests for the installer download endpoints in hermes_cli.web_server.

An endpoint serves an installer from disk when this server hosts one, and
otherwise sends the visitor to the matching asset of the newest GitHub release.
"""

import pytest
from fastapi.testclient import TestClient

from hermes_cli import web_server

GITHUB_DOWNLOAD_BASE = "https://github.com/Tchuekam/tchuekam-desktop/releases/latest/download"

INSTALLERS = {
    "windows": "TchueKAM-Setup.exe",
    "mac-arm64": "TchueKAM-Mac-arm64.dmg",
    "mac-x64": "TchueKAM-Mac-x64.dmg",
    "linux": "TchueKAM-Linux.AppImage",
}


@pytest.fixture
def client():
    # The redirect itself is under test; following it would call github.com.
    return TestClient(web_server.app, follow_redirects=False)


@pytest.fixture
def downloads_dir(tmp_path, monkeypatch):
    """Point every place the endpoint looks for an installer at empty temp dirs."""
    project_root = tmp_path / "project"
    web_dist = tmp_path / "web_dist"
    project_root.mkdir()
    web_dist.mkdir()
    monkeypatch.setattr(web_server, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(web_server, "WEB_DIST", web_dist)
    directory = web_dist / "downloads"
    directory.mkdir()
    return directory


@pytest.mark.parametrize("target,filename", INSTALLERS.items())
def test_redirects_to_the_public_release_when_no_installer_is_hosted(client, downloads_dir, target, filename):
    res = client.get(f"/api/download/{target}")
    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/{filename}"


def test_alias_route_redirects_the_same_way(client, downloads_dir):
    res = client.get("/downloads/windows")
    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"


def test_latest_alias_resolves_to_the_windows_installer(client, downloads_dir):
    res = client.get("/api/download/latest")
    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"


def test_serves_a_hosted_installer_as_an_attachment(client, downloads_dir):
    installer = downloads_dir / "TchueKAM-Setup.exe"
    installer.write_bytes(b"MZ" + b"\0" * web_server._MIN_INSTALLER_BYTES)

    res = client.get("/api/download/windows")

    assert res.status_code == 200
    assert res.headers["content-disposition"] == 'attachment; filename="TchueKAM-Setup.exe"'
    assert res.content == installer.read_bytes()


def test_a_placeholder_file_is_never_served_as_the_installer(client, downloads_dir):
    # tchuekam.com once served 66-byte text files named like installers, so
    # every download saved something that could not be opened.
    placeholder = downloads_dir / "TchueKAM-Setup.exe"
    placeholder.write_text("# TchueKAM Agent Desktop Windows Installer (x64)\n# Version: 1.0.0\n")

    res = client.get("/api/download/windows")

    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"
