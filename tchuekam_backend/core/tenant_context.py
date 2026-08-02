"""
Gestion du contexte et de l'isolation Multi-Tenant pour les Organisations et Workspaces.
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.models import User, Organization, OrganizationMembership, Workspace, WorkspaceMembership
from tchuekam_backend.api.dependencies import get_current_user


def get_current_org(
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    """Déduit l'organisation courante à partir de l'en-tête X-Organization-Id ou de la première adhésion."""
    if x_organization_id:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.org_id == x_organization_id,
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.status == "ACTIVE",
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé. Vous n'êtes pas membre de cette organisation.",
            )
        org = db.query(Organization).filter(Organization.id == x_organization_id, Organization.is_archived == False).first()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation non trouvée ou archivée.")
        return org

    # Repli : première organisation active de l'utilisateur
    first_membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == current_user.id, OrganizationMembership.status == "ACTIVE")
        .first()
    )
    if not first_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aucune organisation associée à cet utilisateur. Veuillez en créer une.",
        )
    org = db.query(Organization).filter(Organization.id == first_membership.org_id, Organization.is_archived == False).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation principale introuvable.")
    return org


def require_org_role(required_roles: list):
    """Vérifie que l'utilisateur possède un des rôles d'organisation requis."""
    def role_checker(
        org: Organization = Depends(get_current_org),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> OrganizationMembership:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.org_id == org.id,
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.status == "ACTIVE",
            )
            .first()
        )
        if not membership or membership.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action restreinte aux rôles organisationnels : {', '.join(required_roles)}.",
            )
        return membership

    return role_checker
