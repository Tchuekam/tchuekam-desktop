"""
Service de gestion des profils utilisateurs, vérifications et réinitialisations de mots de passe.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_complexity,
    verify_password,
)
from tchuekam_backend.domain.models import EmailVerificationToken, PasswordResetToken
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.session_repository import SessionRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)
        self.audit_repo = AuditRepository(db)

    # --- Email Verification ---

    def create_email_verification_token(self, user_id: str) -> str:
        raw_token = generate_secure_token()
        token_h = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_TOKEN_EXPIRE_HOURS)

        tok = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_h,
            expires_at=expires_at,
            is_used=False,
        )
        self.db.add(tok)
        self.db.commit()
        return raw_token

    def verify_email_token(self, raw_token: str) -> Tuple[bool, str]:
        token_h = hash_token(raw_token)
        tok = (
            self.db.query(EmailVerificationToken)
            .filter(
                EmailVerificationToken.token_hash == token_h,
                EmailVerificationToken.is_used == False,
            )
            .first()
        )
        if not tok:
            return False, "Jeton de vérification d'email invalide ou déjà utilisé."

        now = datetime.now(timezone.utc)
        tok_expires = tok.expires_at.replace(tzinfo=timezone.utc) if tok.expires_at.tzinfo is None else tok.expires_at
        if tok_expires < now:
            return False, "Le lien de vérification d'email a expiré."

        tok.is_used = True
        self.user_repo.mark_email_verified(tok.user_id)
        self.db.commit()
        self.audit_repo.log("USER_EMAIL_VERIFIED", user_id=tok.user_id)
        return True, "Adresse e-mail vérifiée avec succès."

    # --- Password Reset ---

    def create_password_reset_token(self, email: str) -> Tuple[bool, str, Optional[str]]:
        user = self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            # Ne pas révéler l'inexistence de l'utilisateur pour éviter le ré-énumération
            return True, "Si l'adresse existe, un e-mail de réinitialisation a été envoyé.", None

        raw_token = generate_secure_token()
        token_h = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)

        tok = PasswordResetToken(
            user_id=user.id,
            token_hash=token_h,
            expires_at=expires_at,
            is_used=False,
        )
        self.db.add(tok)
        self.db.commit()
        self.audit_repo.log("USER_PASSWORD_RESET_REQUESTED", user_id=user.id)
        return True, "Un lien de réinitialisation a été généré.", raw_token

    def reset_password(self, raw_token: str, new_password: str) -> Tuple[bool, str]:
        valid, msg = validate_password_complexity(new_password)
        if not valid:
            return False, msg or "Mot de passe non conforme."

        token_h = hash_token(raw_token)
        tok = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_h,
                PasswordResetToken.is_used == False,
            )
            .first()
        )
        if not tok:
            return False, "Jeton de réinitialisation invalide ou déjà utilisé."

        now = datetime.now(timezone.utc)
        tok_expires = tok.expires_at.replace(tzinfo=timezone.utc) if tok.expires_at.tzinfo is None else tok.expires_at
        if tok_expires < now:
            return False, "Le lien de réinitialisation a expiré."

        pwd_hash = hash_password(new_password)
        self.user_repo.update_password(tok.user_id, pwd_hash)
        tok.is_used = True
        self.db.commit()

        # Révocation des sessions existantes pour des raisons de sécurité
        self.session_repo.revoke_all_user_sessions(tok.user_id)
        self.audit_repo.log("USER_PASSWORD_RESET_SUCCESS", user_id=tok.user_id)

        return True, "Mot de passe réinitialisé avec succès. Toutes vos sessions ont été déconnectées."

    def change_password(self, user_id: str, current_password: str, new_password: str) -> Tuple[bool, str]:
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.password_hash or not verify_password(current_password, user.password_hash):
            return False, "Le mot de passe actuel est incorrect."

        valid, msg = validate_password_complexity(new_password)
        if not valid:
            return False, msg or "Le nouveau mot de passe est non conforme."

        pwd_hash = hash_password(new_password)
        self.user_repo.update_password(user.id, pwd_hash)
        self.audit_repo.log("USER_PASSWORD_CHANGED", user_id=user.id)
        return True, "Mot de passe modifié avec succès."
