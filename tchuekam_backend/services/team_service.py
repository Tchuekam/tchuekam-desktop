"""
Service métier des Équipes et Hiérarchies (Création, Attribution des Membres, Responsables).
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import Team, TeamMember
from tchuekam_backend.repositories.team_repository import TeamRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class TeamService:
    def __init__(self, db: Session):
        self.db = db
        self.team_repo = TeamRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_team(
        self,
        org_id: str,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        workspace_id: Optional[str] = None,
        parent_team_id: Optional[str] = None,
        leader_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Team]]:
        # Vérification parent_team_id s'il est fourni
        if parent_team_id:
            parent = self.team_repo.get_by_id(parent_team_id)
            if not parent or parent.org_id != org_id:
                return False, "L'équipe parente est introuvable dans cette organisation.", None

        team = self.team_repo.create(
            org_id=org_id,
            name=name,
            description=description,
            workspace_id=workspace_id,
            parent_team_id=parent_team_id,
            leader_id=leader_id,
        )

        self.audit_repo.log("TEAM_CREATED", user_id=user_id, org_id=org_id, resource=team.name)
        return True, "Équipe créée avec succès.", team

    def list_teams_by_org(self, org_id: str) -> List[Team]:
        return self.team_repo.list_by_org(org_id)

    def add_team_member(self, team_id: str, actor_id: str, target_user_id: str, role: str = "MEMBER") -> bool:
        team = self.team_repo.get_by_id(team_id)
        if not team:
            return False
        self.team_repo.add_member(team_id, target_user_id, role=role)
        self.audit_repo.log("TEAM_MEMBER_ADDED", user_id=actor_id, org_id=team.org_id, resource=f"user:{target_user_id}")
        return True

    def remove_team_member(self, team_id: str, actor_id: str, target_user_id: str) -> bool:
        team = self.team_repo.get_by_id(team_id)
        if not team:
            return False
        removed = self.team_repo.remove_member(team_id, target_user_id)
        if removed:
            self.audit_repo.log("TEAM_MEMBER_REMOVED", user_id=actor_id, org_id=team.org_id, resource=f"user:{target_user_id}")
        return removed
