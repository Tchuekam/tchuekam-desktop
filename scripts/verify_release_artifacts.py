#!/usr/bin/env python3
"""Verify that desktop release artifacts are genuine, complete installers.

tchuekam.com once served 66-byte text files named ``TchueKAM-Setup.exe``.
Windows answered "This app can't run on your PC", because the download was
never an executable at all.  Nothing in the pipeline looked at the bytes, so a
placeholder sailed through every step and reached customers.

This script is that missing check.  It inspects each artifact's real content --
the magic bytes that make a file an executable, a disk image or a package --
and refuses anything that only *looks* like an installer because of its name.

Run it over a build output directory before publishing:

    python3 scripts/verify_release_artifacts.py apps/desktop/release \
        --version 1.0.0 --require windows --manifest latest.json

Exit status is 0 only when every artifact examined is a real installer, so it
can gate a release job directly.  stdlib only: it has to run in CI with no
install step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# A real Electron desktop installer is tens of megabytes.  These floors sit far
# below any plausible genuine build while still being orders of magnitude above
# a placeholder, so they catch truncated uploads and stub files without ever
# tripping on a legitimate artifact.
_DEFAULT_MIN_BYTES = 20 * 1024 * 1024
_MIN_BYTES_BY_KIND = {
    "apk": 1 * 1024 * 1024,
    "updater-metadata": 64,
    "blockmap": 512,
}

# These are structurally small by nature -- a 20 MB update feed would be absurd
# -- so a --min-bytes override meant for installers must not be applied to them.
_METADATA_KINDS = frozenset({"updater-metadata", "blockmap"})

# Platform keys the website and the download API use to ask for an artifact.
PLATFORM_WINDOWS = "windows"
PLATFORM_MAC_ARM64 = "mac-arm64"
PLATFORM_MAC_X64 = "mac-x64"
PLATFORM_LINUX = "linux"
PLATFORM_ANDROID = "android"


class VerificationError(Exception):
    """An artifact is not a usable installer."""


# --------------------------------------------------------------------------
# Format checks.  Each returns None when the bytes are right, or a string
# describing what was actually found.
# --------------------------------------------------------------------------

def _check_pe(data: bytes, path: Path) -> str | None:
    """Windows .exe / .msi stubs: DOS header then a PE signature."""
    if data[:2] != b"MZ":
        return f"missing the 'MZ' DOS header (starts with {data[:8]!r})"
    if len(data) < 0x40:
        return "truncated before the PE header offset"
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    with path.open("rb") as fh:
        fh.seek(pe_offset)
        signature = fh.read(4)
    if signature != b"PE\0\0":
        return (
            f"has an 'MZ' header but no PE signature at offset {pe_offset} "
            f"(found {signature!r}) -- not a Windows executable"
        )
    return None


def _check_msi(data: bytes, path: Path) -> str | None:
    """MSI packages are OLE compound documents, not PE images."""
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return None
    # electron-builder can emit a PE bootstrapper with a .msi name.
    if data[:2] == b"MZ":
        return _check_pe(data, path)
    return f"is neither an OLE compound file nor a PE image (starts with {data[:8]!r})"


def _check_dmg(data: bytes, path: Path) -> str | None:
    """Apple UDIF disk images carry a 512-byte 'koly' trailer at the end."""
    size = path.stat().st_size
    if size < 512:
        return "too small to contain a UDIF trailer"
    with path.open("rb") as fh:
        fh.seek(size - 512)
        trailer = fh.read(4)
    if trailer != b"koly":
        return (
            f"has no 'koly' UDIF trailer (found {trailer!r}) -- "
            "not a mountable disk image"
        )
    return None


def _check_appimage(data: bytes, _path: Path) -> str | None:
    """AppImages are ELF binaries with an 'AI' type marker at offset 8."""
    if data[:4] != b"\x7fELF":
        return f"missing the ELF magic (starts with {data[:8]!r})"
    if data[8:10] != b"AI":
        return (
            "is an ELF binary but carries no AppImage type marker at offset 8 "
            f"(found {data[8:11]!r})"
        )
    return None


def _check_zip(data: bytes, _path: Path) -> str | None:
    """APK / zip archives begin with a local file header."""
    if data[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return None
    return f"is not a zip archive (starts with {data[:8]!r})"


def _check_deb(data: bytes, _path: Path) -> str | None:
    if data[:8] != b"!<arch>\n":
        return f"is not an ar archive (starts with {data[:8]!r})"
    if b"debian-binary" not in data[:120]:
        return "is an ar archive but has no debian-binary member"
    return None


def _check_rpm(data: bytes, _path: Path) -> str | None:
    if data[:4] != b"\xed\xab\xee\xdb":
        return f"is not an RPM package (starts with {data[:8]!r})"
    return None


def _check_gzip(data: bytes, _path: Path) -> str | None:
    if data[:2] != b"\x1f\x8b":
        return f"is not gzip data (starts with {data[:8]!r})"
    return None


def _check_updater_metadata(_data: bytes, path: Path) -> str | None:
    """electron-updater's latest*.yml -- the file that makes updates work.

    Parsed without PyYAML so this script keeps its stdlib-only promise; the
    three keys that matter are flat scalars at the top level.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "is not UTF-8 text, so electron-updater cannot parse it"
    missing = [key for key in ("version:", "path:", "sha512:") if key not in text]
    if missing:
        return f"is missing required update keys: {', '.join(m.rstrip(':') for m in missing)}"
    return None


