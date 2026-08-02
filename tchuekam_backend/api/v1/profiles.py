"""
Endpoints REST pour la Gestion du Profil Utilisateur Avancé (Langue, Fuseau horaire, Préférences).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.models import User
from tchuekam_backend.domain.schemas import UserProfileSchema
from tchuekam_backend.services.profile_service import ProfileService
from tchuekam_backend.api.dependencies import get_current_user

router = APIRouter(prefix="/profiles", tags=["Profiles & Preferences"])


@router.get("/me", response_model=UserProfileSchema)
def get_my_extended_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil non trouvé.")
    return current_user.profile


@router.put("/me", response_model=UserProfileSchema)
def update_my_extended_profile(
    payload: UserProfileSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile_service = ProfileService(db)
    updated = profile_service.update_profile(
        user_id=current_user.id,
        username=payload.username,
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
        phone_number=payload.phone_number,
        language=payload.language,
        timezone_str=payload.timezone,
        privacy_settings_json=payload.privacy_settings_json,
        notification_settings_json=payload.notification_settings_json,
        preferences_json=payload.preferences_json,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Échec de mise à jour du profil.")
    return updated
