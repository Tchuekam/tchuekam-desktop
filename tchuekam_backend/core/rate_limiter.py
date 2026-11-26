"""Limiteur de débit (Rate Limiter) et protection anti-brute force.

Deux implémentations partagent la même interface :

``RateLimiter``
    Fenêtre glissante en mémoire de processus, bornée et thread-safe. Elle
    protège un déploiement mono-worker. Derrière plusieurs workers uvicorn ou
    plusieurs instances, chaque processus applique son propre quota et le
    seuil effectif est multiplié par le nombre de processus.

``RedisRateLimiter``
    Même fenêtre glissante, mais portée par un ``ZSET`` Redis et un script
    Lua, donc atomique et partagée par tous les workers et toutes les
    instances. C'est l'implémentation requise en production multi-worker.

``HybridRateLimiter`` (exposée via la variable globale ``rate_limiter``)
    Route chaque appel vers Redis quand il est disponible, et retombe sur la
    version mémoire sinon. Une panne de Redis dégrade donc le quota (il
    redevient local au processus) au lieu de rendre l'API indisponible.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Dict, List, Optional, Protocol, Tuple

from tchuekam_backend.core import redis_client

logger = logging.getLogger("tchuekam_backend.rate_limiter")

#: Nombre maximum de clés conservées simultanément. La clé anti-force-brute
#: contient l'email fourni par le client : sans plafond ni purge, un attaquant
#: qui varie l'email à chaque requête fait croître le dictionnaire
#: indéfiniment (épuisement mémoire).
MAX_TRACKED_KEYS = 50_000

#: Intervalle minimum entre deux purges complètes, en secondes.
_SWEEP_INTERVAL_SECONDS = 60.0


class RateLimiterProtocol(Protocol):
    """Interface commune aux implémentations mémoire et Redis."""

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        ...

    def reset(self, key: str) -> None:
        ...


class RateLimiter:
    """Limiteur de débit à fenêtre glissante, borné en mémoire et thread-safe."""

    #: Le quota n'est pas partagé entre processus (voir docstring du module).
    is_process_local = True

    def __init__(self, max_tracked_keys: int = MAX_TRACKED_KEYS):
        # Clé -> liste d'horodatages (float)
        self._requests: Dict[str, List[float]] = {}
        self._max_tracked_keys = max_tracked_keys
        # Les endpoints FastAPI synchrones s'exécutent dans un pool de threads :
        # sans verrou, deux requêtes concurrentes lisent le même compteur puis
        # l'écrivent chacune, ce qui laisse passer plus de tentatives que le
        # quota autorisé.
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep_locked(self, now: float) -> None:
        """Supprime les clés dont toutes les tentatives sont hors fenêtre."""
        self._last_sweep = time.monotonic()
        stale = [
            key
            for key, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] <= now
        ]
        for key in stale:
            del self._requests[key]

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Vérifie si une requête identifiée par `key` est autorisée.

        Returns:
            (is_allowed, remaining_attempts)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Purge périodique amortie : on utilise le cutoff courant comme
            # borne d'obsolescence, ce qui suffit pour les fenêtres homogènes
            # utilisées par l'application.
            if time.monotonic() - self._last_sweep >= _SWEEP_INTERVAL_SECONDS:
                self._sweep_locked(cutoff)

            timestamps = [ts for ts in self._requests.get(key, ()) if ts > cutoff]

            if len(timestamps) >= max_requests:
                self._requests[key] = timestamps
                return False, 0

            # Plafond dur : si le dictionnaire est saturé de clés actives, on
            # purge puis, en dernier recours, on refuse la nouvelle clé plutôt
            # que de laisser la mémoire croître sans limite.
            if key not in self._requests and len(self._requests) >= self._max_tracked_keys:
                self._sweep_locked(cutoff)
                if len(self._requests) >= self._max_tracked_keys:
                    return False, 0

            timestamps.append(now)
            self._requests[key] = timestamps
            return True, max_requests - len(timestamps)

    def reset(self, key: str) -> None:
        """Réinitialise l'historique pour une clé (ex: après connexion réussie)."""
        with self._lock:
            self._requests.pop(key, None)

    def tracked_keys(self) -> int:
        """Nombre de clés actuellement suivies (observabilité et tests)."""
        with self._lock:
            return len(self._requests)


