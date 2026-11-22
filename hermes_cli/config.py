"""
Configuration management for Hermes Agent.

Config files are stored in ~/.hermes/ for easy access:
- ~/.hermes/config.yaml  - All settings (model, toolsets, terminal, etc.)
- ~/.hermes/.env         - API keys and secrets

This module provides:
- hermes config          - Show current configuration
- hermes config edit     - Open config in editor
- hermes config set      - Set a specific value
- hermes config wizard   - Re-run setup wizard
"""

import copy
import logging
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from hermes_cli.secret_prompt import masked_secret_prompt

logger = logging.getLogger(__name__)

# Track which (config_path, mtime_ns, size) tuples we've already warned about
# so concurrent CLI/gateway loads of a broken config.yaml don't spam stderr
# every time. Cleared automatically when the file changes (different mtime).
_CONFIG_PARSE_WARNED: set = set()


def _warn_config_parse_failure(config_path: Path, exc: Exception) -> None:
    """Surface a config.yaml parse failure to user, log, and stderr.

    A YAML parse error in ``~/.hermes/config.yaml`` causes ``load_config()``
    to silently fall back to ``DEFAULT_CONFIG``, which means every user
    override (auxiliary providers, fallback chain, model overrides, etc.)
    is dropped. Before this helper that was a one-line ``print(...)`` that
    scrolled off-screen on the first invocation and was never seen again.

    Now: warn once per (path, mtime_ns, size) on stderr **and** in
    ``agent.log`` / ``errors.log`` at WARNING level so ``hermes logs``
    surfaces it. Re-warns automatically if the file changes (different
    mtime/size), so users editing the config see the next failure.
    """
    try:
        st = config_path.stat()
        key = (str(config_path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(config_path), 0, 0)
    if key in _CONFIG_PARSE_WARNED:
        return
    _CONFIG_PARSE_WARNED.add(key)

    msg = (
        f"Failed to parse {config_path}: {exc}. "
        f"Falling back to default config — every user override "
        f"(auxiliary providers, fallback chain, model settings) is being IGNORED. "
        f"Fix the YAML and restart."
    )
    logger.warning(msg)
    try:
        sys.stderr.write(f"⚠️  hermes config: {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

_IS_WINDOWS = platform.system() == "Windows"
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Env var names that influence how the next subprocess executes —
# never writable through ``save_env_value``. Anything that controls
# the loader, interpreter, shell, or replacement editor counts:
#
# * ``LD_PRELOAD`` / ``LD_LIBRARY_PATH`` / ``LD_AUDIT`` — Linux dynamic
#   loader. ``DYLD_*`` — macOS equivalent. Planting a path here means
#   the next ``subprocess.run([...])`` Hermes makes loads attacker code
#   before main().
# * ``PYTHONPATH`` / ``PYTHONHOME`` / ``PYTHONSTARTUP`` /
#   ``PYTHONUSERBASE`` — Python interpreter init. Hermes itself starts
#   from one of these on every restart.
# * ``NODE_OPTIONS`` / ``NODE_PATH`` — Node interpreter; affects npm,
#   ``hermes update``, the TUI build.
# * ``PATH`` — too broad to allow. The dashboard never needs to rewrite
#   the operator's PATH; if a tool can't be found, the fix is to add an
#   absolute path in the integration config, not to mutate PATH globally.
# * ``GIT_SSH_COMMAND`` / ``GIT_EXEC_PATH`` — git rewrites that fire
#   on every plugin install / ``hermes update``.
# * ``BROWSER`` / ``EDITOR`` / ``VISUAL`` / ``PAGER`` — commands the
#   shell or CLI invokes implicitly. Wrong values here = RCE on next
#   ``$EDITOR``.
# * ``SHELL`` — what subprocess uses with ``shell=True`` (we try to
#   avoid that, but defense in depth).
# * ``HERMES_HOME`` / ``HERMES_PROFILE`` / ``HERMES_CONFIG`` /
#   ``HERMES_ENV`` — Hermes runtime location flags. Writing these into
#   ``.env`` would relocate state in ways the user did not request from
#   the dashboard. ``config.yaml`` is the supported surface for these.
#
# IMPORTANT: ``HERMES_*`` overall is NOT blocked. Many legitimate
# integration credentials follow that prefix (HERMES_GEMINI_CLIENT_ID,
# HERMES_LANGFUSE_PUBLIC_KEY, HERMES_SPOTIFY_CLIENT_ID, ...). The
# denylist is name-by-name on purpose so the gate stays narrow and
# doesn't accidentally break provider setup wizards.
#
# This is enforced on *write* only — values already in ``.env`` (set
# by the operator out-of-band, or pre-existing) keep working. The
# point is that the dashboard's writable surface cannot escalate by
# planting them.
_ENV_VAR_NAME_DENYLIST: frozenset[str] = frozenset({
    # Loader / linker
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
    # Python
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
    "PYTHONEXECUTABLE", "PYTHONNOUSERSITE",
    # Node
    "NODE_OPTIONS", "NODE_PATH",
    # General
    "PATH", "SHELL", "BROWSER", "EDITOR", "VISUAL", "PAGER",
    # Git
    "GIT_SSH_COMMAND", "GIT_EXEC_PATH", "GIT_SHELL",
    # Hermes runtime location — never via dashboard env writer.
    # NOT a HERMES_* blanket: integration credentials (HERMES_GEMINI_*,
    # HERMES_LANGFUSE_*, HERMES_SPOTIFY_*, ...) ARE allowed.
    "HERMES_HOME", "HERMES_PROFILE", "HERMES_CONFIG", "HERMES_ENV",
})


def _reject_denylisted_env_var(key: str) -> None:
    """Raise if ``key`` is in :data:`_ENV_VAR_NAME_DENYLIST`.

    Centralised so both the regular and "secure" env writers share the
    same gate, and so the message is consistent for callers.
    """
    if key in _ENV_VAR_NAME_DENYLIST:
        raise ValueError(
            f"Environment variable {key!r} is on the writer denylist. "
            "Names that influence subprocess execution (LD_PRELOAD, "
            "PYTHONPATH, PATH, EDITOR, ...) or Hermes runtime location "
            "(HERMES_HOME, HERMES_PROFILE, ...) cannot be persisted via "
            "the env writer. If you really need this, edit "
            "~/.hermes/.env directly."
        )

_LAST_EXPANDED_CONFIG_BY_PATH: Dict[str, Any] = {}
# (path, mtime_ns, size) -> cached expanded config dict.
# load_config() returns a deepcopy of the cached value when the file
# hasn't changed since the last load, skipping yaml.safe_load +
# _deep_merge + _normalize_* + _expand_env_vars (~13 ms/call).
# save_config() + migrate_config() write via atomic_yaml_write which
# produces a fresh inode, so stat() sees a new mtime_ns and the next
# load repopulates automatically — no explicit invalidation hook.
_LOAD_CONFIG_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}
# (path, mtime_ns, size) -> cached raw yaml dict. Same pattern as
# _LOAD_CONFIG_CACHE but for read_raw_config() — used when callers want
# the user's on-disk values without defaults merged in.
_RAW_CONFIG_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}
# Serializes all config read/write paths. libyaml's C extension is not
# thread-safe for concurrent safe_load() on the same file, and multiple
# tool threads (approval.py, browser_tool.py, setup flows) hit
# load_config / read_raw_config / save_config from different threads
# during long agent runs. RLock (not Lock) because save_config internally
# calls read_raw_config. Also covers mutation of the module-level cache
# dicts above.
_CONFIG_LOCK = threading.RLock()
# Env var names written to .env that aren't in OPTIONAL_ENV_VARS
# (managed by setup/provider flows directly).
_EXTRA_ENV_KEYS = frozenset({
    "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
    "DISCORD_HOME_CHANNEL", "DISCORD_HOME_CHANNEL_NAME",
    "TELEGRAM_HOME_CHANNEL", "TELEGRAM_HOME_CHANNEL_NAME",
    "SLACK_HOME_CHANNEL", "SLACK_HOME_CHANNEL_NAME",
    "SIGNAL_ACCOUNT", "SIGNAL_HTTP_URL",
    "SIGNAL_ALLOWED_USERS", "SIGNAL_GROUP_ALLOWED_USERS",
    "SIGNAL_HOME_CHANNEL", "SIGNAL_HOME_CHANNEL_NAME",
    "SMS_HOME_CHANNEL", "SMS_HOME_CHANNEL_NAME",
    "DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET",
    "DINGTALK_HOME_CHANNEL", "DINGTALK_HOME_CHANNEL_NAME",
    "FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_ENCRYPT_KEY", "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_HOME_CHANNEL", "FEISHU_HOME_CHANNEL_NAME",
    "YUANBAO_HOME_CHANNEL", "YUANBAO_HOME_CHANNEL_NAME",
    "WECOM_BOT_ID", "WECOM_SECRET",
    "WECOM_CALLBACK_CORP_ID", "WECOM_CALLBACK_CORP_SECRET", "WECOM_CALLBACK_AGENT_ID",
    "WECOM_CALLBACK_TOKEN", "WECOM_CALLBACK_ENCODING_AES_KEY",
    "WECOM_CALLBACK_HOST", "WECOM_CALLBACK_PORT",
    "WECOM_HOME_CHANNEL", "WECOM_HOME_CHANNEL_NAME",
    "WEIXIN_ACCOUNT_ID", "WEIXIN_TOKEN", "WEIXIN_BASE_URL", "WEIXIN_CDN_BASE_URL",
    "WEIXIN_HOME_CHANNEL", "WEIXIN_HOME_CHANNEL_NAME", "WEIXIN_DM_POLICY", "WEIXIN_GROUP_POLICY",
    "WEIXIN_ALLOWED_USERS", "WEIXIN_GROUP_ALLOWED_USERS", "WEIXIN_ALLOW_ALL_USERS",
    "BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_PASSWORD",
    "BLUEBUBBLES_HOME_CHANNEL", "BLUEBUBBLES_HOME_CHANNEL_NAME",
    "QQ_APP_ID", "QQ_CLIENT_SECRET", "QQBOT_HOME_CHANNEL", "QQBOT_HOME_CHANNEL_NAME",
    "QQ_HOME_CHANNEL", "QQ_HOME_CHANNEL_NAME",  # legacy aliases (pre-rename, still read for back-compat)
    "QQ_ALLOWED_USERS", "QQ_GROUP_ALLOWED_USERS", "QQ_ALLOW_ALL_USERS", "QQ_MARKDOWN_SUPPORT",
    "QQ_STT_API_KEY", "QQ_STT_BASE_URL", "QQ_STT_MODEL",
    "IRC_SERVER", "IRC_PORT", "IRC_NICKNAME", "IRC_CHANNEL",
    "IRC_USE_TLS", "IRC_SERVER_PASSWORD", "IRC_NICKSERV_PASSWORD",
    "TERMINAL_ENV", "TERMINAL_SSH_KEY", "TERMINAL_SSH_PORT",
    "WHATSAPP_MODE", "WHATSAPP_ENABLED",
    "MATTERMOST_HOME_CHANNEL", "MATTERMOST_HOME_CHANNEL_NAME", "MATTERMOST_REPLY_MODE",
    "MATRIX_PASSWORD", "MATRIX_ENCRYPTION", "MATRIX_DEVICE_ID", "MATRIX_HOME_ROOM",
    "MATRIX_REQUIRE_MENTION", "MATRIX_FREE_RESPONSE_ROOMS", "MATRIX_AUTO_THREAD", "MATRIX_DM_AUTO_THREAD",
    "MATRIX_RECOVERY_KEY",
    # Langfuse observability plugin — optional tuning keys + standard SDK vars.
    # Activation is via plugins.enabled (opt-in through `hermes plugins enable
    # observability/langfuse` or `hermes tools → Langfuse`); credentials gate
    # the plugin at runtime.
    "HERMES_LANGFUSE_ENV",
    "HERMES_LANGFUSE_RELEASE",
    "HERMES_LANGFUSE_SAMPLE_RATE",
    "HERMES_LANGFUSE_MAX_CHARS",
    "HERMES_LANGFUSE_DEBUG",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
})
import yaml

from hermes_cli.colors import Colors, color
from hermes_cli.default_soul import DEFAULT_SOUL_MD


# =============================================================================
# Managed mode (NixOS declarative config)
# =============================================================================

_MANAGED_TRUE_VALUES = ("true", "1", "yes")
_MANAGED_SYSTEM_NAMES = {
    "brew": "Homebrew",
    "homebrew": "Homebrew",
    "nix": "NixOS",
    "nixos": "NixOS",
}


def get_managed_system() -> Optional[str]:
    """Return the package manager owning this install, if any."""
    raw = os.getenv("HERMES_MANAGED", "").strip()
    if raw:
        normalized = raw.lower()
        if normalized in _MANAGED_TRUE_VALUES:
            return "NixOS"
        return _MANAGED_SYSTEM_NAMES.get(normalized, raw)

    managed_marker = get_hermes_home() / ".managed"
    if managed_marker.exists():
        return "NixOS"
    return None


def is_managed() -> bool:
    """Check if Hermes is running in package-manager-managed mode.

    Two signals: the HERMES_MANAGED env var (set by the systemd service),
    or a .managed marker file in HERMES_HOME (set by the NixOS activation
    script, so interactive shells also see it).
    """
    return get_managed_system() is not None


_NIX_UPDATE_MSG = "Update your Nix flake input and rebuild (e.g. nix flake update, nixos-rebuild, or home-manager switch)"


def get_managed_update_command() -> Optional[str]:
    """Return the preferred upgrade command for a managed install."""
    managed_system = get_managed_system()
    if managed_system == "Homebrew":
        return "brew upgrade hermes-agent"
    if managed_system == "NixOS":
        return _NIX_UPDATE_MSG
    return None


def detect_install_method(project_root: Optional[Path] = None) -> str:
    """Detect how Hermes was installed: 'docker', 'nixos', 'homebrew', 'git', or 'pip'.

    Resolution order:
    1. Stamped ``~/.hermes/.install_method`` file (written by installers)
    2. HERMES_MANAGED env / .managed marker (NixOS, Homebrew)
    3. .git directory presence -> 'git'
    4. Fallback -> 'pip'

    Note: running inside a container is NOT treated as "docker" on its own.
    The two supported install paths both self-identify via the
    ``.install_method`` stamp (caught by step 1), so neither relies on
    container detection here:
      - the curl installer (scripts/install.sh, the README/website install
        command) git-clones the repo and stamps ``git``;
      - the published ``tchuekam/tchuekam-desktop`` image stamps ``docker``
        at boot via ``docker/stage2-hook.sh``.
    An unsupported manual install dropped into a container (no stamp) was
    wrongly classified as the published image by bare container detection,
    so ``hermes update`` bailed with "doesn't apply inside the Docker
    container". Without that fallback such installs fall through to the
    ``.git``/pip checks and behave like any off-path install. See issue #34397.
    """
    stamp = get_hermes_home() / ".install_method"
    try:
        method = stamp.read_text(encoding="utf-8").strip().lower()
        if method:
            return method
    except OSError:
        pass
    managed = get_managed_system()
    if managed:
        return managed.lower().replace(" ", "-")
    if project_root is None:
        project_root = Path(__file__).parent.parent.resolve()
    if (project_root / ".git").is_dir():
        return "git"
    return "pip"


def stamp_install_method(method: str) -> None:
    """Write the install method to ~/.hermes/.install_method."""
    stamp = get_hermes_home() / ".install_method"
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(method + "\n", encoding="utf-8")
    except OSError:
        pass


