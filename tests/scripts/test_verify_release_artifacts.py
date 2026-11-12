"""Tests for the release artifact gate in scripts/verify_release_artifacts.py.

The gate exists because a release once reached customers as a 66-byte text file
named ``TchueKAM-Setup.exe``.  Every step before the download had passed: the
build succeeded, the upload succeeded, the file had the right name.  Nothing
looked at the bytes.

These tests pin the two halves of that lesson -- a genuine installer must pass,
and a file that is merely *named* like one must fail -- so the gate cannot be
loosened back into uselessness without a test going red.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_NAME = "_verify_release_artifacts_under_test"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        _MODULE_NAME,
        Path(__file__).resolve().parents[2] / "scripts" / "verify_release_artifacts.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is None for an unregistered module.
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    return module


verifier = _load_verifier()

# Small enough to keep tests fast; the real floor is 20 MB.
TINY_FLOOR = 64


def _pe_bytes(payload: bytes = b"") -> bytes:
    """A minimal but structurally valid PE image: DOS header -> PE signature."""
    header = bytearray(b"\0" * 0x40)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = (0x40).to_bytes(4, "little")
    return bytes(header) + b"PE\0\0" + payload


def _dmg_bytes(payload: bytes = b"") -> bytes:
    """A UDIF image is identified by a 512-byte trailer beginning with 'koly'."""
    trailer = b"koly" + b"\0" * 508
    return payload + trailer


def _appimage_bytes(payload: bytes = b"") -> bytes:
    return b"\x7fELF" + b"\0" * 4 + b"AI\x02" + b"\0" * 64 + payload


# --------------------------------------------------------------------------
# The failure that shipped
# --------------------------------------------------------------------------

PLACEHOLDERS = {
    "TchueKAM-Setup.exe": b"# TchueKAM Agent Desktop Windows Installer (x64)\n# Version: 1.0.0",
    "TchueKAM-Mac-arm64.dmg": b"# TchueKAM Agent Desktop macOS Apple Silicon DMG\n# Version: 1.0.0",
    "TchueKAM-Linux.AppImage": b"# TchueKAM Agent Desktop Linux AppImage\n# Version: 1.0.0",
}


@pytest.mark.parametrize("filename,content", PLACEHOLDERS.items())
def test_the_placeholder_that_shipped_is_rejected(tmp_path, filename, content):
    artifact = tmp_path / filename
    artifact.write_bytes(content)

    result = verifier.verify_file(artifact)

    assert not result.ok
    assert result.problems


def test_an_html_error_page_saved_as_an_installer_is_rejected(tmp_path):
    # Linking a relative /api path with a download attribute saves the 404 page
    # under the installer's name. Padding it past the size floor must not help.
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(b"<!DOCTYPE html><html><body>404</body></html>" + b" " * 4096)

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert not result.ok
    assert any("MZ" in p or "DOS header" in p for p in result.problems)


def test_an_empty_file_is_rejected(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(b"")

    result = verifier.verify_file(artifact)

    assert not result.ok
    assert "is empty" in result.problems[0]


def test_a_truncated_upload_is_rejected(tmp_path):
    # Right header, far too few bytes: what a cut-off upload looks like.
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_bytes())

    result = verifier.verify_file(artifact)

    assert not result.ok
    assert any("at least" in p for p in result.problems)


def test_an_mz_header_without_a_pe_signature_is_rejected(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(b"MZ" + b"\0" * 4096)

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert not result.ok
    assert any("PE signature" in p for p in result.problems)


# --------------------------------------------------------------------------
# Genuine artifacts must pass, or the gate is just an outage
# --------------------------------------------------------------------------

def test_a_real_windows_installer_passes(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_bytes(b"\0" * 4096))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert result.ok, result.problems
    assert result.platform == verifier.PLATFORM_WINDOWS
    assert len(result.sha256) == 64


def test_a_real_disk_image_passes_and_maps_to_its_architecture(tmp_path):
    arm = tmp_path / "TchueKAM-Mac-arm64.dmg"
    arm.write_bytes(_dmg_bytes(b"\0" * 1024))
    intel = tmp_path / "TchueKAM-Mac-x64.dmg"
    intel.write_bytes(_dmg_bytes(b"\0" * 1024))

    arm_result = verifier.verify_file(arm, min_bytes=TINY_FLOOR)
    intel_result = verifier.verify_file(intel, min_bytes=TINY_FLOOR)

    assert arm_result.ok, arm_result.problems
    assert intel_result.ok, intel_result.problems
    assert arm_result.platform == verifier.PLATFORM_MAC_ARM64
    assert intel_result.platform == verifier.PLATFORM_MAC_X64


def test_a_disk_image_without_its_trailer_is_rejected(tmp_path):
    artifact = tmp_path / "TchueKAM-Mac-arm64.dmg"
    artifact.write_bytes(b"\0" * 2048)

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert not result.ok
    assert any("koly" in p for p in result.problems)


def test_a_real_appimage_passes(tmp_path):
    artifact = tmp_path / "TchueKAM-Linux.AppImage"
    artifact.write_bytes(_appimage_bytes(b"\0" * 1024))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert result.ok, result.problems
    assert result.platform == verifier.PLATFORM_LINUX


def test_an_elf_without_the_appimage_marker_is_rejected(tmp_path):
    # A plain ELF binary is not an AppImage and will not run by double-click.
    artifact = tmp_path / "TchueKAM-Linux.AppImage"
    artifact.write_bytes(b"\x7fELF" + b"\0" * 2048)

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert not result.ok
    assert any("AppImage type marker" in p for p in result.problems)


# --------------------------------------------------------------------------
# The update feed, whose absence silently freezes every installed copy
# --------------------------------------------------------------------------

def test_an_update_feed_missing_its_keys_is_rejected(tmp_path):
    feed = tmp_path / "latest.yml"
    feed.write_text("version: 1.0.0\n")

    result = verifier.verify_file(feed)

    assert not result.ok
    assert any("sha512" in p for p in result.problems)


def test_a_complete_update_feed_passes(tmp_path):
    feed = tmp_path / "latest.yml"
    # Shaped like a real electron-builder feed, not a stub.
    feed.write_text(
        "version: 1.0.0\n"
        "files:\n"
        "  - url: TchueKAM-Setup.exe\n"
        "    sha512: QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eg==\n"
        "    size: 119804694\n"
        "path: TchueKAM-Setup.exe\n"
        "sha512: QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eg==\n"
        "releaseDate: '2026-07-25T08:03:23.000Z'\n"
    )

    result = verifier.verify_file(feed)

    assert result.ok, result.problems


# --------------------------------------------------------------------------
# End-to-end: the CLI that gates the release job
# --------------------------------------------------------------------------

def test_main_fails_and_writes_no_manifest_when_an_artifact_is_fake(tmp_path, capsys):
    (tmp_path / "TchueKAM-Setup.exe").write_bytes(b"# placeholder\n")
    manifest = tmp_path / "latest.json"

    exit_code = verifier.main([str(tmp_path), "--version", "1.0.0", "--manifest", str(manifest)])

    assert exit_code == 1
    assert not manifest.exists(), "a failed release must not leave a manifest claiming success"
    assert "must not be published" in capsys.readouterr().out


def test_main_passes_and_records_what_shipped(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "TchueKAM-Setup.exe").write_bytes(_pe_bytes(b"\0" * 4096))
    (release / "TchueKAM-Linux.AppImage").write_bytes(_appimage_bytes(b"\0" * 4096))
    manifest = tmp_path / "latest.json"

    exit_code = verifier.main(
        [
            str(release),
            "--version", "1.2.3",
            "--require", "windows,linux",
            "--base-url", "https://example.invalid/releases/download/v1.2.3",
            "--manifest", str(manifest),
            "--min-bytes", str(TINY_FLOOR),
        ]
    )

    assert exit_code == 0
    data = json.loads(manifest.read_text())
    assert data["version"] == "1.2.3"
    assert sorted(data["platforms"]) == ["linux", "windows"]
    windows = next(a for a in data["artifacts"] if a["platform"] == "windows")
    assert windows["url"].endswith("/TchueKAM-Setup.exe")
    assert len(windows["sha256"]) == 64
    assert windows["size"] > 0


def test_main_fails_when_a_promised_platform_is_absent(tmp_path, capsys):
    release = tmp_path / "release"
    release.mkdir()
    (release / "TchueKAM-Setup.exe").write_bytes(_pe_bytes(b"\0" * 4096))

    exit_code = verifier.main(
        [str(release), "--require", "windows,mac-arm64", "--min-bytes", str(TINY_FLOOR)]
    )

    assert exit_code == 1
    assert "mac-arm64" in capsys.readouterr().out


def test_main_fails_when_the_build_produced_nothing(tmp_path, capsys):
    empty = tmp_path / "release"
    empty.mkdir()

    exit_code = verifier.main([str(empty)])

    assert exit_code == 1
    assert "nothing was built" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Code signing.
#
# An unsigned installer runs, but Windows SmartScreen tells the customer the
# publisher is unknown and asks them to override the warning — which is the
# opposite of the trust a paid product should carry on first launch.
# --------------------------------------------------------------------------

def _pe_with_cert_table(cert_size: int) -> bytes:
    """A PE image whose certificate-table directory entry reports cert_size."""
    pe_offset = 0x40
    header = bytearray(b"\0" * pe_offset)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = pe_offset.to_bytes(4, "little")

    coff = bytearray(b"PE\0\0" + b"\0" * 20)
    optional = bytearray(b"\0" * 240)
    optional[0:2] = (0x10B).to_bytes(2, "little")  # PE32
    # Data directory 4 (certificate table) starts 96 bytes into the optional
    # header for PE32; each entry is 8 bytes (RVA then size).
    entry = 96 + 4 * 8
    optional[entry:entry + 4] = (0x1000 if cert_size else 0).to_bytes(4, "little")
    optional[entry + 4:entry + 8] = cert_size.to_bytes(4, "little")
    return bytes(header) + bytes(coff) + bytes(optional) + b"\0" * 4096


def test_an_unsigned_installer_is_reported_but_not_blocked_by_default(tmp_path):
    # Reported loudly, but a Windows release is not withheld over it today.
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_cert_table(0))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR)

    assert result.ok, result.problems
    assert result.signed is False


def test_an_unsigned_installer_fails_when_signing_is_required(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_cert_table(0))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, require_signature=True)

    assert not result.ok
    assert any("Authenticode" in p for p in result.problems)


def test_a_signed_installer_passes_when_signing_is_required(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_cert_table(4096))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, require_signature=True)

    assert result.ok, result.problems
    assert result.signed is True


def test_signing_is_not_demanded_of_formats_that_have_no_pe_signature(tmp_path):
    # A .dmg or .AppImage is not a PE file; asking it for an Authenticode
    # signature would block every macOS and Linux release.
    image = tmp_path / "TchueKAM-Linux.AppImage"
    image.write_bytes(_appimage_bytes(b"\0" * 1024))

    result = verifier.verify_file(image, min_bytes=TINY_FLOOR, require_signature=True)

    assert result.ok, result.problems
    assert result.signature_bytes is None


# --------------------------------------------------------------------------
# Version agreement.
#
# The v1.0.0 release shipped a binary that reported itself as 0.15.3. Windows
# listed it under the wrong version, and electron-updater compared the update
# feed against the wrong one, so the two could never agree again.
# --------------------------------------------------------------------------

def _pe_with_version(major: int, minor: int, patch: int, build: int = 0) -> bytes:
    """A PE image carrying a .rsrc section with a VS_FIXEDFILEINFO block."""
    fixed_info = (
        b"\xbd\x04\xef\xfe"                                   # signature
        + (0x00010000).to_bytes(4, "little")                  # strucVersion
        + ((major << 16) | minor).to_bytes(4, "little")       # dwFileVersionMS
        + ((patch << 16) | build).to_bytes(4, "little")       # dwFileVersionLS
        + ((major << 16) | minor).to_bytes(4, "little")       # dwProductVersionMS
        + ((patch << 16) | build).to_bytes(4, "little")       # dwProductVersionLS
    )
    rsrc = fixed_info + b"\0" * 1024

    pe_offset = 0x40
    dos = bytearray(b"\0" * pe_offset)
    dos[0:2] = b"MZ"
    dos[0x3C:0x40] = pe_offset.to_bytes(4, "little")

    optional_size = 240
    coff = bytearray(b"PE\0\0" + b"\0" * 20)
    coff[4 + 2:4 + 4] = (1).to_bytes(2, "little")             # one section
    coff[4 + 16:4 + 18] = optional_size.to_bytes(2, "little")

    optional = bytearray(b"\0" * optional_size)
    optional[0:2] = (0x10B).to_bytes(2, "little")             # PE32

    headers_len = pe_offset + 24 + optional_size + 40
    raw_offset = headers_len + (512 - headers_len % 512) % 512

    section = bytearray(b"\0" * 40)
    section[0:5] = b".rsrc"
    section[16:20] = len(rsrc).to_bytes(4, "little")          # SizeOfRawData
    section[20:24] = raw_offset.to_bytes(4, "little")         # PointerToRawData

    blob = bytes(dos) + bytes(coff) + bytes(optional) + bytes(section)
    return blob + b"\0" * (raw_offset - len(blob)) + rsrc


def test_the_version_mismatch_that_shipped_is_caught(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_version(0, 15, 3))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, expect_version="1.0.0")

    assert not result.ok
    assert any("0.15.3" in p and "1.0.0" in p for p in result.problems)


def test_a_matching_version_passes(tmp_path):
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_version(1, 2, 3))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, expect_version="1.2.3")

    assert result.ok, result.problems
    assert result.embedded_version == "1.2.3.0"


def test_a_tag_style_version_still_matches(tmp_path):
    # Release tags carry a leading v; the binary never does.
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_version(1, 2, 3))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, expect_version="v1.2.3")

    assert result.ok, result.problems


def test_the_build_component_is_not_held_against_a_release(tmp_path):
    # Windows versions are four-part; a release names three.
    artifact = tmp_path / "TchueKAM-Setup.exe"
    artifact.write_bytes(_pe_with_version(1, 2, 3, build=77))

    result = verifier.verify_file(artifact, min_bytes=TINY_FLOOR, expect_version="1.2.3")

    assert result.ok, result.problems


def test_version_is_not_demanded_of_artifacts_that_cannot_carry_one(tmp_path):
    # A .dmg has no PE version resource; requiring one would block every
    # macOS release.
    image = tmp_path / "TchueKAM-Mac-arm64.dmg"
    image.write_bytes(_dmg_bytes(b"\0" * 1024))

    result = verifier.verify_file(image, min_bytes=TINY_FLOOR, expect_version="1.2.3")

    assert result.ok, result.problems
    assert result.embedded_version is None


def test_a_min_bytes_override_does_not_reject_the_update_feed(tmp_path):
    """--min-bytes is for installers; metadata is small by nature.

    A global override once pushed the update feed's floor up to installer size
    and failed a perfectly good latest.yml, which would have blocked the
    release for the opposite of a real problem.
    """
    feed = tmp_path / "latest.yml"
    feed.write_text(
        "version: 1.2.3\n"
        "path: TchueKAM-Setup.exe\n"
        "sha512: QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9wcXJz\n"
    )

    result = verifier.verify_file(feed, min_bytes=20 * 1024 * 1024)

    assert result.ok, result.problems
