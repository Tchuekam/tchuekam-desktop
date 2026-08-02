"""
Configuration centralisée du backend TchueKAM.
"""

import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "TchueKAM Enterprise Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DOMAIN_NAME: str = "tchuekam.com"
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://tchuekam.com")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "https://api.tchuekam.com")
    
    # Base de données
    DATABASE_URL: str = os.getenv(
        "TCHUEKAM_DATABASE_URL",
        "sqlite:///./tchuekam_backend.db"
    )
    
    # Sécurité & JWT
    JWT_SECRET_KEY: str = os.getenv(
        "TCHUEKAM_JWT_SECRET_KEY",
        "tchuekam_super_secret_jwt_key_2026_change_in_production_32_bytes_min!"
    )
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
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    model_config = {"case_sensitive": True}


settings = Settings()

