"""
Endpoints REST pour la Gestion des Invitations par e-mail.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.tenant_context import get_current_org, require_org_role
from tchuekam_backend.domain.models import User, Organization
from tchuekam_backend.domain.schemas import (
    InvitationAcceptSchema,
    InvitationCreateSchema,
    InvitationResponseSchema,
)
from tchuekam_backend.services.invitation_service import InvitationService
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/invitations", tags=["Invitations & Onboarding"])

#: Hiérarchie des rôles d'organisation, du moins au plus privilégié.
_ORG_ROLE_RANK = {"VIEWER": 1, "MEMBER": 2, "ADMIN": 3, "OWNER": 4}


@router.post("", response_model=InvitationResponseSchema, status_code=status.HTTP_201_CREATED)
def invite_member(
    payload: InvitationCreateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    membership=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    # Un invitant ne peut pas accorder un rôle supérieur au sien.
    # ``add_org_member`` met à jour le rôle d'une adhésion existante : sans ce
    # contrôle, un ADMIN s'invitait lui-même en OWNER et voyait son adhésion
    # promue — élévation de privilèges verticale.
    requested_role = (payload.role or "MEMBER").strip().upper()
    if requested_role not in _ORG_ROLE_RANK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle d'organisation inconnu : '{payload.role}'.",
        )
    inviter_rank = _ORG_ROLE_RANK.get((membership.role or "").strip().upper(), 0)
    if _ORG_ROLE_RANK[requested_role] > inviter_rank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez pas accorder un rôle supérieur au vôtre.",
        )

    inv_service = InvitationService(db)
    success, msg, invitation, token = inv_service.create_invitation(
        org_id=org.id,
        invited_by_id=current_user.id,
        email=payload.email,
        role=payload.role,
        workspace_id=payload.workspace_id,
    )
    if not success or not invitation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    res_dict = {
        "id": invitation.id,
        "org_id": invitation.org_id,
        "workspace_id": invitation.workspace_id,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expires_at": invitation.expires_at,
        "created_at": invitation.created_at,
    }
    # Le jeton d'invitation doit parvenir à l'invité par e-mail. Le renvoyer
    # dans la réponse le place dans les journaux d'accès, l'historique du
    # navigateur et tout proxy intermédiaire ; il n'est donc exposé qu'en
    # développement, faute de service d'e-mail branché.
    if settings.EXPOSE_SENSITIVE_TOKENS:
        res_dict["token"] = token
    return res_dict


@router.get("", response_model=List[InvitationResponseSchema])
def list_pending_invitations(
    org: Organization = Depends(get_current_org),
    _role=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    inv_service = InvitationService(db)
    invites = inv_service.invitation_repo.list_pending_by_org(org.id)
    return invites


@router.post("/accept")
def accept_invitation(
    payload: InvitationAcceptSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv_service = InvitationService(db)
    success, msg = inv_service.accept_invitation(payload.token, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"message": msg}
