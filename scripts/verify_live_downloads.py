#!/usr/bin/env python3
"""Check what the public website actually hands a customer.

A green build proves nothing about distribution.  The Windows failure users hit
came from a release whose installer built correctly, uploaded correctly, and
was then served by the website as a 66-byte text file.  Every developer-side
check passed; only the customer's download was broken.

So this script is deliberately a *customer*, not a developer.  It asks the
public URL for the download exactly as a browser would, follows the redirects,
and looks at the bytes that come back:

    python3 scripts/verify_live_downloads.py
    python3 scripts/verify_live_downloads.py --base-url https://staging.example.com
    python3 scripts/verify_live_downloads.py --full        # also check SHA-256

By default it reads only the first and last few kilobytes of each artifact via
HTTP range requests, so verifying a 114 MB installer costs a few KB and the
check is cheap enough to run on every deploy.  Exit status is 0 only when every
advertised download is a real, complete installer.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_release_artifacts import (  # noqa: E402
    _DEFAULT_MIN_BYTES,
    _MIN_BYTES_BY_KIND,
    classify,
)

DEFAULT_BASE_URL = "https://tchuekam.com"

# The paths the website advertises as downloads.  A customer reaches these by
# clicking Download, so each one has to answer with an installer.
DEFAULT_PATHS = [
    "/TchueKAM-Setup.exe",
    "/TchueKAM-Mac-arm64.dmg",
    "/TchueKAM-Mac-x64.dmg",
    "/TchueKAM-Linux.AppImage",
    "/api/download/windows",
    "/api/download/mac-arm64",
    "/api/download/mac-x64",
    "/api/download/linux",
]

# A browser sends one of these; some CDNs serve different bytes to curl.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

_HTML_TYPES = ("text/html", "application/xhtml")


@dataclass
class LiveCheck:
    path: str
    url: str = ""
    status: int = 0
    content_type: str = ""
    size: int | None = None
    sha256: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _request(url: str, *, method: str = "GET", headers: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "*/*")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - explicit https base


def _expected_filename(path: str) -> str:
    """What the browser will name the saved file.

    An /api/download/<target> link carries a download attribute on the website,
    so the browser saves whatever comes back under an installer's name -- which
    is precisely how an HTML error page became 'TchueKAM-Setup.exe'.
    """
    tail = path.rstrip("/").rsplit("/", 1)[-1]
    if "." in tail:
        return tail
    return {
        "windows": "TchueKAM-Setup.exe",
        "mac-arm64": "TchueKAM-Mac-arm64.dmg",
        "mac-x64": "TchueKAM-Mac-x64.dmg",
        "linux": "TchueKAM-Linux.AppImage",
        "android": "TchueKAM-Mobile.apk",
        "latest": "TchueKAM-Setup.exe",
    }.get(tail, tail)


def check_url(base_url: str, path: str, *, full: bool, timeout: int) -> LiveCheck:
    url = base_url.rstrip("/") + path
    check = LiveCheck(path=path, url=url)
    filename = _expected_filename(path)
    kind = classify(Path(filename))

    try:
        with _request(url, timeout=timeout) as resp:
            check.status = resp.status
            check.url = resp.url
            check.content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            length = resp.headers.get("Content-Length")
            check.size = int(length) if length and length.isdigit() else None

            if full or check.size is None:
                digest = hashlib.sha256()
                total = 0
                head = b""
                tail = b""
                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    for chunk in iter(lambda: resp.read(1024 * 1024), b""):
                        digest.update(chunk)
                        total += len(chunk)
                        if not head:
                            head = chunk[:4096]
                        tmp.write(chunk)
                    check.size = total
                    check.sha256 = digest.hexdigest()
                    if total >= 512:
                        tmp.seek(max(0, total - 512))
                        tail = tmp.read(512)
            else:
                head = resp.read(4096)
                tail = b""
    except urllib.error.HTTPError as exc:
        check.status = exc.code
        check.content_type = (exc.headers.get("Content-Type") or "").split(";")[0].strip()
        check.problems.append(
            f"answered HTTP {exc.code}. The browser saves that response as "
            f"'{filename}', so the customer gets an error page named like an installer."
        )
        return check
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        check.problems.append(f"could not be reached: {exc}")
        return check

    if check.status != 200:
        check.problems.append(f"answered HTTP {check.status} instead of 200")

    if any(check.content_type.startswith(t) for t in _HTML_TYPES):
        check.problems.append(
            f"served '{check.content_type}'. An HTML page saved as '{filename}' is "
            "exactly the 'This app can't run on your PC' failure."
        )

    if kind is None:
        check.problems.append(f"resolves to '{filename}', which is not a known installer type")
        return check

    floor = _MIN_BYTES_BY_KIND.get(kind.name, _DEFAULT_MIN_BYTES)
    if check.size is not None and check.size < floor:
        check.problems.append(
            f"is {check.size:,} bytes. A real {kind.description or kind.name} is at least "
            f"{floor:,} bytes -- this is a placeholder or a truncated upload."
        )

    # The tail only matters for formats whose signature lives at the end.
    if kind.name == "dmg" and not full and check.size and check.size >= 512:
        try:
            with _request(
                check.url, headers={"Range": "bytes=-512"}, timeout=timeout
            ) as tail_resp:
                tail = tail_resp.read(512)
        except (urllib.error.URLError, TimeoutError, OSError):
            tail = b""
        if tail and tail[:4] != b"koly":
            check.problems.append("has no 'koly' UDIF trailer -- it will not mount on macOS")
    elif kind.name == "dmg" and full:
        if tail[:4] != b"koly":
            check.problems.append("has no 'koly' UDIF trailer -- it will not mount on macOS")

    # Head-of-file signature checks that do not need the whole download.
    if kind.name in ("exe", "msi") and head[:2] != b"MZ" and head[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        check.problems.append(
            f"does not start with a Windows executable header (starts with {head[:8]!r}). "
            "Windows will refuse to run it."
        )
    elif kind.name == "appimage" and head[:4] != b"\x7fELF":
        check.problems.append(f"does not start with the ELF magic (starts with {head[:8]!r})")
    elif kind.name in ("apk", "zip") and head[:2] != b"PK":
        check.problems.append(f"is not a zip archive (starts with {head[:8]!r})")

    return check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the downloads the public website actually serves.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"site to test (default {DEFAULT_BASE_URL})")
    parser.add_argument("--path", action="append", dest="paths", help="download path to check (repeatable)")
    parser.add_argument("--full", action="store_true", help="download fully and report SHA-256")
    parser.add_argument("--timeout", type=int, default=60, help="per-request timeout in seconds")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="treat a 404 as 'platform not released yet' rather than a failure",
    )
    args = parser.parse_args(argv)

    paths = args.paths or DEFAULT_PATHS
    print(f"Testing the real download experience at {args.base_url}\n")

    failures = 0
    for path in paths:
        check = check_url(args.base_url, path, full=args.full, timeout=args.timeout)

        if args.allow_missing and check.status == 404:
            print(f"  SKIP  {path}  (HTTP 404 -- not published for this platform)")
            continue

        size = f"{check.size:,} bytes" if check.size is not None else "unknown size"
        if check.ok:
            print(f"  PASS  {path}  (HTTP {check.status}, {size}, {check.content_type or 'no content-type'})")
            if check.sha256:
                print(f"        sha256 {check.sha256}")
        else:
            failures += 1
            print(f"  FAIL  {path}  (HTTP {check.status}, {size}, {check.content_type or 'no content-type'})")
            for problem in check.problems:
                print(f"        -> {problem}")

    print()
    if failures:
        print(
            f"FAILED: {failures} of the downloads this site advertises are not usable "
            "installers. Customers clicking Download get a broken file."
        )
        return 1
    print("OK: every advertised download is a real, complete installer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
