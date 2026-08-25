"""
Limiteur de débit (Rate Limiter) et protection anti-brute force.

Note d'exploitation : ce limiteur vit dans la mémoire du processus. Il protège
donc un déploiement mono-worker. Derrière plusieurs workers uvicorn ou
plusieurs instances, chaque processus applique son propre quota et le seuil
effectif est multiplié par le nombre de processus ; un magasin partagé (Redis)
est nécessaire pour un quota global. Voir ``RateLimiter.is_process_local``.
"""

import threading
import time
from typing import Dict, List, Tuple

#: Nombre maximum de clés conservées simultanément. La clé anti-force-brute
#: contient l'email fourni par le client : sans plafond ni purge, un attaquant
#: qui varie l'email à chaque requête fait croître le dictionnaire
#: indéfiniment (épuisement mémoire).
MAX_TRACKED_KEYS = 50_000

#: Intervalle minimum entre deux purges complètes, en secondes.
_SWEEP_INTERVAL_SECONDS = 60.0


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


# Instance globale du limiteur de débit
rate_limiter = RateLimiter()
