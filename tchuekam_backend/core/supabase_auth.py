"""
Vérification cryptographique des jetons JWT Supabase Auth (ES256 JWKS / HS256)
et synchronisation automatique des comptes dans la base TchueKAM SaaS.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import jwt
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import Role, User, UserProfile, UserRole
from tchuekam_backend.repositories.user_repository import UserRepository

logger = logging.getLogger("tchuekam_backend.supabase_auth")

DEFAULT_SUPABASE_URL = "https://fzoiiusuqvjhwivstbyb.supabase.co"
DEFAULT_ADMIN_EMAILS = {
    "founder@tchuekam.com",
    "tchuekrostand@gmail.com",
    "rebornedbetalpha@gmail.com",
}


def get_supabase_url() -> str:
    return (os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL).strip().rstrip("/")


def get_supabase_issuer() -> str:
    return f"{get_supabase_url()}/auth/v1"


@lru_cache(maxsize=4)
def _get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def is_supabase_token(token: str) -> bool:
    """Quickly checks unverified claims to see if a JWT was issued by our Supabase Auth."""
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False, "verify_aud": False},
        )
        return claims.get("iss") == get_supabase_issuer()
    except Exception:
        return False


def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """Verifies a Supabase Auth JWT using JWKS (ES256/RS256) or optional HS256 secret."""
    issuer = get_supabase_issuer()
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    jwt_secret = (os.getenv("SUPABASE_JWT_SECRET") or "").strip()
    if alg.startswith("HS"):
        if not jwt_secret:
            raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET required for HS* Supabase tokens.")
        return jwt.decode(
            token,
            jwt_secret,
            algorithms=[alg],
            audience="authenticated",
            issuer=issuer,
        )

    jwks_url = (os.getenv("SUPABASE_JWKS_URL") or f"{issuer}/.well-known/jwks.json").strip()
    jwk_client = _get_jwks_client(jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[alg or "ES256"],
        audience="authenticated",
        issuer=issuer,
    )


def _get_admin_emails() -> set:
    raw = os.getenv("ADMIN_EMAILS", "")
    if not raw.strip():
        return set(DEFAULT_ADMIN_EMAILS)
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def get_or_provision_supabase_user(
    db: Session, payload: Dict[str, Any]
) -> Tuple[User, str, str]:
    """Finds or provisions a local SaaS User linked to a verified Supabase Auth identity."""
    user_id = str(payload.get("sub") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not user_id or not email:
        raise jwt.InvalidTokenError("Supabase JWT missing sub or email claim.")

    repo = UserRepository(db)
    user = repo.get_by_id(user_id) or repo.get_by_email(email)

    meta = payload.get("user_metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    email_confirmed = bool(meta.get("email_verified") or payload.get("email_verified", True))

    if user is None:
        username = (meta.get("username") or email.split("@")[0]).strip().lower()
        full_name = (meta.get("full_name") or username).strip()

        try:
            user = User(
                id=user_id,
                email=email,
                password_hash=None,
                is_active=True,
                is_verified=email_confirmed,
            )
            db.add(user)
            db.flush()

            # Avoid unique collision on username if another user already picked it
            existing_username = (
                db.query(UserProfile).filter(UserProfile.username == username).first()
            )
            if existing_username:
                username = f"{username}_{user_id[:6]}"

            profile = UserProfile(
                user_id=user.id,
                username=username,
                full_name=full_name,
            )
            db.add(profile)

            user_role = db.query(Role).filter(Role.name == "User").first()
            if user_role:
                db.add(UserRole(user_id=user.id, role_id=user_role.id))

            if email in _get_admin_emails():
                admin_role = db.query(Role).filter(Role.name == "Admin").first()
                if admin_role:
                    db.add(UserRole(user_id=user.id, role_id=admin_role.id))

            db.commit()
            user = repo.get_by_id(user.id)
        except IntegrityError:
            db.rollback()
            user = repo.get_by_id(user_id) or repo.get_by_email(email)
    elif not user.is_verified and email_confirmed:
        user.is_verified = True
        db.commit()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte utilisateur est désactivé.",
        )

    session_id = str(payload.get("session_id") or f"supabase:{user.id}")
    jti = str(payload.get("jti") or f"sb:{user.id}:{session_id}")
    return user, session_id, jti


def resolve_supabase_bearer(token: str, db: Session) -> Optional[Tuple[User, str, str]]:
    """Attempts Supabase JWT authentication if the token issuer matches Supabase Auth.

    Returns ``None`` if the token was not issued by Supabase so callers can let local JWT
    error handling run untouched.
    """
    if not is_supabase_token(token):
        return None

    payload = verify_supabase_jwt(token)
    return get_or_provision_supabase_user(db, payload)
