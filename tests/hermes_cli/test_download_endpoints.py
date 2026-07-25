"""Tests for direct application download endpoints in hermes_cli.web_server."""

import pytest
from fastapi.testclient import TestClient
from hermes_cli.web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_download_windows_endpoint(client):
    """Test that /api/download/windows triggers direct Windows installer download."""
    res = client.get("/api/download/windows")
    assert res.status_code == 200
    assert "Content-Disposition" in res.headers
    assert 'attachment; filename="TchueKAM-Setup.exe"' in res.headers["Content-Disposition"]
    assert res.content.startswith(b"# TchueKAM") or len(res.content) > 0


def test_download_mac_arm64_endpoint(client):
    """Test that /api/download/mac-arm64 triggers direct macOS Apple Silicon DMG download."""
    res = client.get("/api/download/mac-arm64")
    assert res.status_code == 200
    assert "Content-Disposition" in res.headers
    assert 'attachment; filename="TchueKAM-Mac-arm64.dmg"' in res.headers["Content-Disposition"]


def test_download_mac_x64_endpoint(client):
    """Test that /api/download/mac-x64 triggers direct macOS Intel DMG download."""
    res = client.get("/api/download/mac-x64")
    assert res.status_code == 200
    assert "Content-Disposition" in res.headers
    assert 'attachment; filename="TchueKAM-Mac-x64.dmg"' in res.headers["Content-Disposition"]


def test_download_linux_endpoint(client):
    """Test that /api/download/linux triggers direct Linux AppImage download."""
    res = client.get("/api/download/linux")
    assert res.status_code == 200
    assert "Content-Disposition" in res.headers
    assert 'attachment; filename="TchueKAM-Linux.AppImage"' in res.headers["Content-Disposition"]


def test_download_alias_route(client):
    """Test alias route /downloads/windows."""
    res = client.get("/downloads/windows")
    assert res.status_code == 200
    assert "Content-Disposition" in res.headers
    assert 'attachment; filename="TchueKAM-Setup.exe"' in res.headers["Content-Disposition"]
