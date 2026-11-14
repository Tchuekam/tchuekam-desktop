"""Tests for the installer download endpoints in hermes_cli.web_server.

An endpoint serves an installer from disk when this server hosts one, and
otherwise sends the visitor to the matching asset of the newest GitHub release.
"""

import json

import pytest
from fastapi.testclient import TestClient

from hermes_cli import download_targets, web_server

GITHUB_DOWNLOAD_BASE = "https://github.com/Tchuekam/tchuekam-desktop/releases/latest/download"

INSTALLERS = {
    "windows": "TchueKAM-Setup.exe",
    "mac-arm64": "TchueKAM-Mac-arm64.dmg",
    "mac-x64": "TchueKAM-Mac-x64.dmg",
    "linux": "TchueKAM-Linux.AppImage",
    "android": "TchueKAM-Mobile.apk",
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


def test_android_aliases_redirect_to_mobile_apk(client, downloads_dir):
    for alias in ("/api/download/apk", "/api/download/mobile", "/downloads/android"):
        res = client.get(alias)
        assert res.status_code == 302
        assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Mobile.apk"


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


# ---------------------------------------------------------------------------
# Picking the right installer for whoever is asking.
#
# The website has one Download button. If it hands a Mac user an .exe, the
# download is useless even though every byte of it is genuine.
# ---------------------------------------------------------------------------

WINDOWS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
MAC_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
LINUX_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36"


@pytest.fixture(autouse=True)
def _clear_release_cache():
    """Release info is cached in a module global; isolate it per test."""
    web_server._release_info_cache.update({"expires_at": 0.0, "data": None})
    yield
    web_server._release_info_cache.update({"expires_at": 0.0, "data": None})


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        (WINDOWS_UA, "TchueKAM-Setup.exe"),
        (MAC_UA, "TchueKAM-Mac-arm64.dmg"),
        (LINUX_UA, "TchueKAM-Linux.AppImage"),
        # An Android user agent also contains "Linux"; checking it first is the
        # difference between an .apk and an AppImage that will not install.
        (ANDROID_UA, "TchueKAM-Mobile.apk"),
    ],
)
def test_auto_serves_the_installer_for_the_visitors_platform(client, downloads_dir, user_agent, expected):
    res = client.get("/api/download/auto", headers={"User-Agent": user_agent})

    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/{expected}"


def test_auto_falls_back_to_windows_for_an_unknown_client(client, downloads_dir):
    res = client.get("/api/download/auto", headers={"User-Agent": "curl/8.5.0"})

    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"


def test_head_is_answered_so_clients_can_check_before_downloading(client, downloads_dir):
    res = client.head("/api/download/windows")

    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"


def test_every_alias_the_endpoint_accepts_is_publicly_reachable(client, downloads_dir):
    """A supported download link must never answer 401.

    The auth allowlist is matched exactly, so an alias the endpoint understands
    but the allowlist has not heard of would silently stop working -- the kind
    of break nobody notices until a customer reports a dead link. Both sides
    derive from hermes_cli.download_targets; this is the check that they did.
    """
    for alias in download_targets.DOWNLOAD_ALIASES:
        res = client.get(f"/api/download/{alias}", headers={"User-Agent": WINDOWS_UA})
        assert res.status_code == 302, f"/api/download/{alias} answered {res.status_code}"
        assert res.headers["location"].startswith(GITHUB_DOWNLOAD_BASE)


def test_an_unrecognised_target_is_not_exposed(client, downloads_dir):
    # The allowlist is deliberately exact-match, so a path nobody declared
    # stays gated rather than becoming a public endpoint by accident.
    res = client.get("/api/download/plan9")

    assert res.status_code == 401


def test_a_drifted_target_still_resolves_to_a_working_installer(downloads_dir):
    # If a link does slip through, the visitor gets the product, not a crash.
    assert web_server._resolve_download_target("plan9")["filename"] == "TchueKAM-Setup.exe"


