"""Middlewares ASGI : observabilité, en-têtes de sécurité, limitation de débit.

Pourquoi de l'ASGI brut et non ``BaseHTTPMiddleware``
----------------------------------------------------
``BaseHTTPMiddleware`` enveloppe chaque requête dans un groupe de tâches anyio
et deux flux mémoire, pour offrir l'interface confortable
``async def dispatch(request, call_next)``. Ce confort coûte des allocations et
un aller-retour de planification par requête, et il met en tampon les réponses
en flux. À mille requêtes simultanées, c'est un surcoût payé un million de
fois par quart d'heure, sur du code qui ne fait que lire quelques en-têtes.

Les middlewares ci-dessous sont donc des applications ASGI : elles enveloppent
``send`` et transmettent, sans tâche supplémentaire.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Awaitable, Callable, Iterable, Optional

from tchuekam_backend.core import metrics
from tchuekam_backend.core.config import _is_production, settings
from tchuekam_backend.core.rate_limiter import rate_limiter
from tchuekam_backend.core.request_context import (
    REQUEST_ID_HEADER,
    get_request_id,
    reset_request_id,
    sanitize_request_id,
    set_request_id,
)

logger = logging.getLogger("tchuekam_backend.http")

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]

#: En-têtes de sécurité appliqués à chaque réponse.
_SECURITY_HEADERS: tuple = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"x-xss-protection", b"1; mode=block"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
    (b"content-security-policy", b"default-src 'self'; script-src 'self'; object-src 'none';"),
)

_HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")

#: Chemins exemptés de limitation de débit et de log d'accès.
#:
#: Les sondes de l'orchestrateur frappent ces routes toutes les quelques
#: secondes, par instance. Les soumettre au quota ferait refuser les sondes
#: sous charge — donc retirer du service une instance en bonne santé — et les
#: journaliser noierait les logs utiles.
_PROBE_PATHS = frozenset({"/health", "/healthz", "/readyz", "/livez", "/metrics"})


def _header_value(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers", ()):
        if key == name:
            return value.decode("latin-1")
    return None


def _is_probe_path(path: str) -> bool:
    return path in _PROBE_PATHS or path.endswith("/health")


def trusted_proxy_count() -> int:
    """Nombre de proxys de confiance devant l'application.

    ``X-Forwarded-For`` est une liste à laquelle chaque proxy *ajoute*. Le
    client contrôle entièrement ce qu'il y met en premier : faire confiance à
    l'entrée de gauche laisse n'importe qui usurper une adresse et contourner
    un quota par IP en changeant de valeur à chaque requête. Seules les N
    dernières entrées, ajoutées par nos propres proxys, sont dignes de
    confiance.

    0 (défaut) signifie « pas de proxy » : on utilise l'adresse du pair TCP.
    Derrière un répartiteur de charge, cette adresse est celle du répartiteur,
    et tout le trafic partagerait un seul compteur — il faut donc configurer
    cette variable, ou lancer uvicorn avec ``--proxy-headers``, qui réécrit
    l'adresse du pair en amont.
    """
    raw = os.getenv("TCHUEKAM_TRUSTED_PROXY_COUNT", "").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def client_identity(scope: Scope) -> str:
    """Identité utilisée pour le quota : l'adresse du client appelant."""
    hops = trusted_proxy_count()
    if hops > 0:
        forwarded = _header_value(scope, b"x-forwarded-for")
        if forwarded:
            chain = [part.strip() for part in forwarded.split(",") if part.strip()]
            if chain:
                # On compte depuis la droite : la dernière entrée a été ajoutée
                # par le proxy le plus proche de nous.
                index = max(0, len(chain) - hops)
                return chain[index] if index < len(chain) else chain[-1]

    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