def _pe_sections(fh) -> list[tuple[str, int, int]]:
    """(name, raw offset, raw size) for each section of an open PE file."""
    fh.seek(0)
    head = fh.read(0x40)
    if head[:2] != b"MZ" or len(head) < 0x40:
        return []
    pe_offset = int.from_bytes(head[0x3C:0x40], "little")
    fh.seek(pe_offset)
    if fh.read(4) != b"PE\0\0":
        return []
    coff = fh.read(20)
    if len(coff) < 20:
        return []
    section_count = int.from_bytes(coff[2:4], "little")
    optional_size = int.from_bytes(coff[16:18], "little")
    fh.seek(pe_offset + 24 + optional_size)
    sections = []
    for _ in range(section_count):
        entry = fh.read(40)
        if len(entry) < 40:
            break
        name = entry[:8].rstrip(b"\0").decode("ascii", "replace")
        raw_size = int.from_bytes(entry[16:20], "little")
        raw_offset = int.from_bytes(entry[20:24], "little")
        sections.append((name, raw_offset, raw_size))
    return sections


def embedded_windows_version(path: Path) -> str | None:
    """The version a Windows binary reports about itself, or None.

    This is what Windows shows in "Add or remove programs" and what
    electron-updater compares against the update feed.  The v1.0.0 release
    shipped a binary whose own version was 0.15.3, so the product advertised as
    1.0.0 installed as 0.15.3 and the two never agreed again.

    Read with stdlib only: the resource directory is walked by locating the
    VS_FIXEDFILEINFO signature inside the .rsrc section, which avoids a
    dependency this script is not allowed to have.
    """
    try:
        with path.open("rb") as fh:
            rsrc = next(
                (s for s in _pe_sections(fh) if s[0] == ".rsrc" and s[2] > 0),
                None,
            )
            if rsrc is None:
                return None
            _name, offset, size = rsrc
            fh.seek(offset)
            data = fh.read(min(size, 8 * 1024 * 1024))
    except OSError:
        return None

    marker = b"\xbd\x04\xef\xfe"  # VS_FIXEDFILEINFO signature, little-endian
    index = data.find(marker)
    if index < 0 or index + 20 > len(data):
        return None
    # signature(4) strucVersion(4) then dwFileVersionMS, dwFileVersionLS
    ms = int.from_bytes(data[index + 8:index + 12], "little")
    ls = int.from_bytes(data[index + 12:index + 16], "little")
    parts = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    return ".".join(str(p) for p in parts)


def _version_matches(embedded: str, declared: str) -> bool:
    """Compare on the parts a release actually names (major.minor.patch)."""
    def norm(v: str) -> tuple:
        cleaned = v.strip().lstrip("vV").split("-")[0].split("+")[0]
        out = []
        for chunk in cleaned.split("."):
            if not chunk.isdigit():
                break
            out.append(int(chunk))
        return tuple((out + [0, 0, 0])[:3])

    return norm(embedded) == norm(declared)


