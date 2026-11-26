"""Regression tests for the production-hardening work.

Each test here pins a behaviour that an incident depended on. They are
invariants, not snapshots: none of them asserts a current numeric value that
routine tuning would change (pool sizes, quotas and thread counts are all read
from configuration), so changing a default does not break the suite — only
changing the *behaviour* does.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from tchuekam_backend.core import admission, concurrency, metrics, rbac_cache, redis_client
from tchuekam_backend.core.cache import CacheService, HybridCacheService
from tchuekam_backend.core.database import pool_settings
from tchuekam_backend.core.middleware import client_identity, route_label
from tchuekam_backend.core.rate_limiter import HybridRateLimiter, RateLimiter
from tchuekam_backend.core.request_context import sanitize_request_id
from tchuekam_backend.core.security import (
    PasswordHashingBusy,
    hash_password,
    hashing_capacity,
    verify_password,
)
from tchuekam_backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Database URL normalisation
# ---------------------------------------------------------------------------


def test_postgres_url_gets_an_explicit_driver():
    """A bare ``postgresql://`` URL must name its driver.

    SQLAlchemy 2.0 resolved the bare form to psycopg2 and 2.1 resolves it to
    psycopg (v3), so an un-suffixed URL raises ModuleNotFoundError at engine
    construction as soon as the installed driver is not the one the current
    SQLAlchemy expects. The app then fails to boot with no Postgres at all.
    """
    from tchuekam_backend.core.database import _normalise_database_url

    for raw in ("postgresql://u:p@h:5432/db", "postgres://u:p@h:5432/db"):
        normalised = _normalise_database_url(raw)
        assert normalised.startswith("postgresql+"), normalised
        # The legacy postgres:// scheme, which Render/Railway/Heroku hand out,
        # is not a scheme SQLAlchemy accepts.
        assert not normalised.startswith("postgres://")

    # Non-Postgres URLs are passed through untouched.
    assert _normalise_database_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_pool_is_explicitly_sized():
    """Pool sizing must be explicit, not SQLAlchemy's default.

    The defaults (5 + 10) cap a worker at 15 connections while FastAPI runs
    sync endpoints in a 40-thread pool, so threads queue on checkout and fail
    after pool_timeout.
    """
    settings = pool_settings()
    for key in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle"):
        assert key in settings
        assert settings[key] > 0

    # The point of the timeout is to fail fast rather than queue past the
    # client's own deadline; SQLAlchemy's 30s default does the opposite.
    assert settings["pool_timeout"] <= 30


# ---------------------------------------------------------------------------
# Thread pool / connection pool alignment
# ---------------------------------------------------------------------------


def test_thread_limit_does_not_exceed_connection_pool():
    """The thread pool must not be wider than the connection pool.

    This is the defect that produced congestion collapse: 40 AnyIO threads
    against 20 connections left half the threads waiting in
    ``QueuePool._do_get`` for the full pool_timeout, returning 500s while the
    CPU sat idle and no SQL was executing.
    """
    settings = pool_settings()
    limit = concurrency.recommended_thread_limit()
    assert limit <= settings["pool_size"] + settings["max_overflow"], (
        f"thread limit {limit} exceeds connection pool "
        f"{settings['pool_size'] + settings['max_overflow']}"
    )


def test_admission_limit_tracks_thread_limit():
    """Admission control must not admit more work than there are threads."""
    assert admission.default_max_concurrent() <= concurrency.recommended_thread_limit()


def test_admission_queue_timeout_is_shorter_than_pool_timeout():
    """Rejecting must happen before a request can burn a pool timeout.

    If the admission queue waited longer than ``pool_timeout``, an admitted
    request could still spend the full pool timeout waiting for a connection —
    exactly the wasted work admission control exists to prevent.
    """
    mw = admission.ConcurrencyLimitMiddleware(app=None)
    assert mw.queue_timeout < pool_settings()["pool_timeout"]


# ---------------------------------------------------------------------------
# Security headers, request ids, error envelopes
# ---------------------------------------------------------------------------


def test_security_headers_present_on_every_response():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in response.headers
    assert "referrer-policy" in response.headers


def test_request_id_is_generated_echoed_and_returned():
    generated = client.get("/api/v1/health").headers["x-request-id"]
    assert generated

    echoed = client.get("/api/v1/health", headers={"X-Request-Id": "trace-abc.123"})
    assert echoed.headers["x-request-id"] == "trace-abc.123"


@pytest.mark.parametrize(
    "hostile",
    [
        "bad\r\nInjected: evil",
        "a" * 400,
        "   ",
        "drop\ntable",
    ],
)
def test_request_id_cannot_inject_into_logs(hostile):
    """A client-supplied id lands in log lines, so it must be sanitised.

    A newline would let a caller forge log entries; an unbounded length would
    let them inflate every line.
    """
    cleaned = sanitize_request_id(hostile)
    assert "\n" not in cleaned and "\r" not in cleaned and " " not in cleaned
    assert 0 < len(cleaned) <= 128


def test_error_envelope_carries_the_request_id():
    """Without it, a user's bug report cannot be matched to a server log line."""
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["request_id"] == response.headers["x-request-id"]


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def test_liveness_does_not_depend_on_the_database():
    """Liveness must not check the database.

    A liveness probe that failed on a database incident would restart every
    worker. Restarting repairs nothing and the reconnect storm deepens the
    outage.
    """
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_dependencies_and_degradation():
    response = client.get("/readyz")
    body = response.json()
    for key in ("status", "accepting_traffic", "database", "redis", "db_pool", "degraded"):
        assert key in body


