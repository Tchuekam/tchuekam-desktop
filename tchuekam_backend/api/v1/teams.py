"""
Endpoints REST pour la Gestion des Équipes et Hiérarchies.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.tenant_context import get_current_org
from tchuekam_backend.domain.models import User, Organization
from tchuekam_backend.domain.schemas import (
    TeamCreateSchema,
    TeamMemberAddSchema,
    TeamResponseSchema,
    TeamUpdateSchema,
)
from tchuekam_backend.services.team_service import TeamService
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/teams", tags=["Teams & Hierarchy"])


@router.post("", response_model=TeamResponseSchema, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team_service = TeamService(db)
    success, msg, team = team_service.create_team(
        org_id=org.id,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        workspace_id=payload.workspace_id,
        parent_team_id=payload.parent_team_id,
        leader_id=payload.leader_id,
    )
    if not success or not team:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return team


@router.get("", response_model=List[TeamResponseSchema])
def list_teams(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    team_service = TeamService(db)
    return team_service.list_teams_by_org(org.id)


@router.post("/{team_id}/members")
def add_team_member(
    team_id: str,
    payload: TeamMemberAddSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team_service = TeamService(db)
    team = team_service.team_repo.get_by_id(team_id)
    if not team or team.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Équipe introuvable.")

    success = team_service.add_team_member(team_id, current_user.id, payload.user_id, role=payload.role)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Échec de l'ajout du membre.")
    return {"message": "Membre ajouté à l'équipe avec succès."}


@router.delete("/{team_id}/members/{target_user_id}")
def remove_team_member(
    team_id: str,
    target_user_id: str,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team_service = TeamService(db)
    team = team_service.team_repo.get_by_id(team_id)
    if not team or team.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Équipe introuvable.")

    success = team_service.remove_team_member(team_id, current_user.id, target_user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable dans cette équipe.")
    return {"message": "Membre retiré de l'équipe avec succès."}