def is_uv_tool_install() -> bool:
    """Return True when the *running* Hermes lives in a ``uv tool`` layout.

    ``uv tool install hermes-agent`` places the install at
    ``.../uv/tools/hermes-agent/...`` (default ``~/.local/share/uv/tools``,
    or ``$UV_TOOL_DIR/...``). Such installs live outside any virtualenv, so
    ``uv pip install`` fails with ``No virtual environment found`` and the
    update path must use ``uv tool upgrade`` instead.

    Detection is intentionally restricted to properties of the running
    interpreter (``sys.prefix`` / ``sys.executable``). We deliberately do
    NOT consult ``uv tool list``: it would also return True when
    ``hermes-agent`` happens to be uv-tool-installed on the machine while
    the *active* Hermes is a regular pip/venv install, causing
    ``hermes update`` to upgrade the wrong copy. It would also block on a
    subprocess call (~seconds) just to compute a recommendation string.
    """
    def _has_uv_tool_marker(path: str) -> bool:
        norm = os.path.normpath(path).replace(os.sep, "/").lower()
        return "/uv/tools/hermes-agent/" in norm + "/"

    if _has_uv_tool_marker(sys.prefix):
        return True
    if _has_uv_tool_marker(sys.executable or ""):
        return True
    return False


def recommended_update_command_for_method(method: str) -> str:
    """Return the update command or guidance for a given install method."""
    if method == "nixos":
        return _NIX_UPDATE_MSG
    if method == "homebrew":
        return "brew upgrade hermes-agent"
    if method == "docker":
        return "docker pull tchuekam/tchuekam-desktop:latest"
    if method == "pip":
        if is_uv_tool_install():
            return "uv tool upgrade hermes-agent"
        import shutil
        if shutil.which("uv"):
            return "uv pip install --upgrade hermes-agent"
        return "pip install --upgrade hermes-agent"
    return "hermes update"


def recommended_update_command() -> str:
    """Return the best update command for the current installation."""
    managed_cmd = get_managed_update_command()
    if managed_cmd:
        return managed_cmd
    method = detect_install_method()
    return recommended_update_command_for_method(method)


# Long-form text for ``hermes update`` / ``--check`` when running inside the
# Docker image.  Surfaced by ``cmd_update`` and ``_cmd_update_check`` in
# hermes_cli/main.py; lives here so the wording stays consistent and we
# don't grow two slightly-different copies.
#
# Why this matters:
#   - The published image excludes ``.git`` (see .dockerignore), so the
#     git-based update path can never succeed inside the container.
#   - The pre-existing fallback message ("✗ Not a git repository. Please
#     reinstall: curl ... install.sh") is actively misleading inside Docker
#     — that script installs a *new* host-side Hermes, it doesn't update
#     the running container.
#   - The right action is ``docker pull`` + restart the container; this
#     helper spells that out, with notes on tag pinning and config
#     persistence so users don't get blindsided.
_DOCKER_UPDATE_MESSAGE = """\
✗ ``hermes update`` doesn't apply inside the Docker container.

Hermes Agent runs as a published image (tchuekam/tchuekam-desktop), not a
git checkout — the container has no working tree to pull into.  Update by
pulling a fresh image and restarting your container instead:

  docker pull tchuekam/tchuekam-desktop:latest
  # then restart whatever started the container, e.g.:
  docker compose up -d --force-recreate hermes-agent
  # or, for ad-hoc runs, exit the current container and `docker run` again

Verify the new version after restart:
  docker run --rm tchuekam/tchuekam-desktop:latest --version

Notes:
  • If you pinned a specific tag (e.g. ``:v0.14.0``) the ``:latest`` tag
    won't move your container — pull the newer tag you actually want, or
    switch to ``:latest`` / ``:main`` for rolling updates.  See available
    tags at https://hub.docker.com/r/tchuekam/tchuekam-desktop/tags
  • Your config and session history live under ``$HERMES_HOME`` (``/opt/data``
    in the container, typically bind-mounted from the host) and persist
    across image upgrades — re-pulling doesn't lose any state.
  • Running a fork?  Build your own image with this repo's ``Dockerfile``
    and replace the ``docker pull`` step with your build/push pipeline."""


def format_docker_update_message() -> str:
    """Return the user-facing message for ``hermes update`` inside Docker.

    Centralised so ``cmd_update`` (the apply path) and ``_cmd_update_check``
    (the dry-run path) share the same wording.  See ``_DOCKER_UPDATE_MESSAGE``
    above for the full rationale.
    """
    return _DOCKER_UPDATE_MESSAGE


def format_managed_message(action: str = "modify this Hermes installation") -> str:
    """Build a user-facing error for managed installs."""
    managed_system = get_managed_system() or "a package manager"
    raw = os.getenv("HERMES_MANAGED", "").strip().lower()

    if managed_system == "NixOS":
        env_hint = "true" if raw in _MANAGED_TRUE_VALUES else raw or "true"
        return (
            f"Cannot {action}: this Hermes installation is managed by NixOS "
            f"(HERMES_MANAGED={env_hint}).\n"
            "Edit services.hermes-agent.settings in your configuration.nix and run:\n"
            "  sudo nixos-rebuild switch"
        )

    if managed_system == "Homebrew":
        env_hint = raw or "homebrew"
        return (
            f"Cannot {action}: this Hermes installation is managed by Homebrew "
            f"(HERMES_MANAGED={env_hint}).\n"
            "Use:\n"
            "  brew upgrade hermes-agent"
        )

    return (
        f"Cannot {action}: this Hermes installation is managed by {managed_system}.\n"
        "Use your package manager to upgrade or reinstall Hermes."
    )

def managed_error(action: str = "modify configuration"):
    """Print user-friendly error for managed mode."""
    print(format_managed_message(action), file=sys.stderr)


# =============================================================================
# Container-aware CLI (NixOS container mode)
# =============================================================================