# ---------------------------------------------------------------------------
# Size alone is not enough.
# ---------------------------------------------------------------------------

def test_a_large_html_page_named_like_an_installer_is_never_served(client, downloads_dir):
    # The original failure was small, but nothing stops an error page from
    # being large. Only the leading bytes prove it is an executable.
    impostor = downloads_dir / "TchueKAM-Setup.exe"
    impostor.write_bytes(b"<!DOCTYPE html><html><body>Not found</body></html>" + b" " * 2_000_000)

    res = client.get("/api/download/windows")

    assert res.status_code == 302, "an HTML page must never be served as the installer"
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Setup.exe"


def test_a_disk_image_without_its_trailer_is_never_served(client, downloads_dir):
    impostor = downloads_dir / "TchueKAM-Mac-arm64.dmg"
    impostor.write_bytes(b"\0" * (web_server._MIN_INSTALLER_BYTES + 1024))

    res = client.get("/api/download/mac-arm64")

    assert res.status_code == 302
    assert res.headers["location"] == f"{GITHUB_DOWNLOAD_BASE}/TchueKAM-Mac-arm64.dmg"


# ---------------------------------------------------------------------------
# Telling the website what actually exists.
# ---------------------------------------------------------------------------

def test_download_info_reports_what_the_manifest_recorded(client, downloads_dir, monkeypatch):
    manifest = {
        "version": "1.0.0",
        "artifacts": [
            {
                "filename": "TchueKAM-Setup.exe",
                "platform": "windows",
                "size": 119804694,
                "sha256": "6b4a47740849eb54015d4c54cabd7e5a3a732e77ce0c6af4cf2a0d41a540f796",
                "url": "https://example.invalid/TchueKAM-Setup.exe",
            }
        ],
        "platforms": ["windows"],
    }
    (downloads_dir / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")

    res = client.get("/api/download-info", headers={"User-Agent": WINDOWS_UA})

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["version"] == "1.0.0"
    assert body["detected_platform"] == "windows"
    assert set(body["platforms"]) == {"windows"}
    assert body["platforms"]["windows"]["size"] == 119804694


def test_download_info_hides_a_platform_with_no_published_asset(client, downloads_dir, monkeypatch):
    # macOS, Linux and Android had no asset in the v1.0.0 release, yet the site
    # offered all of them. Only what exists may be advertised.
    monkeypatch.setattr(
        web_server,
        "_fetch_published_release",
        lambda: {
            "tag_name": "v1.0.0",
            "html_url": "https://example.invalid/releases/v1.0.0",
            "assets": [
                {
                    "name": "TchueKAM-Setup.exe",
                    "size": 119804694,
                    "digest": "sha256:6b4a4774",
                    "browser_download_url": "https://example.invalid/TchueKAM-Setup.exe",
                }
            ],
        },
    )

    res = client.get("/api/download-info", headers={"User-Agent": MAC_UA})

    assert res.status_code == 200
    body = res.json()
    assert set(body["platforms"]) == {"windows"}
    assert "mac-arm64" not in body["platforms"]
    assert body["detected_platform"] == "mac-arm64"


def test_download_info_rejects_a_published_asset_that_is_too_small(client, downloads_dir, monkeypatch):
    monkeypatch.setattr(
        web_server,
        "_fetch_published_release",
        lambda: {
            "tag_name": "v1.0.0",
            "assets": [
                {
                    "name": "TchueKAM-Setup.exe",
                    "size": 66,
                    "browser_download_url": "https://example.invalid/TchueKAM-Setup.exe",
                }
            ],
        },
    )

    res = client.get("/api/download-info")

    body = res.json()
    assert body["available"] is False
    assert body["platforms"] == {}


def test_download_info_claims_nothing_when_the_release_cannot_be_read(client, downloads_dir, monkeypatch):
    monkeypatch.setattr(web_server, "_fetch_published_release", lambda: None)

    res = client.get("/api/download-info")

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["platforms"] == {}
    assert body["release_url"]
