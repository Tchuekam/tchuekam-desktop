"""
Endpoints REST pour la Gestion des Workspaces (Création, Édition, Archivage, Membres).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.tenant_context import get_current_org
from tchuekam_backend.domain.models import User, Organization, Workspace
from tchuekam_backend.domain.schemas import (
    WorkspaceCreateSchema,
    WorkspaceResponseSchema,
    WorkspaceUpdateSchema,
)
from tchuekam_backend.services.workspace_service import WorkspaceService
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/workspaces", tags=["Workspaces & Resources"])


@router.post("", response_model=WorkspaceResponseSchema, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_service = WorkspaceService(db)
    success, msg, ws = ws_service.create_workspace(
        org_id=org.id,
        user_id=current_user.id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    if not success or not ws:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return ws


@router.get("", response_model=List[WorkspaceResponseSchema])
def list_workspaces(
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_service = WorkspaceService(db)
    return ws_service.list_workspaces_for_org(org.id, current_user.id)


@router.put("/{workspace_id}", response_model=WorkspaceResponseSchema)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_service = WorkspaceService(db)
    updated_ws = ws_service.update_workspace(
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        settings_json=payload.settings_json,
    )
    if not updated_ws or updated_ws.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace introuvable.")
    return updated_ws


@router.post("/{workspace_id}/archive")
def archive_workspace(
    workspace_id: str,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_service = WorkspaceService(db)
    ws = ws_service.workspace_repo.get_by_id(workspace_id)
    if not ws or ws.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace introuvable.")
    success = ws_service.archive_workspace(workspace_id, current_user.id)
    return {"message": "Workspace archivé avec succès."}
