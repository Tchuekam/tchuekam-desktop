"""Publication d'événements temps réel vers les clients connectés.

Ce module vit dans ``core`` et non dans ``api.ws`` parce que les deux couches
en ont besoin : la couche API l'utilise pour *distribuer* les événements aux
sockets qu'elle détient, la couche service pour en *émettre* (une révocation
de session, par exemple). Un service qui importerait ``api.ws`` inverserait
les dépendances — et créerait un cycle via ``api.router``.

La publication est synchrone, donc appelable depuis un endpoint FastAPI
``def`` exécuté dans un thread. La livraison, elle, est asynchrone et reste
l'affaire de la boucle d'abonnement de ``api.ws.notifications``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from tchuekam_backend.core import redis_client

logger = logging.getLogger("tchuekam_backend.realtime")

#: Canal Redis de diffusion des événements utilisateur.
BROADCAST_CHANNEL = "ws:user-events"


def broadcast_channel() -> str:
    """Nom complet (préfixé) du canal de diffusion."""
    return redis_client.namespaced(BROADCAST_CHANNEL)


def publish_user_event(user_id: str, message: dict) -> bool:
    """Publie un événement vers toutes les instances.

    Returns:
        True si l'événement a été publié sur le bus partagé. False si Redis
        n'est pas configuré ou injoignable : l'appelant n'a alors aucune
        garantie de diffusion au-delà du processus courant, et c'est à lui de
        décider s'il livre localement.
    """
    if not user_id or not isinstance(message, dict):
        return False
    if not redis_client.is_configured():
        return False
    client = redis_client.get_sync_client()
    if client is None:
        return False
    try:
        client.publish(
            broadcast_channel(),
            json.dumps({"user_id": str(user_id), "message": message}),
        )
    except Exception as exc:
        redis_client.report_failure(exc)
        return False
    return True


def notify_sessions_revoked(
    user_id: str, session_ids: Optional[Iterable[str]] = None
) -> None:
    """Prévient les clients d'un utilisateur que des sessions ont été révoquées.

    ``session_ids`` vide signifie « toutes les sessions ». L'absence de Redis
    n'est pas une erreur : la révocation est déjà persistée en base et le
    client sera rejeté à sa prochaine requête authentifiée. La notification ne
    fait qu'avancer le moment où il l'apprend.
    """
    publish_user_event(
        user_id,
        {
            "type": "SESSIONS_REVOKED",
            "payload": {"session_ids": [str(s) for s in (session_ids or [])]},
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
