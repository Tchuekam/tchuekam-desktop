"""Shared Redis backplane for multi-worker / multi-instance deployments.

Why this module exists
----------------------
The backend keeps four pieces of state that *must* be shared once more than
one process serves traffic:

* the rate-limit counters (``core.rate_limiter``),
* the JWT revocation list (``core.security``),
* the RBAC permission cache (``core.cache``),
* the set of live WebSocket subscribers (``api.ws.notifications``).

Held in process memory, each of those is wrong the moment a second worker
exists: quotas multiply by the worker count, a revoked token stays valid on
every worker but the one that revoked it, a cache invalidation reaches one
worker out of N, and a security alert reaches only the subscribers that
happen to share a process with the publisher.

Design rules
------------
1. **Optional.** With no ``REDIS_URL`` configured the helpers return ``None``
   and every caller falls back to its in-process implementation. That keeps
   local development, the test suite and single-worker deploys working with
   no Redis at all.
2. **Fail-open, never fail-shut.** A Redis outage must degrade the quota and
   the cache, not take the API down. Every accessor swallows connection
   errors, logs at most once per cooldown window, and reports unavailability
   so the caller can fall back.
3. **Both drivers.** Service-layer code is synchronous (FastAPI runs ``def``
   endpoints in a worker thread); middleware and the WebSocket channel are
   asynchronous. Calling the sync client from the event loop would block it,
   so both a sync and an async pool are managed here.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("tchuekam_backend.redis")

#: Seconds between two "Redis is unavailable" log lines. Without a cooldown a
#: Redis outage turns every single request into a log line.
_LOG_COOLDOWN_SECONDS = 30.0

#: How long to wait before retrying after a connection failure. Retrying on
#: every request during an outage adds a full connect timeout to each one.
_RETRY_BACKOFF_SECONDS = 5.0

_CONNECT_TIMEOUT_SECONDS = 2.0
_OPERATION_TIMEOUT_SECONDS = 2.0


def redis_url() -> str:
    """Configured Redis URL, or an empty string when Redis is not in use."""
    for key in ("TCHUEKAM_REDIS_URL", "REDIS_URL"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def is_configured() -> bool:
    """True when a Redis URL is configured (it may still be unreachable)."""
    return bool(redis_url())


def key_prefix() -> str:
    """Namespace for every key written by this backend.

    Deployments routinely share one Redis instance between staging and
    production, or between this service and another. An explicit prefix keeps
    a ``FLUSHDB`` or a key collision in one from corrupting the other.
    """
    return os.getenv("TCHUEKAM_REDIS_PREFIX", "tchuekam").strip() or "tchuekam"


def namespaced(*parts: str) -> str:
    """Build a prefixed key, e.g. ``namespaced("rl", "ip:1.2.3.4")``."""
    return ":".join((key_prefix(), *parts))


class _ClientState:
    """Tracks one driver's client plus its failure/backoff bookkeeping."""

    def __init__(self, name: str):
        self.name = name
        self.client: Any = None
        self.lock = threading.Lock()
        self.last_failure_at = 0.0
        self.last_log_at = 0.0
        self.unavailable = False

    def should_retry(self) -> bool:
        if not self.unavailable:
            return True
        return (time.monotonic() - self.last_failure_at) >= _RETRY_BACKOFF_SECONDS

    def note_failure(self, exc: BaseException) -> None:
        now = time.monotonic()
        self.unavailable = True
        self.last_failure_at = now
        if (now - self.last_log_at) >= _LOG_COOLDOWN_SECONDS:
            self.last_log_at = now
            logger.warning(
                "Redis (%s) unavailable, falling back to in-process state: %s",
                self.name,
                exc,
            )

    def note_success(self) -> None:
        if self.unavailable:
            logger.info("Redis (%s) connection restored.", self.name)
        self.unavailable = False


_sync_state = _ClientState("sync")
_async_state = _ClientState("async")


def get_sync_client() -> Optional[Any]:
    """Return a connected synchronous Redis client, or ``None``.

    Safe to call from a worker thread. Never raises: a missing driver, a
    missing URL or an unreachable server all return ``None``.
    """
    url = redis_url()
    if not url:
        return None

    state = _sync_state
    if state.client is not None:
        return state.client
    if not state.should_retry():
        return None

    with state.lock:
        if state.client is not None:
            return state.client
        if not state.should_retry():
            return None
        try:
            import redis as redis_sync

            client = redis_sync.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                socket_timeout=_OPERATION_TIMEOUT_SECONDS,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=_max_connections(),
            )
            client.ping()
        except Exception as exc:  # ImportError, ConnectionError, TimeoutError...
            state.note_failure(exc)
            return None
        state.note_success()
        state.client = client
        return client


async def get_async_client() -> Optional[Any]:
    """Return a connected asynchronous Redis client, or ``None``.

    Safe to call from the event loop. Never raises.
    """
    url = redis_url()
    if not url:
        return None

    state = _async_state
    if state.client is not None:
        return state.client
    if not state.should_retry():
        return None

    try:
        import redis.asyncio as redis_async

        client = redis_async.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=_OPERATION_TIMEOUT_SECONDS,
            health_check_interval=30,
            retry_on_timeout=True,
            max_connections=_max_connections(),
        )
        await client.ping()
    except Exception as exc:
        state.note_failure(exc)
        return None
    state.note_success()
    # Last writer wins: two coroutines racing here both produce a working
    # client, and the loser's is dropped without having opened a connection
    # beyond the ping (the pool is lazy).
    state.client = client
    return client


def _max_connections() -> int:
    """Per-process Redis connection cap.

    Each worker needs far fewer Redis connections than HTTP connections —
    every operation here is sub-millisecond — but the cap has to exceed the
    thread-pool width or sync endpoints will serialise on connection checkout.
    """
    raw = os.getenv("TCHUEKAM_REDIS_MAX_CONNECTIONS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 64


def report_failure(exc: BaseException, *, is_async: bool = False) -> None:
    """Record an operation-time failure so callers back off together.

    ``get_*_client`` only validates the connection once, at creation. When a
    later command fails because the server went away, the caller reports it
    here: the cached client is dropped and the backoff window opens, so the
    next request falls back immediately instead of paying a timeout.
    """
    state = _async_state if is_async else _sync_state
    state.client = None
    state.note_failure(exc)


def reset_for_tests() -> None:
    """Drop cached clients and failure state (test-suite helper)."""
    for state in (_sync_state, _async_state):
        state.client = None
        state.unavailable = False
        state.last_failure_at = 0.0
        state.last_log_at = 0.0


def health() -> dict:
    """Readiness snapshot for the ``/readyz`` probe and ``/metrics``."""
    if not is_configured():
        return {"configured": False, "available": False, "degraded": False}
    client = get_sync_client()
    if client is None:
        return {"configured": True, "available": False, "degraded": True}
    try:
        client.ping()
    except Exception as exc:
        report_failure(exc)
        return {"configured": True, "available": False, "degraded": True}
    return {"configured": True, "available": True, "degraded": False}
