"""
Module de sécurité : Hachage des mots de passe, gestion des jetons JWT,
génération de jetons sécurisés et liste noire de révocations.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, Tuple

import jwt
from tchuekam_backend.core.config import settings

# In-memory revocation blacklist for instant JWT invalidation
_REVOKED_JTI_BLACKLIST: Set[str] = set()

# Try importing argon2 or bcrypt for primary enterprise hashing
try:
    from argon2 import PasswordHasher
    _ARGON2_HASHER = PasswordHasher()
except ImportError:
    _ARGON2_HASHER = None


def hash_password(password: str) -> str:
    """Hache un mot de passe de manière sécurisée (Argon2id si disponible, ou PBKDF2-HMAC-SHA256)."""
    if _ARGON2_HASHER:
        try:
            return f"argon2id${_ARGON2_HASHER.hash(password)}"
        except Exception:
            pass

    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 120_000)
    return f"pbkdf2_sha256$120000${base64.b64encode(salt).decode('ascii')}${base64.b64encode(key).decode('ascii')}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie qu'un mot de passe en clair correspond au hash enregistré (Argon2id ou PBKDF2)."""
    try:
        if hashed_password.startswith("argon2id$"):
            if _ARGON2_HASHER:
                raw_hash = hashed_password[len("argon2id$"):]
                return _ARGON2_HASHER.verify(raw_hash, plain_password)

        parts = hashed_password.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode('ascii'))
        expected_key = base64.b64decode(parts[3].encode('ascii'))
        computed_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(computed_key, expected_key)
    except Exception:
        return False


def validate_password_complexity(password: str) -> Tuple[bool, Optional[str]]:
    """Valide la complexité minimale d'un mot de passe."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Le mot de passe doit contenir au moins {settings.PASSWORD_MIN_LENGTH} caractères."
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre majuscule."
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre minuscule."
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r'\d', password):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[@$!%*?&_\-#^\(\)\[\]\{\}]', password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial (@$!%*?&_)."
    return True, None


def generate_secure_token() -> str:
    """Génère un jeton aléatoire sécurisé de 32 octets (hex)."""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """Hache un jeton temporaire avec SHA256."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_access_token(
    user_id: str,
    email: str,
    session_id: str,
    roles: list = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Crée un Access Token JWT avec une durée de vie courte (par défaut 15 min)."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + delta
    jti = secrets.token_hex(16)
    
    payload = {
        "sub": str(user_id),
        "email": email,
        "session_id": str(session_id),
        "roles": roles or [],
        "type": "access",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    user_id: str,
    session_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Crée un Refresh Token JWT avec une durée de vie plus longue (par défaut 7 jours)."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = now + delta
    jti = secrets.token_hex(16)
    
    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Décode et vérifie la signature et l'expiration d'un jeton JWT.
    
    Raises:
        jwt.ExpiredSignatureError: Si le jeton est expiré.
        jwt.InvalidTokenError: Si le jeton est invalide ou en liste noire.
    """
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    jti = payload.get("jti")
    if jti and is_jti_revoked(jti):
        raise jwt.InvalidTokenError("Ce jeton a été révoqué.")
    return payload


def revoke_jti(jti: str) -> None:
    """Ajoute un ID unique de jeton (JTI) à la liste noire de révocation."""
    if jti:
        _REVOKED_JTI_BLACKLIST.add(jti)


def is_jti_revoked(jti: str) -> bool:
    """Vérifie si un JTI est dans la liste noire."""
    return jti in _REVOKED_JTI_BLACKLIST