def get_container_exec_info() -> Optional[dict]:
    """Read container mode metadata from HERMES_HOME/.container-mode.

    Returns a dict with keys: backend, container_name, exec_user, hermes_bin
    or None if container mode is not active, we're already inside the
    container, or HERMES_DEV=1 is set.

    The .container-mode file is written by the NixOS activation script when
    container.enable = true. It tells the host CLI to exec into the container
    instead of running locally.
    """
    if os.environ.get("HERMES_DEV") == "1":
        return None

    from hermes_constants import is_container
    if is_container():
        return None

    container_mode_file = get_hermes_home() / ".container-mode"

    try:
        info = {}
        with open(container_mode_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    info[key.strip()] = value.strip()
    except FileNotFoundError:
        return None
    # All other exceptions (PermissionError, malformed data, etc.) propagate

    backend = info.get("backend", "docker")
    container_name = info.get("container_name", "hermes-agent")
    exec_user = info.get("exec_user", "hermes")
    hermes_bin = info.get("hermes_bin", "/data/current-package/bin/hermes")

    return {
        "backend": backend,
        "container_name": container_name,
        "exec_user": exec_user,
        "hermes_bin": hermes_bin,
    }


# =============================================================================
# Config paths
# =============================================================================

# Re-export from hermes_constants — canonical definition lives there.
from hermes_constants import get_hermes_home  # noqa: F811,E402
from utils import atomic_replace

def get_config_path() -> Path:
    """Get the main config file path."""
    return get_hermes_home() / "config.yaml"

def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"

def get_project_root() -> Path:
    """Get the project installation directory."""
    return Path(__file__).parent.parent.resolve()

def _resolve_hermes_uid_gid() -> tuple[Optional[int], Optional[int]]:
    """Read the HERMES_UID / HERMES_GID env vars set by Docker deployments.

    Docker containers running Hermes commonly set these to map the in-container
    user to a host user so volume-mounted state files end up with the right
    ownership. The entrypoint chowns the top-level HERMES_HOME once, but
    subdirectories created at runtime by ``ensure_hermes_home()`` (especially
    for profile namespaces under ``profiles/<name>/``) need the same chown
    or they land as ``root:root`` and block subsequent uid-mapped workers
    with ``PermissionError [Errno 13]``. See #34107.

    Returns ``(uid, gid)`` parsed from the env vars, or ``(None, None)``
    when either is missing/invalid. Returns ``(None, None)`` on Windows
    too (where chown is a no-op anyway).
    """
    if sys.platform == "win32":
        return None, None
    uid_str = os.environ.get("HERMES_UID", "").strip()
    gid_str = os.environ.get("HERMES_GID", "").strip()
    try:
        uid = int(uid_str) if uid_str else None
    except ValueError:
        uid = None
    try:
        gid = int(gid_str) if gid_str else None
    except ValueError:
        gid = None
    return uid, gid


def _chown_to_hermes_uid(path) -> None:
    """Chown ``path`` to ``HERMES_UID:HERMES_GID`` if those env vars are set.

    No-op when:
      - Either env var is unset/invalid
      - The current process isn't root (chown will EPERM — silently ignored)
      - On Windows (chown semantics don't apply)

    Used by :func:`_secure_dir` to keep ownership consistent across all
    directories created by :func:`ensure_hermes_home` on Docker deployments.
    See #34107.
    """
    uid, gid = _resolve_hermes_uid_gid()
    if uid is None and gid is None:
        return
    try:
        # os.chown with -1 means "don't change" for that field.
        os.chown(
            path,
            uid if uid is not None else -1,
            gid if gid is not None else -1,
        )
    except (OSError, AttributeError, NotImplementedError):
        # OSError covers EPERM (not running as root) and ENOENT (race),
        # both of which are non-fatal — the dir is still created and
        # the entrypoint's startup chown -R will fix it on next restart.
        pass


def _secure_dir(path):
    """Set directory to owner-only access (0700 by default). No-op on Windows.

    Skipped in managed mode — the NixOS module sets group-readable
    permissions (0750) so interactive users in the hermes group can
    share state with the gateway service.

    The mode can be overridden via the HERMES_HOME_MODE environment variable
    (e.g. HERMES_HOME_MODE=0701) for deployments where a web server (nginx,
    caddy, etc.) needs to traverse HERMES_HOME to reach a served subdirectory.
    The execute-only bit on a directory permits cd-through without exposing
    directory listings.

    Also applies ``HERMES_UID``/``HERMES_GID``-based ownership when those env
    vars are set (#34107 — Docker deployments need this so profile subdirs
    created at runtime by kanban workers don't land as root:root and block
    subsequent uid-mapped workers).
    """
    if is_managed():
        return
    try:
        mode_str = os.environ.get("HERMES_HOME_MODE", "").strip()
        mode = int(mode_str, 8) if mode_str else 0o700
    except ValueError:
        mode = 0o700
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass
    _chown_to_hermes_uid(path)


def _is_container() -> bool:
    """Detect if we're running inside a Docker/Podman/LXC container.

    When Hermes runs in a container with volume-mounted config files, forcing
    0o600 permissions breaks multi-process setups where the gateway and
    dashboard run as different UIDs or the volume mount requires broader
    permissions.
    """
    # Explicit opt-out
    if os.environ.get("HERMES_CONTAINER") or os.environ.get("HERMES_SKIP_CHMOD"):
        return True
    # Docker / Podman marker file
    if os.path.exists("/.dockerenv"):
        return True
    # LXC / cgroup-based detection
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            cgroup_content = f.read()
        if "docker" in cgroup_content or "lxc" in cgroup_content or "kubepods" in cgroup_content:
            return True
    except (OSError, IOError):
        pass
    return False


def _secure_file(path):
    """Set file to owner-only read/write (0600). No-op on Windows.

    Skipped in managed mode — the NixOS activation script sets
    group-readable permissions (0640) on config files.

    Skipped in containers — Docker/Podman volume mounts often need broader
    permissions.  Set HERMES_SKIP_CHMOD=1 to force-skip on other systems.
    """
    if is_managed() or _is_container():
        return
    try:
        if os.path.exists(str(path)):
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def _ensure_default_soul_md(home: Path) -> None:
    """Seed a default SOUL.md into HERMES_HOME if the user doesn't have one yet."""
    soul_path = home / "SOUL.md"
    if soul_path.exists():
        return
    soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    _secure_file(soul_path)


def ensure_hermes_home():
    """Ensure ~/.hermes directory structure exists with secure permissions.

    In managed mode (NixOS), dirs are created by the activation script with
    setgid + group-writable (2770). We skip mkdir and set umask(0o007) so
    any files created (e.g. SOUL.md) are group-writable (0660).
    """
    home = get_hermes_home()
    if is_managed():
        old_umask = os.umask(0o007)
        try:
            _ensure_hermes_home_managed(home)
        finally:
            os.umask(old_umask)
    else:
        home.mkdir(parents=True, exist_ok=True)
        _secure_dir(home)
        for subdir in (
            "cron", "sessions", "logs", "logs/curator", "memories",
            "pairing", "hooks", "image_cache", "audio_cache", "skills",
        ):
            d = home / subdir
            d.mkdir(parents=True, exist_ok=True)
            _secure_dir(d)
        _ensure_default_soul_md(home)


def _ensure_hermes_home_managed(home: Path):
    """Managed-mode variant: verify dirs exist (activation creates them), seed SOUL.md."""
    if not home.is_dir():
        raise RuntimeError(
            f"HERMES_HOME {home} does not exist. "
            "Run 'sudo nixos-rebuild switch' first."
        )
    for subdir in ("cron", "sessions", "logs", "memories"):
        d = home / subdir
        if not d.is_dir():
            raise RuntimeError(
                f"{d} does not exist. "
                "Run 'sudo nixos-rebuild switch' first."
            )
    # Curator reports dir is a sub-path of logs/; create it if missing.
    # In managed mode the activation script may not know about this subdir,
    # so we mkdir it ourselves (it's inside an already-secured logs/ dir).
    (home / "logs" / "curator").mkdir(parents=True, exist_ok=True)
    # Inside umask(0o007) scope — SOUL.md will be created as 0660
    _ensure_default_soul_md(home)


# =============================================================================
# Config loading/saving
# =============================================================================

DEFAULT_CONFIG = {
    "model": "",
    "providers": {},
    "fallback_providers": [],
    "credential_pool_strategies": {},
    "toolsets": ["hermes-cli"],
    "agent": {
        "max_turns": 90,
        # Inactivity timeout for gateway agent execution (seconds).
        # The agent can run indefinitely as long as it's actively calling
        # tools or receiving API responses.  Only fires when the agent has
        # been completely idle for this duration.  0 = unlimited.
        "gateway_timeout": 1800,
        # Graceful drain timeout for gateway stop/restart (seconds).
        # The gateway stops accepting new work, waits for running agents
        # to finish, then interrupts any remaining runs after the timeout.
        # 0 = no drain, interrupt immediately.
        #
        # 180s is calibrated for realistic in-flight agent turns: a typical
        # coding conversation mid-reasoning runs 60–150s per call, so a 60s
        # budget routinely interrupted legitimate work on /restart. Raise
        # further in config.yaml if you run very-long-reasoning models.
        "restart_drain_timeout": 180,
        # Max app-level retry attempts for API errors (connection drops,
        # provider timeouts, 5xx, etc.) before the agent surfaces the
        # failure.  The OpenAI SDK already does its own low-level retries
        # (max_retries=2 default) for transient network errors; this is
        # the Hermes-level retry loop that wraps the whole call.  Lower
        # this to 1 if you use fallback providers and want fast failover
        # on flaky primaries; raise it if you prefer to tolerate longer
        # provider hiccups on a single provider.
        "api_max_retries": 3,
        "service_tier": "",
        # Tool-use enforcement: injects system prompt guidance that tells the
        # model to actually call tools instead of describing intended actions.
        # Values: "auto" (default — applies to gpt/codex models), true/false
        # (force on/off for all models), or a list of model-name substrings
        # to match (e.g. ["gpt", "codex", "gemini", "qwen"]).
        "tool_use_enforcement": "auto",
        # Universal "finish the job" guidance — short prompt block applied to
        # all models that targets two cross-family failure modes: (1) stopping
        # after a stub instead of finishing the artifact, (2) fabricating
        # plausible-looking output when a real path is blocked.  Costs ~80
        # tokens in the cached system prompt.  Set False to disable globally.
        "task_completion_guidance": True,
        # Local-environment toolchain probe — surfaces Python/pip/uv/PEP-668
        # state in the system prompt when something non-default is detected
        # (e.g. python3 has no pip module, pip→python version mismatch, PEP
        # 668 enforcement without uv).  Costs zero tokens when the env is
        # clean (probe emits nothing).  Skipped for remote terminal backends
        # (docker/modal/ssh — they have their own probe).  Set False to
        # disable entirely.
        "environment_probe": True,
        # Embedder-supplied environment description appended to the system
        # prompt's environment-hints block. Lets a host that wraps Hermes
        # (sandbox runner, managed platform) explain the runtime environment
        # — proxy, credential handling, mount layout — without editing the
        # identity slot (SOUL.md). Empty by default. The HERMES_ENVIRONMENT_HINT
        # env var overrides this (build-time/container mechanism).
        "environment_hint": "",
        # Staged inactivity warning: send a warning to the user at this
        # threshold before escalating to a full timeout.  The warning fires
        # once per run and does not interrupt the agent.  0 = disable warning.
        "gateway_timeout_warning": 900,
        # Maximum time (seconds) the gateway will block an agent waiting for
        # a clarify-tool response from the user.  Hit this and the agent
        # unblocks with "[user did not respond within Xm]" so it can adapt
        # rather than pinning the running-agent guard forever.  CLI clarify
        # blocks indefinitely (input() is synchronous) and ignores this.
        "clarify_timeout": 600,
        # Periodic "still working" notification interval (seconds).
        # Sends a status message every N seconds so the user knows the
        # agent hasn't died during long tasks.  0 = disable notifications.
        # Lower values mean faster feedback on slow tasks but more chat
        # noise; 180s is a compromise that catches spinning weak-model runs
        # (60+ tool iterations with tiny output) before users assume the
        # bot is dead and /restart.
        "gateway_notify_interval": 180,
        # Freshness window for the gateway auto-continue note (seconds).
        # After a gateway crash/restart/SIGTERM mid-run, the next user
        # message gets a "[System note: your previous turn was
        # interrupted — process the unfinished tool result(s) first]"
        # prepended so the model picks up where it left off.  That's the
        # right behaviour while the interruption is fresh, but stale
        # markers (transcript last touched hours or days ago) can revive
        # an unrelated old task when the user's next message starts new
        # work.  This window is the max age of the last persisted
        # transcript row for which we still inject the continue note.
        # Default 3600s comfortably covers a long turn (gateway_timeout
        # default is 1800s) plus runtime slack.  Set to 0 to disable the
        # gate and restore pre-fix behaviour (always inject).
        "gateway_auto_continue_freshness": 3600,
        # How user-attached images are presented to the main model on each turn.
        #   "auto"   — attach natively when the active model reports
        #              supports_vision=True AND the user hasn't explicitly
        #              configured auxiliary.vision.provider.  Otherwise fall
        #              back to text (vision_analyze pre-analysis).
        #   "native" — always attach natively; non-vision models will either
        #              error at the provider or get a last-chance text fallback
        #              (see run_agent._prepare_messages_for_api).
        #   "text"   — always pre-analyze with vision_analyze and prepend the
        #              description as text; the main model never sees pixels.
        # Affects gateway platforms, the TUI, and CLI /attach.  vision_analyze
        # remains available as a tool regardless of this setting — the routing
        # only controls how inbound user images are presented.
        "image_input_mode": "auto",
        "disabled_toolsets": [],
    },
    
    "terminal": {
        "backend": "local",
        "modal_mode": "auto",
        "cwd": ".",  # Use current directory
        "timeout": 180,
        # Environment variables to pass through to sandboxed execution
        # (terminal and execute_code).  Skill-declared required_environment_variables
        # are passed through automatically; this list is for non-skill use cases.
        "env_passthrough": [],
        # Extra files to source in the login shell when building the
        # per-session environment snapshot.  Use this when tools like nvm,
        # pyenv, asdf, or custom PATH entries are registered by files that
        # a bash login shell would skip — most commonly ``~/.bashrc``
        # (bash doesn't source bashrc in non-interactive login mode) or
        # zsh-specific files like ``~/.zshrc`` / ``~/.zprofile``.
        # Paths support ``~`` / ``${VAR}``. Missing files are silently
        # skipped. When empty, Hermes auto-sources ``~/.profile``,
        # ``~/.bash_profile``, and ``~/.bashrc`` (in that order) if the
        # snapshot shell is bash (this is the ``auto_source_bashrc``
        # behaviour — disable with that key if you want strict login-only
        # semantics).
        "shell_init_files": [],
        # When true (default), Hermes sources the user's shell rc files
        # (``~/.profile``, ``~/.bash_profile``, ``~/.bashrc``) in the
        # login shell used to build the environment snapshot. This
        # captures PATH additions, shell functions, and aliases — which a
        # plain ``bash -l -c`` would otherwise miss because bash skips
        # bashrc in non-interactive login mode, and because a default
        # Debian/Ubuntu ``~/.bashrc`` short-circuits on non-interactive
        # sources. ``~/.profile`` and ``~/.bash_profile`` are tried first
        # because ``n`` / ``nvm`` / ``asdf`` installers typically write
        # their PATH exports there without an interactivity guard. Turn
        # this off if your rc files misbehave when sourced
        # non-interactively (e.g. one that hard-exits on TTY checks).
        "auto_source_bashrc": True,
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "docker_forward_env": [],
        # Explicit environment variables to set inside Docker containers.
        # Unlike docker_forward_env (which reads values from the host process),
        # docker_env lets you specify exact key-value pairs — useful when Hermes
        # runs as a systemd service without access to the user's shell environment.
        # Example: {"SSH_AUTH_SOCK": "/run/user/1000/ssh-agent.sock"}
        "docker_env": {},
        "singularity_image": "docker://nikolaik/python-nodejs:python3.11-nodejs20",
        "modal_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "daytona_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        # Container resource limits (docker, singularity, modal, daytona — ignored for local/ssh)
        "container_cpu": 1,
        "container_memory": 5120,       # MB (default 5GB)
        "container_disk": 51200,        # MB (default 50GB)
        "container_persistent": True,   # Persist filesystem across sessions
        # Docker volume mounts — share host directories with the container.
        # Each entry is "host_path:container_path" (standard Docker -v syntax).
        # Example:
        # ["/home/user/projects:/workspace/projects",
        #  "/home/user/.hermes/cache/documents:/output"]
        # For gateway MEDIA delivery, write inside Docker to /output/... and emit
        # the host-visible path in MEDIA:, not the container path.
        "docker_volumes": [],
        # Explicit opt-in: mount the host cwd into /workspace for Docker sessions.
        # Default off because passing host directories into a sandbox weakens isolation.
        "docker_mount_cwd_to_workspace": False,
        "docker_extra_args": [],        # Extra flags passed verbatim to docker run
        # Explicit opt-in: run the Docker container as the host user's uid:gid
        # (via `--user`).  When enabled, files written into bind-mounted dirs
        # (docker_volumes, the persistent workspace, or the auto-mounted cwd)
        # are owned by your host user instead of root, which avoids needing
        # `sudo chown` after container runs. Default off to preserve behavior
        # for images whose entrypoints expect to start as root (e.g. the
        # bundled Hermes image, which drops to the `hermes` user via
        # s6-setuidgid inside each supervised service).
        # When on, SETUID/SETGID caps are omitted from the container since
        # no privilege drop is needed.
        "docker_run_as_host_user": False,
        # Persistent shell — keep a long-lived bash shell across execute() calls
        # so cwd/env vars/shell variables survive between commands.
        # Enabled by default for non-local backends (SSH); local is always opt-in
        # via TERMINAL_LOCAL_PERSISTENT env var.
        "persistent_shell": True,
    },

    "web": {
        "backend": "",           # shared fallback — applies to both search and extract
        "search_backend": "",    # per-capability override for web_search (e.g. "searxng")
        "extract_backend": "",   # per-capability override for web_extract (e.g. "native")
    },

    "browser": {
        "inactivity_timeout": 120,
        "command_timeout": 30,  # Timeout for browser commands in seconds (screenshot, navigate, etc.)
        "record_sessions": False,  # Auto-record browser sessions as WebM videos
        "allow_private_urls": False,  # Allow navigating to private/internal IPs (localhost, 192.168.x.x, etc.)
        # Browser engine for local mode.  Passed as ``--engine <value>`` to
        # agent-browser v0.25.3+.
        # "auto"       — use Chrome (default, don't pass --engine at all)
        # "lightpanda" — use Lightpanda (1.3-5.8x faster navigation, no screenshots)
        # "chrome"     — explicitly request Chrome
        # Also settable via AGENT_BROWSER_ENGINE env var.
        "engine": "auto",
        "auto_local_for_private_urls": True,  # When a cloud provider is set, auto-spawn local Chromium for LAN/localhost URLs instead of sending them to the cloud
        "cdp_url": "",  # Optional persistent CDP endpoint for attaching to an existing Chromium/Chrome
        # CDP supervisor — dialog + frame detection via a persistent WebSocket.
        # Active only when a CDP-capable backend is attached (Browserbase or
        # local Chrome via /browser connect). See
        # website/docs/developer-guide/browser-supervisor.md.
        "dialog_policy": "must_respond",  # must_respond | auto_dismiss | auto_accept
        "dialog_timeout_s": 300,  # Safety auto-dismiss after N seconds under must_respond
        "camofox": {
            # When true, Hermes sends a stable profile-scoped userId to Camofox
            # so the server maps it to a persistent Firefox profile automatically.
            # When false (default), each session gets a random userId (ephemeral).
            "managed_persistence": False,
            # Optional externally managed Camofox identity. Useful when another
            # app owns the visible browser and Hermes should operate in it.
            "user_id": "",
            "session_key": "",
            # Rehydrate tab_id from Camofox before creating a new tab.
            "adopt_existing_tab": False,
            # Docker Camofox opens page URLs from inside the container. Enable
            # this to rewrite loopback page URLs (localhost/127.0.0.1/::1) to a
            # host alias while leaving CAMOFOX_URL itself unchanged.
            "rewrite_loopback_urls": False,
            "loopback_host_alias": "host.docker.internal",
        },
    },

    # Filesystem checkpoints — automatic snapshots before destructive file ops.
    # When enabled, the agent takes a snapshot of the working directory once
    # per conversation turn (on first write_file/patch call).  Use /rollback
    # to restore.
    #
    # Defaults changed in v2 (single shared shadow store, real pruning):
    #   - enabled: True -> False   (opt-in; most users never use /rollback)
    #   - max_snapshots: 50 -> 20  (now actually enforced via ref rewrite)
    #   - auto_prune:   False -> True (orphans/stale pruned automatically)
    # Opt in via ``hermes chat --checkpoints`` or set enabled=True here.
    "checkpoints": {
        "enabled": False,
        # Max checkpoints to keep per working directory.  Pre-v2 this only
        # limited the `/rollback` listing; v2 actually rewrites the ref and
        # garbage-collects older commits.
        "max_snapshots": 20,
        # Hard ceiling on total ``~/.hermes/checkpoints/`` size (MB).  When
        # exceeded, the oldest checkpoint per project is dropped in a
        # round-robin pass until total size falls under the cap.
        # 0 disables the size cap.
        "max_total_size_mb": 500,
        # Skip any single file larger than this when staging a checkpoint.
        # Prevents accidental snapshotting of datasets, model weights, and
        # other large generated assets.  0 disables the filter.
        "max_file_size_mb": 10,
        # Auto-maintenance: hermes sweeps the checkpoint base at startup
        # (at most once per ``min_interval_hours``) and:
        #   * deletes project entries whose workdir no longer exists (orphan)
        #   * deletes project entries whose last_touch is older than
        #     ``retention_days``
        #   * GCs the single shared store to reclaim unreachable objects
        #   * enforces ``max_total_size_mb`` across remaining projects
        #   * deletes ``legacy-*`` archives older than ``retention_days``
        "auto_prune": True,
        "retention_days": 7,
        "delete_orphans": True,
        "min_interval_hours": 24,
    },

    # Maximum characters returned by a single read_file call.  Reads that
    # exceed this are rejected with guidance to use offset+limit.
    # 100K chars ≈ 25–35K tokens across typical tokenisers.
    "file_read_max_chars": 100_000,

    # Tool-output truncation thresholds. When terminal output or a
    # single read_file page exceeds these limits, Hermes truncates the
    # payload sent to the model (keeping head + tail for terminal,
    # enforcing pagination for read_file). Tuning these trades context
    # footprint against how much raw output the model can see in one
    # shot. Ported from anomalyco/opencode PR #23770.
    #
    # - max_bytes:       terminal_tool output cap, in chars
    #                    (default 50_000 ≈ 12-15K tokens).
    # - max_lines:       read_file pagination cap — the maximum `limit`
    #                    a single read_file call can request before
    #                    being clamped (default 2000).
    # - max_line_length: per-line cap applied when read_file emits a
    #                    line-numbered view (default 2000 chars).
    "tool_output": {
        "max_bytes": 50_000,
        "max_lines": 2000,
        "max_line_length": 2000,
    },

    # Tool loop guardrails nudge models when they repeat failed or
    # non-progressing tool calls. Soft warnings are always-on by default;
    # hard stops are opt-in so interactive CLI/TUI sessions keep flowing.
    "tool_loop_guardrails": {
        "warnings_enabled": True,
        "hard_stop_enabled": False,
        "warn_after": {
            "exact_failure": 2,
            "same_tool_failure": 3,
            "idempotent_no_progress": 2,
        },
        "hard_stop_after": {
            "exact_failure": 5,
            "same_tool_failure": 8,
            "idempotent_no_progress": 5,
        },
    },

    "compression": {
        "enabled": True,
        "threshold": 0.50,            # compress when context usage exceeds this ratio
        "target_ratio": 0.20,         # fraction of threshold to preserve as recent tail
        "protect_last_n": 20,         # minimum recent messages to keep uncompressed
        "hygiene_hard_message_limit": 400,  # gateway session-hygiene force-compress threshold by message count
        "protect_first_n": 3,         # non-system head messages always preserved
                                      # verbatim, in ADDITION to the system prompt
                                      # (which is always implicitly protected). Set to
                                      # 0 for long-running rolling-compaction sessions
                                      # where you want nothing pinned except the
                                      # system prompt + rolling summary + recent tail.
        "abort_on_summary_failure": False,  # When True, auto-compression that fails
                                      # to generate a summary (aux LLM errored / returned
                                      # non-JSON / timed out) aborts entirely instead of
                                      # dropping the middle window with a static
                                      # "summary unavailable" placeholder.  Messages are
                                      # preserved unchanged and the session "freezes" at
                                      # its current size until the user runs /compress
                                      # (which bypasses the failure cooldown) or /new.
                                      # Default False matches historical behavior; set to
                                      # True if you'd rather pause than silently lose
                                      # context turns when your aux model is flaky.
    },

    # Anthropic prompt caching (Claude via OpenRouter or native Anthropic API).
    # cache_ttl must be "5m" or "1h" (Anthropic-supported tiers); other values are ignored.
    "prompt_caching": {
        "cache_ttl": "5m",
    },

    # OpenRouter-specific settings.
    # response_cache: enable OpenRouter response caching (X-OpenRouter-Cache header).
    #   When enabled, identical requests return cached responses for free (zero billing).
    #   This is separate from Anthropic prompt caching and works alongside it.
    #   See: https://openrouter.ai/docs/guides/features/response-caching
    # response_cache_ttl: how long cached responses remain valid, in seconds (1-86400).
    #   Default 300 (5 minutes). Only used when response_cache is enabled.
    # min_coding_score: knob for the openrouter/pareto-code router (0.0-1.0).
    #   Only applied when model.model is "openrouter/pareto-code". Higher
    #   values route to stronger (more expensive) coders; lower values open
    #   up cheaper, faster options. Default 0.65 lands on the mid-tier
    #   coder on the current Pareto frontier. Empty string = let OpenRouter
    #   pick the strongest available coder (router's documented default
    #   when the plugins block is omitted).
    #   See: https://openrouter.ai/docs/guides/routing/routers/pareto-router
    "openrouter": {
        "response_cache": True,
        "response_cache_ttl": 300,
        "min_coding_score": 0.65,
    },

    # AWS Bedrock provider configuration.
    # Only used when model.provider is "bedrock".
    "bedrock": {
        "region": "",  # AWS region for Bedrock API calls (empty = AWS_REGION env var → us-east-1)
        "discovery": {
            "enabled": True,           # Auto-discover models via ListFoundationModels
            "provider_filter": [],     # Only show models from these providers (e.g. ["anthropic", "amazon"])
            "refresh_interval": 3600,  # Cache discovery results for this many seconds
        },
        "guardrail": {
            # Amazon Bedrock Guardrails — content filtering and safety policies.
            # Create a guardrail in the Bedrock console, then set the ID and version here.
            # See: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html
            "guardrail_identifier": "",  # e.g. "abc123def456"
            "guardrail_version": "",     # e.g. "1" or "DRAFT"
            "stream_processing_mode": "async",  # "sync" or "async"
            "trace": "disabled",         # "enabled", "disabled", or "enabled_full"
        },
    },

    # Auxiliary model config — provider:model for each side task.
    # Format: provider is the provider name, model is the model slug.
    # "auto" for provider = auto-detect best available provider.
    # Empty model = use provider's default auxiliary model.
    # All tasks fall back to openrouter:google/gemini-3-flash-preview if
    # the configured provider is unavailable.
    #
    # extra_body: forwarded verbatim as request body fields on every aux call
    # for that task. Use this to set provider-specific knobs (independent of
    # main-agent settings). On OpenRouter you can set provider routing prefs
    # and the Pareto Code coding-score floor here. Example:
    #
    #   auxiliary:
    #     compression:
    #       provider: openrouter
    #       model: openrouter/pareto-code
    #       extra_body:
    #         provider:           # OpenRouter provider routing
    #           order: [anthropic, google]
    #           sort: throughput  # or price | latency
    #         plugins:            # OpenRouter Pareto Code router
    #           - id: pareto-router
    #             min_coding_score: 0.5
    #
    # Each aux task is independent — main-agent provider_routing and
    # openrouter.min_coding_score do NOT propagate to aux calls by design.
    "auxiliary": {
        "vision": {
            "provider": "auto",    # auto | openrouter | nous | codex | custom
            "model": "",           # e.g. "google/gemini-2.5-flash", "gpt-4o"
            "base_url": "",        # direct OpenAI-compatible endpoint (takes precedence over provider)
            "api_key": "",         # API key for base_url (falls back to OPENAI_API_KEY)
            "timeout": 120,        # seconds — LLM API call timeout; vision payloads need generous timeout
            "extra_body": {},      # OpenAI-compatible provider-specific request fields
            "download_timeout": 30,  # seconds — image HTTP download timeout; increase for slow connections
        },
        "web_extract": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 360,        # seconds (6min) — per-attempt LLM summarization timeout; increase for slow local models
            "extra_body": {},
        },
        "compression": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 120,        # seconds — compression summarises large contexts; increase for local models
            "extra_body": {},
        },
        # Note: session_search no longer uses an auxiliary LLM (PR #27590 —
        # single-shape tool returns DB content directly). The old
        # ``auxiliary.session_search.*`` block was removed here. Existing
        # values in user config.yaml files are harmless leftovers and ignored.
        "skills_hub": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
            "extra_body": {},
        },
        "approval": {
            "provider": "auto",
            "model": "",           # fast/cheap model recommended (e.g. gemini-flash, haiku)
            "base_url": "",
            "api_key": "",
            "timeout": 30,
            "extra_body": {},
        },
        "mcp": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
            "extra_body": {},
        },
        "title_generation": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
            "extra_body": {},
        },
        # Triage specifier — flesh out a rough one-liner in the Kanban
        # Triage column into a concrete spec, then promote it to ``todo``.
        # Invoked by ``hermes kanban specify`` (single id or --all). Set a
        # cheap, capable model here (gemini-flash works well); the main
        # model is overkill for short spec expansion.
        "triage_specifier": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 120,
            "extra_body": {},
        },
        # Kanban decomposer — decomposes a triage task into a graph of
        # child tasks routed to specialist profiles by description.
        # Invoked by ``hermes kanban decompose`` and the kanban
        # auto-decompose dispatcher tick. Returns a JSON task graph;
        # uses more tokens than the specifier so allow more headroom.
        "kanban_decomposer": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 180,
            "extra_body": {},
        },
        # Profile describer — auto-generates a 1-2 sentence description
        # of what a profile is good at. Invoked by
        # ``hermes profile describe <name> --auto`` and the dashboard's
        # auto-generate button. Short, cheap call.
        "profile_describer": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 60,
            "extra_body": {},
        },
        # Curator — skill-usage review fork. Timeout is generous because the
        # review pass can take several minutes on reasoning models (umbrella
        # building over hundreds of candidate skills). "auto" = use main chat
        # model; override via `hermes model` → auxiliary → Curator to route
        # to a cheaper aux model (e.g. openrouter google/gemini-3-flash-preview).
        "curator": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 600,
            "extra_body": {},
        },
    },
    
    "display": {
        "compact": False,
        "personality": "",
        "resume_display": "full",
        # Recap tuning for /resume and startup resume. The defaults match the
        # historical hardcoded values; expose them as config so power users can
        # widen or tighten the snapshot to taste.
        "resume_exchanges": 10,            # max user+assistant pairs to show
        "resume_max_user_chars": 300,      # truncate user message text
        "resume_max_assistant_chars": 200, # truncate non-last assistant text
        "resume_max_assistant_lines": 3,   # truncate non-last assistant lines
        # When True (default), assistant entries that are *only* tool calls
        # (no visible text) are skipped in the recap. This prevents the recap
        # from being dominated by `[2 tool calls: terminal, read_file]` lines
        # when an exchange was tool-heavy. Set False to restore the legacy
        # behavior of showing tool-call summaries inline.
        "resume_skip_tool_only": True,
        "busy_input_mode": "interrupt",  # interrupt | queue | steer
        # Which interface bare `hermes` (and `hermes chat`) launches by default:
        #   "cli" — the classic prompt_toolkit REPL (default, preserves prior behavior)
        #   "tui" — the modern Ink TUI (same as passing `--tui`)
        # Explicit flags always win over this setting: `--cli` forces the classic
        # REPL and `--tui` (or HERMES_TUI=1) forces the TUI regardless of config.
        "interface": "cli",
        # When true, `hermes --tui` auto-resumes the most recent human-
        # facing session on launch instead of forging a fresh one.
        # Mirrors `hermes -c` muscle memory.  Default off so existing
        # users aren't surprised.  HERMES_TUI_RESUME=<id> always wins.
        "tui_auto_resume_recent": False,
        # When true (default), `hermes --tui` drops a one-time hint
        # ("subagents working · /agents to watch live") the first time a turn
        # starts delegating, nudging the user toward the live spawn-tree
        # dashboard. Set false to suppress the hint.
        "tui_agents_nudge": True,
        "bell_on_complete": False,
        "show_reasoning": False,
        "streaming": False,
        "timestamps": False,      # Show [HH:MM] on user and assistant labels
        "final_response_markdown": "strip",  # render | strip | raw
        # Preserve recent classic CLI output across Ctrl+L, /redraw, and
        # terminal resize full-screen clears. Disable if a terminal emulator
        # behaves badly with replayed scrollback.
        "persistent_output": True,
        "persistent_output_max_lines": 200,
        "inline_diffs": True,     # Show inline diff previews for write actions (write_file, patch, skill_manage)
        # File-mutation verifier footer.  When true (default), the agent
        # appends a one-line advisory to its final response whenever a
        # write_file / patch call failed during the turn and was never
        # superseded by a successful write to the same path.  This catches
        # the "batch of parallel patches, half fail, model claims success"
        # class of over-claim that otherwise forces users to run
        # `git status` to verify edits landed.  Set false to suppress.
        "file_mutation_verifier": True,
        # Turn-completion explainer.  When true (default), the agent appends a
        # one-line explanation to its final response whenever a turn ends
        # abnormally with no usable reply — empty content after retries, a
        # partial/truncated stream, a still-pending tool result, or an
        # iteration/budget limit.  Replaces the bare "(empty)" sentinel so the
        # failure isn't silent from the UI's perspective.  Set false to suppress.
        "turn_completion_explainer": True,
        "show_cost": False,       # Show $ cost in the status bar (off by default)
        "skin": "default",
        # UI language for static user-facing messages (approval prompts, a
        # handful of gateway slash-command replies).  Does NOT affect agent
        # responses, log lines, tool outputs, or slash-command descriptions.
        # Supported: en, zh, ja, de, es, fr, tr, uk.  Unknown values fall back to en.
        "language": "en",
        # TUI busy indicator style: kaomoji (default), emoji, unicode (braille
        # spinner), or ascii.  Live-swappable via `/indicator <style>`.
        "tui_status_indicator": "kaomoji",
        "user_message_preview": {  # CLI: how many submitted user-message lines to echo back in scrollback
            "first_lines": 2,
            "last_lines": 2,
        },
        "interim_assistant_messages": True,  # Gateway: show natural mid-turn assistant status messages
        "tool_progress_command": False,  # Enable /verbose command in messaging gateway
        "tool_progress_overrides": {},  # DEPRECATED — use display.platforms instead
        "tool_preview_length": 0,  # Max chars for tool call previews (0 = no limit, show full paths/commands)
        # Auto-delete system-notice replies (e.g. "✨ New session started!",
        # "♻ Restarting gateway…", "⚡ Stopped…") after N seconds on platforms
        # that support message deletion (currently Telegram; other platforms
        # ignore and leave the message in place).  Only affects slash-command
        # replies wrapped with gateway.platforms.base.EphemeralReply — agent
        # responses and content messages are never touched.  Default 0
        # (disabled) preserves prior behavior.
        "ephemeral_system_ttl": 0,
        # Per-platform display/streaming overrides. Each key is a gateway
        # platform ("telegram", "discord", "slack", …) mapping to a dict of
        # display settings that override the global value for that platform
        # only. A setting left unset here falls through to the global default.
        #
        # Shipped defaults encode the streaming experience that works best
        # per platform:
        #   - Telegram has native animated draft streaming (sendMessageDraft),
        #     which is smooth, so streaming is on by default there.
        #   - Discord/Slack/etc. only have edit-based streaming (repeated
        #     editMessage), which flickers and is noticeably jankier, so
        #     streaming is off by default there.
        # These are gap-fillers: a user who explicitly sets, e.g.,
        # display.platforms.discord.streaming: true keeps their value
        # (config deep-merge has user values win over defaults). The global
        # streaming.enabled master switch still gates everything — these
        # per-platform flags only take effect once streaming is enabled.
        "platforms": {
            "telegram": {"streaming": True},
            "discord": {"streaming": False},
        },
        # Gateway runtime-metadata footer appended to the FINAL message of a turn
        # (disabled by default to keep replies minimal). When enabled, renders
        # e.g. `model · 68% · ~/projects/hermes`. Per-platform overrides go under
        # display.platforms.<platform>.runtime_footer.
        "runtime_footer": {
            "enabled": False,
            "fields": ["model", "context_pct", "cwd"],  # Order shown; drop any to hide
        },
        "copy_shortcut": "auto",  # "auto" (platform default) | "ctrl_c" | "ctrl_shift_c" | "disabled"
    },

    # Web dashboard settings
    "dashboard": {
        "theme": "default",  # Dashboard visual theme: "default", "midnight", "ember", "mono", "cyberpunk", "rose"
        # Hide the token/cost analytics surfaces (Analytics page, token bars and
        # cost figures on the Models page) by default.  The numbers shown there
        # are a local debug estimate: they only count successful main-agent
        # responses with a usable ``response.usage``, and silently exclude every
        # auxiliary call (context compression, title generation, vision,
        # session search, web extract, smart approval, MCP routing, plugin LLM
        # access) plus provider-side retries, fallback attempts, and any call
        # whose usage block didn't come back.  Cache writes are also missing
        # from the API response.  On models with heavy auxiliary traffic
        # (Kimi K2.6, MiniMax M2.7) the local total can be 10x-100x lower than
        # the provider bill, which is worse than hiding the numbers entirely
        # because they look precise enough to compare against the provider.
        # Set this to True to re-enable the surfaces with the understanding
        # that the numbers are a local lower-bound estimate, not billing.
        "show_token_analytics": False,
        # OAuth gate configuration (engaged when ``--host`` is set and
        # ``--insecure`` is not). The bundled Nous Portal plugin reads
        # both keys at startup; they are the canonical surface for these
        # settings. Each can be overridden by an environment variable —
        # ``HERMES_DASHBOARD_OAUTH_CLIENT_ID`` and
        # ``HERMES_DASHBOARD_PORTAL_URL`` respectively — and the env var
        # wins when set to a non-empty value. The override path is what
        # Fly.io's platform-secret injection uses to push the per-deploy
        # client_id at provisioning time without operators needing to
        # touch config.yaml. Local dev / non-Fly deploys can set either
        # surface; missing values fall through to the plugin's defaults
        # (no provider registered when ``client_id`` is empty;
        # ``portal_url`` defaults to https://portal.nousresearch.com).
        "oauth": {
            "client_id": "",  # agent:{instance_id} — Portal provisions this
            "portal_url": "",  # blank → use plugin default (production Portal)
        },
        # Public URL override (env: ``HERMES_DASHBOARD_PUBLIC_URL``).
        # When set, this is the complete authority — scheme + host +
        # optional path prefix (e.g. ``https://example.com/hermes``) —
        # the OAuth ``redirect_uri`` is built from. Set this for deploys
        # behind reverse proxies that don't reliably forward
        # ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` / ``X-Forwarded-Prefix``
        # (manual nginx setups, on-prem ingresses, custom-domain Fly
        # deploys without proper proxy headers). When set,
        # ``X-Forwarded-Prefix`` is IGNORED on the OAuth path because
        # the operator has declared the public URL — we no longer need
        # to guess from proxy headers, and stacking the prefix on top
        # would double-prefix the common case where the prefix is
        # already baked into ``public_url``. Leave empty to use the
        # existing proxy-header reconstruction (the default).
        #
        # Validation: rejects values without ``http(s)://`` scheme or
        # without a host, and any string containing quote / angle /
        # whitespace / control characters. A malformed value silently
        # falls through to request reconstruction rather than breaking
        # the login flow.
        "public_url": "",
    },

    # Privacy settings
    "privacy": {
        "redact_pii": False,  # When True, hash user IDs and strip phone numbers from LLM context
    },
    
    # Text-to-speech configuration
    # Each provider supports an optional `max_text_length:` override for the
    # per-request input-character cap. Omit it to use the provider's documented
    # limit (OpenAI 4096, xAI 15000, MiniMax 10000, ElevenLabs 5k-40k model-aware,
    # Gemini 5000, Edge 5000, Mistral 4000, NeuTTS/KittenTTS 2000).
    "tts": {
        "provider": "edge",  # "edge" (free) | "elevenlabs" (premium) | "openai" | "xai" | "minimax" | "mistral" | "gemini" | "neutts" (local) | "kittentts" (local) | "piper" (local)
        "edge": {
            "voice": "en-US-AriaNeural",
            # Popular: AriaNeural, JennyNeural, AndrewNeural, BrianNeural, SoniaNeural
        },
        "elevenlabs": {
            "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam
            "model_id": "eleven_multilingual_v2",
        },
        "openai": {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            # Voices: alloy, echo, fable, onyx, nova, shimmer
        },
        "xai": {
            "voice_id": "eve",  # or custom voice ID — see https://docs.x.ai/developers/model-capabilities/audio/custom-voices
            "language": "en",
            "sample_rate": 24000,
            "bit_rate": 128000,
        },
        "mistral": {
            "model": "voxtral-mini-tts-2603",
            "voice_id": "c69964a6-ab8b-4f8a-9465-ec0925096ec8",  # Paul - Neutral
        },
        "neutts": {
            "ref_audio": "",  # Path to reference voice audio (empty = bundled default)
            "ref_text": "",   # Path to reference voice transcript (empty = bundled default)
            "model": "neuphonic/neutts-air-q4-gguf",  # HuggingFace model repo
            "device": "cpu",  # cpu, cuda, or mps
        },
        "piper": {
            # Voice name (e.g. "en_US-lessac-medium") downloaded on first
            # use, OR an absolute path to a pre-downloaded .onnx file.
            # Full voice list: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md
            "voice": "en_US-lessac-medium",
            # "voices_dir": "",        # Override voice cache dir; default = ~/.hermes/cache/piper-voices/
            # "use_cuda": False,       # Requires onnxruntime-gpu
            # "length_scale": 1.0,     # 2.0 = twice as slow
            # "noise_scale": 0.667,
            # "noise_w_scale": 0.8,
            # "volume": 1.0,
            # "normalize_audio": True,
        },
        "kokoro": {
            "voice": "bm_george",       # English JARVIS-style default voice
            "voice_fr": "ff_siwis",     # French offline neural voice
            "speed": 1.05,
            "models_dir": "",           # Optional override; defaults to ~/.hermes/models/kokoro
        },
    },
    
    "stt": {
        "enabled": True,
        "provider": "local",  # "local" (free, faster-whisper) | "groq" | "openai" (Whisper API) | "mistral" (Voxtral Transcribe) | "elevenlabs" (Scribe)
        "local": {
            "model": "base",  # tiny, base, small, medium, large-v3
            "language": "",  # auto-detect by default; set to "en", "es", "fr", etc. to force
        },
        "openai": {
            "model": "whisper-1",  # whisper-1, gpt-4o-mini-transcribe, gpt-4o-transcribe
        },
        "mistral": {
            "model": "voxtral-mini-latest",  # voxtral-mini-latest, voxtral-mini-2602
        },
        "elevenlabs": {
            "model_id": "scribe_v2",  # scribe_v2, scribe_v1
            "language_code": "",  # auto-detect by default; set to "eng", "spa", "fra", etc. to force
            "tag_audio_events": False,
            "diarize": False,
        },
    },

    "voice": {
        "record_key": "ctrl+b",
        "max_recording_seconds": 120,
        "auto_tts": False,
        "beep_enabled": True,         # Play record start/stop beeps in CLI voice mode
        "silence_threshold": 200,     # RMS below this = silence (0-32767)
        "silence_duration": 3.0,      # Seconds of silence before auto-stop
    },
    
    "human_delay": {
        "mode": "off",
        "min_ms": 800,
        "max_ms": 2500,
    },
    
    # Context engine -- controls how the context window is managed when
    # approaching the model's token limit.
    # "compressor" = built-in lossy summarization (default).
    # Set to a plugin name to activate an alternative engine (e.g. "lcm"
    # for Lossless Context Management).  The engine must be installed as
    # a plugin in plugins/context_engine/<name>/ or ~/.hermes/plugins/.
    "context": {
        "engine": "compressor",
    },

    # Persistent memory -- bounded curated memory injected into system prompt
    "memory": {
        "memory_enabled": True,
        "user_profile_enabled": True,
        "memory_char_limit": 2200,   # ~800 tokens at 2.75 chars/token
        "user_char_limit": 1375,     # ~500 tokens at 2.75 chars/token
        # External memory provider plugin (empty = built-in only).
        # Set to a provider name to activate: "openviking", "mem0",
        # "hindsight", "holographic", "retaindb", "byterover".
        # Only ONE external provider is allowed at a time.
        "provider": "",
    },

    # Subagent delegation — override the provider:model used by delegate_task
    # so child agents can run on a different (cheaper/faster) provider and model.
    # Uses the same runtime provider resolution as CLI/gateway startup, so all
    # configured providers (OpenRouter, Nous, Z.ai, Kimi, etc.) are supported.
    "delegation": {
        "model": "",       # e.g. "google/gemini-3-flash-preview" (empty = inherit parent model)
        "provider": "",    # e.g. "openrouter" (empty = inherit parent provider + credentials)
        "base_url": "",    # direct OpenAI-compatible endpoint for subagents
        "api_key": "",     # API key for delegation.base_url (falls back to OPENAI_API_KEY)
        "api_mode": "",    # wire protocol for delegation.base_url: "chat_completions",
                           # "codex_responses", or "anthropic_messages". Empty = auto-detect
                           # from URL (e.g. /anthropic suffix → anthropic_messages). Set this
                           # explicitly for non-standard endpoints the heuristic can't detect.
        # When delegate_task narrows child toolsets explicitly, preserve any
        # MCP toolsets the parent already has enabled. On by default so
        # narrowing (e.g. toolsets=["web","browser"]) expresses "I want these
        # extras" without silently stripping MCP tools the parent already has.
        # Set to false for strict intersection.
        "inherit_mcp_toolsets": True,
        "max_iterations": 50,  # per-subagent iteration cap (each subagent gets its own budget,
                               # independent of the parent's max_iterations)
        "child_timeout_seconds": 600,  # wall-clock timeout for each child agent (floor 30s,
                                       # no ceiling). High-reasoning models on large tasks
                                       # (e.g. gpt-5.5 xhigh, opus-4.6) need generous budgets;
                                       # raise if children time out before producing output.
        "reasoning_effort": "",  # reasoning effort for subagents: "xhigh", "high", "medium",
                                 # "low", "minimal", "none" (empty = inherit parent's level)
        "max_concurrent_children": 3,  # max parallel children per batch; floor of 1 enforced, no ceiling
        # Orchestrator role controls (see tools/delegate_tool.py:_get_max_spawn_depth
        # and _get_orchestrator_enabled).  Values are clamped to [1, 3] with a
        # warning log if out of range.
        "max_spawn_depth": 1,        # depth cap (1 = flat [default], 2 = orchestrator→leaf, 3 = three-level)
        "orchestrator_enabled": True,  # kill switch for role="orchestrator"
        # When a subagent hits a dangerous-command approval prompt, the parent's
        # prompt_toolkit TUI owns stdin — a thread-local input() call from the
        # subagent worker would deadlock the parent UI. To avoid the deadlock,
        # subagent threads ALWAYS resolve approvals non-interactively:
        #   false (default) → auto-deny with a logger.warning audit line (safe)
        #   true             → auto-approve "once" with a logger.warning audit line
        # Flip to true only if you trust delegated work to run dangerous cmds
        # without human review (cron pipelines, batch automation, etc.).
        "subagent_auto_approve": False,
    },

    # Ephemeral prefill messages file — JSON list of {role, content} dicts
    # injected at the start of every API call for few-shot priming.
    # Never saved to sessions, logs, or trajectories.
    "prefill_messages_file": "",

    # Goals — persistent cross-turn goals (Ralph-style loop).
    # After every turn, a lightweight judge call asks the auxiliary model
    # whether the active /goal is satisfied by the assistant's last
    # response. If not, Hermes feeds a continuation prompt back into the
    # same session and keeps working until the goal is done, the turn
    # budget is exhausted, or the user pauses/clears it. Judge failures
    # fail OPEN (continue) so a flaky judge never wedges progress — the
    # turn budget is the real backstop.
    "goals": {
        # Max continuation turns before Hermes auto-pauses the goal and
        # asks the user to /goal resume. Protects against judge false
        # negatives (goal actually done but judge says continue) and
        # unbounded model spend on fuzzy / unachievable goals.
        "max_turns": 20,
    },

    # Skills — external skill directories for sharing skills across tools/agents.
    # Each path is expanded (~, ${VAR}) and resolved.  Read-only — skill creation
    # always goes to ~/.hermes/skills/.
    "skills": {
        "external_dirs": [],   # e.g. ["~/.agents/skills", "/shared/team-skills"]
        # Substitute ${HERMES_SKILL_DIR} and ${HERMES_SESSION_ID} in SKILL.md
        # content with the absolute skill directory and the active session id
        # before the agent sees it.  Lets skill authors reference bundled
        # scripts without the agent having to join paths.
        "template_vars": True,
        # Pre-execute inline shell snippets written as !`cmd` in SKILL.md
        # body.  Their stdout is inlined into the skill message before the
        # agent reads it, so skills can inject dynamic context (dates, git
        # state, detected tool versions, …).  Off by default because any
        # content from the skill author runs on the host without approval;
        # only enable for skill sources you trust.
        "inline_shell": False,
        # Timeout (seconds) for each !`cmd` snippet when inline_shell is on.
        "inline_shell_timeout": 10,
        # Run the keyword/pattern security scanner on skills the agent
        # writes via skill_manage (create/edit/patch).  Off by default
        # because the agent can already execute the same code paths via
        # terminal() with no gate, so the scan adds friction (blocks
        # skills that mention risky keywords in prose) without meaningful
        # security.  Turn on if you want the belt-and-suspenders — a
        # dangerous verdict will then surface as a tool error to the
        # agent, which can retry with the flagged content removed.
        # External hub installs (trusted/community sources) are always
        # scanned regardless of this setting.
        "guard_agent_created": False,
    },

    # Curator — background skill maintenance.
    #
    # Periodically reviews AGENT-CREATED skills (never bundled or
    # hub-installed) and keeps the collection tidy: marks long-unused skills
    # as stale, archives genuinely obsolete ones (archive only, never
    # deletes), and spawns a forked aux-model agent to consolidate overlaps
    # and patch drift. Runs inactivity-triggered from session start — no
    # cron daemon.
    #
    # See `hermes curator status` for the last run summary.
    "curator": {
        "enabled": True,
        # How long to wait between curator runs (hours).  Default: 7 days.
        "interval_hours": 24 * 7,
        # Only run when the agent has been idle at least this long (hours).
        "min_idle_hours": 2,
        # Mark a skill as "stale" after this many days without use.
        "stale_after_days": 30,
        # Archive a skill (move to skills/.archive/) after this many days
        # without use. Archived skills are recoverable — no auto-deletion.
        "archive_after_days": 90,
        # Also prune (archive) bundled built-in skills after the inactivity
        # period, not just agent-created ones. ON by default. Built-ins are
        # normally restored on every `hermes update`, so pruning them only
        # sticks because a suppression list tells the re-seeder to leave them
        # archived. Hub-installed skills are NEVER pruned here — they have an
        # external upstream owner. Built-ins accrue usage telemetry and their
        # inactivity clock starts the first time the curator sees them, so a
        # long-unused built-in is archived only after archive_after_days of
        # genuine non-use (never a mass-prune on the first run). Set to false
        # to keep all bundled built-ins permanently.
        "prune_builtins": True,
        # Pre-run backup: before every real curator pass (dry-run is
        # skipped), snapshot ~/.hermes/skills/ into
        # ~/.hermes/skills/.curator_backups/<utc-iso>/skills.tar.gz so the
        # user can roll back with `hermes curator rollback`.
        "backup": {
            "enabled": True,
            "keep": 5,  # retain last N regular snapshots
        },
    },

    # Honcho AI-native memory -- reads ~/.honcho/config.json as single source of truth.
    # This section is only needed for hermes-specific overrides; everything else
    # (apiKey, workspace, peerName, sessions, enabled) comes from the global config.
    "honcho": {},

    # IANA timezone (e.g. "Asia/Kolkata", "America/New_York").
    # Empty string means use server-local time.
    "timezone": "",

    # Slack platform settings (gateway mode)
    "slack": {
        "require_mention": True,       # Require @mention to respond in channels
        "free_response_channels": "",  # Comma-separated channel IDs where bot responds without mention
        "allowed_channels": "",        # If set, bot ONLY responds in these channel IDs (whitelist)
        "channel_prompts": {},         # Per-channel ephemeral system prompts
    },

    # Discord platform settings (gateway mode)
    "discord": {
        "require_mention": True,       # Require @mention to respond in server channels
        "free_response_channels": "",  # Comma-separated channel IDs where bot responds without mention
        "allowed_channels": "",        # If set, bot ONLY responds in these channel IDs (whitelist)
        "auto_thread": True,           # Auto-create threads on @mention in channels (like Slack)
        "thread_require_mention": False,  # If True, require @mention in threads too (multi-bot threads)
        "history_backfill": True,         # If True, prepend recent channel scrollback when bot is triggered (recovers messages missed while require_mention gated them out)
        "history_backfill_limit": 50,     # Max number of recent messages to scan when assembling the backfill block
        "reactions": True,             # Add 👀/✅/❌ reactions to messages during processing
        "channel_prompts": {},         # Per-channel ephemeral system prompts (forum parents apply to child threads)
        # Opt-in DM role-based auth (#12136). By default, DISCORD_ALLOWED_ROLES
        # authorizes only guild messages in the role's own guild — DMs require
        # DISCORD_ALLOWED_USERS. Set dm_role_auth_guild to a guild ID to also
        # authorize DMs from members of that one trusted guild holding the
        # allowed role. Unset / empty / 0 = secure default (DM role-auth off).
        "dm_role_auth_guild": "",
        # discord / discord_admin tools: restrict which actions the agent may call.
        # Default (empty) = all actions allowed (subject to bot privileged intents).
        # Accepts comma-separated string ("list_guilds,list_channels,fetch_messages")
        # or YAML list. Unknown names are dropped with a warning at load time.
        # Actions: list_guilds, server_info, list_channels, channel_info,
        # list_roles, member_info, search_members, fetch_messages, list_pins,
        # pin_message, unpin_message, create_thread, add_role, remove_role.
        "server_actions": "",
        # Accept arbitrary attachment file types (not just SUPPORTED_DOCUMENT_TYPES).
        # When True, any uploaded file is cached to disk with mime
        # application/octet-stream and the path is surfaced to the agent so it
        # can use terminal/read_file/etc. against it. Default False preserves
        # the historical allowlist behaviour.
        # Env override: DISCORD_ALLOW_ANY_ATTACHMENT.
        "allow_any_attachment": False,
        # Maximum bytes per attachment the gateway will cache. The whole file
        # is held in memory while being written, so unlimited uploads carry a
        # real memory cost. Default 32 MiB matches the historical hardcoded
        # cap. Set to 0 for no cap. Env override: DISCORD_MAX_ATTACHMENT_BYTES.
        "max_attachment_bytes": 33554432,
    },

    # WhatsApp platform settings (gateway mode)
    "whatsapp": {
        # Reply prefix prepended to every outgoing WhatsApp message.
        # Default (None) uses the built-in "⚕ *Hermes Agent*" header.
        # Set to "" (empty string) to disable the header entirely.
        # Supports \n for newlines, e.g. "🤖 *My Bot*\n──────\n"
    },

    # Telegram platform settings (gateway mode)
    "telegram": {
        "reactions": False,            # Add 👀/✅/❌ reactions to messages during processing
        "channel_prompts": {},         # Per-chat/topic ephemeral system prompts (topics inherit from parent group)
        "allowed_chats": "",           # If set, bot ONLY responds in these group/supergroup chat IDs (whitelist)
    },

    # Mattermost platform settings (gateway mode)
    "mattermost": {
        "require_mention": True,       # Require @mention to respond in channels
        "free_response_channels": "",  # Comma-separated channel IDs where bot responds without mention
        "allowed_channels": "",        # If set, bot ONLY responds in these channel IDs (whitelist)
        "channel_prompts": {},         # Per-channel ephemeral system prompts
    },

    # Matrix platform settings (gateway mode)
    "matrix": {
        "require_mention": True,       # Require @mention to respond in rooms
        "free_response_rooms": "",     # Comma-separated room IDs where bot responds without mention
        "allowed_rooms": "",           # If set, bot ONLY responds in these room IDs (whitelist)
    },

    # Approval mode for dangerous commands:
    #   manual — always prompt the user (default)
    #   smart  — use auxiliary LLM to auto-approve low-risk commands, prompt for high-risk
    #   off    — skip all approval prompts (equivalent to --yolo)
    #
    # cron_mode — what to do when a cron job hits a dangerous command:
    #   deny    — block the command and let the agent find another way (default, safe)
    #   approve — auto-approve all dangerous commands in cron jobs
    "approvals": {
        "mode": "manual",
        "timeout": 60,
        "cron_mode": "deny",
        # When true, /reload-mcp asks the user to confirm before rebuilding
        # the MCP tool set for the active session.  Reloading invalidates
        # the provider prompt cache (tool schemas are baked into the system
        # prompt), so the next message re-sends full input tokens — this can
        # be expensive on long-context or high-reasoning models.  Users click
        # "Always Approve" to silence the prompt permanently; that flips
        # this key to false.
        "mcp_reload_confirm": True,
        # When true, destructive session slash commands (/clear, /new, /reset,
        # /undo) ask the user to confirm before discarding conversation state.
        # Three-option prompt (Approve Once / Always Approve / Cancel) routed
        # through tools.slash_confirm — native yes/no buttons on Telegram,
        # Discord, and Slack; text fallback elsewhere.  Users click "Always
        # Approve" to silence the prompt permanently; that flips this key to
        # false.  TUI has its own modal overlay (HERMES_TUI_NO_CONFIRM=1 to
        # opt out there).
        "destructive_slash_confirm": True,
    },

    # Permanently allowed dangerous command patterns (added via "always" approval)
    "command_allowlist": [],
    # User-defined quick commands that bypass the agent loop (type: exec only)
    "quick_commands": {},

    # Shell-script hooks — declarative bridge that invokes shell scripts
    # on plugin-hook events (pre_tool_call, post_tool_call, pre_llm_call,
    # subagent_stop, etc.).  Each entry maps an event name to a list of
    # {matcher, command, timeout} dicts.  First registration of a new
    # command prompts the user for consent; subsequent runs reuse the
    # stored approval from ~/.hermes/shell-hooks-allowlist.json.
    # See `website/docs/user-guide/features/hooks.md` for schema + examples.
    "hooks": {},

    # Auto-accept shell-hook registrations without a TTY prompt.  Also
    # toggleable per-invocation via --accept-hooks or HERMES_ACCEPT_HOOKS=1.
    # Gateway / cron / non-interactive runs need this (or one of the other
    # channels) to pick up newly-added hooks.
    "hooks_auto_accept": False,
    # Custom personalities — add your own entries here
    # Supports string format: {"name": "system prompt"}
    # Or dict format: {"name": {"description": "...", "system_prompt": "...", "tone": "...", "style": "..."}}
    "personalities": {},

    # Pre-exec security scanning via tirith
    "security": {
        "allow_private_urls": False,  # Allow requests to private/internal IPs (for OpenWrt, proxies, VPNs)
        "redact_secrets": True,
        "tirith_enabled": True,
        "tirith_path": "tirith",
        "tirith_timeout": 5,
        "tirith_fail_open": True,
        "website_blocklist": {
            "enabled": False,
            "domains": [],
            "shared_files": [],
        },
        # Acknowledged supply-chain security advisories. Each entry is the
        # ID of an advisory the user has read and acted on (uninstalled the
        # compromised package, rotated credentials). Acked advisories no
        # longer trigger the startup banner. Add via `hermes doctor --ack
        # <id>`; remove by editing the list directly. See
        # ``hermes_cli/security_advisories.py`` for the catalog.
        "acked_advisories": [],
        # Allow Hermes to lazy-install opt-in backend packages from PyPI
        # the first time the user enables a backend that needs them
        # (e.g. installing ``elevenlabs`` when the user picks ElevenLabs as
        # their TTS provider). Set to false to require explicit
        # ``pip install`` for everything beyond the base set — appropriate
        # for restricted networks, audited environments, or air-gapped
        # systems where any runtime install is unacceptable.
        "allow_lazy_installs": True,
    },

    "cron": {
        # Wrap delivered cron responses with a header (task name) and footer
        # ("The agent cannot see this message").  Set to false for clean output.
        "wrap_response": True,
        # Maximum number of due jobs to run in parallel per tick.
        # null/0 = unbounded (limited only by thread count).
        # 1 = serial (pre-v0.9 behaviour).
        # Also overridable via HERMES_CRON_MAX_PARALLEL env var.
        "max_parallel_jobs": None,
    },

    # Kanban multi-agent coordination — controls the dispatcher loop that
    # spawns workers for ready tasks. The dispatcher ticks every N seconds
    # (default 60), reclaims stale claims, promotes dependency-satisfied
    # todos to ready, and fires `hermes -p <assignee> chat -q ...` for
    # each claimable ready task. One dispatcher per profile is sufficient;
    # running more than one on the same kanban.db will race for claims.
    "kanban": {
        # Run the dispatcher inside the gateway process. On by default —
        # the cost is ~300µs every `dispatch_interval_seconds` when idle,
        # and gateway is the supervisor users already have. Set to false
        # only if you run the dispatcher as a separate systemd unit or
        # don't want the gateway to spawn workers.
        "dispatch_in_gateway": True,
        # Seconds between dispatcher ticks (idle or not). Lower = snappier
        # pickup of newly-ready tasks; higher = less SQL pressure.
        "dispatch_interval_seconds": 60,
        # Auto-block after this many consecutive non-success attempts for the
        # same task/profile (spawn_failed, timed_out, or crashed). Reassignment
        # resets the streak for the new profile.
        "failure_limit": 2,
        # Worker stdout/stderr logs rotate at spawn time. Defaults preserve
        # the historical 2 MiB + one-backup behavior; long-running workers can
        # raise these to keep more early failure evidence.
        "worker_log_rotate_bytes": 2 * 1024 * 1024,
        "worker_log_backup_count": 1,
        # Profile that decomposes tasks in the Triage column. When unset,
        # falls back to the default profile (the one `hermes` launches with
        # no -p flag). Set this to a dedicated 'orchestrator' profile if you
        # want decomposition to use a different model/skills from your main
        # working profile.
        "orchestrator_profile": "",
        # Where a child task lands if the orchestrator can't match an
        # assignee to any installed profile. When unset, falls back to the
        # default profile. A task never ends up with assignee=None.
        "default_assignee": "",
        # Per-profile concurrency cap (#21582). When set to a positive int,
        # no single profile can have more than N workers running at once,
        # even if the global max_in_progress / max_spawn caps would allow
        # it. Tasks blocked this way defer to the next dispatcher tick.
        # Unset (None) means "no per-profile cap" — backward-compatible
        # with existing installs. Useful for fan-out workflows that would
        # otherwise saturate one profile's local model / API quota /
        # browser pool while leaving other profiles idle.
        "max_in_progress_per_profile": None,
        # When true, the kanban dispatcher auto-runs the decomposer on
        # tasks that land in Triage (every dispatcher tick). When false,
        # decomposition is manual via `hermes kanban decompose <id>` or
        # the dashboard's Decompose button.
        "auto_decompose": True,
        # Max triage tasks to decompose per dispatcher tick. Prevents a
        # large bulk-load of triage tasks from spending a burst of aux
        # LLM calls in one tick. Excess tasks defer to the next tick.
        "auto_decompose_per_tick": 3,
        # Stale detection: running tasks that have exceeded this many
        # seconds without a heartbeat (since ``last_heartbeat_at``) are
        # auto-reclaimed to ``ready`` on the next dispatcher tick. The
        # worker process (if still running host-locally) is terminated
        # before the reclaim.  0 disables stale detection entirely.
        "dispatch_stale_timeout_seconds": 14400,
    },

    # execute_code settings — controls the tool used for programmatic tool calls.
    "code_execution": {
        # Execution mode:
        #   project (default) — scripts run in the session's working directory
        #     with the active virtualenv/conda env's python, so project deps
        #     (pandas, torch, project packages) and relative paths resolve.
        #   strict            — scripts run in an isolated temp directory with
        #     hermes-agent's own python (sys.executable). Maximum isolation
        #     and reproducibility; project deps and relative paths won't work.
        # Env scrubbing (strips *_API_KEY, *_TOKEN, *_SECRET, ...) and the
        # tool whitelist apply identically in both modes.
        "mode": "project",
    },

    # Tool Search (progressive disclosure for large tool surfaces).
    # When the model is connected to many MCP servers or non-core plugin
    # tools, their JSON schemas can consume a substantial fraction of the
    # context window on every turn. When enabled, those tools are replaced
    # in the model-facing tools array with three bridge tools —
    # tool_search / tool_describe / tool_call — and surfaced on demand.
    #
    # Core Hermes tools (terminal, read_file, write_file, patch,
    # search_files, todo, memory, browser_*, etc.) are NEVER deferred.
    # See tools/tool_search.py for full design notes and the
    # openclaw-tool-search-report PDF in this PR for the rationale.
    "tools": {
        "tool_search": {
            # "auto" (default) — activate only when deferrable tool schemas
            #   exceed ``threshold_pct`` of the active model's context length,
            #   so small toolsets pay no overhead.
            # "on"  — always activate when there is at least one deferrable
            #   tool. Use when you have many MCP servers and want maximum
            #   token reduction unconditionally.
            # "off" — disable entirely. Tools-array assembly is a pass-through.
            "enabled": "auto",
            # Percentage of context length at which "auto" mode kicks in.
            # 10 matches the Claude Code default. Range 0..100.
            "threshold_pct": 10,
            # When the model calls tool_search without a ``limit`` argument,
            # how many hits to return. Range 1..max_search_limit.
            "search_default_limit": 5,
            # Hard upper bound the model can request via ``limit``. Range 1..50.
            "max_search_limit": 20,
        },
    },

    # Logging — controls file logging to ~/.hermes/logs/.
    # agent.log captures INFO+ (all agent activity); errors.log captures WARNING+.
    "logging": {
        "level": "INFO",       # Minimum level for agent.log: DEBUG, INFO, WARNING
        "max_size_mb": 5,      # Max size per log file before rotation
        "backup_count": 3,     # Number of rotated backup files to keep
    },

    # Remotely-hosted model catalog manifest.  When enabled, the CLI fetches
    # curated model lists for OpenRouter and Nous Portal from this URL,
    # falling back to the in-repo snapshot on network failure.  Lets us
    # update model picker lists without shipping a hermes-agent release.
    # The default URL is served by the docs site GitHub Pages deploy.
    "model_catalog": {
        "enabled": False,
        "url": "",
        # Disk cache TTL in hours.  Beyond this, the CLI refetches on the
        # next /model or `hermes model` invocation; network failures
        # silently fall back to the stale cache.
        "ttl_hours": 1,
        # Optional per-provider override URLs for third parties that want
        # to self-host their own curation list using the same schema.
        # Example:
        #   providers:
        #     openrouter:
        #       url: https://example.com/my-curation.json
        "providers": {},
    },

    # Network settings — workarounds for connectivity issues.
    "network": {
        # Force IPv4 connections.  On servers with broken or unreachable IPv6,
        # Python tries AAAA records first and hangs for the full TCP timeout
        # before falling back to IPv4.  Set to true to skip IPv6 entirely.
        "force_ipv4": False,
    },

    # Gateway settings — control how messaging platforms (Telegram, Discord,
    # Slack, etc.) deliver agent-produced files as native attachments.
    "gateway": {
        # When false (default), any file path the agent emits is delivered
        # as a native attachment as long as it isn't under the credential /
        # system-path denylist (/etc, /proc, ~/.ssh, ~/.aws, ~/.hermes/.env,
        # auth.json, etc.). This matches the symmetry of inbound delivery
        # — we accept any document type the user uploads, and the agent
        # can hand back any file that isn't a credential.
        #
        # When true, fall back to the older allowlist+recency-window
        # behavior: files must live under the Hermes cache, under
        # ``media_delivery_allow_dirs``, or be freshly produced inside the
        # ``trust_recent_files_seconds`` window. Recommended for
        # public-facing gateways where prompt injection from one user
        # shouldn't be able to exfiltrate the host's secrets to that same
        # user. Bridged to HERMES_MEDIA_DELIVERY_STRICT.
        "strict": False,
        # Extra directories from which model-emitted bare file paths may be
        # uploaded as native gateway attachments. Files inside the Hermes
        # cache (~/.hermes/cache/{documents,images,audio,video,screenshots})
        # are always trusted; this list adds operator-controlled roots
        # (project dirs, scratch dirs, mounted shares). Accepts a list of
        # absolute paths or a single os.pathsep-separated string. Bridged
        # to HERMES_MEDIA_ALLOW_DIRS at gateway startup. Tilde paths are
        # expanded. Honored in both default and strict mode.
        "media_delivery_allow_dirs": [],
        # When true, files whose mtime is within ``trust_recent_files_seconds``
        # of "now" are trusted for native delivery even outside the cache /
        # operator allowlist — useful for ``pandoc -o /tmp/report.pdf`` or
        # PDFs the agent writes into a working directory. System paths
        # (/etc, /proc, ~/.ssh, ~/.aws, etc.) remain blocked regardless.
        # Disable to fall back to pure-allowlist mode. Bridged to
        # HERMES_MEDIA_TRUST_RECENT_FILES. Only consulted when ``strict``
        # is true; in default mode the denylist alone gates delivery.
        "trust_recent_files": True,
        # Recency window in seconds. 600 (10 min) comfortably covers a
        # multi-tool agent turn. Bridged to HERMES_MEDIA_TRUST_RECENT_SECONDS.
        # Only consulted when ``strict`` is true.
        "trust_recent_files_seconds": 600,
    },

    # Real-time token streaming to messaging platforms (Telegram, Discord,
    # Slack, etc.). Read at the top level by the gateway; absent this block the
    # gateway falls back to these same defaults, so adding it here only makes
    # the feature discoverable in config.yaml — it does not change behavior.
    #
    # Disabled by default: streaming costs extra edit/draft API calls per
    # response. Set ``enabled: true`` and restart the gateway to turn it on.
    "streaming": {
        # Master switch. When false, each response is delivered as a single
        # final message (no progressive updates).
        "enabled": False,
        # Transport selection:
        #   "auto"  — prefer native draft streaming where the platform
        #             supports it (Telegram DMs via sendMessageDraft,
        #             Bot API 9.5+) and fall back to edit-based elsewhere.
        #             Safe global default: platforms without draft support
        #             (Discord, Slack, Matrix, Telegram groups) transparently
        #             use the edit path, so "auto" only upgrades chats that
        #             can render the smoother native preview.
        #   "draft" — explicitly request native drafts; falls back to edit
        #             when the platform/chat doesn't support them.
        #   "edit"  — progressive editMessageText only (legacy behavior).
        #   "off"   — disable streaming entirely (same as enabled: false).
        "transport": "auto",
        # Minimum seconds between progressive edits — tuned for Telegram's
        # ~1 edit/s flood envelope.
        "edit_interval": 0.8,
        # Flush the buffer to the platform once this many characters have
        # accumulated, so short replies feel near-instant.
        "buffer_threshold": 24,
        # Cursor glyph appended to the in-progress message while streaming.
        "cursor": " \u2589",
        # When >0, the final edit for a long-running streamed response is
        # delivered as a fresh message if the preview has been visible at
        # least this many seconds, so the platform timestamp reflects
        # completion time. Telegram only; other platforms ignore it.
        "fresh_final_after_seconds": 60.0,
    },

    # Session storage — controls automatic cleanup of ~/.hermes/state.db.
    # state.db accumulates every session, message, tool call, and FTS5 index
    # entry forever.  Without auto-pruning, a heavy user (gateway + cron)
    # reports 384MB+ databases with 68K+ messages, which slows down FTS5
    # inserts, /resume listing, and insights queries.
    "sessions": {
        # When true, prune ended sessions older than retention_days once
        # per (roughly) min_interval_hours at CLI/gateway/cron startup.
        # Only touches ended sessions — active sessions are always preserved.
        # Default false: session history is valuable for search recall, and
        # silently deleting it could surprise users.  Opt in explicitly.
        "auto_prune": False,
        # How many days of ended-session history to keep.  Matches the
        # default of ``hermes sessions prune``.
        "retention_days": 90,
        # VACUUM after a prune that actually deleted rows.  SQLite does not
        # reclaim disk space on DELETE — freed pages are just reused on
        # subsequent INSERTs — so without VACUUM the file stays bloated
        # even after pruning.  VACUUM blocks writes for a few seconds per
        # 100MB, so it only runs at startup, and only when prune deleted
        # ≥1 session.
        "vacuum_after_prune": True,
        # Minimum hours between auto-maintenance runs (avoids repeating
        # the sweep on every CLI invocation).  Tracked via state_meta in
        # state.db itself, so it's shared across all processes.
        "min_interval_hours": 24,
        # Legacy per-session JSON snapshot writer.  When true, the agent
        # rewrites ``~/.hermes/sessions/session_{sid}.json`` on every turn
        # boundary with the full message list.  state.db is canonical and
        # has every field the snapshot stored (plus per-message timestamps
        # and token counts), so this is off by default — the snapshots had
        # no consumer outside their own overwrite guard and accumulated
        # GBs of disk on heavy users.  Opt in only if you have an external
        # tool that consumes the JSON files directly.
        "write_json_snapshots": False,
    },

    # Contextual first-touch onboarding hints (see agent/onboarding.py).
    # Each hint is shown once per install and then latched here so it
    # never fires again.  Users can wipe the section to re-see all hints.
    "onboarding": {
        "seen": {},
    },

    # ``hermes update`` behaviour.
    "updates": {
        # Run a full ``hermes backup``-style zip of HERMES_HOME before every
        # ``hermes update``.  Backups land in ``<HERMES_HOME>/backups/`` and
        # can be restored with ``hermes import <path>``.  Off by default —
        # on large HERMES_HOME directories the zip can add minutes to every
        # update.  Set to true to re-enable, or pass ``--backup`` to opt in
        # for a single update run.
        "pre_update_backup": False,
        # How many pre-update backup zips to retain.  Older ones are pruned
        # automatically after each successful backup.  Values below 1 are
        # floored to 1 — the backup just created is always preserved.  To
        # disable backups entirely, set ``pre_update_backup: false`` above
        # rather than ``backup_keep: 0``.
        "backup_keep": 5,
    },

    # Language Server Protocol — semantic diagnostics from real
    # language servers (pyright, gopls, rust-analyzer, etc.) wired
    # into the post-write lint check used by ``write_file`` and
    # ``patch``.
    #
    # LSP is gated on git-workspace detection: when the agent's
    # cwd (or the file being edited) is inside a git worktree, LSP
    # runs against that workspace.  When neither is in a git repo,
    # LSP stays dormant and the in-process syntax check is the only
    # tier — handy for Telegram/Discord chats where the cwd is the
    # user's home directory.
    "lsp": {
        # Master toggle.  Setting this to false disables the entire
        # subsystem — no servers spawn, no background event loop, no
        # cost.
        "enabled": True,

        # Diagnostic-wait mode for the post-write check.
        # ``"document"`` waits up to ``wait_timeout`` seconds for the
        # current file's diagnostics; ``"full"`` additionally requests
        # workspace-wide diagnostics (slower).
        "wait_mode": "document",
        "wait_timeout": 5.0,

        # How to handle missing server binaries.
        # ``"auto"`` — try to install via npm/go/pip into
        #              ``<HERMES_HOME>/lsp/bin/`` on first use.
        # ``"manual"`` — only use binaries already on PATH.
        # ``"off"`` — alias for ``manual``.
        "install_strategy": "auto",

        # Per-server overrides.  Each key is a server_id from the
        # registry (``pyright``, ``typescript``, ``gopls``,
        # ``rust-analyzer``, etc.) and accepts:
        #   disabled: true
        #     — skip this server even when its extensions match
        #   command: ["full/path/to/server", "--stdio"]
        #     — pin a custom binary path; bypasses auto-install
        #   env: {"KEY": "value"}
        #     — extra env vars passed to the spawned process
        #   initialization_options: {...}
        #     — merged into the LSP ``initializationOptions``
        # Empty by default; the registry defaults work for typical
        # setups.
        "servers": {},
    },


    # X (Twitter) Search via xAI's built-in x_search Responses tool.
    # The tool registers when xAI credentials are available (SuperGrok
    # OAuth or XAI_API_KEY) AND the x_search toolset is enabled in
    # `hermes tools`. These settings tune the backing Responses API call.
    "x_search": {
        # xAI model used for the Responses call. grok-4.20-reasoning is
        # the recommended default; any Grok model with x_search tool
        # access works.
        "model": "grok-4.20-reasoning",
        # Request timeout in seconds (minimum 30). x_search can take
        # 60-120s for complex queries — the default is generous.
        "timeout_seconds": 180,
        # Number of automatic retries on 5xx / ReadTimeout / ConnectionError.
        # Each retry backs off (1.5x attempt seconds, capped at 5s).
        "retries": 2,
    },

    # =========================================================================
    # External secret sources
    # =========================================================================
    # Pull credentials from external secret managers at process startup
    # rather than storing them in ~/.hermes/.env.
    "secrets": {
        "bitwarden": {
            # Master switch.  When false, BSM is never contacted and the
            # bws binary is never auto-installed — same as not having
            # this section at all.
            "enabled": False,
            # Name of the env var that holds the Bitwarden machine-account
            # access token.  This is the one bootstrap secret; it lives
            # in ~/.hermes/.env (or your shell) and never in config.yaml.
            "access_token_env": "BWS_ACCESS_TOKEN",
            # UUID of the BSM project to sync from.
            "project_id": "",
            # Seconds to cache fetched secrets in-process.  0 disables.
            "cache_ttl_seconds": 300,
            # When True, BSM values overwrite existing env vars.  Default
            # True because the point of using BSM is centralized rotation —
            # if .env had the final say, rotating in Bitwarden wouldn't
            # take effect until you also cleared the matching .env line.
            "override_existing": True,
            # When True, the bws binary is auto-downloaded into
            # ~/.hermes/bin/ on first use.  When False you must install
            # bws yourself and have it on PATH.
            "auto_install": True,
            # Bitwarden region / self-hosted endpoint.  Empty string
            # means use the bws CLI default (US Cloud,
            # https://vault.bitwarden.com).  Set to
            # https://vault.bitwarden.eu for EU Cloud, or your own URL
            # for self-hosted Bitwarden.  Plumbed into the bws subprocess
            # as BWS_SERVER_URL.  Prompted for during
            # `hermes secrets bitwarden setup`.
            "server_url": "",
        },
    },

    # Paste collapse thresholds (TUI + CLI).
    #
    # paste_collapse_threshold (default 5)
    #   Bracketed-paste handler. Pastes with this many newlines or more
    #   collapse to a file reference. Set 0 to disable.
    #
    # paste_collapse_threshold_fallback (default 5)
    #   Fallback heuristic for terminals without bracketed paste support.
    #   Same line count test but heuristically gated by chars-added /
    #   newlines-added to avoid false positives from normal typing.
    #   Set 0 to disable.
    #
    # paste_collapse_char_threshold (default 2000)
    #   Long single-line paste guard. Pastes whose total char length
    #   reaches this value collapse to a file reference even if line
    #   count is below the line threshold. Catches the "8000 chars of
    #   minified JSON / log output on one line" case. Set 0 to disable.
    "paste_collapse_threshold": 5,
    "paste_collapse_threshold_fallback": 5,
    "paste_collapse_char_threshold": 2000,


    # Hybrid local-first intelligence ecosystem (MbowaGPT Main / Cybertrunk / Relentless)
    "intelligence": {
        "mode": "hybrid",                 # "hybrid" | "local" | "online"
        "auto_local_fallback": True,      # Seamless offline / cloud-outage failover to MbowaGPT
        "local_voice_first": True,        # Prefer local faster-whisper + Kokoro when offline/low-latency
        "default_local_model": "mbowagpt-auto",
        "local_models": {},               # Optional per-role GGUF/Ollama overrides
    },

    # Config schema version - bump this when adding new required fields
    "_config_version": 26,
}