#: Fenêtre glissante atomique.
#:
#: ``ZREMRANGEBYSCORE`` purge les horodatages sortis de la fenêtre, ``ZCARD``
#: compte ce qui reste, et l'insertion n'a lieu que sous le quota. Les trois
#: opérations doivent être atomiques : exécutées en commandes séparées, deux
#: requêtes concurrentes lisent le même ``ZCARD`` puis insèrent toutes les
#: deux, ce qui laisse passer plus que le quota — exactement le défaut que le
#: verrou corrige dans la version mémoire.
#:
#: Le membre inséré porte un suffixe aléatoire : deux requêtes arrivées dans
#: la même milliseconde produiraient sinon le même membre, et ``ZADD`` en
#: écraserait une (deux requêtes comptées comme une seule).
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('PEXPIRE', key, window_ms)
  return {0, 0}
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, limit - count - 1}
"""


class RedisRateLimiter:
    """Fenêtre glissante partagée entre tous les workers, via Redis."""

    is_process_local = False

    def __init__(self) -> None:
        self._script_sha: Optional[str] = None
        self._lock = threading.Lock()

    @staticmethod
    def _redis_key(key: str) -> str:
        return redis_client.namespaced("rl", key)

    def _eval(self, client, key: str, args: list) -> Optional[list]:
        """Exécute le script Lua, en le chargeant (``EVALSHA``) si besoin."""
        sha = self._script_sha
        if sha:
            try:
                return client.evalsha(sha, 1, key, *args)
            except Exception as exc:
                # Un ``NOSCRIPT`` survient après un redémarrage de Redis ou un
                # ``SCRIPT FLUSH`` : on recharge au lieu d'échouer.
                if "NOSCRIPT" not in str(exc).upper():
                    raise
                with self._lock:
                    self._script_sha = None
        loaded = client.script_load(_SLIDING_WINDOW_LUA)
        with self._lock:
            self._script_sha = loaded
        return client.evalsha(loaded, 1, key, *args)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Comme ``RateLimiter.is_allowed``, mais le quota est global.

        Raises:
            RuntimeError: si Redis est injoignable. L'appelant
                (``HybridRateLimiter``) rattrape et retombe sur la mémoire.
        """
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")

        now_ms = int(time.time() * 1000)
        member = f"{now_ms}-{secrets.token_hex(8)}"
        try:
            result = self._eval(
                client,
                self._redis_key(key),
                [now_ms, int(window_seconds * 1000), int(max_requests), member],
            )
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc

        allowed = bool(result and int(result[0]) == 1)
        remaining = int(result[1]) if result and len(result) > 1 else 0
        return allowed, remaining

    def reset(self, key: str) -> None:
        client = redis_client.get_sync_client()
        if client is None:
            raise RuntimeError("Redis indisponible")
        try:
            client.delete(self._redis_key(key))
        except Exception as exc:
            redis_client.report_failure(exc)
            raise RuntimeError(f"Échec de l'opération Redis : {exc}") from exc


class HybridRateLimiter:
    """Route vers Redis quand il répond, vers la mémoire sinon.

    La dégradation est volontairement silencieuse côté appelant : un quota
    local au processus reste une protection utile, alors qu'une erreur 500 sur
    chaque requête pendant une panne Redis ne l'est pas. ``redis_client``
    journalise l'indisponibilité (avec une temporisation) et ouvre une fenêtre
    de backoff, donc les requêtes suivantes basculent sans payer de timeout.
    """

    def __init__(
        self,
        memory_limiter: Optional[RateLimiter] = None,
        redis_limiter: Optional[RedisRateLimiter] = None,
    ) -> None:
        self._memory = memory_limiter or RateLimiter()
        self._redis = redis_limiter or RedisRateLimiter()

    @property
    def is_process_local(self) -> bool:
        """True quand le quota appliqué n'est *pas* partagé entre processus."""
        return not self.backend_is_shared()

    def backend_is_shared(self) -> bool:
        """True quand Redis est configuré et joignable."""
        return redis_client.is_configured() and redis_client.get_sync_client() is not None

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        if redis_client.is_configured():
            try:
                return self._redis.is_allowed(key, max_requests, window_seconds)
            except RuntimeError:
                pass
        return self._memory.is_allowed(key, max_requests, window_seconds)

    def reset(self, key: str) -> None:
        # On réinitialise les deux côtés : après une panne Redis, des
        # tentatives ont pu être comptées en mémoire, et les laisser derrière
        # bloquerait un utilisateur pourtant authentifié avec succès.
        if redis_client.is_configured():
            try:
                self._redis.reset(key)
            except RuntimeError:
                pass
        self._memory.reset(key)

    def tracked_keys(self) -> int:
        """Clés suivies en mémoire (observabilité du repli)."""
        return self._memory.tracked_keys()


# Instance globale du limiteur de débit
rate_limiter = HybridRateLimiter()
