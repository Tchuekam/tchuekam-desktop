"""Contexte de requête propagé hors de la signature des fonctions.

Un identifiant de requête n'a d'intérêt que s'il apparaît partout : dans la
ligne de log d'accès, dans les logs émis au fond d'un service, et dans la
réponse d'erreur renvoyée au client. Le faire circuler en paramètre
traverserait toutes les couches ; une ``ContextVar`` le rend lisible de
n'importe où dans la requête courante.

``ContextVar`` et non ``threading.local`` : le même identifiant doit rester
visible dans le code asynchrone (middlewares, canal WebSocket) comme dans les
endpoints synchrones, que FastAPI exécute dans un thread du pool. Starlette
propage le contexte vers ce thread, donc une ``ContextVar`` couvre les deux ;
un ``threading.local`` perdrait la valeur à chaque bascule.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

#: En-tête standard de corrélation, accepté en entrée et renvoyé en sortie.
REQUEST_ID_HEADER = "x-request-id"

_request_id: ContextVar[Optional[str]] = ContextVar("tchuekam_request_id", default=None)

#: Longueur maximale retenue d'un identifiant fourni par le client. Sans
#: plafond, un client peut faire grossir chaque ligne de log à volonté, ce qui
#: est à la fois un vecteur de saturation du stockage de logs et un moyen de
#: noyer les lignes voisines.
_MAX_REQUEST_ID_LENGTH = 128


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(raw: Optional[str]) -> str:
    """Normalise un identifiant fourni par le client, ou en génère un.

    Les identifiants entrants finissent dans les lignes de log : on ne garde
    que des caractères inoffensifs. Un retour à la ligne injecté permettrait
    de forger de fausses entrées de log (log injection) ; les autres
    caractères de contrôle cassent les analyseurs en aval.
    """
    if not raw:
        return new_request_id()
    cleaned = "".join(ch for ch in raw.strip() if ch.isalnum() or ch in "-_.:")
    if not cleaned:
        return new_request_id()
    return cleaned[:_MAX_REQUEST_ID_LENGTH]


def set_request_id(value: str):
    """Fixe l'identifiant courant et retourne le jeton de réinitialisation."""
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> Optional[str]:
    """Identifiant de la requête courante, ou ``None`` hors requête."""
    return _request_id.get()
