"""
Service de gestion administrative des utilisateurs (Suspension, Réactivation, Rôles organisationnels).
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import User, OrganizationMembership
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.membership_repository import MembershipRepository
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class UserManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.session_repo = SessionRepository(db)
        self.audit_repo = AuditRepository(db)

    def suspend_user_in_org(self, org_id: str, actor_id: str, target_user_id: str) -> bool:
        membership = self.membership_repo.get_org_membership(org_id, target_user_id)
        if not membership:
            return False
        membership.status = "SUSPENDED"
        self.db.commit()

        # Révoquer les sessions actives de l'utilisateur
        self.session_repo.revoke_all_user_sessions(target_user_id)
        self.audit_repo.log("USER_SUSPENDED_IN_ORG", user_id=actor_id, org_id=org_id, resource=f"user:{target_user_id}")
        return True

    def reactivate_user_in_org(self, org_id: str, actor_id: str, target_user_id: str) -> bool:
        membership = self.membership_repo.get_org_membership(org_id, target_user_id)
        if not membership:
            return False
        membership.status = "ACTIVE"
        self.db.commit()
        self.audit_repo.log("USER_REACTIVATED_IN_ORG", user_id=actor_id, org_id=org_id, resource=f"user:{target_user_id}")
        return True

    def change_user_org_role(self, org_id: str, actor_id: str, target_user_id: str, new_role: str) -> bool:
        membership = self.membership_repo.get_org_membership(org_id, target_user_id)
        if not membership:
            return False
        membership.role = new_role
        self.db.commit()
        self.audit_repo.log("USER_ORG_ROLE_CHANGED", user_id=actor_id, org_id=org_id, resource=f"user:{target_user_id}", details={"new_role": new_role})
        return True