def test_metrics_endpoint_exports_counters():
    client.get("/api/v1/health")
    body = client.get("/metrics").text
    assert "tchuekam_http_requests_total" in body
    assert "tchuekam_db_pool_connections" in body


def test_probe_paths_are_not_turned_into_metric_series():
    """Probes run every few seconds per instance.

    Counting them would swamp real traffic in every rate and percentile, and
    make an error-rate panel read as healthy during an outage.
    """
    for path in ("/livez", "/readyz"):
        client.get(path)
    body = client.get("/metrics").text
    assert 'path="/livez"' not in body
    assert 'path="/readyz"' not in body


def test_route_label_is_low_cardinality():
    """Metric path labels must be route templates, not request URLs.

    A raw URL as a label creates one Prometheus time series per distinct path,
    so ``/users/<uuid>`` would create one per user and exhaust the metrics
    backend's memory.
    """
    assert route_label({}) == "__unmatched__"

    class _Route:
        path = "/api/v1/users/{user_id}"

    assert route_label({"route": _Route()}) == "/api/v1/users/{user_id}"


# ---------------------------------------------------------------------------
# Client identity behind a proxy
# ---------------------------------------------------------------------------


def test_forwarded_for_is_ignored_unless_proxies_are_declared(monkeypatch):
    """X-Forwarded-For must not be trusted by default.

    The header is client-controlled. Trusting it without declaring how many
    proxies sit in front lets any caller bypass a per-IP quota by sending a
    fresh value on every request.
    """
    monkeypatch.delenv("TCHUEKAM_TRUSTED_PROXY_COUNT", raising=False)
    scope = {
        "client": ("203.0.113.9", 1234),
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
    }
    assert client_identity(scope) == "203.0.113.9"


def test_forwarded_for_is_read_from_the_right_end(monkeypatch):
    """With one declared proxy, the client is the last XFF entry.

    Each proxy appends, so the right-most entries are the trustworthy ones.
    Reading the left-most would read whatever the caller injected.
    """
    monkeypatch.setenv("TCHUEKAM_TRUSTED_PROXY_COUNT", "1")
    scope = {
        "client": ("10.0.0.1", 1234),
        "headers": [(b"x-forwarded-for", b"spoofed, 5.6.7.8")],
    }
    assert client_identity(scope) == "5.6.7.8"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_sliding_window_stops_at_the_quota():
    limiter = RateLimiter()
    outcomes = [limiter.is_allowed("k", 5, 60) for _ in range(7)]
    assert [allowed for allowed, _ in outcomes] == [True] * 5 + [False] * 2
    assert [remaining for _, remaining in outcomes] == [4, 3, 2, 1, 0, 0, 0]


