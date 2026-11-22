"""
Canal WebSocket pour les notifications de sécurité en temps réel et la révocation de sessions.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional, Set
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import jwt
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.security import decode_jwt_token, is_jti_revoked
from tchuekam_backend.domain.models import User
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.repositories.user_repository import UserRepository

router = APIRouter(prefix="/ws", tags=["WebSockets Real-Time"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        connections = list(self.active_connections.get(user_id, ()))
        if not connections:
            return
        msg_str = json.dumps(message)
        for connection in connections:
            try:
                await connection.send_text(msg_str)
            except Exception:
                self.disconnect(user_id, connection)


ws_manager = ConnectionManager()


def _origin_is_allowed(origin: Optional[str]) -> bool:
    if not origin:
        return True
    allowed = {o.rstrip("/") for o in settings.ALLOWED_ORIGINS}
    if "*" in allowed:
        return True
    return origin.rstrip("/") in allowed


def _authenticate_ws_token(token: str, db: Session) -> Optional[User]:
    if not token:
        return None
    try:
        payload = decode_jwt_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        session_id = payload.get("session_id")
        jti = payload.get("jti")
        if not user_id or not session_id or (jti and is_jti_revoked(jti)):
            return None

        session_repo = SessionRepository(db)
        user_session = session_repo.get_by_id(session_id)
        if not user_session or user_session.is_revoked or user_session.user_id != user_id:
            return None

        expires_at = user_session.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None

        user = UserRepository(db).get_by_id(user_id)
        if not user or not user.is_active:
            return None
        return user
    except jwt.PyJWTError:
        try:
            from tchuekam_backend.core.supabase_auth import resolve_supabase_bearer

            sb_result = resolve_supabase_bearer(token, db)
            if sb_result is not None:
                user = sb_result[0]
                return user if user and user.is_active else None
        except Exception:
            return None
        return None
    except Exception:
        return None


@router.websocket("/security-alerts/{user_id}")
async def websocket_security_alerts(
    websocket: WebSocket,
    user_id: str,
    db: Session = Depends(get_db),
):
    origin = websocket.headers.get("origin")
    if not _origin_is_allowed(origin):
        await websocket.close(code=4403)
        return

    auth_header = websocket.headers.get("authorization") or ""
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        token = (websocket.query_params.get("token") or "").strip()

    auth_user = _authenticate_ws_token(token, db)
    if not auth_user:
        await websocket.close(code=4401)
        return
    if auth_user.id != user_id:
        await websocket.close(code=4403)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo ping / pong keepalive
            await websocket.send_text(json.dumps({"type": "PONG", "payload": data}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(user_id, websocket)
