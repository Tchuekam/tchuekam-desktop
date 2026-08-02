"""
Service métier des Workspaces (Création, Isolation, Gestion des Membres et Archivage).
"""

import re
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import Workspace, WorkspaceMembership
from tchuekam_backend.repositories.workspace_repository import WorkspaceRepository
from tchuekam_backend.repositories.membership_repository import MembershipRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class WorkspaceService:
    def __init__(self, db: Session):
        self.db = db
        self.workspace_repo = WorkspaceRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_workspace(
        self,
        org_id: str,
        user_id: str,
        name: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Workspace]]:
        computed_slug = slug or re.sub(r"[^a-z0-9\-]", "", name.lower().replace(" ", "-"))
        if not computed_slug:
            computed_slug = f"ws-{user_id[:8]}"

        existing = (
            self.db.query(Workspace)
            .filter(Workspace.org_id == org_id, Workspace.slug == computed_slug)
            .first()
        )
        if existing:
            return False, f"Le workspace '{computed_slug}' existe déjà dans cette organisation.", None

        ws = self.workspace_repo.create(org_id=org_id, name=name, slug=computed_slug, description=description)

        # Ajouter le créateur comme ADMIN du workspace
        self.membership_repo.add_workspace_member(ws.id, user_id, role="ADMIN")

        self.audit_repo.log("WORKSPACE_CREATED", user_id=user_id, org_id=org_id, resource=ws.name)
        return True, "Workspace créé avec succès.", ws

    def list_workspaces_for_org(self, org_id: str, user_id: str) -> List[Workspace]:
        # Un administrateur voit tous les workspaces, un utilisateur voit ses workspaces
        return self.workspace_repo.list_by_org(org_id)

    def update_workspace(
        self,
        workspace_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings_json: Optional[str] = None,
    ) -> Optional[Workspace]:
        ws = self.workspace_repo.update(workspace_id, name=name, description=description, settings_json=settings_json)
        if ws:
            self.audit_repo.log("WORKSPACE_UPDATED", user_id=user_id, org_id=ws.org_id, resource=ws.name)
        return ws

    def archive_workspace(self, workspace_id: str, user_id: str) -> bool:
        ws = self.workspace_repo.get_by_id(workspace_id)
        if not ws:
            return False
        success = self.workspace_repo.archive(workspace_id)
        if success:
            self.audit_repo.log("WORKSPACE_ARCHIVED", user_id=user_id, org_id=ws.org_id, resource=ws.name)
        return success