def authenticode_signature_size(path: Path) -> int | None:
    """Bytes of Authenticode signature on a PE file, or None if not a PE.

    An unsigned installer still runs, but Windows SmartScreen shows an
    "unknown publisher" warning that asks the user to override it -- the
    opposite of the trust a paid product should carry on first launch.
    Reported for every Windows artifact; enforced with --require-signature.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(0x40)
            if head[:2] != b"MZ" or len(head) < 0x40:
                return None
            pe_offset = int.from_bytes(head[0x3C:0x40], "little")
            fh.seek(pe_offset)
            if fh.read(4) != b"PE\0\0":
                return None
            fh.seek(pe_offset + 24)
            magic = int.from_bytes(fh.read(2), "little")
            # The certificate table is data directory 4; its position depends
            # on whether this is PE32 (96 bytes of standard fields) or PE32+.
            dir_offset = pe_offset + 24 + (112 if magic == 0x20B else 96)
            fh.seek(dir_offset + 4 * 8)
            entry = fh.read(8)
            if len(entry) < 8:
                return None
            _rva, size = int.from_bytes(entry[:4], "little"), int.from_bytes(entry[4:], "little")
            return size
    except OSError:
        return None


@dataclass(frozen=True)
class ArtifactKind:
    """How to tell whether a file of this type is real."""

    name: str
    check: object
    platform: str | None = None
    description: str = ""


_KINDS: dict[str, ArtifactKind] = {
    ".exe": ArtifactKind("exe", _check_pe, PLATFORM_WINDOWS, "Windows installer"),
    ".msi": ArtifactKind("msi", _check_msi, PLATFORM_WINDOWS, "Windows MSI package"),
    ".dmg": ArtifactKind("dmg", _check_dmg, None, "macOS disk image"),
    ".appimage": ArtifactKind("appimage", _check_appimage, PLATFORM_LINUX, "Linux AppImage"),
    ".apk": ArtifactKind("apk", _check_zip, PLATFORM_ANDROID, "Android package"),
    ".zip": ArtifactKind("zip", _check_zip, None, "zip archive"),
    ".deb": ArtifactKind("deb", _check_deb, PLATFORM_LINUX, "Debian package"),
    ".rpm": ArtifactKind("rpm", _check_rpm, PLATFORM_LINUX, "RPM package"),
    ".yml": ArtifactKind("updater-metadata", _check_updater_metadata, None, "update feed"),
    ".yaml": ArtifactKind("updater-metadata", _check_updater_metadata, None, "update feed"),
    ".blockmap": ArtifactKind("blockmap", _check_gzip, None, "differential update block map"),
}

# Files that are build by-products rather than things a customer downloads.
_IGNORED_SUFFIXES = {".txt", ".md", ".json", ".log", ".sha256", ".sha512"}


def classify(path: Path) -> ArtifactKind | None:
    """Return how ``path`` should be verified, or None if it is not an artifact."""
    name = path.name.lower()
    if name.endswith(".blockmap"):
        return _KINDS[".blockmap"]
    suffix = path.suffix.lower()
    if suffix in _IGNORED_SUFFIXES:
        return None
    return _KINDS.get(suffix)


def platform_for(path: Path, kind: ArtifactKind) -> str | None:
    """Work out which download button an artifact belongs behind."""
    if kind.platform is not None:
        return kind.platform
    name = path.name.lower()
    if kind.name == "dmg":
        if "arm64" in name or "aarch64" in name or "silicon" in name:
            return PLATFORM_MAC_ARM64
        if "x64" in name or "intel" in name or "x86_64" in name:
            return PLATFORM_MAC_X64
        return None
    return None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Result:
    path: Path
    kind: ArtifactKind
    size: int
    sha256: str
    platform: str | None
    signature_bytes: int | None = None
    embedded_version: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def signed(self) -> bool:
        return bool(self.signature_bytes)

    @property
    def ok(self) -> bool:
        return not self.problems


def verify_file(
    path: Path,
    *,
    min_bytes: int | None = None,
    require_signature: bool = False,
    expect_version: str = "",
) -> Result:
    """Inspect one artifact's real bytes."""
    kind = classify(path)
    if kind is None:
        raise VerificationError(f"{path.name}: unrecognised artifact type")

    size = path.stat().st_size
    if min_bytes is not None and kind.name not in _METADATA_KINDS:
        floor = min_bytes
    else:
        floor = _MIN_BYTES_BY_KIND.get(kind.name, _DEFAULT_MIN_BYTES)

    result = Result(
        path=path,
        kind=kind,
        size=size,
        sha256=sha256_of(path),
        platform=platform_for(path, kind),
        signature_bytes=authenticode_signature_size(path),
        embedded_version=embedded_windows_version(path),
    )

    if size == 0:
        result.problems.append("is empty")
        return result

    with path.open("rb") as fh:
        head = fh.read(4096)

    problem = kind.check(head, path)
    if problem:
        result.problems.append(f"{problem}")

    if expect_version and result.embedded_version and not _version_matches(
        result.embedded_version, expect_version
    ):
        result.problems.append(
            f"reports version {result.embedded_version}, but this release is "
            f"{expect_version}. Windows would list it under the wrong version and "
            "the updater would compare against the wrong one."
        )

    if require_signature and result.signature_bytes == 0:
        result.problems.append(
            "carries no Authenticode signature. Windows SmartScreen will warn "
            "customers that the publisher is unknown."
        )

    if size < floor:
        result.problems.append(
            f"is {size:,} bytes -- a genuine {kind.description or kind.name} is at "
            f"least {floor:,} bytes. This is what a placeholder or a truncated "
            "upload looks like."
        )

    return result


