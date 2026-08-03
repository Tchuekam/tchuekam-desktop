"""
In-memory TTL cache service for high-performance data retrieval (e.g., RBAC permissions, roles).
"""

import time
import threading
from typing import Any, Dict, Optional, Tuple


class CacheService:
    """Thread-safe in-memory cache with TTL expiration and pattern-based invalidation."""

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


# Global cache instance for high-frequency application lookups
cache_service = CacheService(default_ttl_seconds=300)
