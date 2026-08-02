"""
Dépôt de données pour les Équipes et leurs hiérarchies.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import Team, TeamMember, User


class TeamRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        org_id: str,
        name: str,
        description: Optional[str] = None,
        workspace_id: Optional[str] = None,
        parent_team_id: Optional[str] = None,
        leader_id: Optional[str] = None,
    ) -> Team:
        team = Team(
            org_id=org_id,
            workspace_id=workspace_id,
            parent_team_id=parent_team_id,
            name=name,
            description=description,
            leader_id=leader_id,
            is_archived=False,
        )
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)

        # Si un responsable est désigné, l'ajouter automatiquement avec le rôle LEADER
        if leader_id:
            self.add_member(team.id, leader_id, role="LEADER")

        return team

    def get_by_id(self, team_id: str) -> Optional[Team]:
        return self.db.query(Team).filter(Team.id == team_id).first()

    def list_by_org(self, org_id: str) -> List[Team]:
        return self.db.query(Team).filter(Team.org_id == org_id, Team.is_archived == False).all()

    def add_member(self, team_id: str, user_id: str, role: str = "MEMBER") -> TeamMember:
        existing = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if existing:
            existing.role = role
            self.db.commit()
            return existing

        member = TeamMember(team_id=team_id, user_id=user_id, role=role)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, team_id: str, user_id: str) -> bool:
        member = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if not member:
            return False
        self.db.delete(member)
        self.db.commit()
        return True

    def list_team_members(self, team_id: str) -> List[TeamMember]:
        return self.db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
