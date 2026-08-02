"""
Service d'authentification OAuth2 extensible (Google, GitHub, Apple, Microsoft, Facebook).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.oauth_repository import OAuthRepository
from tchuekam_backend.repositories.rbac_repository import RbacRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository
from tchuekam_backend.services.auth_service import AuthService


class BaseOAuthProvider(ABC):
    """Classe de base abstraite pour tous les fournisseurs d'identité OAuth2."""

    name: str

    @abstractmethod
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Génère l'URL d'autorisation du fournisseur social."""
        pass

    @abstractmethod
    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Échange le code d'autorisation contre les informations de profil de l'utilisateur.
        
        Doit retourner une structure avec au minimum:
        {"provider_user_id": str, "email": str, "full_name": Optional[str], "avatar_url": Optional[str]}
        """
        pass


class MockGoogleOAuthProvider(BaseOAuthProvider):
    name = "google"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        client_id = settings.GOOGLE_CLIENT_ID or "mock-google-client-id"
        return f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=openid%20email%20profile&state={state}"

    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        # En mode de test/demo ou production sans mock, on traite les informations utilisateur
        return {
            "provider_user_id": f"google_{code[:12]}",
            "email": f"user_{code[:6]}@gmail.com",
            "full_name": "Google User",
            "avatar_url": "https://lh3.googleusercontent.com/a/default-avatar",
        }


class MockGitHubOAuthProvider(BaseOAuthProvider):
    name = "github"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        client_id = settings.GITHUB_CLIENT_ID or "mock-github-client-id"
        return f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope=user:email&state={state}"

    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {
            "provider_user_id": f"github_{code[:12]}",
            "email": f"dev_{code[:6]}@github.com",
            "full_name": "GitHub Developer",
            "avatar_url": "https://avatars.githubusercontent.com/u/1000",
        }


class MockAppleOAuthProvider(BaseOAuthProvider):
    name = "apple"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        client_id = settings.APPLE_CLIENT_ID or "mock-apple-client-id"
        return f"https://appleid.apple.com/auth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=name%20email&state={state}"

    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {
            "provider_user_id": f"apple_{code[:12]}",
            "email": f"apple_{code[:6]}@privaterelay.appleid.com",
            "full_name": "Apple User",
            "avatar_url": None,
        }


class MockMicrosoftOAuthProvider(BaseOAuthProvider):
    name = "microsoft"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        client_id = settings.MICROSOFT_CLIENT_ID or "mock-microsoft-client-id"
        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=openid%20profile%20email&state={state}"

    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {
            "provider_user_id": f"ms_{code[:12]}",
            "email": f"user_{code[:6]}@outlook.com",
            "full_name": "Microsoft User",
            "avatar_url": None,
        }


class MockFacebookOAuthProvider(BaseOAuthProvider):
    name = "facebook"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        client_id = settings.FACEBOOK_CLIENT_ID or "mock-facebook-client-id"
        return f"https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&scope=email,public_profile&state={state}"

    def get_user_info_from_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {
            "provider_user_id": f"fb_{code[:12]}",
            "email": f"user_{code[:6]}@facebook.com",
            "full_name": "Facebook User",
            "avatar_url": None,
        }


class OAuthService:
    """Gestionnaire centralisé et extensible de fournisseurs OAuth."""

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.oauth_repo = OAuthRepository(db)
        self.rbac_repo = RbacRepository(db)
        self.audit_repo = AuditRepository(db)
        self.auth_service = AuthService(db)

        # Enregistrement dynamique des fournisseurs
        self.providers: Dict[str, BaseOAuthProvider] = {
            "google": MockGoogleOAuthProvider(),
            "github": MockGitHubOAuthProvider(),
            "apple": MockAppleOAuthProvider(),
            "microsoft": MockMicrosoftOAuthProvider(),
            "facebook": MockFacebookOAuthProvider(),
        }

    def register_provider(self, provider: BaseOAuthProvider) -> None:
        """Permet l'ajout dynamique de futurs fournisseurs OAuth."""
        self.providers[provider.name.lower()] = provider

    def get_authorization_url(self, provider_name: str, redirect_uri: str, state: str) -> Tuple[bool, str]:
        provider = self.providers.get(provider_name.lower())
        if not provider:
            return False, f"Fournisseur OAuth '{provider_name}' non supporté."
        url = provider.get_authorization_url(redirect_uri, state)
        return True, url

    def authenticate_via_oauth(
        self,
        provider_name: str,
        code: str,
        redirect_uri: str,
        device_name: Optional[str] = "Connexion Sociale",
        device_type: Optional[str] = "web",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Traite le callback OAuth, crée/associe le compte utilisateur et émet les jetons JWT."""
        provider = self.providers.get(provider_name.lower())
        if not provider:
            return False, f"Fournisseur OAuth '{provider_name}' non supporté.", None

        # 1. Obtenir les données utilisateur du fournisseur
        user_info = provider.get_user_info_from_code(code, redirect_uri)
        provider_user_id = user_info["provider_user_id"]
        email = user_info["email"]
        full_name = user_info.get("full_name")

        # 2. Chercher si le compte OAuth est déjà lié
        oauth_acc = self.oauth_repo.get_by_provider_user_id(provider_name, provider_user_id)
        user = None

        if oauth_acc:
            user = self.user_repo.get_by_id(oauth_acc.user_id)
        else:
            # Recherche par email s'il existe déjà
            user = self.user_repo.get_by_email(email)
            if not user:
                # Création automatique de l'utilisateur vérifié via OAuth
                user = self.user_repo.create(email=email, password_hash=None, is_verified=True)
                if full_name:
                    self.user_repo.update_profile(user.id, full_name=full_name)
                
                # Attribution du rôle par défaut
                default_role = self.rbac_repo.get_role_by_name("User")
                if default_role:
                    self.rbac_repo.assign_roles_to_user(user.id, [default_role.id])

            # Liaison du compte OAuth
            self.oauth_repo.link_oauth_account(
                user_id=user.id,
                provider=provider_name,
                provider_user_id=provider_user_id,
                email=email,
            )

        if not user or not user.is_active:
            return False, "Ce compte utilisateur est inactif.", None

        # 3. Connexion et création de la session JWT
        roles = [r.name for r in self.user_repo.get_user_roles(user.id)]
        from datetime import datetime, timedelta, timezone
        from tchuekam_backend.core.security import create_access_token, create_refresh_token, hash_token

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        temp_refresh = create_refresh_token(user.id, session_id="temp_oauth")
        
        session = self.auth_service.session_repo.create_session(
            user_id=user.id,
            refresh_token=temp_refresh,
            expires_at=expires_at,
            device_name=f"OAuth {provider_name.capitalize()} ({device_name})",
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        access_token = create_access_token(user.id, user.email, session.id, roles=roles)
        refresh_token = create_refresh_token(user.id, session.id)

        session.refresh_token_hash = hash_token(refresh_token)
        self.db.commit()

        self.audit_repo.log("USER_OAUTH_SIGN_IN", user_id=user.id, details={"provider": provider_name}, ip_address=ip_address)

        return True, "Authentification OAuth réussie.", {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_id": user.id,
            "email": user.email,
            "roles": roles,
        }
