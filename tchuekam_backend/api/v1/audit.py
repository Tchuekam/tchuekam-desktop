"""
Endpoints REST pour la consultation des journaux d'audit de sécurité.
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.schemas import AuditLogResponseSchema
from tchuekam_backend.repositories.audit_repository import AuditRepository
from tchuekam_backend.api.dependencies import require_permission

router = APIRouter(prefix="/audit", tags=["Security Audit Logs"])


@router.get("/logs", response_model=List[AuditLogResponseSchema])
def get_audit_logs(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("audit", "logs", "READ")),
):
    audit_repo = AuditRepository(db)
    logs = audit_repo.list_logs(limit=limit, offset=offset)
    return logs
