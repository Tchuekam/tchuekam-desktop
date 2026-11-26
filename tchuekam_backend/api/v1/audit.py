"""
Endpoints REST pour la consultation des journaux d'audit de sécurité.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.schemas import AuditLogResponseSchema
from tchuekam_backend.repositories.audit_repository import AuditRepository
from tchuekam_backend.api.dependencies import require_permission

router = APIRouter(prefix="/audit", tags=["Security Audit Logs"])

#: Décalage maximum accepté pour la pagination par OFFSET.
#:
#: ``OFFSET n`` demande au moteur de lire puis de *jeter* les n premières
#: lignes. Le coût croît donc linéairement avec le décalage — mesuré sur
#: ``audit_logs`` (``scripts/benchmark.py --suite database``) :
#:
#:     offset      0 :  0,1 ms,    100 lignes lues
#:     offset  1 000 :  1,3 ms,  1 100 lignes lues
#:     offset 10 000 :  5,4 ms, 10 100 lignes lues
#:     offset 40 000 : 18,7 ms, 40 100 lignes lues
#:
#: Soit ~0,45 ms par millier de lignes sautées. ``audit_logs`` ne cesse de
#: croître : à quelques millions de lignes — ce qu'un millier d'utilisateurs
#: produit en quelques mois — un seul appel avec un décalage profond occupe
#: une connexion du pool pendant plusieurs secondes. Le pool compte quelques
#: dizaines de connexions par instance : une poignée de ces appels suffit à
#: le saturer et à dégrader tout le reste de l'API.
#:
#: Le plafond transforme donc une dégradation globale en une erreur locale et
#: explicite, qui indique à l'appelant comment obtenir ce qu'il cherche.
MAX_AUDIT_OFFSET = 10_000


@router.get("/logs", response_model=List[AuditLogResponseSchema])
def get_audit_logs(
    limit: int = Query(default=100, le=500),
    offset: int = Query(
        default=0,
        ge=0,
        le=MAX_AUDIT_OFFSET,
        description=(
            "Décalage de pagination. Plafonné : au-delà, filtrez par date "
            "(before/after) au lieu de paginer en profondeur."
        ),
    ),
    before: Optional[datetime] = Query(
        default=None,
        description=(
            "Ne retourner que les entrées antérieures à cette date. "
            "C'est la façon de parcourir tout l'historique : passez la date "
            "de la dernière entrée reçue pour obtenir la page suivante, à coût "
            "constant quelle que soit la profondeur."
        ),
    ),
    after: Optional[datetime] = Query(
        default=None,
        description="Ne retourner que les entrées postérieures à cette date.",
    ),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("audit", "logs", "READ")),
):
    """Journaux d'audit, les plus récents d'abord.

    Deux façons de paginer :

    * ``offset`` — simple, mais plafonné à ``MAX_AUDIT_OFFSET`` car son coût
      croît avec le décalage (voir la constante).
    * ``before`` — pagination par curseur : en passant l'horodatage de la
      dernière entrée reçue, chaque page coûte le même prix, quelle que soit
      la profondeur atteinte dans l'historique. C'est la méthode à utiliser
      pour un export ou un parcours complet.
    """
    audit_repo = AuditRepository(db)
    logs = audit_repo.list_logs(limit=limit, offset=offset, before=before, after=after)
    return logs
