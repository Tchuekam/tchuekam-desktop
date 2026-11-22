"""Thread-safe internet connectivity and intelligence-mode monitor for TchuekaM.

Tracks whether the host can reach cloud inference endpoints and combines that
live probe with the user's configured intelligence mode:

- ``"hybrid"``: Use cloud providers when online; transparently switch to the
  local MbowaGPT ecosystem whenever offline or cloud endpoints fail.
- ``"local"``: Stay strictly on the local MbowaGPT ecosystem (zero cloud calls).
- ``"online"``: Prefer configured cloud providers while still surfacing clear
  errors and optional fallback behavior.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_MODES = ("hybrid", "local", "online")
VALID_STATES = ("online", "degraded", "offline")

_PROBE_TARGETS: tuple[tuple[str, int], ...] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
)

_NETWORK_ERRNO_NAMES = (
    "ENETUNREACH",
    "EHOSTUNREACH",
    "ENETDOWN",
    "ECONNREFUSED",
    "EAI_AGAIN",
    "EAI_NONAME",
    "WSAENETUNREACH",
    "WSAEHOSTUNREACH",
    "WSAENETDOWN",
    "WSAECONNREFUSED",
    "WSAHOST_NOT_FOUND",
    "WSATRY_AGAIN",
)

_NETWORK_ERROR_SUBSTRINGS = (
    "getaddrinfo failed",
    "failed to resolve",
    "name or service not known",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "network is unreachable",
    "host is unreachable",
    "no route to host",
    "connection error",
    "connecterror",
    "connection aborted",
    "connection refused",
    "connection reset",
    "remotedisconnected",
    "apiconnectionerror",
    "apitimeouterror",
    "readtimeout",
    "connecttimeout",
    "dns resolution",
    "dns lookup",
    "offline",
)


def normalize_intelligence_mode(value: Any, default: str = "hybrid") -> str:
    """Normalize user/config mode string to one of hybrid|local|online."""
    if not isinstance(value, str):
        return default
    candidate = value.strip().lower()
    if candidate in VALID_MODES:
        return candidate
    if candidate in {"offline", "airgapped", "mbowagpt"}:
        return "local"
    if candidate in {"auto", "cloud+local"}:
        return "hybrid"
    return default


def is_network_error(exc_or_msg: Any) -> bool:
    """Return True if *exc_or_msg* looks like an offline/DNS/transport failure."""
    if exc_or_msg is None:
        return False

    # Walk exception chain if given an exception object
    seen: set[int] = set()
    cur: Any = exc_or_msg
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        cls_name = type(cur).__name__.lower() if isinstance(cur, BaseException) else ""
        if cls_name in {
            "connecterror",
            "connecttimeout",
            "apiconnectionerror",
            "apitimeouterror",
            "gaierror",
            "nameresolutionerror",
        }:
            return True
        if isinstance(cur, (ConnectionError, TimeoutError, socket.gaierror, socket.timeout)):
            return True
        if isinstance(cur, OSError) and getattr(cur, "errno", None) is not None:
            import errno as _errno

            for name in _NETWORK_ERRNO_NAMES:
                code = getattr(_errno, name, None)
                if code is not None and cur.errno == code:
                    return True
        msg = str(cur).lower()
        if any(token in msg for token in _NETWORK_ERROR_SUBSTRINGS):
            return True
        if not isinstance(cur, BaseException):
            break
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)

    return False


def _probe_tcp(targets: tuple[tuple[str, int], ...], timeout: float) -> bool:
    """Attempt fast non-HTTP TCP reachability check to public DNS IPs."""
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


class ConnectivityMonitor:
    """Cached, thread-safe connectivity tracker and mode coordinator."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: str = "online"
        self._mode: Optional[str] = None
        self._last_checked_at: float = 0.0
        self._last_error: str = ""
        self._last_provider: str = ""
        self._consecutive_failures: int = 0
        self._online_cache_ttl: float = 12.0
        self._offline_cache_ttl: float = 5.0
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

    def _probe_network(self, timeout: float = 0.7) -> bool:
        forced_offline = (os.getenv("HERMES_OFFLINE_FORCE") or "").strip().lower()
        if forced_offline in {"1", "true", "yes", "on"}:
            return False
        forced_online = (os.getenv("HERMES_ONLINE_FORCE") or "").strip().lower()
        if forced_online in {"1", "true", "yes", "on"}:
            return True
        return _probe_tcp(_PROBE_TARGETS, timeout=timeout)

    def _load_configured_mode(self) -> str:
        try:
            from hermes_cli.config import load_config

            cfg = load_config()
            intel = cfg.get("intelligence") if isinstance(cfg, dict) else {}
            if isinstance(intel, dict) and intel.get("mode"):
                return normalize_intelligence_mode(intel.get("mode"))
        except Exception:
            pass
        env_mode = os.getenv("HERMES_INTELLIGENCE_MODE")
        if env_mode:
            return normalize_intelligence_mode(env_mode)
        return "hybrid"

    def get_mode(self) -> str:
        with self._lock:
            if self._mode is None:
                self._mode = self._load_configured_mode()
            return self._mode

    def set_mode(self, mode: str, *, persist: bool = False) -> str:
        normalized = normalize_intelligence_mode(mode)
        if persist:
            try:
                from hermes_cli.config import save_config_value

                save_config_value("intelligence.mode", normalized)
            except Exception as exc:
                logger.warning("Failed to persist intelligence.mode=%s: %s", normalized, exc)
        snapshot: Optional[Dict[str, Any]] = None
        with self._lock:
            changed = self._mode != normalized
            self._mode = normalized
            if changed:
                snapshot = self._build_status_locked()
        if snapshot is not None:
            self._notify(snapshot)
        return normalized

    def probe(self, *, force: bool = False, timeout: float = 0.7) -> str:
        """Probe current internet state (cached for a few seconds)."""
        with self._lock:
            now = time.monotonic()
            ttl = self._offline_cache_ttl if self._state == "offline" else self._online_cache_ttl
            if not force and self._last_checked_at > 0 and (now - self._last_checked_at) < ttl:
                return self._state

        reachable = False
        try:
            reachable = bool(self._probe_network(timeout=timeout))
        except Exception as exc:
            logger.debug("Connectivity probe raised: %s", exc)
            reachable = False

        snapshot: Optional[Dict[str, Any]] = None
        with self._lock:
            prev = self._state
            self._last_checked_at = time.monotonic()
            if reachable:
                # If network just recovered, leave degraded alone only for the
                # explicit recovery transition; restore to online cleanly.
                self._state = "online"
                if prev == "offline":
                    self._consecutive_failures = 0
                    self._last_error = ""
            else:
                self._state = "offline"
            if prev != self._state:
                snapshot = self._build_status_locked()
            current_state = self._state

        if snapshot is not None:
            logger.info("Connectivity state changed: %s", current_state)
            self._notify(snapshot)
        return current_state

    def is_offline(self, *, force_probe: bool = False) -> bool:
        return self.probe(force=force_probe) == "offline"

    def is_online(self, *, force_probe: bool = False) -> bool:
        return self.probe(force=force_probe) != "offline"

    def should_use_local_first(self, *, force_probe: bool = False) -> bool:
        """Return True when intelligence/voice should immediately execute locally."""
        mode = self.get_mode()
        if mode == "local":
            return True
        if mode == "online":
            return False
        return self.probe(force=force_probe) == "offline"

    def report_cloud_failure(self, exc_or_msg: Any, *, provider: str = "") -> str:
        """Record a cloud request failure and update connectivity state."""
        network_down = is_network_error(exc_or_msg)
        # Double-check socket connectivity on suspicious transport errors so a single
        # provider outage while internet is fine becomes 'degraded', while total loss
        # becomes 'offline'.
        if network_down:
            try:
                reachable = bool(self._probe_network(timeout=0.5))
            except Exception:
                reachable = False
            new_state = "degraded" if reachable else "offline"
        else:
            new_state = "degraded"

        snapshot: Optional[Dict[str, Any]] = None
        with self._lock:
            prev = self._state
            self._consecutive_failures += 1
            self._last_checked_at = time.monotonic()
            self._last_error = str(exc_or_msg)[:300]
            if provider:
                self._last_provider = provider
            self._state = new_state
            if prev != self._state:
                snapshot = self._build_status_locked()
            result_state = self._state

        if snapshot is not None:
            logger.warning(
                "Cloud failure (%s): connectivity transitioned %s -> %s",
                provider or "unknown",
                prev,
                result_state,
            )
            self._notify(snapshot)
        return result_state

    def report_cloud_success(self, *, provider: str = "") -> str:
        """Record a healthy cloud completion and restore online state."""
        snapshot: Optional[Dict[str, Any]] = None
        with self._lock:
            prev = self._state
            self._state = "online"
            self._consecutive_failures = 0
            self._last_error = ""
            self._last_checked_at = time.monotonic()
            if provider:
                self._last_provider = provider
            if prev != "online":
                snapshot = self._build_status_locked()
            result_state = self._state

        if snapshot is not None:
            logger.info("Cloud connectivity restored (%s)", provider or "cloud")
            self._notify(snapshot)
        return result_state

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(callback)

        def _unsub() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return _unsub

    def _notify(self, snapshot: Dict[str, Any]) -> None:
        with self._lock:
            callbacks = list(self._listeners)
        for cb in callbacks:
            try:
                cb(dict(snapshot))
            except Exception as exc:
                logger.debug("Connectivity listener raised: %s", exc)

    def _build_status_locked(self) -> Dict[str, Any]:
        mode = self._mode or "hybrid"
        state = self._state
        active_tier = "local" if (mode == "local" or state == "offline") else "cloud"
        return {
            "mode": mode,
            "connectivity": state,
            "online": state != "offline",
            "offline": state == "offline",
            "degraded": state == "degraded",
            "active_tier": active_tier,
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error,
            "last_provider": self._last_provider,
            "last_checked_at": self._last_checked_at,
        }

    def get_status(self, *, probe_if_stale: bool = True) -> Dict[str, Any]:
        if probe_if_stale:
            self.probe(force=False)
        with self._lock:
            if self._mode is None:
                self._mode = self._load_configured_mode()
            return self._build_status_locked()


_MONITOR_SINGLETON: Optional[ConnectivityMonitor] = None
_MONITOR_LOCK = threading.Lock()


def get_connectivity_monitor() -> ConnectivityMonitor:
    """Return the process-wide ConnectivityMonitor singleton."""
    global _MONITOR_SINGLETON
    if _MONITOR_SINGLETON is None:
        with _MONITOR_LOCK:
            if _MONITOR_SINGLETON is None:
                _MONITOR_SINGLETON = ConnectivityMonitor()
    return _MONITOR_SINGLETON
