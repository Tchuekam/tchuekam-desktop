"""
Dépôt de données pour la gestion des Workspaces par organisation.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import Workspace, WorkspaceMembership


class WorkspaceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, org_id: str, name: str, slug: str, description: Optional[str] = None) -> Workspace:
        workspace = Workspace(
            org_id=org_id,
            name=name,
            slug=slug.lower().strip(),
            description=description,
            is_archived=False,
        )
        self.db.add(workspace)
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def get_by_id(self, workspace_id: str) -> Optional[Workspace]:
        return self.db.query(Workspace).filter(Workspace.id == workspace_id).first()

    def list_by_org(self, org_id: str) -> List[Workspace]:
        return (
            self.db.query(Workspace)
            .filter(Workspace.org_id == org_id, Workspace.is_archived == False)
            .all()
        )

    def list_for_user_in_org(self, org_id: str, user_id: str) -> List[Workspace]:
        return (
            self.db.query(Workspace)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .filter(
                Workspace.org_id == org_id,
                WorkspaceMembership.user_id == user_id,
                Workspace.is_archived == False,
            )
            .all()
        )

    def update(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings_json: Optional[str] = None,
    ) -> Optional[Workspace]:
        ws = self.get_by_id(workspace_id)
        if not ws:
            return None
        if name is not None:
            ws.name = name
        if description is not None:
            ws.description = description
        if settings_json is not None:
            ws.settings_json = settings_json
        self.db.commit()
        self.db.refresh(ws)
        return ws

    def archive(self, workspace_id: str) -> bool:
        ws = self.get_by_id(workspace_id)
        if not ws or ws.is_archived:
            return False
        ws.is_archived = True
        self.db.commit()
        return True

    def delete_permanently(self, workspace_id: str) -> bool:
        ws = self.get_by_id(workspace_id)
        if not ws:
            return False
        self.db.delete(ws)
        self.db.commit()
        return True
