"""
Dépôt de données pour la persistance des journaux d'audit de sécurité.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_
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

    def list_paginated_logs(
        self,
        page: int = 1,
        per_page: int = 20,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> Tuple[List[AuditLog], int]:
        """Returns paginated and filtered audit logs."""
        query = self.db.query(AuditLog)

        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if org_id:
            query = query.filter(AuditLog.org_id == org_id)

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    AuditLog.action.ilike(pattern),
                    AuditLog.resource.ilike(pattern),
                    AuditLog.ip_address.ilike(pattern),
                )
            )

        total = query.count()

        sort_attr = getattr(AuditLog, sort_by, AuditLog.created_at) if hasattr(AuditLog, sort_by or "") else AuditLog.created_at
        if sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())

        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        return items, total
