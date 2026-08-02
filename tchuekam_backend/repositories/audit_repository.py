"""
Dépôt de données pour la persistance des journaux d'audit de sécurité.
"""

import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import AuditLog


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        audit = AuditLog(
            user_id=user_id,
            org_id=org_id,
            action=action,
            resource=resource,
            details_json=json.dumps(details or {}, ensure_ascii=False),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        return audit

    def list_logs(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        return (
            self.db.query(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
