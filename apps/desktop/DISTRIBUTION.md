# Desktop Distribution

How a TchueKAM Agent release reaches a customer, and what stands between a
build and a broken download.

## The failure this guards against

In the v1.0.0 release the Windows download did not work. Users saw:

> This app can't run on your PC

The installer they received was **66 bytes of text**:

```
# TchueKAM Agent Desktop Windows Installer (x64)
# Version: 1.0.0
```

The genuine 114 MB installer existed the whole time, published correctly as a
GitHub release asset. The website served a placeholder file of the same name
instead, and nothing in the pipeline ever compared the two. Every developer-side
check was green:

| Step | Status | What it actually proved |
|---|---|---|
| Build succeeded | ✅ | The app compiles |
| Artifact uploaded | ✅ | A file with the right name exists |
| Website links to it | ✅ | The link is not a 404 |
| **Customer runs it** | ❌ | **Nobody checked the bytes** |

The lesson is narrow and worth stating plainly: *a release is not what you
built, it is what the customer downloads.* Everything below exists to check
that second thing.

## The two gates

### 1. Before publishing — `scripts/verify_release_artifacts.py`

Reads each artifact's real content, not its name:

| Format | What must be true |
|---|---|
| `.exe` | `MZ` DOS header **and** a `PE\0\0` signature at the offset it points to |
| `.msi` | OLE compound-file magic, or a valid PE |
| `.dmg` | A 512-byte `koly` UDIF trailer, or macOS will not mount it |
| `.AppImage` | ELF magic **and** the `AI` type marker at offset 8 |
| `.apk` / `.zip` | A zip local-file header |
| `.deb` / `.rpm` | `!<arch>` + `debian-binary`, or the RPM lead |
| `latest*.yml` | Parses, and carries `version`, `path` and `sha512` |

Plus a size floor (20 MB for desktop installers) that catches truncated uploads,
and a SHA-256 for every artifact.

It also checks that a Windows artifact's **own version matches the release**.
Pass `--version` and an installer that disagrees fails:

```
FAIL  TchueKAM-Setup.exe
      -> reports version 0.15.3.0, but this release is 1.0.0. Windows would
         list it under the wrong version and the updater would compare
         against the wrong one.
```

That is not hypothetical — it is what the published v1.0.0 asset does today
(see *Known gaps*).

```bash
python3 scripts/verify_release_artifacts.py apps/desktop/release \
    --version 1.2.3 \
    --require windows \
    --manifest latest.json
```

Exit code 1 blocks the release job. `--require` additionally fails when a
platform we advertise has no verified artifact — so we cannot ship a release
that silently drops macOS.

### 2. After deploying — `scripts/verify_live_downloads.py`

Acts as a customer against the real public site: follows the redirects, and
inspects the bytes that come back.

```bash
python3 scripts/verify_live_downloads.py --base-url https://tchuekam.com
```

It uses HTTP range requests, so checking a 114 MB installer costs a few KB and
is cheap enough to run on every deploy. Add `--full` to download completely and
report SHA-256.

This is the check that would have caught v1.0.0. Run it **after** any website
deploy, not just after a release.

## Cutting a release

1. Bump `version` in `apps/desktop/package.json`.
2. Commit, tag `vX.Y.Z`, push the tag.
3. `.github/workflows/release-desktop.yml` builds Windows, macOS (arm64 + x64)
   and Linux, verifies each platform's artifacts, then verifies everything
   together and uploads to a **draft** release.
4. Review the draft, then publish it on github.com.
5. Run `verify_live_downloads.py` against the live site.

Publishing the draft is what makes `electron-updater` offer the version to
installed copies, so nothing reaches customers until a human has looked at it.

### Why the workflow packages with `--publish never`

electron-builder's `--publish always` uploads while it builds, which puts
artifacts in front of customers before anything has checked them. The workflow
packages first, verifies, and only then uploads. Verification is not a report
you read afterwards — it is a gate the bytes pass through.

## The update feed

`electron-updater` finds new versions by reading `latest.yml` (and
`latest-mac.yml` / `latest-linux.yml`) from the newest published release. The
v1.0.0 release shipped **without** it, so every installed copy silently stopped
receiving updates.

The publish job now fails when no `latest*.yml` is present. If you ever upload
assets by hand, upload the feed too.

## Website download links

The download page must follow two rules, both learned from the outage:

1. **Link to the absolute URL of a published release asset.** The old page used
   relative paths like `/api/download/windows` together with
   `download="TchueKAM-Setup.exe"`. On a static host nothing answers those
   paths, so the browser saved the 404 page itself under the installer's name.
   A cross-origin release URL cannot do that.
2. **Only render a platform that has an asset in the release.** The page reads
   `/api/download-info` where a backend exists and the public GitHub releases
   API otherwise, and draws a button only for platforms it can actually serve.
   An artifact below 1 MB is treated as absent.

`website/src/pages/download.tsx` implements both.

## Download endpoints

`hermes_cli/web_server.py` serves these, and `hermes_cli/download_targets.py`
holds the target tables that both the endpoint and the public auth allowlist
derive from — so a link the endpoint understands can never be one the allowlist
silently answers 401 for.

| Endpoint | Purpose |
|---|---|
| `/api/download/auto` | Picks the installer from the request's User-Agent |
| `/api/download/<platform>` | A specific installer (many aliases accepted) |
| `/api/download-info` | Version, sizes, SHA-256 and which platforms exist |

A locally hosted installer is served only when its leading bytes match the
format its name claims. Otherwise the endpoint redirects to the published
release asset rather than handing over a file that will not open.

## Known gaps

### The Windows installer is not code-signed

`TchueKAM-Setup.exe` carries no Authenticode signature, so Windows SmartScreen
warns customers that the publisher is unknown and asks them to override it.
The installer works; the first-run experience does not look trustworthy.

`.github/workflows/build-windows-installer.yml` already signs the bootstrap
installer through Azure Trusted Signing. Applying the same step to the Electron
NSIS output, and setting `win.signAndEditExecutable` back to `true`, would close
this. Once signing is in place, add `--require-signature` to the verify step and
an unsigned build stops being publishable:

```bash
python3 scripts/verify_release_artifacts.py apps/desktop/release --require-signature
```

The verifier already reports signing state on every run, so the gap stays
visible until it is fixed.

### The published v1.0.0 installer reports itself as 0.15.3

The asset attached to the `v1.0.0` release carries `FileVersion 0.15.3` in its
PE version resource, matching `apps/desktop/package.json` rather than the tag.
So a customer who installs "1.0.0" sees **0.15.3** in *Add or remove programs*,
and `electron-updater` compares the update feed against 0.15.3.

The release workflow already refuses to run when the tag and `package.json`
disagree, which means this artifact was not produced by it. Re-cutting the
release through the workflow — bump `package.json` to the version you intend,
commit, tag, let CI build — produces an installer whose version matches, and
`--version` now fails the build if it ever does not.

### The live site is deployed from another repository

`www.tchuekam.com` is not built from this repo — its pages (`/installation`,
`/about-founder`, `/explore/`) do not exist here, and it serves the placeholder
files from its own `static/` directory. The fixes in this repo cover the release
pipeline, the download API and this repo's download page; the placeholder files
themselves must be deleted from the website repository, and its download links
pointed at the release assets, before the public download works.

`verify_live_downloads.py` is the check for that work: it passes only once
tchuekam.com serves real installers.
