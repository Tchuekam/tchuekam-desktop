"""
Service de gestion avancée des Profils Utilisateurs et des Clés API.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import UserProfile, ApiKey
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.api_key_repository import ApiKeyRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.api_key_repo = ApiKeyRepository(db)
        self.audit_repo = AuditRepository(db)

    def update_profile(
        self,
        user_id: str,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        phone_number: Optional[str] = None,
        language: Optional[str] = None,
        timezone_str: Optional[str] = None,
        privacy_settings_json: Optional[str] = None,
        notification_settings_json: Optional[str] = None,
        preferences_json: Optional[str] = None,
    ) -> Optional[UserProfile]:
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.profile:
            return None
        profile = user.profile

        if username is not None:
            profile.username = username.strip()
        if full_name is not None:
            profile.full_name = full_name
        if avatar_url is not None:
            profile.avatar_url = avatar_url
        if phone_number is not None:
            profile.phone_number = phone_number
        if language is not None:
            profile.language = language
        if timezone_str is not None:
            profile.timezone = timezone_str
        if privacy_settings_json is not None:
            profile.privacy_settings_json = privacy_settings_json
        if notification_settings_json is not None:
            profile.notification_settings_json = notification_settings_json
        if preferences_json is not None:
            profile.preferences_json = preferences_json

        self.db.commit()
        self.db.refresh(profile)
        self.audit_repo.log("PROFILE_UPDATED", user_id=user_id)
        return profile

    # --- API Keys Management ---

    def create_api_key(
        self,
        org_id: str,
        user_id: str,
        name: str,
        scopes: List[str] = None,
        expires_in_days: Optional[int] = 365,
    ) -> Tuple[ApiKey, str]:
        raw_key = f"tk_live_{secrets.token_urlsafe(32)}"
        prefix = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        api_key = self.api_key_repo.create(
            org_id=org_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        self.audit_repo.log("API_KEY_CREATED", user_id=user_id, org_id=org_id, resource=name)
        return api_key, raw_key

    def list_api_keys(self, org_id: str, user_id: str) -> List[ApiKey]:
        return self.api_key_repo.list_by_org(org_id)

    def revoke_api_key(self, key_id: str, user_id: str) -> bool:
        success = self.api_key_repo.revoke(key_id)
        if success:
            self.audit_repo.log("API_KEY_REVOKED", user_id=user_id, resource=key_id)
        return success
