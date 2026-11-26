"""Contrôle d'admission : borne la concurrence et rejette vite le surplus.

Le problème mesuré
------------------
Sans borne, le débit du service ne plafonne pas — il *s'effondre*. Relevé sur
ce backend, en boucle fermée, avant ce middleware :

    concurrence     débit        p50        succès
         10       182 req/s     24 ms      100 %
         25       363 req/s     31 ms      100 %   <- plateau
         50       311 req/s    130 ms      100 %
        100       223 req/s    157 ms     98,5 %
        200        15 req/s     10 s      55,8 %   <- effondrement

Au-delà du plateau, chaque requête supplémentaire *réduit* le débit. Le
mécanisme : les requêtes au-delà de la largeur du pool de threads s'empilent
sans limite dans la boucle d'événements, puis chacune attend une connexion
jusqu'à ``pool_timeout`` (10 s). Pendant ces 10 secondes le client a déjà
abandonné — le travail est perdu, et la place qu'il occupait n'a servi à
personne. C'est un effondrement de congestion : le système passe son temps à
produire des réponses que plus personne n'attend.

Le principe
-----------
Un service ne peut pas traiter plus que sa capacité. Il n'a que deux façons de
répondre à l'excédent : le faire attendre, ou le refuser. L'attente n'est utile
que si elle est courte ; au-delà, refuser *immédiatement* est strictement
meilleur pour tout le monde — le client refusé peut réessayer ou se replier, et
surtout la capacité reste disponible pour les requêtes admises, dont la latence
ne se dégrade pas.

Ce middleware admet donc au plus ``max_concurrent`` requêtes en traitement, en
fait patienter au plus ``max_queued`` de plus pendant au plus
``queue_timeout``, et répond 503 au reste sans toucher ni à la base ni au pool
de threads.

Dimensionnement
---------------
``max_concurrent`` vaut par défaut la largeur du pool de connexions, qui est la
ressource réellement rare : au-delà, une requête admise ne pourrait de toute
façon qu'attendre une connexion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Optional

from tchuekam_backend.core import metrics
from tchuekam_backend.core.request_context import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger("tchuekam_backend.admission")

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]

#: Mêmes exemptions que le limiteur de débit : une sonde refusée ferait sortir
#: de la rotation une instance qui, justement, est en train de travailler.
_EXEMPT_PATHS = frozenset({"/health", "/healthz", "/readyz", "/livez", "/metrics"})


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def is_enabled() -> bool:
    """Actif par défaut. ``TCHUEKAM_ADMISSION_ENABLED=0`` le désactive."""
    raw = os.getenv("TCHUEKAM_ADMISSION_ENABLED", "").strip().lower()
    return raw not in {"0", "false", "no"}


def default_max_concurrent() -> int:
    """Requêtes simultanément en traitement, par worker."""
    explicit = _int_env("TCHUEKAM_MAX_CONCURRENT_REQUESTS", 0)
    if explicit:
        return explicit
    from tchuekam_backend.core.concurrency import recommended_thread_limit

    return recommended_thread_limit()


class ConcurrencyLimitMiddleware:
    """Admet un nombre borné de requêtes, refuse le surplus en 503."""

    def __init__(
        self,
        app,
        max_concurrent: Optional[int] = None,
        max_queued: Optional[int] = None,
        queue_timeout: Optional[float] = None,
    ):
        self.app = app
        self._max_concurrent = max_concurrent
        self._max_queued = max_queued
        self._queue_timeout = queue_timeout
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._waiting = 0
        self._in_flight = 0

    # Le sémaphore est créé paresseusement : instancié à l'import du module,
    # il se lierait à la boucle d'événements de l'import et non à celle du
    # worker, ce qui le rend inutilisable depuis celle-ci.
    def _ensure_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    @property
    def max_concurrent(self) -> int:
        if self._max_concurrent is not None:
            return self._max_concurrent
        self._max_concurrent = default_max_concurrent()
        return self._max_concurrent

    @property
    def max_queued(self) -> int:
        """Requêtes autorisées à patienter, en plus de celles en traitement.

        Une petite file absorbe les rafales — un à-coup de trafic ne doit pas
        produire d'erreurs alors que la capacité moyenne est suffisante. Une
        grande file ne fait que transformer des refus rapides en attentes
        longues suivies de refus : le client a déjà abandonné quand sa réponse
        arrive. Deux fois la concurrence est un compromis usuel.
        """
        if self._max_queued is not None:
            return self._max_queued
        self._max_queued = _int_env("TCHUEKAM_MAX_QUEUED_REQUESTS", self.max_concurrent * 2)
        return self._max_queued

    @property
    def queue_timeout(self) -> float:
        """Attente maximale avant refus.

        Volontairement bien inférieure au ``pool_timeout`` de SQLAlchemy
        (10 s) : l'intérêt est de refuser *avant* d'avoir immobilisé une place
        pendant dix secondes pour rien.
        """
        if self._queue_timeout is not None:
            return self._queue_timeout
        self._queue_timeout = _float_env("TCHUEKAM_QUEUE_TIMEOUT_SECONDS", 3.0)
        return self._queue_timeout

    def stats(self) -> dict:
        return {
            "max_concurrent": self.max_concurrent,
            "max_queued": self.max_queued,
            "in_flight": self._in_flight,
            "waiting": self._waiting,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_enabled():
            await self.app(scope, receive, send)
            return

        if scope.get("path", "") in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        semaphore = self._ensure_semaphore()

        # File pleine : on refuse sans attendre. C'est le cœur du dispositif —
        # refuser en une milliseconde laisse la capacité aux requêtes admises,
        # alors qu'accepter d'attendre la consomme sans rien produire.
        if self._waiting >= self.max_queued:
            metrics.note_rate_limit_rejection("admission_queue_full")
            await _send_overloaded(send, reason="queue_full")
            return

        self._waiting += 1
        try:
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=self.queue_timeout)
            except (asyncio.TimeoutError, TimeoutError):
                metrics.note_rate_limit_rejection("admission_timeout")
                logger.warning(
                    json.dumps(
                        {
                            "event": "admission_rejected",
                            "reason": "queue_timeout",
                            "path": scope.get("path", ""),
                            "waiting": self._waiting,
                            "in_flight": self._in_flight,
                            "max_concurrent": self.max_concurrent,
                            "request_id": get_request_id(),
                        },
                        separators=(",", ":"),
                    )
                )
                await _send_overloaded(send, reason="timeout")
                return
        finally:
            self._waiting -= 1

        self._in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._in_flight -= 1
            semaphore.release()


async def _send_overloaded(send: Send, reason: str) -> None:
    """503 immédiat, dans l'enveloppe d'erreur habituelle de l'API.

    503 et non 429 : 429 signifie « tu as dépassé *ton* quota », alors qu'ici
    le client n'a rien fait de mal — c'est le service qui est saturé. La
    distinction compte pour un client qui décide s'il doit ralentir ou
    simplement réessayer.
    """
    body = json.dumps(
        {
            "success": False,
            "error": {
                "code": "SERVICE_OVERLOADED",
                "message": (
                    "Service momentanément saturé. Veuillez réessayer dans quelques instants."
                ),
                "details": [],
            },
        }
    ).encode()

    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"retry-after", b"1"),
        # Indique à un répartiteur ou un maillage de services que la requête
        # n'a pas été traitée et peut être réessayée ailleurs sans risque.
        (b"connection", b"close"),
        (b"x-overload-reason", reason.encode()),
        (b"x-content-type-options", b"nosniff"),
    ]
    request_id = get_request_id()
    if request_id:
        headers.append((REQUEST_ID_HEADER.encode(), request_id.encode("latin-1")))

    await send({"type": "http.response.start", "status": 503, "headers": headers})
    await send({"type": "http.response.body", "body": body})