def collect(paths: list[Path]) -> list[Path]:
    """Expand directories into the artifact files inside them."""
    found: list[Path] = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and classify(child) is not None:
                    found.append(child)
        elif p.is_file():
            found.append(p)
        else:
            raise VerificationError(f"{p}: no such file or directory")
    return found


def build_manifest(results: list[Result], version: str, base_url: str | None) -> dict:
    """Describe the release so the website can show real numbers, not guesses."""
    artifacts = []
    for r in sorted(results, key=lambda r: r.path.name):
        if r.kind.name in ("updater-metadata", "blockmap"):
            continue
        entry = {
            "filename": r.path.name,
            "platform": r.platform,
            "kind": r.kind.name,
            "size": r.size,
            "sha256": r.sha256,
        }
        if r.signature_bytes is not None:
            entry["signed"] = r.signed
        if base_url:
            entry["url"] = f"{base_url.rstrip('/')}/{r.path.name}"
        artifacts.append(entry)
    return {
        "version": version,
        "artifacts": artifacts,
        "platforms": sorted({a["platform"] for a in artifacts if a["platform"]}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify desktop release artifacts are genuine installers.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="artifact files or a build output directory")
    parser.add_argument("--version", default="", help="release version recorded in the manifest")
    parser.add_argument("--manifest", type=Path, help="write a release manifest to this path")
    parser.add_argument("--base-url", default="", help="public URL prefix the artifacts are served from")
    parser.add_argument(
        "--require",
        default="",
        help="comma-separated platforms that must be present (e.g. windows,linux)",
    )
    parser.add_argument("--min-bytes", type=int, help="override the per-type minimum size")
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help="fail Windows artifacts that carry no Authenticode signature",
    )
    args = parser.parse_args(argv)

    try:
        files = collect(args.paths)
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not files:
        print("error: no release artifacts found -- nothing was built", file=sys.stderr)
        return 1

    results: list[Result] = []
    failures = 0
    print(f"Verifying {len(files)} artifact(s)\n")
    for path in files:
        try:
            result = verify_file(
                path,
                min_bytes=args.min_bytes,
                require_signature=args.require_signature,
                expect_version=args.version,
            )
        except VerificationError as exc:
            print(f"  SKIP  {path.name}: {exc}")
            continue
        results.append(result)
        if result.ok:
            print(f"  PASS  {path.name}  ({result.size:,} bytes, {result.kind.description or result.kind.name})")
            print(f"        sha256 {result.sha256}")
            if result.embedded_version:
                print(f"        reports version {result.embedded_version}")
            if result.signature_bytes is not None:
                if result.signed:
                    print(f"        signed ({result.signature_bytes:,} bytes of Authenticode signature)")
                else:
                    print("        UNSIGNED -- SmartScreen will warn customers about an unknown publisher")
        else:
            failures += 1
            print(f"  FAIL  {path.name}  ({result.size:,} bytes)")
            for problem in result.problems:
                print(f"        -> {path.name} {problem}")

    required = [p.strip() for p in args.require.split(",") if p.strip()]
    present = {r.platform for r in results if r.ok and r.platform}
    missing = [p for p in required if p not in present]
    if missing:
        failures += len(missing)
        print()
        for p in missing:
            print(f"  FAIL  no verified artifact for required platform '{p}'")

    print()
    if failures:
        print(f"FAILED: {failures} problem(s). This release must not be published.")
        return 1

    if args.manifest:
        manifest = build_manifest(results, args.version, args.base_url or None)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote manifest: {args.manifest}")

    print(f"OK: {len(results)} artifact(s) verified as genuine installers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
