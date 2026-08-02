"""
Endpoints REST pour la Gestion des Profils Utilisateurs et des Appareils Connectés.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.models import User
from tchuekam_backend.domain.schemas import (
    ChangePasswordSchema,
    UserProfileSchema,
    UserResponseSchema,
    UserSessionSchema,
)
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.services.user_service import UserService
from tchuekam_backend.api.dependencies import get_current_user, get_current_user_with_token

router = APIRouter(prefix="/users", tags=["Users & Sessions"])


@router.get("/me", response_model=UserResponseSchema)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    roles = [r.name for r in user_repo.get_user_roles(current_user.id)]
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at,
        "profile": current_user.profile,
        "roles": roles,
    }


@router.put("/me/profile", response_model=UserProfileSchema)
def update_my_profile(
    payload: UserProfileSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_repo = UserRepository(db)
    updated_profile = user_repo.update_profile(
        user_id=current_user.id,
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
        phone_number=payload.phone_number,
        preferences_json=payload.preferences_json,
    )
    if not updated_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil non trouvé.")
    return updated_profile


@router.post("/me/password")
def change_my_password(
    payload: ChangePasswordSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_service = UserService(db)
    success, msg = user_service.change_password(current_user.id, payload.current_password, payload.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"message": msg}


@router.get("/me/devices", response_model=List[UserSessionSchema])
def list_connected_devices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session_repo = SessionRepository(db)
    sessions = session_repo.get_active_sessions(current_user.id)
    return sessions


@router.delete("/me/devices/{session_id}")
def revoke_device_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_repo = SessionRepository(db)
    target_session = session_repo.get_by_id(session_id)
    if not target_session or target_session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appareil/Session non trouvé.")
    session_repo.revoke_session(session_id)
    return {"message": "Session révoquée avec succès."}
