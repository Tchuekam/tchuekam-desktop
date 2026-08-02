"""
Dépôt de données pour les invitations aux Organisations et Workspaces.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import Invitation


class InvitationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        org_id: str,
        email: str,
        role: str,
        token_hash: str,
        expires_at: datetime,
        invited_by_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Invitation:
        invitation = Invitation(
            org_id=org_id,
            workspace_id=workspace_id,
            email=email.lower().strip(),
            role=role,
            token_hash=token_hash,
            invited_by_id=invited_by_id,
            expires_at=expires_at,
            status="PENDING",
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def get_by_token_hash(self, token_hash: str) -> Optional[Invitation]:
        return self.db.query(Invitation).filter(Invitation.token_hash == token_hash).first()

    def list_pending_by_org(self, org_id: str) -> List[Invitation]:
        return (
            self.db.query(Invitation)
            .filter(Invitation.org_id == org_id, Invitation.status == "PENDING")
            .all()
        )

    def mark_status(self, invitation_id: str, status: str) -> bool:
        inv = self.db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if not inv:
            return False
        inv.status = status
        self.db.commit()
        return True
