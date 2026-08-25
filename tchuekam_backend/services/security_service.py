"""
Service de sécurité avancée : Détection d'activités suspectes et contrôles globaux.
"""

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from tchuekam_backend.core.config import settings
from tchuekam_backend.core.rate_limiter import rate_limiter
from tchuekam_backend.core.audit_logger import log_security_event
from tchuekam_backend.repositories.audit_repository import AuditRepository


class SecurityService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_repo = AuditRepository(db)

    def check_brute_force_login(self, client_ip: str, email: str) -> Tuple[bool, int]:
        """Vérifie si la tentative de connexion dépasse le seuil anti force-brute."""
        key = f"login:{client_ip}:{email.lower()}"
        allowed, remaining = rate_limiter.is_allowed(
            key,
            max_requests=settings.RATE_LIMIT_LOGIN_ATTEMPTS,
            window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        )
        if not allowed:
            self.audit_repo.log("SECURITY_SUSPECTED_BRUTE_FORCE", resource=email, ip_address=client_ip)
            log_security_event("SECURITY_SUSPECTED_BRUTE_FORCE", resource=email, ip_address=client_ip, status="ALERT")
        return allowed, remaining

    def reset_brute_force_counter(self, client_ip: str, email: str) -> None:
        key = f"login:{client_ip}:{email.lower()}"
        rate_limiter.reset(key)
