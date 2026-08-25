"""
Service d'authentification principal : Inscription, Connexion, Rafraîchissement et Révocation.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
import jwt

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    dummy_verify_password,
    hash_password,
    revoke_jti,
    validate_password_complexity,
    verify_password,
)
from tchuekam_backend.core.audit_logger import log_security_event
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.repositories.rbac_repository import RbacRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)
        self.rbac_repo = RbacRepository(db)
        self.audit_repo = AuditRepository(db)

    def sign_up(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Inscrit un nouvel utilisateur."""
        # 1. Vérification de la complexité du mot de passe
        valid, msg = validate_password_complexity(password)
        if not valid:
            return False, msg or "Mot de passe non conforme.", None

        # 2. Vérification de l'unicité de l'email
        existing = self.user_repo.get_by_email(email)
        if existing:
            return False, "Cet email est déjà utilisé.", None

        # 3. Hashage et création
        pwd_hash = hash_password(password)
        user = self.user_repo.create(email=email, password_hash=pwd_hash, is_verified=False)

        if full_name:
            self.user_repo.update_profile(user.id, full_name=full_name)

        # 4. Attribution du rôle par défaut ("User")
        default_role = self.rbac_repo.get_role_by_name("User")
        if default_role:
            self.rbac_repo.assign_roles_to_user(user.id, [default_role.id])

        # 5. Journal d'audit
        self.audit_repo.log("USER_SIGN_UP", user_id=user.id, ip_address=ip_address)
        log_security_event("USER_SIGN_UP", user_id=user.id, ip_address=ip_address)

        return True, "Inscription réussie. Veuillez vérifier votre adresse e-mail.", {
            "user_id": user.id,
            "email": user.email,
        }

    def sign_in(
        self,
        email: str,
        password: str,
        device_name: Optional[str] = "Navigateur Web",
        device_type: Optional[str] = "web",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Authentifie un utilisateur et émet des jetons JWT."""
        user = self.user_repo.get_by_email(email)
        if not user or not user.password_hash:
            # Compte inexistant : on effectue tout de même une vérification de
            # mot de passe contre un hash de leurre afin que la latence de la
            # réponse ne révèle pas si l'adresse est enregistrée.
            dummy_verify_password(password)
            authenticated = False
        else:
            authenticated = verify_password(password, user.password_hash)

        if not authenticated:
            self.audit_repo.log("FAILED_SIGN_IN", resource=email, ip_address=ip_address)
            log_security_event("FAILED_SIGN_IN", resource=email, ip_address=ip_address, status="FAILED")
            return False, "Identifiants invalides.", None

        if not user.is_active:
            return False, "Ce compte a été désactivé.", None

        # Rôles utilisateur
        roles = [r.name for r in self.user_repo.get_user_roles(user.id)]

        # Durée de la session
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # 1. Émission initiale temporaire pour l'identifiant de session
        temp_refresh = create_refresh_token(user.id, session_id="temp")
        session = self.session_repo.create_session(
            user_id=user.id,
            refresh_token=temp_refresh,
            expires_at=expires_at,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # 2. Jetons définitifs liés au session_id
        access_token = create_access_token(user.id, user.email, session.id, roles=roles)
        refresh_token = create_refresh_token(user.id, session.id)

        # Mettre à jour le hash du refresh token dans la session
        from tchuekam_backend.core.security import hash_token
        session.refresh_token_hash = hash_token(refresh_token)
        self.db.commit()

        self.audit_repo.log("USER_SIGN_IN", user_id=user.id, ip_address=ip_address)
        log_security_event("USER_SIGN_IN", user_id=user.id, ip_address=ip_address)

        return True, "Connexion réussie.", {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_id": user.id,
            "email": user.email,
            "roles": roles,
        }

    def refresh_access_token(
        self, refresh_token: str, ip_address: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Renouvelle un Access Token et effectue la rotation du Refresh Token."""
        try:
            payload = decode_jwt_token(refresh_token)
            if payload.get("type") != "refresh":
                return False, "Type de jeton invalide.", None

            user_id = payload.get("sub")
            session_id = payload.get("session_id")
            old_jti = payload.get("jti")

            session = self.session_repo.get_by_id(session_id)
            if not session or session.is_revoked:
                return False, "Session révoquée ou inexistante.", None

            # Rotation *durable* : le jeton présenté doit être celui actuellement
            # enregistré pour la session. La liste noire de JTI vit en mémoire :
            # elle est vidée à chaque redémarrage et n'est pas partagée entre
            # workers uvicorn, si bien qu'un ancien jeton déjà consommé
            # redevenait exploitable pendant toute sa fenêtre de validité
            # (7 jours). Le hash est déjà persisté à chaque émission ; il suffit
            # de le comparer.
            from tchuekam_backend.core.security import hash_token
            presented = hash_token(refresh_token)
            stored = session.refresh_token_hash or ""
            if not hmac.compare_digest(presented, stored):
                # Un jeton valide mais périmé qui resurgit signale un vol :
                # on invalide toute la session plutôt que de la laisser vivre.
                self.session_repo.revoke_session(session.id)
                self.audit_repo.log(
                    "REFRESH_TOKEN_REUSE_DETECTED", user_id=user_id, ip_address=ip_address
                )
                log_security_event(
                    "REFRESH_TOKEN_REUSE_DETECTED",
                    user_id=user_id,
                    ip_address=ip_address,
                    status="ALERT",
                )
                return False, "Session révoquée ou inexistante.", None

            user = self.user_repo.get_by_id(user_id)
            if not user or not user.is_active:
                return False, "Utilisateur inactif.", None

            # Révocation de l'ancien JTI (rotation) — défense immédiate au sein
            # du processus courant, complémentaire au contrôle de hash ci-dessus.
            if old_jti:
                revoke_jti(old_jti, expires_at=payload.get("exp"))

            # Rôles et réémission
            roles = [r.name for r in self.user_repo.get_user_roles(user.id)]
            new_access_token = create_access_token(user.id, user.email, session.id, roles=roles)
            new_refresh_token = create_refresh_token(user.id, session.id)

            from tchuekam_backend.core.security import hash_token
            session.refresh_token_hash = hash_token(new_refresh_token)
            self.session_repo.update_last_active(session.id)

            return True, "Jeton renouvelé avec succès.", {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
                "expires_in_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user_id": user.id,
                "email": user.email,
                "roles": roles,
            }
        except jwt.ExpiredSignatureError:
            return False, "Le jeton de rafraîchissement a expiré. Veuillez vous re-connecter.", None
        except jwt.InvalidTokenError as e:
            return False, f"Jeton invalide : {str(e)}", None

    def logout_session(self, session_id: str, jti: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Déconnecte une session spécifique et révoque le JTI courant."""
        if jti:
            revoke_jti(jti)
        revoked = self.session_repo.revoke_session(session_id)
        if revoked:
            self.audit_repo.log("USER_LOGOUT_SESSION", user_id=user_id, resource=session_id)
        return revoked

    def logout_all(self, user_id: str, jti: Optional[str] = None) -> int:
        """Déconnecte l'utilisateur de l'ensemble de ses appareils."""
        if jti:
            revoke_jti(jti)
        count = self.session_repo.revoke_all_user_sessions(user_id)
        self.audit_repo.log("USER_LOGOUT_ALL_DEVICES", user_id=user_id, details={"count": count})
        return count
