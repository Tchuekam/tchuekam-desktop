"""
Configuration centralisée du backend TchueKAM.
"""

import os
import secrets
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

#: Environnements considérés comme non-production (secrets éphémères tolérés).
_DEV_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() not in _DEV_ENVIRONMENTS


def _resolve_jwt_secret() -> str:
    """Retourne le secret JWT, en échouant au démarrage s'il manque en production."""
    secret = os.getenv("TCHUEKAM_JWT_SECRET_KEY", "").strip()
    if secret:
        if _is_production() and len(secret) < 32:
            raise RuntimeError(
                "TCHUEKAM_JWT_SECRET_KEY doit contenir au moins 32 caractères en production."
            )
        return secret
    if _is_production():
        raise RuntimeError(
            "TCHUEKAM_JWT_SECRET_KEY est obligatoire lorsque ENVIRONMENT n'est pas un "
            "environnement de développement. Générez-en un avec "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` puis "
            "définissez-le dans l'environnement de déploiement."
        )
    # Développement uniquement : secret éphémère, jamais committé.
    return secrets.token_urlsafe(48)


def _resolve_allowed_origins() -> List[str]:
    """Origines CORS autorisées.

    ``["*"]`` combiné à ``allow_credentials=True`` fait renvoyer par Starlette
    l'origine de la requête accompagnée de ``Access-Control-Allow-Credentials:
    true`` : n'importe quel site peut alors émettre des requêtes authentifiées
    et en lire la réponse. On exige donc une liste explicite.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins
    frontend = os.getenv("FRONTEND_URL", "https://tchuekam.com").strip()
    if _is_production():
        return [frontend]
    return [frontend, "http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"]


class Settings(BaseSettings):
    PROJECT_NAME: str = "TchueKAM Enterprise Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DOMAIN_NAME: str = "tchuekam.com"
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://tchuekam.com")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "https://api.tchuekam.com")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Base de données
    DATABASE_URL: str = os.getenv(
        "TCHUEKAM_DATABASE_URL",
        "sqlite:///./tchuekam_backend.db"
    )
    
    # Sécurité & JWT
    #
    # Aucune valeur de repli n'est codée en dur : un secret committé dans un
    # dépôt public permet à quiconque le lit de forger un jeton d'accès pour
    # n'importe quel utilisateur, y compris un administrateur. Hors
    # développement, l'absence de TCHUEKAM_JWT_SECRET_KEY est une erreur de
    # démarrage (fail-closed). En développement, un secret aléatoire est
    # généré à chaque démarrage — les jetons ne survivent pas à un
    # redémarrage, ce qui est le comportement souhaité en local.
    JWT_SECRET_KEY: str = _resolve_jwt_secret()
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1
    
    # Complexité mot de passe
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    
    # Anti force brute & Rate limiting
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 300
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = 120
    
    # File Upload Security
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    ALLOWED_MIME_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
    ]
    DISALLOWED_EXTENSIONS: List[str] = [
        ".exe", ".bat", ".sh", ".php", ".py", ".js", ".vbs", ".cmd", ".msi", ".dll", ".so", ".dylib", ".html", ".htm", ".svg"
    ]

    # Pagination Defaults
    DEFAULT_PAGE: int = 1
    DEFAULT_PER_PAGE: int = 20
    MAX_PER_PAGE: int = 100

    # OAuth Providers
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID", None)
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET", None)
    
    GITHUB_CLIENT_ID: Optional[str] = os.getenv("GITHUB_CLIENT_ID", None)
    GITHUB_CLIENT_SECRET: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET", None)
    
    APPLE_CLIENT_ID: Optional[str] = os.getenv("APPLE_CLIENT_ID", None)
    APPLE_CLIENT_SECRET: Optional[str] = os.getenv("APPLE_CLIENT_SECRET", None)
    
    MICROSOFT_CLIENT_ID: Optional[str] = os.getenv("MICROSOFT_CLIENT_ID", None)
    MICROSOFT_CLIENT_SECRET: Optional[str] = os.getenv("MICROSOFT_CLIENT_SECRET", None)
    
    FACEBOOK_CLIENT_ID: Optional[str] = os.getenv("FACEBOOK_CLIENT_ID", None)
    FACEBOOK_CLIENT_SECRET: Optional[str] = os.getenv("FACEBOOK_CLIENT_SECRET", None)
    
    # CORS & WebSockets
    ALLOWED_ORIGINS: List[str] = Field(default_factory=_resolve_allowed_origins)
    
    model_config = {"case_sensitive": True}


settings = Settings()
