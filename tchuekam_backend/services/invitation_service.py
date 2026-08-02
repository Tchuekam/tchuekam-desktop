"""
Service d'envoi, de validation et d'acceptation des invitations par e-mail.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.core.security import generate_secure_token, hash_token
from tchuekam_backend.domain.models import Invitation
from tchuekam_backend.repositories.invitation_repository import InvitationRepository
from tchuekam_backend.repositories.membership_repository import MembershipRepository
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class InvitationService:
    def __init__(self, db: Session):
        self.db = db
        self.invitation_repo = InvitationRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_invitation(
        self,
        org_id: str,
        invited_by_id: str,
        email: str,
        role: str = "MEMBER",
        workspace_id: Optional[str] = None,
        expires_in_days: int = 7,
    ) -> Tuple[bool, str, Optional[Invitation], Optional[str]]:
        raw_token = generate_secure_token()
        token_h = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        invitation = self.invitation_repo.create(
            org_id=org_id,
            email=email,
            role=role,
            token_hash=token_h,
            expires_at=expires_at,
            invited_by_id=invited_by_id,
            workspace_id=workspace_id,
        )

        self.audit_repo.log("INVITATION_CREATED", user_id=invited_by_id, org_id=org_id, resource=email)
        return True, "Invitation envoyée avec succès.", invitation, raw_token

    def accept_invitation(self, raw_token: str, user_id: str) -> Tuple[bool, str]:
        token_h = hash_token(raw_token)
        invitation = self.invitation_repo.get_by_token_hash(token_h)
        if not invitation or invitation.status != "PENDING":
            return False, "Invitation invalide ou déjà traitée."

        now = datetime.now(timezone.utc)
        expires_at = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at
        if expires_at < now:
            self.invitation_repo.mark_status(invitation.id, "EXPIRED")
            return False, "Cette invitation a expiré."

        # 1. Ajouter l'utilisateur à l'organisation
        self.membership_repo.add_org_member(invitation.org_id, user_id, role=invitation.role, status="ACTIVE")

        # 2. Si un workspace spécifique était lié
        if invitation.workspace_id:
            self.membership_repo.add_workspace_member(invitation.workspace_id, user_id, role="MEMBER")

        # 3. Marquer comme acceptée
        self.invitation_repo.mark_status(invitation.id, "ACCEPTED")
        self.audit_repo.log("INVITATION_ACCEPTED", user_id=user_id, org_id=invitation.org_id)
        return True, "Vous avez rejoint l'organisation avec succès !"
