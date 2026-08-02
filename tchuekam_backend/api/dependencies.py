"""
Dépendances FastAPI pour l'authentification et l'autorisation RBAC.
"""

from typing import Callable, Optional, Tuple
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import jwt

from tchuekam_backend.core.database import get_db
from tchuekam_backend.core.security import decode_jwt_token
from tchuekam_backend.domain.models import User
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.services.rbac_service import RbacService

security_scheme = HTTPBearer(auto_error=False)


def get_current_user_with_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Tuple[User, str, str]:
    """Extrait l'utilisateur, le JTI et le session_id du jeton JWT Bearer."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="En-tête d'authentification Bearer manquant.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_jwt_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Type de jeton invalide. Access Token requis.",
            )
        user_id = payload.get("sub")
        session_id = payload.get("session_id")
        jti = payload.get("jti")

        # Vérification de la session en DB
        session_repo = SessionRepository(db)
        user_session = session_repo.get_by_id(session_id)
        if not user_session or user_session.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La session associée à ce jeton a été révoquée.",
            )

        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Compte utilisateur inactif ou inexistant.",
            )

        session_repo.update_last_active(user_session.id)
        return user, jti, session_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Le jeton d'accès a expiré.",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Jeton invalide : {str(e)}",
        )


def get_current_user(user_tuple: Tuple[User, str, str] = Depends(get_current_user_with_token)) -> User:
    """Dépendance retournant uniquement l'entité User courant."""
    return user_tuple[0]


def require_permission(module: str, resource: str, action: str) -> Callable:
    """Fabrique de dépendance pour la vérification dynamique du RBAC."""
    def permission_checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        rbac_service = RbacService(db)
        if not rbac_service.has_permission(user.id, module, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission insuffisante : [{module}.{resource}.{action}] requis.",
            )
        return user

    return permission_checker
