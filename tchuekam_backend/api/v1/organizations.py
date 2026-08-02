"""
Endpoints REST pour la Gestion des Organisations (CRUD, Archivage, Membres, Paramètres).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.tenant_context import get_current_org, require_org_role
from tchuekam_backend.domain.models import User, Organization
from tchuekam_backend.domain.schemas import (
    OrganizationCreateSchema,
    OrganizationMemberSchema,
    OrganizationResponseSchema,
    OrganizationUpdateSchema,
)
from tchuekam_backend.services.organization_service import OrganizationService
from tchuekam_backend.services.user_management_service import UserManagementService
from tchuekam_backend.repositories.membership_repository import MembershipRepository
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/organizations", tags=["Organizations & Multi-Tenancy"])


@router.post("", response_model=OrganizationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_service = OrganizationService(db)
    success, msg, org = org_service.create_organization(
        user_id=current_user.id,
        name=payload.name,
        slug=payload.slug,
        logo_url=payload.logo_url,
        custom_domain=payload.custom_domain,
    )
    if not success or not org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return org


@router.get("", response_model=List[OrganizationResponseSchema])
def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_service = OrganizationService(db)
    return org_service.list_user_organizations(current_user.id)


@router.get("/current", response_model=OrganizationResponseSchema)
def get_current_organization(org: Organization = Depends(get_current_org)):
    return org


@router.put("/current", response_model=OrganizationResponseSchema)
def update_current_organization(
    payload: OrganizationUpdateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    org_service = OrganizationService(db)
    success, msg, updated_org = org_service.update_organization(
        org_id=org.id,
        user_id=current_user.id,
        name=payload.name,
        logo_url=payload.logo_url,
        custom_domain=payload.custom_domain,
        settings_json=payload.settings_json,
    )
    if not success or not updated_org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return updated_org


@router.post("/current/archive")
def archive_current_organization(
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_org_role(["OWNER"])),
    db: Session = Depends(get_db),
):
    org_service = OrganizationService(db)
    success = org_service.archive_organization(org.id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Échec de l'archivage.")
    return {"message": "Organisation archivée avec succès."}


@router.get("/current/members", response_model=List[OrganizationMemberSchema])
def list_organization_members(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    mem_repo = MembershipRepository(db)
    memberships = mem_repo.list_org_members(org.id)
    result = []
    for m in memberships:
        user = db.query(User).filter(User.id == m.user_id).first()
        full_name = user.profile.full_name if user and user.profile else None
        result.append({
            "id": m.id,
            "org_id": m.org_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "joined_at": m.joined_at,
            "user_email": user.email if user else None,
            "user_full_name": full_name,
        })
    return result


@router.post("/current/members/{target_user_id}/suspend")
def suspend_member(
    target_user_id: str,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    um_service = UserManagementService(db)
    success = um_service.suspend_user_in_org(org.id, current_user.id, target_user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable.")
    return {"message": "Membre suspendu avec succès."}
