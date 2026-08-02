"""
Dépôt de données pour la gestion des sessions utilisateurs et appareils.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import UserSession
from tchuekam_backend.core.security import hash_token


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        user_id: str,
        refresh_token: str,
        expires_at: datetime,
        device_name: Optional[str] = "Inconnu",
        device_type: Optional[str] = "web",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=expires_at,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
            is_revoked=False,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_id(self, session_id: str) -> Optional[UserSession]:
        return self.db.query(UserSession).filter(UserSession.id == session_id).first()

    def get_active_sessions(self, user_id: str) -> List[UserSession]:
        now = datetime.now(timezone.utc)
        return (
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == user_id,
                UserSession.is_revoked == False,
                UserSession.expires_at > now,
            )
            .order_by(UserSession.last_active_at.desc())
            .all()
        )

    def revoke_session(self, session_id: str) -> bool:
        session = self.get_by_id(session_id)
        if not session or session.is_revoked:
            return False
        session.is_revoked = True
        self.db.commit()
        return True

    def revoke_all_user_sessions(self, user_id: str, except_session_id: Optional[str] = None) -> int:
        query = self.db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_revoked == False,
        )
        if except_session_id:
            query = query.filter(UserSession.id != except_session_id)
        sessions = query.all()
        for session in sessions:
            session.is_revoked = True
        self.db.commit()
        return len(sessions)

    def update_last_active(self, session_id: str) -> None:
        session = self.get_by_id(session_id)
        if session and not session.is_revoked:
            session.last_active_at = datetime.now(timezone.utc)
            self.db.commit()
