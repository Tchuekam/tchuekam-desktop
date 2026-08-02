"""
Limiteur de débit (Rate Limiter) et protection anti-brute force.
"""

import time
from collections import defaultdict
from typing import Dict, List, Tuple


class RateLimiter:
    """Implémentation d'un limiteur de débit à fenêtre glissante."""

    def __init__(self):
        # Clé -> liste d'horodatages (float)
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Vérifie si une requête identifiée par `key` est autorisée.
        
        Returns:
            (is_allowed, remaining_attempts)
        """
        now = time.time()
        cutoff = now - window_seconds

        # Nettoyage des anciennes tentatives
        timestamps = [ts for ts in self._requests[key] if ts > cutoff]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            return False, 0

        self._requests[key].append(now)
        remaining = max_requests - len(self._requests[key])
        return True, remaining

    def reset(self, key: str) -> None:
        """Réinitialise l'historique pour une clé (ex: après connexion réussie)."""
        if key in self._requests:
            del self._requests[key]


# Instance globale du limiteur de débit
rate_limiter = RateLimiter()
