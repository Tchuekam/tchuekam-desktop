FROM ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:b3c543b6c4f23a5f2df22866bd7857e5d304b67a564f4feab6ac22044dde719b AS uv_source
# Node 22 LTS source stage. Debian trixie's bundled nodejs is pinned to 20.x
# which reached EOL in April 2026 — we copy node + npm + corepack from the
# upstream node:22 image instead so we can stay on a supported LTS without
# waiting for Debian 14 (forky, ~mid-2027).  Bookworm-based slim image used
# so the produced binary links against glibc 2.36, which runs cleanly on
# our Debian 13 (trixie, glibc 2.41) runtime.  Bumping to a new Node major
# is a one-line ARG change; see #4977.
FROM node:22-bookworm-slim@sha256:7af03b14a13c8cdd38e45058fd957bf00a72bbe17feac43b1c15a689c029c732 AS node_source

# ---------- Web app build stage ----------
# Builds apps/desktop's browser bundle, which the dashboard serves as its SPA
# (HERMES_WEB_DIST, below). This is a separate stage on purpose: the runtime
# image deliberately never `npm install`s apps/* — see the HERMES_TUI_DIR
# comment near the end of this file for why installing it there would break
# the TUI launcher's lockfile check. Only the built static output crosses
# over, so the runtime node_modules tree is untouched and no Electron
# toolchain lands in the final image.
#
# Serving the app from the dashboard's own origin is what makes the auth gate
# usable: its session cookies are SameSite=Lax, so a bundle hosted elsewhere
# never gets them on fetch or WebSocket handshakes. See apps/desktop/WEB.md.
FROM node:22-bookworm-slim@sha256:7af03b14a13c8cdd38e45058fd957bf00a72bbe17feac43b1c15a689c029c732 AS webapp_builder
WORKDIR /build

# Every workspace manifest, so npm can resolve the root lockfile. They are
# tiny; the sources that actually get built are copied further down.
COPY package.json package-lock.json ./
COPY apps/desktop/package.json apps/desktop/
COPY apps/shared/package.json apps/shared/
COPY apps/mobile/package.json apps/mobile/
COPY apps/bootstrap-installer/package.json apps/bootstrap-installer/
COPY web/package.json web/
COPY ui-tui/package.json ui-tui/
COPY ui-tui/packages/hermes-ink/ ui-tui/packages/hermes-ink/

# Scope the install to the one workspace being built, plus the root (whose
# node_modules holds the hoisted React that vite.aliases.ts resolves against).
# Electron is a devDependency of apps/desktop and its postinstall would pull a
# ~100MB binary that no browser build needs.
ENV npm_config_install_links=false
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
RUN npm install --prefer-offline --no-audit \
        --workspace apps/desktop --include-workspace-root && \
    npm cache clean --force

COPY apps/desktop/ apps/desktop/
COPY apps/shared/ apps/shared/

# VITE_HERMES_API_URL is intentionally unset: the bundle is served by the
# dashboard itself, so it addresses the API on its own origin. Overridable at
# build time for a split-origin deployment.
ARG VITE_HERMES_API_URL=""
# Keeps the host-management surfaces (settings, profiles, messaging,
# automation) hidden. Flip to 0 only once the auth gate is configured and
# everyone who can load the page is someone you'd trust to edit this
# deployment's provider credentials — until then there is no login in front of
# those screens. The terminal and file browser stay hidden either way; they
# need a PTY and filesystem the browser does not have.
ARG VITE_HERMES_DEMO="1"
ARG VITE_HERMES_APP_VERSION="docker"
ENV VITE_HERMES_API_URL=${VITE_HERMES_API_URL} \
    VITE_HERMES_DEMO=${VITE_HERMES_DEMO} \
    VITE_HERMES_APP_VERSION=${VITE_HERMES_APP_VERSION}
RUN npm run build:web --workspace apps/desktop

FROM debian:13.4@sha256:7a372138a0a86616428e35cf82315b674b05a76bbd352baf6fb6b000574f88bd

# Disable Python stdout buffering to ensure logs are printed immediately
ENV PYTHONUNBUFFERED=1

# Store Playwright browsers outside the volume mount so the build-time
# install survives the /opt/data volume overlay at runtime.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright

