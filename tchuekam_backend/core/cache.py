"""TTL cache for high-frequency lookups (RBAC permissions, roles).

Two implementations share one interface:

``CacheService``
    Process-local dict with TTL expiry. Correct for a single worker.

``RedisCacheService``
    Same interface over Redis, so every worker reads the same entry and an
    invalidation performed by one worker is seen by all of them.

``HybridCacheService`` (exposed as the global ``cache_service``)
    Uses Redis when it is reachable and the process-local dict otherwise.

Why there is no in-process L1 in front of Redis
-----------------------------------------------
This cache backs permission checks. An L1 copy inside each worker cannot be
reached by another worker's ``invalidate_pattern``, so revoking a role would
keep granting access for the length of the L1 TTL on every worker that had
already cached it. A Redis round trip is ~0.2 ms against ~2 ms for the two
Postgres queries it replaces, so the L1 buys little and costs correctness.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from tchuekam_backend.core import redis_client

logger = logging.getLogger("tchuekam_backend.cache")

#: Batch size for the SCAN cursor used by pattern invalidation.
_SCAN_COUNT = 500

#: Upper bound on keys deleted by one ``invalidate_pattern`` call. Pattern
#: invalidation is rare (a role or permission changed), but an unbounded SCAN
#: against a large shared Redis would hold a connection for an unbounded time.
_SCAN_MAX_KEYS = 100_000


class CacheService:
    """Thread-safe in-memory cache with TTL expiration and pattern-based invalidation."""

    is_process_local = True

    def __init__(self, default_ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """Retrieves an entry if it exists and has not expired."""
        with self._lock:
            if key not in self._cache:
                return None

            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores a key-value pair with a TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Deletes a specific key from the cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_pattern(self, prefix: str) -> int:
        """Invalidates all cache keys starting with prefix."""
        count = 0
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]
                count += 1
        return count

    def clear(self) -> None:
        """Flushes the entire cache."""
        with self._lock:
            self._cache.clear()


class RedisCacheService:
    """Shared cache backed by Redis string keys with native TTL expiry."""

    is_process_local = False

    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl = default_ttl_seconds

    @staticmethod
    def _redis_key(key: str) -> str:
        return redis_client.namespaced("cache", key)

    def get(self, key: str) -> Optional[Any]:
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")
        try:
            raw = client.get(self._redis_key(key))
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            # A value written by an older build, or corrupted. Treat it as a
            # miss rather than raising into the request path; the caller will
            # recompute and overwrite it.
            logger.warning("Entrée de cache illisible pour %s, ignorée.", key)
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError) as exc:
            # Not every object survives a JSON round trip. Refusing here lets
            # the hybrid fall back to the in-process cache instead of silently
            # dropping the entry.
            raise TypeError(f"Valeur non sérialisable en JSON pour la clé {key}") from exc
        try:
            client.set(self._redis_key(key), payload, ex=max(1, int(ttl)))
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc

    def delete(self, key: str) -> bool:
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")
        try:
            return bool(client.delete(self._redis_key(key)))
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc

    def invalidate_pattern(self, prefix: str) -> int:
        """Deletes every shared key whose logical name starts with ``prefix``.

        ``SCAN`` is used rather than ``KEYS`` because ``KEYS`` blocks the Redis
        server for the length of the sweep, which on a shared instance stalls
        every other client.
        """
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")
        # Escape glob metacharacters so a prefix containing e.g. "[" matches
        # literally instead of being read as a character class.
        escaped = (
            self._redis_key(prefix)
            .replace("\\", "\\\\")
            .replace("*", "\\*")
            .replace("?", "\\?")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        pattern = f"{escaped}*"
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=_SCAN_COUNT)
                if keys:
                    deleted += int(client.delete(*keys) or 0)
                if cursor == 0 or deleted >= _SCAN_MAX_KEYS:
                    break
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc
        return deleted

    def clear(self) -> None:
        """Drops every key owned by this service (not the whole database)."""
        self.invalidate_pattern("")


class HybridCacheService:
    """Reads and writes Redis when reachable, the process-local dict otherwise.

    Invalidation is applied to *both* backends. During a Redis outage entries
    accumulate in process memory; once Redis returns, a later invalidation
    must still clear those local copies or a worker would keep serving a stale
    permission set from before the outage.
    """

    def __init__(self, default_ttl_seconds: int = 300):
        self._memory = CacheService(default_ttl_seconds=default_ttl_seconds)
        self._redis = RedisCacheService(default_ttl_seconds=default_ttl_seconds)

    @property
    def is_process_local(self) -> bool:
        return not self.backend_is_shared()

    def backend_is_shared(self) -> bool:
        return redis_client.is_configured() and redis_client.get_sync_client() is not None

    def get(self, key: str) -> Optional[Any]:
        if redis_client.is_configured():
            try:
                return self._redis.get(key)
            except RuntimeError:
                pass
        return self._memory.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        if redis_client.is_configured():
            try:
                self._redis.set(key, value, ttl_seconds)
                return
            except TypeError:
                # Not JSON-serialisable: keep it process-local rather than
                # dropping it, and say so once so the caller can be fixed.
                logger.debug("Valeur non sérialisable pour %s, cache local utilisé.", key)
            except RuntimeError:
                pass
        self._memory.set(key, value, ttl_seconds)

    def delete(self, key: str) -> bool:
        removed = False
        if redis_client.is_configured():
            try:
                removed = self._redis.delete(key)
            except RuntimeError:
                pass
        return self._memory.delete(key) or removed

    def invalidate_pattern(self, prefix: str) -> int:
        count = 0
        if redis_client.is_configured():
            try:
                count += self._redis.invalidate_pattern(prefix)
            except RuntimeError:
                pass
        return count + self._memory.invalidate_pattern(prefix)

    def clear(self) -> None:
        if redis_client.is_configured():
            try:
                self._redis.clear()
            except RuntimeError:
                pass
        self._memory.clear()


# Global cache instance for high-frequency application lookups
cache_service = HybridCacheService(default_ttl_seconds=300)
