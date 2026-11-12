#!/usr/bin/env python3
"""Check that a packaged Electron app can actually load its own code.

The v1.0.0 installer was a genuine, complete, correctly signed-size 114 MB
NSIS installer. It installed perfectly. Then it died before opening a window:

    A JavaScript error occurred in the main process
    Error: Cannot find module 'electron-updater'

``electron/auto-updater.cjs`` required a module that was not in the package.
npm workspaces had hoisted it to the repo root, so electron-builder's
``node_modules/electron-updater/**`` glob -- resolved relative to the app
directory -- matched nothing. A glob matching nothing is not an error, so the
build was green, the artifact was real, and the app was broken.

Checking that the bytes are a valid installer could never have caught that.
This checks the next thing: that every module the packaged main process
requires by name is actually inside the package.

    python3 scripts/verify_packaged_asar.py apps/desktop/release/win-unpacked/resources/app.asar

Exit status is 0 only when every require() resolves. stdlib only, so it runs
in CI with no install step.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

# Modules Electron and Node provide; a require() of one of these needs nothing
# in the package.
_PROVIDED = {
    "electron",
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads",
    "zlib",
}

_REQUIRE = re.compile(r"""require\(\s*(['"])([^'"\n]+)\1\s*\)""")

_SOURCE_SUFFIXES = {".js", ".cjs", ".mjs"}


def read_asar(path: Path) -> tuple[dict, int]:
    """Return the asar's header and the offset its file data starts at."""
    with path.open("rb") as fh:
        _, _, _, json_len = struct.unpack("<IIII", fh.read(16))
        header = json.loads(fh.read(json_len).decode("utf-8"))
    base = 16 + json_len
    base += (4 - json_len % 4) % 4  # pickle 4-byte alignment
    return header, base


def walk(node: dict, prefix: str = ""):
    for name, meta in (node.get("files") or {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in meta:
            yield from walk(meta, path)
        else:
            yield path, meta


class Package:
    """Either an .asar or an unpacked app directory.

    Some modules are deliberately shipped *beside* the asar rather than inside
    it: a native dependency cannot be loaded from an archive, so node-pty is
    staged into ``resources/native-deps/`` and main.cjs resolves it from
    ``process.resourcesPath``. Those roots are checked too, otherwise this
    would report a module that is present and working -- and a check that
    cries wolf is a check people learn to skip.
    """

    def __init__(self, target: Path, extra_roots: list[str] | None = None):
        self.target = target
        # For an asar this is resources/; for an unpacked dir, its parent.
        self.resources_dir = target.parent if target.is_file() else target
        self.extra_roots = extra_roots or []
        self.is_asar = target.is_file()
        if self.is_asar:
            header, self._base = read_asar(target)
            self._entries = dict(walk(header))
            self.paths = set(self._entries)
            self._dirs = {p.rsplit("/", 1)[0] for p in self.paths if "/" in p}
        else:
            self.paths = {
                str(p.relative_to(target)).replace("\\", "/")
                for p in target.rglob("*")
                if p.is_file()
            }
            self._dirs = {
                str(p.relative_to(target)).replace("\\", "/")
                for p in target.rglob("*")
                if p.is_dir()
            }

    def read(self, rel: str) -> str:
        if not self.is_asar:
            return (self.target / rel).read_text(encoding="utf-8", errors="replace")
        meta = self._entries[rel]
        with self.target.open("rb") as fh:
            fh.seek(self._base + int(meta["offset"]))
            return fh.read(int(meta["size"])).decode("utf-8", errors="replace")

    def has_dir(self, rel: str) -> bool:
        return rel in self._dirs or any(p.startswith(rel + "/") for p in self.paths)

    def has_module(self, name: str) -> tuple[bool, str]:
        """Is this module loadable at runtime, and from where?"""
        if self.has_dir(f"node_modules/{name}"):
            return True, "asar"
        for root in self.extra_roots:
            if (self.resources_dir / root / name / "package.json").is_file():
                return True, f"resources/{root}"
        return False, ""


def module_name(specifier: str) -> str:
    """'@scope/pkg/sub' -> '@scope/pkg'; 'pkg/sub' -> 'pkg'."""
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def resolves_relative(pkg: Package, source: str, specifier: str) -> bool:
    """Does a './x' or '../x' require point at something in the package?"""
    base = source.rsplit("/", 1)[0] if "/" in source else ""
    parts = (base.split("/") if base else []) + specifier.split("/")
    stack: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
            continue
        stack.append(part)
    target = "/".join(stack)
    candidates = [target, f"{target}.js", f"{target}.cjs", f"{target}.mjs", f"{target}.json",
                  f"{target}/index.js", f"{target}/index.cjs", f"{target}/package.json"]
    return any(c in pkg.paths for c in candidates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a packaged Electron app's requires resolve inside the package.",
    )
    parser.add_argument("target", type=Path, help="app.asar, or an unpacked app directory")
    parser.add_argument(
        "--scan",
        default="electron",
        help="directory inside the package holding main-process code (default: electron)",
    )
    parser.add_argument(
        "--resource-root",
        action="append",
        default=None,
        dest="resource_roots",
        help="directory beside the asar that the app loads modules from "
             "(repeatable; default: native-deps)",
    )
    parser.add_argument(
        "--expect",
        default="",
        help="comma-separated modules that must be present (e.g. electron-updater)",
    )
    args = parser.parse_args(argv)

    if not args.target.exists():
        print(f"error: {args.target} does not exist", file=sys.stderr)
        return 2

    pkg = Package(args.target, args.resource_roots or ["native-deps"])
    print(f"Inspecting {args.target}")
    print(f"  {len(pkg.paths)} file(s) in the package\n")

    bundled = sorted(
        {
            module_name(p[len("node_modules/"):])
            for p in pkg.paths
            if p.startswith("node_modules/")
        }
    )
    print(f"=== bundled modules ({len(bundled)}) ===")
    print("  " + (", ".join(bundled) if bundled else "*** none ***"))
    print()

    # Main-process sources: whatever package.json points at, plus the scan dir.
    sources = sorted(
        p for p in pkg.paths
        if p.startswith(f"{args.scan}/")
        and Path(p).suffix in _SOURCE_SUFFIXES
        and ".test." not in Path(p).name
    )
    main_field = ""
    if "package.json" in pkg.paths:
        try:
            main_field = json.loads(pkg.read("package.json")).get("main", "")
        except ValueError:
            pass
    if main_field and main_field in pkg.paths and main_field not in sources:
        sources.append(main_field)

    if not sources:
        print(f"error: no main-process sources found under '{args.scan}/'", file=sys.stderr)
        return 2

    missing: dict[str, set[str]] = {}
    found_outside: dict[str, str] = {}
    checked = 0
    for source in sources:
        text = pkg.read(source)
        for _quote, specifier in _REQUIRE.findall(text):
            checked += 1
            if specifier.startswith("node:"):
                continue
            if specifier.startswith("."):
                if not resolves_relative(pkg, source, specifier):
                    missing.setdefault(specifier, set()).add(source)
                continue
            if specifier.startswith("/") or ":" in specifier:
                continue  # absolute or a URL-ish specifier; not ours to resolve
            name = module_name(specifier)
            if name in _PROVIDED:
                continue
            ok, where = pkg.has_module(name)
            if ok:
                found_outside.setdefault(name, where)
                continue
            missing.setdefault(name, set()).add(source)

    print(f"=== resolved {checked} require() call(s) across {len(sources)} main-process file(s) ===\n")

    required = [m.strip() for m in args.expect.split(",") if m.strip()]
    for name in required:
        ok, _where = pkg.has_module(name)
        if not ok:
            missing.setdefault(name, set()).add("(required by --expect)")

    shipped_beside = {n: w for n, w in found_outside.items() if w != "asar"}
    if shipped_beside:
        print("=== resolved from outside the asar (extraResources) ===")
        for name, where in sorted(shipped_beside.items()):
            print(f"  {name} -> {where}/")
        print()

    if missing:
        print("FAILED: the packaged app requires modules that are not in the package.")
        print("This installs fine and then dies at startup.\n")
        for name, sources_using in sorted(missing.items()):
            print(f"  MISSING  {name}")
            for s in sorted(sources_using):
                print(f"           required by {s}")
        print(
            "\nIf these are workspace-hoisted dependencies, they need staging into "
            "the package (see apps/desktop/scripts/stage-app-deps.cjs)."
        )
        return 1

    print("OK: every module the packaged main process requires is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