# Install system dependencies in one layer, clear APT cache.
# tini was previously PID 1 to reap orphaned zombie processes (MCP stdio
# subprocesses, git, bun, etc.) that would otherwise accumulate when hermes
# ran as PID 1. See #15012. Phase 2 of the s6-overlay supervision plan
# replaces tini with s6-overlay's /init (PID 1 = s6-svscan), which reaps
# zombies non-blockingly on SIGCHLD and additionally supervises the main
# hermes process, the dashboard, and per-profile gateways.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl iputils-ping python3 python-is-python3 ripgrep ffmpeg gcc python3-dev python3-venv libffi-dev procps git openssh-client docker-cli xz-utils && \
    rm -rf /var/lib/apt/lists/*

# ---------- s6-overlay install ----------
# s6-overlay provides supervision for the main hermes process, the dashboard,
# and per-profile gateways. /init becomes PID 1 below — see ENTRYPOINT.
#
# Multi-arch: BuildKit auto-populates TARGETARCH (amd64 / arm64). s6-overlay
# uses tarball names keyed on the kernel arch string (x86_64 / aarch64), so
# we map between them inline. The noarch + symlinks tarballs are
# architecture-independent and reused as-is.
#
# We use `curl` instead of `ADD` for the per-arch tarball because `ADD`
# evaluates its URL at parse time, before any ARG / TARGETARCH substitution
# — splitting one URL per arch into two ADDs would download both on every
# build and leave dead bytes in the cache. A single curl + arch-keyed URL
# is simpler and cache-friendlier.
#
# Supply-chain integrity: every tarball is checksum-verified against the
# upstream-published SHA256. To bump S6_OVERLAY_VERSION, fetch the four
# `.sha256` files from the corresponding release and update the ARGs. The
# checksum lookup happens during build, so a compromised release artifact
# fails the build loudly instead of silently producing a tampered image.
ARG TARGETARCH
ARG S6_OVERLAY_VERSION=3.2.3.0
ARG S6_OVERLAY_NOARCH_SHA256=b720f9d9340efc8bb07528b9743813c836e4b02f8693d90241f047998b4c53cf
ARG S6_OVERLAY_X86_64_SHA256=a93f02882c6ed46b21e7adb5c0add86154f01236c93cd82c7d682722e8840563
ARG S6_OVERLAY_AARCH64_SHA256=0952056ff913482163cc30e35b2e944b507ba1025d78f5becbb89367bf344581
ARG S6_OVERLAY_SYMLINKS_SHA256=a60dc5235de3ecbcf874b9c1f18d73263ab99b289b9329aa950e8729c4789f0e
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
        amd64) s6_arch="x86_64"; s6_arch_sha="${S6_OVERLAY_X86_64_SHA256}" ;; \
        arm64) s6_arch="aarch64"; s6_arch_sha="${S6_OVERLAY_AARCH64_SHA256}" ;; \
        *) echo "Unsupported TARGETARCH=${TARGETARCH} for s6-overlay" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 5 -o /tmp/s6-overlay-noarch.tar.xz \
        "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz"; \
    curl -fsSL --retry 5 -o /tmp/s6-overlay-symlinks-noarch.tar.xz \
        "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-symlinks-noarch.tar.xz"; \
    curl -fsSL --retry 5 -o /tmp/s6-overlay-arch.tar.xz \
        "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${s6_arch}.tar.xz"; \
    { \
        printf '%s  %s\n' "${S6_OVERLAY_NOARCH_SHA256}" /tmp/s6-overlay-noarch.tar.xz; \
        printf '%s  %s\n' "${s6_arch_sha}" /tmp/s6-overlay-arch.tar.xz; \
        printf '%s  %s\n' "${S6_OVERLAY_SYMLINKS_SHA256}" /tmp/s6-overlay-symlinks-noarch.tar.xz; \
    } > /tmp/s6-overlay.sha256; \
    sha256sum -c /tmp/s6-overlay.sha256; \
    tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-overlay-arch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-overlay-symlinks-noarch.tar.xz; \
    rm /tmp/s6-overlay-*.tar.xz /tmp/s6-overlay.sha256; \
    # #34192: backward-compat shim for orchestration templates that still\
    # reference the legacy /usr/bin/tini entrypoint (e.g. Hostinger's\
    # 'Hermes WebUI' catalog). The image has moved to s6-overlay /init\
    # as PID 1 (see ENTRYPOINT below + the migration comment at the top\
    # of this file), but external wrappers pinned to /usr/bin/tini will\
    # crash with 'tini: No such file or directory' on startup. The shim\
    # symlinks /usr/bin/tini -> /init so legacy wrappers exec the right\
    # PID-1 reaper without behavior change for users on the current\
    # ENTRYPOINT. Safe to drop once the affected catalogs are updated.\
    ln -sf /init /usr/bin/tini

# Non-root user for runtime; UID can be overridden via HERMES_UID at runtime
RUN useradd -u 10000 -m -d /opt/data hermes

COPY --chmod=0755 --from=uv_source /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# Node 22 LTS: copy the node binary plus the bundled npm + corepack JS
# installs from the upstream image.  npm and npx are recreated as symlinks
# because they're symlinks in the source image (and need to live on PATH).
# See node_source stage at the top of the file for the version-bump
# rationale (#4977).
COPY --chmod=0755 --from=node_source /usr/local/bin/node /usr/local/bin/
COPY --from=node_source /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=node_source /usr/local/lib/node_modules/corepack /usr/local/lib/node_modules/corepack
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    ln -sf /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack

WORKDIR /opt/hermes

# ---------- Layer-cached dependency install ----------
# Copy only package manifests first so npm install + Playwright are cached
# unless the lockfiles themselves change.
#
# ui-tui/packages/hermes-ink/ is copied IN FULL (not just its manifests)
# because it is referenced as a `file:` workspace dependency from
# ui-tui/package.json.  Copying the tree up front lets npm resolve the
# workspace to real content instead of stopping at a bare package.json.
COPY --chown=hermes:hermes package.json package-lock.json ./
COPY --chown=hermes:hermes web/package.json web/
COPY --chown=hermes:hermes ui-tui/package.json ui-tui/
COPY --chown=hermes:hermes ui-tui/packages/hermes-ink/ ui-tui/packages/hermes-ink/

# `npm_config_install_links=false` forces npm to install `file:` deps as
# symlinks instead of copies.  This is the default since npm 10+, which is
# what the image ships now (via the node:22 source stage).  We set it
# explicitly anyway as defense-in-depth: the previous Debian-bundled npm
# 9.x defaulted to install-as-copy, which produced a hidden
# node_modules/.package-lock.json that permanently disagreed with the root
# lock on the @hermes/ink entry, tripped the TUI launcher's
# `_tui_need_npm_install()` check on every startup, and triggered a
# runtime `npm install` that then failed with EACCES.  Keeping the env
# guards against a future regression if the source npm version changes.
ENV npm_config_install_links=false

RUN npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium --only-shell && \
    npm cache clean --force && \