def route_label(scope: Scope) -> str:
    """Libellé de chemin à faible cardinalité, pour les métriques.

    Utiliser l'URL brute comme étiquette Prometheus crée une série temporelle
    par valeur distincte : ``/api/v1/users/<uuid>`` en produirait une par
    utilisateur. Quelques milliers d'utilisateurs suffisent à faire exploser
    la mémoire du serveur de métriques. On publie donc le *gabarit* de route
    (``/api/v1/users/{user_id}``), que Starlette dépose dans le scope après le
    routage.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    # Aucune route n'a été appariée (404, ou erreur avant le routage) :
    # un libellé constant évite qu'un scanner d'URL crée une série par essai.
    return "__unmatched__"


class ObservabilityMiddleware:
    """Identifiant de corrélation, log d'accès structuré, métriques, en-têtes.

    Les quatre responsabilités sont regroupées parce qu'elles ont besoin des
    mêmes informations au même moment — le début et la fin de la requête — et
    que chaque couche ASGI supplémentaire est un enveloppement de ``send`` de
    plus sur le chemin critique.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        request_id = sanitize_request_id(_header_value(scope, REQUEST_ID_HEADER.encode()))
        token = set_request_id(request_id)

        if scope["type"] == "websocket":
            try:
                await self.app(scope, receive, send)
            finally:
                reset_request_id(token)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        is_probe = _is_probe_path(path)
        started = time.perf_counter()
        status_holder = {"status": 500}

        # ``x-forwarded-proto`` est posé par le proxy TLS ; sans lui, une
        # application derrière un répartiteur voit toujours du HTTP et
        # n'émettrait jamais HSTS.
        forwarded_proto = (_header_value(scope, b"x-forwarded-proto") or "").split(",")[0].strip().lower()
        is_https = scope.get("scheme") == "https" or forwarded_proto == "https"

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 500)
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in _SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                if is_https and _HSTS_HEADER[0] not in existing:
                    headers.append(_HSTS_HEADER)
                if REQUEST_ID_HEADER.encode() not in existing:
                    headers.append((REQUEST_ID_HEADER.encode(), request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        if metrics.is_available() and not is_probe:
            metrics.REQUESTS_IN_FLIGHT.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration = time.perf_counter() - started
            # Le gestionnaire global renverra un 500 ; on journalise ici parce
            # que c'est le seul endroit qui connaît la durée et le contexte.
            _log_access(
                method, path, 500, duration, request_id, client_identity(scope), error=True
            )
            if metrics.is_available() and not is_probe:
                metrics.observe_request(method, route_label(scope), 500, duration)
            raise
        else:
            duration = time.perf_counter() - started
            if not is_probe:
                _log_access(
                    method,
                    path,
                    status_holder["status"],
                    duration,
                    request_id,
                    client_identity(scope),
                )
            if metrics.is_available() and not is_probe:
                metrics.observe_request(
                    method, route_label(scope), status_holder["status"], duration
                )
        finally:
            if metrics.is_available() and not is_probe:
                metrics.REQUESTS_IN_FLIGHT.dec()
            reset_request_id(token)


def _log_access(
    method: str,
    path: str,
    status: int,
    duration_seconds: float,
    request_id: str,
    client: str,
    error: bool = False,
) -> None:
    """Émet une ligne de log d'accès.

    En production, la ligne est un objet JSON : c'est ce qu'attendent les
    collecteurs (Loki, CloudWatch, Datadog), et cela évite d'avoir à écrire un
    motif d'extraction fragile. En développement, une ligne lisible à l'œil
    reste plus utile dans un terminal.
    """
    duration_ms = round(duration_seconds * 1000, 2)
    if _is_production():
        payload = {
            "event": "http_access",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
            "request_id": request_id,
            "client": client,
        }
        line = json.dumps(payload, separators=(",", ":"))
    else:
        line = f"{method} {path} {status} {duration_ms}ms req={request_id}"

    if error or status >= 500:
        logger.error(line)
    elif status >= 400:
        logger.warning(line)
    else:
        logger.info(line)


class RateLimitMiddleware:
    """Quota global par identité appelante.

    ``settings.RATE_LIMIT_GLOBAL_PER_MINUTE`` existait sans être appliqué
    nulle part : seuls la connexion et un endpoint biocompute étaient
    protégés. Tout le reste de l'API — création d'organisation, listes
    paginées, téléversement — pouvait être appelé sans borne, et un seul
    client suffisait à saturer le pool de connexions pour tous les autres.
    """

    def __init__(self, app, requests_per_minute: Optional[int] = None):
        self.app = app
        self._configured_limit = requests_per_minute

    @property
    def limit(self) -> int:
        if self._configured_limit is not None:
            return self._configured_limit
        return int(settings.RATE_LIMIT_GLOBAL_PER_MINUTE)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_rate_limiting_enabled():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if _is_probe_path(path):
            await self.app(scope, receive, send)
            return

        # Les pré-vols CORS sont émis par le navigateur, pas par le code
        # applicatif : les compter ferait consommer son quota à un client au
        # double de son trafic réel.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        identity = client_identity(scope)
        limit = self.limit
        allowed, remaining = rate_limiter.is_allowed(
            f"global:{identity}", max_requests=limit, window_seconds=60
        )

        if not allowed:
            metrics.note_rate_limit_rejection("global")
            logger.warning(
                json.dumps(
                    {
                        "event": "rate_limit_rejected",
                        "scope": "global",
                        "client": identity,
                        "path": path,
                        "limit": limit,
                        "request_id": get_request_id(),
                    },
                    separators=(",", ":"),
                )
            )
            await _send_rate_limited(send, limit)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"ratelimit-limit", str(limit).encode()))
                headers.append((b"ratelimit-remaining", str(max(0, remaining)).encode()))
                headers.append((b"ratelimit-reset", b"60"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def is_rate_limiting_enabled() -> bool:
    """Le quota global est-il appliqué ?

    Activé en production, désactivé ailleurs. Un quota actif pendant les tests
    ferait échouer les suites qui enchaînent les requêtes depuis une même
    adresse, pour une raison sans rapport avec ce qu'elles vérifient.
    ``TCHUEKAM_RATE_LIMIT_ENABLED`` force l'un ou l'autre, ce qui permet de
    tester le comportement explicitement.
    """
    raw = os.getenv("TCHUEKAM_RATE_LIMIT_ENABLED", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return _is_production()


async def _send_rate_limited(send: Send, limit: int) -> None:
    """Réponse 429 dans la même enveloppe d'erreur que le reste de l'API."""
    body = json.dumps(
        {
            "success": False,
            "error": {
                "code": "TOO_MANY_REQUESTS",
                "message": (
                    "Trop de requêtes. Veuillez réessayer dans quelques instants."
                ),
                "details": [],
            },
        }
    ).encode()

    request_id = get_request_id()
    headers: list = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        # ``Retry-After`` indique au client *quand* réessayer ; sans lui, un
        # client qui réessaie immédiatement amplifie la saturation.
        (b"retry-after", b"60"),
        (b"ratelimit-limit", str(limit).encode()),
        (b"ratelimit-remaining", b"0"),
        (b"ratelimit-reset", b"60"),
    ]
    headers.extend(_SECURITY_HEADERS)
    if request_id:
        headers.append((REQUEST_ID_HEADER.encode(), request_id.encode("latin-1")))

    await send({"type": "http.response.start", "status": 429, "headers": headers})
    await send({"type": "http.response.body", "body": body})