# =============================================================================
# Config Migration System
# =============================================================================

# Track which env vars were introduced in each config version.
# Migration only mentions vars new since the user's previous version.
ENV_VARS_BY_VERSION: Dict[int, List[str]] = {
    3: ["FIRECRAWL_API_KEY", "BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID", "FAL_KEY"],
    4: ["VOICE_TOOLS_OPENAI_KEY", "ELEVENLABS_API_KEY"],
    5: ["WHATSAPP_ENABLED", "WHATSAPP_MODE", "WHATSAPP_ALLOWED_USERS",
        "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_ALLOWED_USERS"],
    10: ["TAVILY_API_KEY"],
    11: ["TERMINAL_MODAL_MODE"],
}

# Required environment variables with metadata for migration prompts.
# LLM provider is required but handled in the setup wizard's provider
# selection step (Nous Portal / OpenRouter / Custom endpoint), so this
# dict is intentionally empty — no single env var is universally required.
REQUIRED_ENV_VARS = {}

# Optional environment variables that enhance functionality
OPTIONAL_ENV_VARS = {
    # ── Provider (handled in provider selection, not shown in checklists) ──
    "NOUS_BASE_URL": {
        "description": "Nous Portal base URL override",
        "prompt": "Nous Portal base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENROUTER_API_KEY": {
        "description": "OpenRouter API key (for vision, web scraping helpers, and MoA)",
        "prompt": "OpenRouter API key",
        "url": "https://openrouter.ai/keys",
        "password": True,
        "tools": ["vision_analyze", "mixture_of_agents"],
        "category": "provider",
        "advanced": True,
    },
    "GOOGLE_API_KEY": {
        "description": "Google AI Studio API key (also recognized as GEMINI_API_KEY)",
        "prompt": "Google AI Studio API key",
        "url": "https://aistudio.google.com/app/apikey",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GEMINI_API_KEY": {
        "description": "Google AI Studio API key (alias for GOOGLE_API_KEY)",
        "prompt": "Gemini API key",
        "url": "https://aistudio.google.com/app/apikey",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GEMINI_BASE_URL": {
        "description": "Google AI Studio base URL override",
        "prompt": "Gemini base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "XAI_API_KEY": {
        "description": "xAI API key",
        "prompt": "xAI API key",
        "url": "https://console.x.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "XAI_BASE_URL": {
        "description": "xAI base URL override",
        "prompt": "xAI base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "NVIDIA_API_KEY": {
        "description": "NVIDIA NIM API key (build.nvidia.com or local NIM endpoint)",
        "prompt": "NVIDIA NIM API key",
        "url": "https://build.nvidia.com/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "NVIDIA_BASE_URL": {
        "description": "NVIDIA NIM base URL override (e.g. http://localhost:8000/v1 for local NIM)",
        "prompt": "NVIDIA NIM base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "LM_API_KEY": {
        "description": "LM Studio bearer token for auth-enabled local servers",
        "prompt": "LM Studio API key / bearer token",
        "url": None,
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "LM_BASE_URL": {
        "description": "LM Studio base URL override",
        "prompt": "LM Studio base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "GLM_API_KEY": {
        "description": "Z.AI / GLM API key (also recognized as ZAI_API_KEY / Z_AI_API_KEY)",
        "prompt": "Z.AI / GLM API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "ZAI_API_KEY": {
        "description": "Z.AI API key (alias for GLM_API_KEY)",
        "prompt": "Z.AI API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "Z_AI_API_KEY": {
        "description": "Z.AI API key (alias for GLM_API_KEY)",
        "prompt": "Z.AI API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GLM_BASE_URL": {
        "description": "Z.AI / GLM base URL override",
        "prompt": "Z.AI / GLM base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "KIMI_API_KEY": {
        "description": "Kimi / Moonshot API key",
        "prompt": "Kimi API key",
        "url": "https://platform.moonshot.cn/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "KIMI_BASE_URL": {
        "description": "Kimi / Moonshot base URL override",
        "prompt": "Kimi base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "KIMI_CN_API_KEY": {
        "description": "Kimi / Moonshot China API key",
        "prompt": "Kimi (China) API key",
        "url": "https://platform.moonshot.cn/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "STEPFUN_API_KEY": {
        "description": "StepFun Step Plan API key",
        "prompt": "StepFun Step Plan API key",
        "url": "https://platform.stepfun.com/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "STEPFUN_BASE_URL": {
        "description": "StepFun Step Plan base URL override",
        "prompt": "StepFun Step Plan base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "ARCEEAI_API_KEY": {
        "description": "Arcee AI API key",
        "prompt": "Arcee AI API key",
        "url": "https://chat.arcee.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "ARCEE_BASE_URL": {
        "description": "Arcee AI base URL override",
        "prompt": "Arcee base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "GMI_API_KEY": {
        "description": "GMI Cloud API key",
        "prompt": "GMI Cloud API key",
        "url": "https://www.gmicloud.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GMI_BASE_URL": {
        "description": "GMI Cloud base URL override",
        "prompt": "GMI Cloud base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_API_KEY": {
        "description": "MiniMax API key (international)",
        "prompt": "MiniMax API key",
        "url": "https://www.minimax.io/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_BASE_URL": {
        "description": "MiniMax base URL override",
        "prompt": "MiniMax base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_CN_API_KEY": {
        "description": "MiniMax API key (China endpoint)",
        "prompt": "MiniMax (China) API key",
        "url": "https://www.minimaxi.com/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_CN_BASE_URL": {
        "description": "MiniMax (China) base URL override",
        "prompt": "MiniMax (China) base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "DEEPSEEK_API_KEY": {
        "description": "DeepSeek API key for direct DeepSeek access",
        "prompt": "DeepSeek API Key",
        "url": "https://platform.deepseek.com/api_keys",
        "password": True,
        "category": "provider",
    },
    "DEEPSEEK_BASE_URL": {
        "description": "Custom DeepSeek API base URL (advanced)",
        "prompt": "DeepSeek Base URL",
        "url": "",
        "password": False,
        "category": "provider",
    },
    "DASHSCOPE_API_KEY": {
        "description": "Alibaba Cloud DashScope API key (Qwen + multi-provider models)",
        "prompt": "DashScope API Key",
        "url": "https://modelstudio.console.alibabacloud.com/",
        "password": True,
        "category": "provider",
    },
    "DASHSCOPE_BASE_URL": {
        "description": "Custom DashScope base URL (default: coding-intl OpenAI-compat endpoint)",
        "prompt": "DashScope Base URL",
        "url": "",
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "HERMES_QWEN_BASE_URL": {
        "description": "Qwen Portal base URL override (default: https://portal.qwen.ai/v1)",
        "prompt": "Qwen Portal base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "HERMES_GEMINI_CLIENT_ID": {
        "description": "Google OAuth client ID for google-gemini-cli (optional; defaults to Google's public gemini-cli client)",
        "prompt": "Google OAuth client ID (optional — leave empty to use the public default)",
        "url": "https://console.cloud.google.com/apis/credentials",
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "HERMES_GEMINI_CLIENT_SECRET": {
        "description": "Google OAuth client secret for google-gemini-cli (optional)",
        "prompt": "Google OAuth client secret (optional)",
        "url": "https://console.cloud.google.com/apis/credentials",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "HERMES_GEMINI_PROJECT_ID": {
        "description": "GCP project ID for paid Gemini tiers (free tier auto-provisions)",
        "prompt": "GCP project ID for Gemini OAuth (leave empty for free tier)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_ZEN_API_KEY": {
        "description": "OpenCode Zen API key (pay-as-you-go access to curated models)",
        "prompt": "OpenCode Zen API key",
        "url": "https://opencode.ai/auth",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_ZEN_BASE_URL": {
        "description": "OpenCode Zen base URL override",
        "prompt": "OpenCode Zen base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_GO_API_KEY": {
        "description": "OpenCode Go API key ($10/month subscription for open models)",
        "prompt": "OpenCode Go API key",
        "url": "https://opencode.ai/auth",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_GO_BASE_URL": {
        "description": "OpenCode Go base URL override",
        "prompt": "OpenCode Go base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "HF_TOKEN": {
        "description": "Hugging Face token for Inference Providers (20+ open models via router.huggingface.co)",
        "prompt": "Hugging Face Token",
        "url": "https://huggingface.co/settings/tokens",
        "password": True,
        "category": "provider",
    },
    "HF_BASE_URL": {
        "description": "Hugging Face Inference Providers base URL override",
        "prompt": "HF base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OLLAMA_API_KEY": {
        "description": "Ollama Cloud API key (ollama.com — cloud-hosted open models)",
        "prompt": "Ollama Cloud API key",
        "url": "https://ollama.com/settings",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OLLAMA_BASE_URL": {
        "description": "Ollama Cloud base URL override (default: https://ollama.com/v1)",
        "prompt": "Ollama base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "XIAOMI_API_KEY": {
        "description": "Xiaomi MiMo API key for MiMo models (mimo-v2.5-pro, mimo-v2.5, mimo-v2-pro, mimo-v2-omni, mimo-v2-flash)",
        "prompt": "Xiaomi MiMo API Key",
        "url": "https://platform.xiaomimimo.com",
        "password": True,
        "category": "provider",
    },
    "XIAOMI_BASE_URL": {
        "description": "Xiaomi MiMo base URL override (default: https://api.xiaomimimo.com/v1)",
        "prompt": "Xiaomi base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "AWS_REGION": {
        "description": "AWS region for Bedrock API calls (e.g. us-east-1, eu-central-1)",
        "prompt": "AWS Region",
        "url": "https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html",
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "AWS_PROFILE": {
        "description": "AWS named profile for Bedrock authentication (from ~/.aws/credentials)",
        "prompt": "AWS Profile",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "AZURE_FOUNDRY_API_KEY": {
        "description": "Azure Foundry API key for custom Azure endpoints",
        "prompt": "Azure Foundry API Key",
        "url": "https://ai.azure.com/",
        "password": True,
        "category": "provider",
    },
    "AZURE_FOUNDRY_BASE_URL": {
        "description": "Azure Foundry base URL (set via 'hermes model' for endpoint-specific config)",
        "prompt": "Azure Foundry base URL",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },

    # ── Tool API keys ──
    "EXA_API_KEY": {
        "description": "Exa API key for AI-native web search and contents",
        "prompt": "Exa API key",
        "url": "https://exa.ai/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "PARALLEL_API_KEY": {
        "description": "Parallel API key for AI-native web search and extract",
        "prompt": "Parallel API key",
        "url": "https://parallel.ai/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "FIRECRAWL_API_KEY": {
        "description": "Firecrawl API key for web search and scraping",
        "prompt": "Firecrawl API key",
        "url": "https://firecrawl.dev/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "FIRECRAWL_API_URL": {
        "description": "Firecrawl API URL for self-hosted instances (optional)",
        "prompt": "Firecrawl API URL (leave empty for cloud)",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "FIRECRAWL_GATEWAY_URL": {
        "description": "Exact Firecrawl tool-gateway origin override for Nous Subscribers only (optional)",
        "prompt": "Firecrawl gateway URL (leave empty to derive from domain)",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_DOMAIN": {
        "description": "Shared tool-gateway domain suffix for Nous Subscribers only, used to derive vendor hosts, e.g. nousresearch.com -> firecrawl-gateway.nousresearch.com",
        "prompt": "Tool-gateway domain suffix",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_SCHEME": {
        "description": "Shared tool-gateway URL scheme for Nous Subscribers only, used to derive vendor hosts (`https` by default, set `http` for local gateway testing)",
        "prompt": "Tool-gateway URL scheme",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_USER_TOKEN": {
        "description": "Explicit Nous Subscriber access token for tool-gateway requests (optional; otherwise read from the Hermes auth store)",
        "prompt": "Tool-gateway user token",
        "url": None,
        "password": True,
        "category": "tool",
        "advanced": True,
    },
    "TAVILY_API_KEY": {
        "description": "Tavily API key for AI-native web search and extract",
        "prompt": "Tavily API key",
        "url": "https://app.tavily.com/home",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "SEARXNG_URL": {
        "description": "URL of your SearXNG instance for free self-hosted web search",
        "prompt": "SearXNG URL (e.g. http://localhost:8080)",
        "url": "https://searxng.github.io/searxng/",
        "tools": ["web_search"],
        "password": False,
        "category": "tool",
    },
    "BRAVE_SEARCH_API_KEY": {
        "description": "Brave Search API subscription token (free tier: 2,000 queries/mo)",
        "prompt": "Brave Search subscription token",
        "url": "https://brave.com/search/api/",
        "tools": ["web_search"],
        "password": True,
        "category": "tool",
    },
    "BROWSERBASE_API_KEY": {
        "description": "Browserbase API key for cloud browser (optional — local browser works without this)",
        "prompt": "Browserbase API key",
        "url": "https://browserbase.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": True,
        "category": "tool",
    },
    "BROWSERBASE_PROJECT_ID": {
        "description": "Browserbase project ID (optional — only needed for cloud browser)",
        "prompt": "Browserbase project ID",
        "url": "https://browserbase.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": False,
        "category": "tool",
    },
    "BROWSER_USE_API_KEY": {
        "description": "Browser Use API key for cloud browser (optional — local browser works without this)",
        "prompt": "Browser Use API key",
        "url": "https://browser-use.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": True,
        "category": "tool",
    },
    "FIRECRAWL_BROWSER_TTL": {
        "description": "Firecrawl browser session TTL in seconds (optional, default 300)",
        "prompt": "Browser session TTL (seconds)",
        "tools": ["browser_navigate", "browser_click"],
        "password": False,
        "category": "tool",
    },
    "AGENT_BROWSER_ENGINE": {
        "description": "Browser engine for local mode: auto (default Chrome), lightpanda (faster, no screenshots), chrome",
        "prompt": "Browser engine (auto/lightpanda/chrome)",
        "url": "https://github.com/vercel-labs/agent-browser",
        "tools": ["browser_navigate", "browser_snapshot", "browser_click", "browser_vision"],
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "CAMOFOX_URL": {
        "description": "Camofox browser server URL for local anti-detection browsing (e.g. http://localhost:9377)",
        "prompt": "Camofox server URL",
        "url": "https://github.com/jo-inc/camofox-browser",
        "tools": ["browser_navigate", "browser_click"],
        "password": False,
        "category": "tool",
    },
    "FAL_KEY": {
        "description": "FAL API key for image and video generation",
        "prompt": "FAL API key",
        "url": "https://fal.ai/",
        "tools": ["image_generate", "video_generate"],
        "password": True,
        "category": "tool",
    },
    "KREA_API_KEY": {
        "description": "Krea API key for Krea 2 image generation (Medium + Large)",
        "prompt": "Krea API key",
        "url": "https://www.krea.ai/settings/api-tokens",
        "tools": ["image_generate"],
        "password": True,
        "category": "tool",
    },
    "MUAPI_KEY": {
        "description": "MuAPI key for Image Studio generation and editing",
        "prompt": "MuAPI key",
        "url": "https://muapi.ai",
        "tools": ["image_studio"],
        "password": True,
        "category": "tool",
    },
    "VOICE_TOOLS_OPENAI_KEY": {
        "description": "OpenAI API key for voice transcription (Whisper) and OpenAI TTS",
        "prompt": "OpenAI API Key (for Whisper STT + TTS)",
        "url": "https://platform.openai.com/api-keys",
        "tools": ["voice_transcription", "openai_tts"],
        "password": True,
        "category": "tool",
    },
    "ELEVENLABS_API_KEY": {
        "description": "ElevenLabs API key for premium text-to-speech voices and Scribe transcription",
        "prompt": "ElevenLabs API key",
        "url": "https://elevenlabs.io/",
        "tools": ["elevenlabs_tts", "voice_transcription"],
        "password": True,
        "category": "tool",
    },
    "MISTRAL_API_KEY": {
        "description": "Mistral API key for Voxtral TTS and transcription (STT)",
        "prompt": "Mistral API key",
        "url": "https://console.mistral.ai/",
        "password": True,
        "category": "tool",
    },
    "GITHUB_TOKEN": {
        "description": "GitHub token for Skills Hub (higher API rate limits, skill publish)",
        "prompt": "GitHub Token",
        "url": "https://github.com/settings/tokens",
        "password": True,
        "category": "tool",
    },

    # ── Bundled skills (opt-in: only needed if the user uses that skill) ──
    # These use category="skill" (distinct from "tool") so the sandbox
    # env blocklist in tools/environments/local.py does NOT rewrite them —
    # skills legitimately need these passed through to curl via
    # tools/env_passthrough.py when the user's skill calls out.
    "NOTION_API_KEY": {
        "description": "Notion integration token (used by the `notion` skill)",
        "prompt": "Notion API key",
        "url": "https://www.notion.so/my-integrations",
        "password": True,
        "category": "skill",
        "advanced": True,
    },
    "LINEAR_API_KEY": {
        "description": "Linear personal API key (used by the `linear` skill)",
        "prompt": "Linear API key",
        "url": "https://linear.app/settings/account/security",
        "password": True,
        "category": "skill",
        "advanced": True,
    },
    "AIRTABLE_API_KEY": {
        "description": "Airtable personal access token (used by the `airtable` skill)",
        "prompt": "Airtable API key",
        "url": "https://airtable.com/create/tokens",
        "password": True,
        "category": "skill",
        "advanced": True,
    },
    "TENOR_API_KEY": {
        "description": "Tenor API key for GIF search (used by the `gif-search` skill)",
        "prompt": "Tenor API key",
        "url": "https://developers.google.com/tenor/guides/quickstart",
        "password": True,
        "category": "skill",
        "advanced": True,
    },

    # ── Honcho ──
    "HONCHO_API_KEY": {
        "description": "Honcho API key for AI-native persistent memory",
        "prompt": "Honcho API key",
        "url": "https://app.honcho.dev",
        "tools": ["honcho_context"],
        "password": True,
        "category": "tool",
    },
    "HONCHO_BASE_URL": {
        "description": "Base URL for self-hosted Honcho instances (no API key needed)",
        "prompt": "Honcho base URL (e.g. http://localhost:8000)",
        "category": "tool",
    },

    # ── Langfuse observability ──
    "HERMES_LANGFUSE_PUBLIC_KEY": {
        "description": "Langfuse project public key (pk-lf-...)",
        "prompt": "Langfuse public key",
        "url": "https://cloud.langfuse.com",
        "password": False,
        "category": "tool",
    },
    "HERMES_LANGFUSE_SECRET_KEY": {
        "description": "Langfuse project secret key (sk-lf-...)",
        "prompt": "Langfuse secret key",
        "url": "https://cloud.langfuse.com",
        "password": True,
        "category": "tool",
    },
    "HERMES_LANGFUSE_BASE_URL": {
        "description": "Langfuse server URL (default: https://cloud.langfuse.com)",
        "prompt": "Langfuse server URL (leave empty for cloud.langfuse.com)",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },

    # ── Messaging platforms ──
    "TELEGRAM_BOT_TOKEN": {
        "description": "Telegram bot token from @BotFather",
        "prompt": "Telegram bot token",
        "url": "https://t.me/BotFather",
        "password": True,
        "category": "messaging",
    },
    "TELEGRAM_ALLOWED_USERS": {
        "description": "Comma-separated Telegram user IDs allowed to use the bot (get ID from @userinfobot)",
        "prompt": "Allowed Telegram user IDs (comma-separated)",
        "url": "https://t.me/userinfobot",
        "password": False,
        "category": "messaging",
    },
    "TELEGRAM_PROXY": {
        "description": "Proxy URL for Telegram connections (overrides HTTPS_PROXY). Supports http://, https://, socks5://",
        "prompt": "Telegram proxy URL (optional)",
        "password": False,
        "category": "messaging",
    },
    "DISCORD_BOT_TOKEN": {
        "description": "Discord bot token from Developer Portal",
        "prompt": "Discord bot token",
        "url": "https://discord.com/developers/applications",
        "password": True,
        "category": "messaging",
    },
    "DISCORD_ALLOWED_USERS": {
        "description": "Comma-separated Discord user IDs allowed to use the bot",
        "prompt": "Allowed Discord user IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "DISCORD_REPLY_TO_MODE": {
        "description": "Discord reply threading mode: 'off' (no reply references), 'first' (reply on first message only, default), 'all' (reply on every chunk)",
        "prompt": "Discord reply mode (off/first/all)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_BOT_TOKEN": {
        "description": "Slack bot token (xoxb-). Get from OAuth & Permissions after installing your app. "
                       "Required scopes: chat:write, app_mentions:read, channels:history, groups:history, "
                       "im:history, im:read, im:write, users:read, files:read, files:write",
        "prompt": "Slack Bot Token (xoxb-...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_APP_TOKEN": {
        "description": "Slack app-level token (xapp-) for Socket Mode. Get from Basic Information → "
                       "App-Level Tokens. Also ensure Event Subscriptions include: message.im, "
                       "message.channels, message.groups, app_mention",
        "prompt": "Slack App Token (xapp-...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "MATTERMOST_URL": {
        "description": "Mattermost server URL (e.g. https://mm.example.com)",
        "prompt": "Mattermost server URL",
        "url": "https://mattermost.com/deploy/",
        "password": False,
        "category": "messaging",
    },
    "MATTERMOST_TOKEN": {
        "description": "Mattermost bot token or personal access token",
        "prompt": "Mattermost bot token",
        "url": None,
        "password": True,
        "category": "messaging",
    },
    "MATTERMOST_ALLOWED_USERS": {
