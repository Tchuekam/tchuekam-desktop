"""
Dépôt de données pour les Utilisateurs et leurs Profils.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import User, UserProfile, UserRole, Role


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email.lower().strip()).first()

    def create(self, email: str, password_hash: Optional[str] = None, is_verified: bool = False) -> User:
        user = User(
            email=email.lower().strip(),
            password_hash=password_hash,
            is_verified=is_verified,
        )
        self.db.add(user)
        self.db.flush()
        
        # Création automatique d'un profil vierge
        profile = UserProfile(user_id=user.id)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_password(self, user_id: str, new_password_hash: str) -> bool:
        user = self.get_by_id(user_id)
        if not user:
            return False
        user.password_hash = new_password_hash
        self.db.commit()
        return True

    def mark_email_verified(self, user_id: str) -> bool:
        user = self.get_by_id(user_id)
        if not user:
            return False
        user.is_verified = True
        self.db.commit()
        return True

    def get_user_roles(self, user_id: str) -> List[Role]:
        return (
            self.db.query(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        )

    def update_profile(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        phone_number: Optional[str] = None,
        preferences_json: Optional[str] = None,
    ) -> Optional[UserProfile]:
        user = self.get_by_id(user_id)
        if not user or not user.profile:
            return None
        profile = user.profile
        if full_name is not None:
            profile.full_name = full_name
        if avatar_url is not None:
            profile.avatar_url = avatar_url
        if phone_number is not None:
            profile.phone_number = phone_number
        if preferences_json is not None:
            profile.preferences_json = preferences_json
        self.db.commit()
        self.db.refresh(profile)
        return profile
