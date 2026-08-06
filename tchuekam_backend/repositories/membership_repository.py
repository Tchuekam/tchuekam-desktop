"""
Dépôt de données pour les Adhésions aux Organisations et Workspaces.
"""

from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from tchuekam_backend.domain.models import OrganizationMembership, WorkspaceMembership, User


class MembershipRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- Organisation Memberships ---

    def add_org_member(self, org_id: str, user_id: str, role: str = "MEMBER", status: str = "ACTIVE") -> OrganizationMembership:
        existing = (
            self.db.query(OrganizationMembership)
            .filter(OrganizationMembership.org_id == org_id, OrganizationMembership.user_id == user_id)
            .first()
        )
        if existing:
            existing.role = role
            existing.status = status
            self.db.commit()
            return existing

        membership = OrganizationMembership(org_id=org_id, user_id=user_id, role=role, status=status)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def get_org_membership(self, org_id: str, user_id: str) -> Optional[OrganizationMembership]:
        return (
            self.db.query(OrganizationMembership)
            .filter(OrganizationMembership.org_id == org_id, OrganizationMembership.user_id == user_id)
            .first()
        )

    def list_org_members(self, org_id: str, skip: int = 0, limit: int = 100) -> List[OrganizationMembership]:
        return self.db.query(OrganizationMembership).options(
            joinedload(OrganizationMembership.user).joinedload(User.profile)
        ).filter(OrganizationMembership.org_id == org_id).offset(skip).limit(limit).all()

    def remove_org_member(self, org_id: str, user_id: str) -> bool:
        membership = self.get_org_membership(org_id, user_id)
        if not membership:
            return False
        self.db.delete(membership)
        self.db.commit()
        return True

    # --- Workspace Memberships ---

    def add_workspace_member(self, workspace_id: str, user_id: str, role: str = "MEMBER") -> WorkspaceMembership:
        existing = (
            self.db.query(WorkspaceMembership)
            .filter(WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == user_id)
            .first()
        )
        if existing:
            existing.role = role
            self.db.commit()
            return existing

        membership = WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def get_workspace_membership(self, workspace_id: str, user_id: str) -> Optional[WorkspaceMembership]:
        return (
            self.db.query(WorkspaceMembership)
            .filter(WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == user_id)
            .first()
        )

    def list_workspace_members(self, workspace_id: str) -> List[WorkspaceMembership]:
        return self.db.query(WorkspaceMembership).filter(WorkspaceMembership.workspace_id == workspace_id).all()
