"""
Service métier des Organisations (Création, Édition, Archivage, Restauration, Domaines et Membres).
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.domain.models import Organization, OrganizationMembership, User
from tchuekam_backend.repositories.organization_repository import OrganizationRepository
from tchuekam_backend.repositories.membership_repository import MembershipRepository
from tchuekam_backend.repositories.workspace_repository import WorkspaceRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db
        self.org_repo = OrganizationRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.workspace_repo = WorkspaceRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_organization(
        self,
        user_id: str,
        name: str,
        slug: Optional[str] = None,
        logo_url: Optional[str] = None,
        custom_domain: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Organization]]:
        """Créer une organisation et attribue le rôle OWNER au créateur."""
        computed_slug = slug or re.sub(r"[^a-z0-9\-]", "", name.lower().replace(" ", "-"))
        if not computed_slug:
            computed_slug = f"org-{user_id[:8]}"

        existing_slug = self.org_repo.get_by_slug(computed_slug)
        if existing_slug:
            return False, f"Le slug d'organisation '{computed_slug}' est déjà utilisé.", None

        org = self.org_repo.create(name=name, slug=computed_slug, logo_url=logo_url, custom_domain=custom_domain)

        # 1. Création de l'adhésion OWNER
        self.membership_repo.add_org_member(org.id, user_id, role="OWNER", status="ACTIVE")

        # 2. Création automatique d'un workspace par défaut ("Général")
        self.workspace_repo.create(org.id, name="Général", slug="general", description="Workspace par défaut")

        self.audit_repo.log("ORG_CREATED", user_id=user_id, org_id=org.id, resource=org.name)
        return True, "Organisation créée avec succès.", org

    def list_user_organizations(self, user_id: str) -> List[Organization]:
        return self.org_repo.list_for_user(user_id)

    def update_organization(
        self,
        org_id: str,
        user_id: str,
        name: Optional[str] = None,
        logo_url: Optional[str] = None,
        custom_domain: Optional[str] = None,
        settings_json: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Organization]]:
        org = self.org_repo.update(
            org_id, name=name, logo_url=logo_url, custom_domain=custom_domain, settings_json=settings_json
        )
        if not org:
            return False, "Organisation introuvable.", None
        self.audit_repo.log("ORG_UPDATED", user_id=user_id, org_id=org_id)
        return True, "Organisation mise à jour avec succès.", org

    def archive_organization(self, org_id: str, user_id: str) -> bool:
        archived = self.org_repo.archive(org_id)
        if archived:
            self.audit_repo.log("ORG_ARCHIVED", user_id=user_id, org_id=org_id)
        return archived

    def restore_organization(self, org_id: str, user_id: str) -> bool:
        restored = self.org_repo.restore(org_id)
        if restored:
            self.audit_repo.log("ORG_RESTORED", user_id=user_id, org_id=org_id)
        return restored
