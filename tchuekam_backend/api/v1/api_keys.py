"""
Endpoints REST pour la Création, Listing et Révocation des Clés API.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.tenant_context import get_current_org, require_org_role
from tchuekam_backend.domain.models import User, Organization
from tchuekam_backend.domain.schemas import ApiKeyCreateSchema, ApiKeyResponseSchema
from tchuekam_backend.services.profile_service import ProfileService
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/api-keys", tags=["API Keys & Programmatic Access"])


@router.post("", response_model=ApiKeyResponseSchema, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreateSchema,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    profile_service = ProfileService(db)
    api_key, raw_key = profile_service.create_api_key(
        org_id=org.id,
        user_id=current_user.id,
        name=payload.name,
        scopes=payload.scopes,
        expires_in_days=payload.expires_in_days,
    )
    return {
        "id": api_key.id,
        "org_id": api_key.org_id,
        "user_id": api_key.user_id,
        "name": api_key.name,
        "prefix": api_key.prefix,
        "created_at": api_key.created_at,
        "expires_at": api_key.expires_at,
        "last_used_at": api_key.last_used_at,
        "raw_api_key": raw_key,  # Renvoyé uniquement lors de la création initiale
    }


@router.get("", response_model=List[ApiKeyResponseSchema])
def list_api_keys(
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile_service = ProfileService(db)
    return profile_service.list_api_keys(org.id, current_user.id)


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_org_role(["OWNER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    profile_service = ProfileService(db)
    success = profile_service.revoke_api_key(key_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clé API non trouvée.")
    return {"message": "Clé API révoquée avec succès."}
