"""
Dépôt de données pour les Utilisateurs et leurs Profils avec optimisation des requêtes et pagination.
"""

from typing import List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from tchuekam_backend.domain.models import User, UserProfile, UserRole, Role


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        return (
            self.db.query(User)
            .options(
                selectinload(User.profile),
                selectinload(User.user_roles).selectinload(UserRole.role),
            )
            .filter(User.id == user_id)
            .first()
        )

    def get_by_email(self, email: str) -> Optional[User]:
        return (
            self.db.query(User)
            .options(
                selectinload(User.profile),
                selectinload(User.user_roles).selectinload(UserRole.role),
            )
            .filter(User.email == email.lower().strip())
            .first()
        )

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

    def list_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> Tuple[List[User], int]:
        """Returns paginated users with Eager-Loaded relationships to eliminate N+1 queries."""
        query = self.db.query(User).options(
            selectinload(User.profile),
            selectinload(User.user_roles).selectinload(UserRole.role),
        )

        if search:
            search_pattern = f"%{search}%"
            query = query.outerjoin(UserProfile).filter(
                or_(
                    User.email.ilike(search_pattern),
                    UserProfile.full_name.ilike(search_pattern),
                    UserProfile.username.ilike(search_pattern),
                )
            )

        total = query.count()

        # Sorting
        sort_attr = getattr(User, sort_by, User.created_at) if hasattr(User, sort_by or "") else User.created_at
        if sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())

        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        return items, total

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
