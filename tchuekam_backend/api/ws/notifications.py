"""Canal WebSocket pour les notifications de sécurité en temps réel et la révocation de sessions.

Trois propriétés sont nécessaires pour tenir un millier de connexions
simultanées :

1. **Aucune session de base de données n'est retenue pendant la connexion.**
   Une dépendance ``Depends(get_db)`` sur un endpoint WebSocket garde la
   connexion SQL ouverte aussi longtemps que la socket, car la dépendance
   n'est libérée qu'à la fermeture. Mille sockets immobiliseraient mille
   connexions PostgreSQL, alors que le pool en compte quelques dizaines :
   l'API entière se bloque. L'authentification ouvre donc une session courte
   et la referme avant la boucle de réception.

2. **La diffusion passe par Redis.** ``active_connections`` est local au
   processus : sans bus partagé, un message publié par un worker n'atteint que
   les sockets de ce worker. Chaque worker s'abonne à un canal Redis et
   distribue à ses propres sockets.

3. **Le nombre de connexions est borné.** Sans plafond, un seul compte peut
   ouvrir autant de sockets que le système accepte de descripteurs, et une
   socket dont le client est mort sans fermer proprement reste indéfiniment.
   Un plafond par utilisateur, un plafond global et une inactivité maximale
   couvrent les deux cas.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Set

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tchuekam_backend.core import database, redis_client
from tchuekam_backend.core.config import settings
from tchuekam_backend.core.realtime import (
    broadcast_channel,
    notify_sessions_revoked,  # noqa: F401  (ré-export pour compatibilité)
    publish_user_event,
)
from tchuekam_backend.core.security import decode_jwt_token, is_jti_revoked
from tchuekam_backend.domain.models import User
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.repositories.user_repository import UserRepository

logger = logging.getLogger("tchuekam_backend.ws")

router = APIRouter(prefix="/ws", tags=["WebSockets Real-Time"])

#: Fermeture d'une socket restée muette ce nombre de secondes. Le client est
#: censé émettre un ping périodique ; au-delà, on considère la connexion morte
#: (client tué, réseau coupé sans FIN) et on libère le descripteur.
_IDLE_TIMEOUT_SECONDS = 300.0


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return default


def max_connections_per_user() -> int:
    """Plafond de sockets simultanées pour un même compte."""
    return _int_env("TCHUEKAM_WS_MAX_CONNECTIONS_PER_USER", 10)


def max_connections_total() -> int:
    """Plafond de sockets simultanées pour ce processus."""
    return _int_env("TCHUEKAM_WS_MAX_CONNECTIONS_TOTAL", 5_000)


class ConnectionManager:
    """Registre des sockets locales, avec plafonds et diffusion inter-workers."""

    def __init__(self) -> None:
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._total = 0
        self._lock = asyncio.Lock()
        self._subscriber_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Cycle de vie des sockets
    # ------------------------------------------------------------------

    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        """Accepte la socket si les plafonds le permettent.

        Returns:
            True si la socket a été acceptée et enregistrée. False si un
            plafond est atteint ; l'appelant doit alors fermer la socket.
        """
        async with self._lock:
            if self._total >= max_connections_total():
                logger.warning(
                    "Plafond global de connexions WebSocket atteint (%s), connexion refusée.",
                    self._total,
                )
                return False
            existing = self.active_connections.get(user_id)
            if existing is not None and len(existing) >= max_connections_per_user():
                logger.info(
                    "Plafond de connexions WebSocket atteint pour l'utilisateur %s (%s).",
                    user_id,
                    len(existing),
                )
                return False

        await websocket.accept()

        async with self._lock:
            self.active_connections.setdefault(user_id, set()).add(websocket)
            self._total += 1
        return True

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(user_id)
            if connections is None:
                return
            if websocket in connections:
                connections.discard(websocket)
                self._total -= 1
            if not connections:
                del self.active_connections[user_id]

    def total_connections(self) -> int:
        """Sockets ouvertes sur ce processus (observabilité, ``/metrics``)."""
        return self._total

    # ------------------------------------------------------------------
    # Diffusion
    # ------------------------------------------------------------------

    async def deliver_local(self, message: dict, user_id: str) -> int:
        """Envoie le message aux sockets de cet utilisateur sur ce processus."""
        async with self._lock:
            connections = list(self.active_connections.get(user_id, ()))
        if not connections:
            return 0

        msg_str = json.dumps(message)
        delivered = 0
        for connection in connections:
            try:
                await connection.send_text(msg_str)
                delivered += 1
            except Exception:
                # Socket déjà morte : on la retire du registre. ``send_text``
                # sur une socket fermée lève, c'est le signal le plus fiable.
                await self.disconnect(user_id, connection)
        return delivered

    async def send_personal_message(self, message: dict, user_id: str) -> None:
        """Diffuse un message à toutes les sockets de l'utilisateur, tous workers confondus.

        Avec Redis, le message est *publié* et non envoyé directement : la
        boucle d'abonnement de chaque worker — y compris celui-ci — le
        distribue à ses propres sockets. Envoyer en local *et* publier
        livrerait deux fois le message aux sockets de ce worker.
        """
        if publish_user_event(user_id, message):
            return
        await self.deliver_local(message, user_id)

    # ------------------------------------------------------------------
    # Boucle d'abonnement Redis
    # ------------------------------------------------------------------

    async def start_subscriber(self) -> None:
        """Démarre la boucle d'abonnement si Redis est configuré."""
        self._loop = asyncio.get_running_loop()
        if not redis_client.is_configured():
            return
        if self._subscriber_task is not None and not self._subscriber_task.done():
            return
        self._subscriber_task = asyncio.create_task(
            self._subscribe_loop(), name="ws-redis-subscriber"
        )

    async def stop_subscriber(self) -> None:
        task = self._subscriber_task
        self._subscriber_task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _subscribe_loop(self) -> None:
        """Consomme le canal Redis et redistribue localement, en se reconnectant.

        La boucle ne doit jamais mourir sur une erreur transitoire : si elle
        s'arrête, ce worker cesse silencieusement de recevoir les événements
        des autres workers jusqu'au prochain redémarrage.
        """
        backoff = 1.0
        channel = broadcast_channel()
        while True:
            pubsub = None
            try:
                client = await redis_client.get_async_client()
                if client is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue

                pubsub = client.pubsub()
                await pubsub.subscribe(channel)
                backoff = 1.0
                logger.info("Abonnement au canal de diffusion WebSocket %s.", channel)

                async for raw in pubsub.listen():
                    if raw is None or raw.get("type") != "message":
                        continue
                    await self._dispatch_raw(raw.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                redis_client.report_failure(exc, is_async=True)
                logger.warning(
                    "Boucle d'abonnement WebSocket interrompue, reprise dans %.0fs : %s",
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                if pubsub is not None:
                    with contextlib.suppress(Exception):
                        await pubsub.close()

    async def _dispatch_raw(self, data) -> None:
        if not data:
            return
        try:
            envelope = json.loads(data)
        except (TypeError, ValueError):
            logger.debug("Message de diffusion WebSocket illisible, ignoré.")
            return
        user_id = envelope.get("user_id")
        message = envelope.get("message")
        if not user_id or not isinstance(message, dict):
            return
        await self.deliver_local(message, str(user_id))


ws_manager = ConnectionManager()


def _origin_is_allowed(origin: Optional[str]) -> bool:
    if not origin:
        return True
    allowed = {o.rstrip("/") for o in settings.ALLOWED_ORIGINS}
    if "*" in allowed:
        return True
    return origin.rstrip("/") in allowed


def _authenticate_ws_token(token: str) -> Optional[str]:
    """Valide le jeton et retourne l'identifiant utilisateur, ou ``None``.

    La session de base de données est ouverte et refermée ici même. Elle ne
    doit surtout pas survivre à cet appel : la socket peut rester ouverte des
    heures, et une connexion SQL retenue tout ce temps est une fuite du pool.

    Seul l'identifiant est retourné, et non l'entité ``User`` : un objet
    SQLAlchemy détaché de sa session lève ``DetachedInstanceError`` au premier
    accès à un attribut non chargé.
    """
    if not token:
        return None

    # ``database.new_session`` et non ``SessionLocal`` importé directement :
    # l'accès par attribut est résolu à l'appel, donc un test qui remplace la
    # fabrique de sessions redirige aussi ce chemin.
    db = database.new_session()
    try:
        try:
            payload = decode_jwt_token(token)
        except jwt.PyJWTError:
            try:
                from tchuekam_backend.core.supabase_auth import resolve_supabase_bearer

                sb_result = resolve_supabase_bearer(token, db)
            except Exception:
                return None
            if sb_result is None:
                return None
            user = sb_result[0]
            if not user or not user.is_active:
                return None
            return str(user.id)
        except Exception:
            return None

        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        session_id = payload.get("session_id")
        jti = payload.get("jti")
        if not user_id or not session_id or (jti and is_jti_revoked(jti)):
            return None

        user_session = SessionRepository(db).get_by_id(session_id)
        if not user_session or user_session.is_revoked or user_session.user_id != user_id:
            return None

        expires_at = user_session.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None

        user: Optional[User] = UserRepository(db).get_by_id(user_id)
        if not user or not user.is_active:
            return None
        return str(user.id)
    except Exception:
        logger.debug("Échec de l'authentification WebSocket.", exc_info=True)
        return None
    finally:
        db.close()


@router.websocket("/security-alerts/{user_id}")
async def websocket_security_alerts(websocket: WebSocket, user_id: str):
    origin = websocket.headers.get("origin")
    if not _origin_is_allowed(origin):
        await websocket.close(code=4403)
        return

    auth_header = websocket.headers.get("authorization") or ""
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        token = (websocket.query_params.get("token") or "").strip()

    # L'authentification touche la base : on l'exécute dans un thread pour ne
    # pas bloquer la boucle d'événements. Avec mille poignées de main
    # concurrentes, un appel bloquant de quelques millisecondes dans la boucle
    # suffit à retarder toutes les autres requêtes du worker.
    authenticated_user_id = await asyncio.to_thread(_authenticate_ws_token, token)
    if not authenticated_user_id:
        await websocket.close(code=4401)
        return
    if authenticated_user_id != user_id:
        await websocket.close(code=4403)
        return

    if not await ws_manager.connect(user_id, websocket):
        # 1013 « Try Again Later » : le client doit réessayer plus tard, c'est
        # une saturation et non un refus d'autorisation.
        await websocket.close(code=1013)
        return

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await websocket.close(code=1001)
                return
            # Echo ping / pong keepalive
            await websocket.send_text(json.dumps({"type": "PONG", "payload": data}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Connexion WebSocket terminée sur erreur.", exc_info=True)
    finally:
        await ws_manager.disconnect(user_id, websocket)