def test_rate_limiter_is_thread_safe():
    """Sync endpoints share the limiter across thread-pool threads.

    Without a lock, two threads read the same counter and both write, letting
    more requests through than the quota allows.
    """
    limiter = RateLimiter()
    allowed = []
    lock = threading.Lock()

    def hammer():
        ok, _ = limiter.is_allowed("shared", 50, 60)
        with lock:
            allowed.append(ok)

    threads = [threading.Thread(target=hammer) for _ in range(120)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(allowed) == 50


def test_rate_limiter_falls_back_when_redis_is_unreachable(monkeypatch):
    """A Redis outage must degrade the quota, not fail requests.

    A process-local quota is still a useful protection; returning 500 on every
    request during a Redis incident is not.
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # nothing listening
    redis_client.reset_for_tests()
    limiter = HybridRateLimiter()

    allowed, _ = limiter.is_allowed("fallback", 3, 60)
    assert allowed is True
    assert limiter.is_process_local is True

    redis_client.reset_for_tests()


def test_cache_falls_back_when_redis_is_unreachable(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    redis_client.reset_for_tests()
    cache = HybridCacheService()

    cache.set("k", {"v": 1}, ttl_seconds=30)
    assert cache.get("k") == {"v": 1}

    redis_client.reset_for_tests()


def test_cache_invalidate_pattern_only_removes_the_prefix():
    cache = CacheService()
    cache.set("rbac:user:1", ["a"])
    cache.set("rbac:user:2", ["b"])
    cache.set("other:1", ["c"])

    assert cache.invalidate_pattern("rbac:") == 2
    assert cache.get("rbac:user:1") is None
    assert cache.get("other:1") == ["c"]


def test_global_quota_is_wired_and_gated(monkeypatch):
    """The global quota must actually be applied, and off in tests.

    ``RATE_LIMIT_GLOBAL_PER_MINUTE`` existed as a setting that no code path
    read: only login and one biocompute route were limited, so every other
    endpoint was unbounded.
    """
    from tchuekam_backend.core.middleware import is_rate_limiting_enabled

    monkeypatch.setenv("TCHUEKAM_RATE_LIMIT_ENABLED", "1")
    assert is_rate_limiting_enabled() is True
    monkeypatch.setenv("TCHUEKAM_RATE_LIMIT_ENABLED", "0")
    assert is_rate_limiting_enabled() is False


def test_probe_paths_bypass_the_quota():
    """Throttling probes would pull a healthy instance out of rotation."""
    from tchuekam_backend.core.middleware import _is_probe_path

    for path in ("/health", "/healthz", "/readyz", "/livez", "/metrics", "/api/v1/health"):
        assert _is_probe_path(path) is True
    assert _is_probe_path("/api/v1/users/me") is False


# ---------------------------------------------------------------------------
# RBAC caching
# ---------------------------------------------------------------------------


def test_rbac_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TCHUEKAM_RBAC_CACHE_TTL", "0")
    assert rbac_cache.is_enabled() is False
    monkeypatch.setenv("TCHUEKAM_RBAC_CACHE_TTL", "30")
    assert rbac_cache.is_enabled() is True


def test_rbac_cache_ttl_bounds_staleness(monkeypatch):
    """A TTL must always apply.

    Explicit invalidation covers the normal path, but not a direct database
    write nor the cache-aside race where a reader stores a value a concurrent
    mutation has already invalidated. The TTL is what bounds how long a revoked
    permission can still be honoured.
    """
    monkeypatch.delenv("TCHUEKAM_RBAC_CACHE_TTL", raising=False)
    assert 0 < rbac_cache.cache_ttl_seconds() <= 300


def test_rbac_role_change_invalidates_the_cached_decision(db_session):
    """Downgrading a user must take effect immediately, not after the TTL."""
    from tchuekam_backend.repositories.user_repository import UserRepository
    from tchuekam_backend.services.rbac_service import RbacService

    service = RbacService(db_session)
    service.seed_default_roles_and_permissions()
    user = UserRepository(db_session).create(
        email="rbac-invalidation@tchuekam.com", password_hash="x", is_verified=True
    )

    admin = service.rbac_repo.get_role_by_name("Admin")
    service.assign_user_roles(user.id, [admin.id])
    assert service.has_permission(user.id, "users", "profile", "READ") is True

    plain = service.rbac_repo.get_role_by_name("User")
    service.assign_user_roles(user.id, [plain.id])
    assert service.has_permission(user.id, "users", "profile", "READ") is False


def test_rbac_permission_change_invalidates_every_holder(db_session):
    """Removing a permission from a role must affect its holders at once."""
    from tchuekam_backend.repositories.user_repository import UserRepository
    from tchuekam_backend.services.rbac_service import RbacService

    service = RbacService(db_session)
    service.seed_default_roles_and_permissions()
    user = UserRepository(db_session).create(
        email="rbac-role-perms@tchuekam.com", password_hash="x", is_verified=True
    )

    admin = service.rbac_repo.get_role_by_name("Admin")
    service.assign_user_roles(user.id, [admin.id])
    assert service.has_permission(user.id, "users", "profile", "READ") is True

    audit_only = service.rbac_repo.get_permission_by_name("audit.read")
    service.rbac_repo.assign_permissions_to_role(admin.id, [audit_only.id])

    assert service.has_permission(user.id, "users", "profile", "READ") is False
    assert service.has_permission(user.id, "audit", "logs", "READ") is True


def test_rbac_seed_is_idempotent(db_session):
    """Re-seeding must not duplicate or fail.

    Every worker runs the seed at boot. The advisory lock serialises them, but
    it fails open where advisory locks are unavailable, so the seed itself has
    to tolerate being run twice.
    """
    from tchuekam_backend.domain.models import Permission, Role
    from tchuekam_backend.services.rbac_service import RbacService

    service = RbacService(db_session)
    service.seed_default_roles_and_permissions()
    roles_first = db_session.query(Role).count()
    perms_first = db_session.query(Permission).count()

    service.seed_default_roles_and_permissions()
    assert db_session.query(Role).count() == roles_first
    assert db_session.query(Permission).count() == perms_first


# ---------------------------------------------------------------------------
# Password hashing concurrency
# ---------------------------------------------------------------------------


def test_password_hashing_memory_is_bounded():
    """Concurrent Argon2 memory must be bounded.

    Argon2id reserves its memory cost per in-flight verification. Unbounded,
    a login burst reserves (concurrent logins x memory_cost) and the process
    is killed by the OOM killer.
    """
    capacity = hashing_capacity()
    assert capacity["slots"] >= 1
    # Keep the worst case within a sane container budget (1 GiB).
    assert capacity["max_resident_kib"] <= 1024 * 1024


def test_password_round_trip_still_works():
    digest = hash_password("Password123!")
    assert verify_password("Password123!", digest) is True
    assert verify_password("wrong", digest) is False


def test_hashing_saturation_raises_rather_than_denying_access(monkeypatch):
    """Saturation must not be reported as a wrong password.

    Returning False would lock out legitimate users during a load spike and
    send them to reset a password that was correct.
    """
    import tchuekam_backend.core.security as security

    monkeypatch.setattr(security, "_HASHING_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(security, "_HASHING_WAIT_SECONDS", 0.05)

    security._HASHING_SLOTS.acquire()  # occupy the only slot
    try:
        with pytest.raises(PasswordHashingBusy):
            security.verify_password("x", "pbkdf2_sha256$1$YQ==$YQ==")
    finally:
        security._HASHING_SLOTS.release()


def test_hashing_saturation_is_reported_as_503(monkeypatch):
    """A 503, not a 500: nothing is broken, the service is busy."""
    import tchuekam_backend.core.security as security

    monkeypatch.setattr(security, "_HASHING_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(security, "_HASHING_WAIT_SECONDS", 0.05)

    security._HASHING_SLOTS.acquire()
    try:
        response = client.post(
            "/api/v1/auth/signin",
            json={"email": "someone@tchuekam.com", "password": "Password123!"},
        )
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "SERVICE_OVERLOADED"
        assert response.headers["retry-after"] == "2"
    finally:
        security._HASHING_SLOTS.release()


# ---------------------------------------------------------------------------
# WebSocket resource bounds
# ---------------------------------------------------------------------------


def test_websocket_connection_caps_are_configured():
    """Per-user and global socket caps must exist.

    Without them one account can open as many sockets as the process has file
    descriptors.
    """
    from tchuekam_backend.api.ws import notifications

    assert notifications.max_connections_per_user() >= 1
    assert notifications.max_connections_total() >= notifications.max_connections_per_user()


def test_websocket_auth_does_not_hold_a_database_session():
    """The WebSocket handler must not depend on a request-scoped DB session.

    A ``Depends(get_db)`` on a WebSocket route holds its SQL connection for the
    whole life of the socket. A thousand sockets would pin a thousand
    connections against a pool of a few dozen, blocking the entire API.
    """
    import inspect

    from tchuekam_backend.api.ws.notifications import websocket_security_alerts

    params = inspect.signature(websocket_security_alerts).parameters
    for param in params.values():
        assert "Depends" not in repr(param.default), (
            f"{param.name} uses a request-scoped dependency; the socket would "
            "hold it for its whole lifetime"
        )


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def test_json_formatter_merges_structured_messages():
    """Middleware already emits JSON; it must not be double-encoded.

    Nested as an escaped string, its fields are not queryable by the log
    collector, which defeats the point of emitting JSON at all.
    """
    import logging

    from tchuekam_backend.core.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg=json.dumps({"event": "http_access", "status": 200}), args=(), exc_info=None,
    )
    rendered = json.loads(JsonFormatter().format(record))
    assert rendered["event"] == "http_access"
    assert rendered["status"] == 200
    assert "message" not in rendered


def test_logging_is_configured_so_info_is_not_discarded():
    """The root logger must have a handler.

    With none, Python falls back to ``logging.lastResort``, which drops
    everything below WARNING — silently discarding every access log line.
    """
    import logging

    from tchuekam_backend.core.logging_config import configure_logging

    configure_logging(force=True)
    root = logging.getLogger()
    assert root.handlers, "root logger has no handler; INFO records are dropped"
    assert root.level <= logging.INFO
