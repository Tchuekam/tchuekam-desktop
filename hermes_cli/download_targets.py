"""Single source of truth for the installer download targets.

Two places need to agree on which download URLs exist: the endpoint that serves
them (``hermes_cli.web_server``) and the auth allowlist that lets the public
reach them (``hermes_cli.dashboard_auth.public_paths``).  The allowlist is
matched exactly, on purpose, so a target the endpoint understands but the
allowlist has never heard of answers 401 instead of handing over an installer.

That drift is invisible until a customer clicks a link that used to work, so
both sides derive from the tables here rather than keeping their own copies.
"""

from __future__ import annotations

# The file names are fixed by the electron-builder config in
# apps/desktop/package.json, so a release built from it carries assets under
# exactly these names.
DOWNLOAD_ASSETS: dict[str, dict[str, str]] = {
    "windows": {"filename": "TchueKAM-Setup.exe", "media_type": "application/x-msdownload"},
    "mac-arm64": {"filename": "TchueKAM-Mac-arm64.dmg", "media_type": "application/x-apple-diskimage"},
    "mac-x64": {"filename": "TchueKAM-Mac-x64.dmg", "media_type": "application/x-apple-diskimage"},
    "linux": {"filename": "TchueKAM-Linux.AppImage", "media_type": "application/x-executable"},
    "android": {"filename": "TchueKAM-Mobile.apk", "media_type": "application/vnd.android.package-archive"},
}

# Every spelling the website, the docs and older links use, mapped to one
# asset.  Old spellings stay here forever: a link someone bookmarked or printed
# in a release note has to keep working.
DOWNLOAD_ALIASES: dict[str, str] = {
    # Chooses the right installer from the request's User-Agent.
    "auto": "auto",
    "detect": "auto",
    # Windows
    "windows": "windows", "windows-64bit": "windows", "win": "windows",
    "win32": "windows", "win64": "windows", "exe": "windows", "setup": "windows",
    "latest": "windows",
    # macOS
    "mac-arm64": "mac-arm64", "mac-arm": "mac-arm64", "mac-m1": "mac-arm64",
    "mac-silicon": "mac-arm64", "macos-arm64": "mac-arm64", "darwin-arm64": "mac-arm64",
    "mac-x64": "mac-x64", "mac-intel": "mac-x64", "mac": "mac-x64",
    "macos": "mac-x64", "darwin": "mac-x64", "dmg": "mac-x64",
    # Linux
    "linux": "linux", "appimage": "linux",
    # Android
    "android": "android", "apk": "android", "mobile": "android", "android-apk": "android",
}

# The routes the endpoint is mounted on.
DOWNLOAD_ROUTE_PREFIXES: tuple[str, ...] = ("/api/download", "/downloads")


def public_download_paths() -> frozenset[str]:
    """Every download URL that must be reachable without signing in.

    Downloading an installer is what a visitor does *before* they have an
    account, so these are public by definition.
    """
    return frozenset(
        f"{prefix}/{alias}"
        for prefix in DOWNLOAD_ROUTE_PREFIXES
        for alias in DOWNLOAD_ALIASES
    )
