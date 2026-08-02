"""
Dépôt de données pour les Organisations et leurs paramètres Multi-Tenant.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import Organization, OrganizationMembership


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, slug: str, logo_url: Optional[str] = None, custom_domain: Optional[str] = None) -> Organization:
        org = Organization(
            name=name,
            slug=slug.lower().strip(),
            logo_url=logo_url,
            custom_domain=custom_domain,
            billing_plan="free",
            is_archived=False,
        )
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        return org

    def get_by_id(self, org_id: str) -> Optional[Organization]:
        return self.db.query(Organization).filter(Organization.id == org_id).first()

    def get_by_slug(self, slug: str) -> Optional[Organization]:
        return self.db.query(Organization).filter(Organization.slug == slug.lower().strip()).first()

    def list_for_user(self, user_id: str) -> List[Organization]:
        return (
            self.db.query(Organization)
            .join(OrganizationMembership, OrganizationMembership.org_id == Organization.id)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "ACTIVE",
                Organization.is_archived == False,
            )
            .all()
        )

    def update(
        self,
        org_id: str,
        name: Optional[str] = None,
        logo_url: Optional[str] = None,
        custom_domain: Optional[str] = None,
        settings_json: Optional[str] = None,
    ) -> Optional[Organization]:
        org = self.get_by_id(org_id)
        if not org:
            return None
        if name is not None:
            org.name = name
        if logo_url is not None:
            org.logo_url = logo_url
        if custom_domain is not None:
            org.custom_domain = custom_domain
        if settings_json is not None:
            org.settings_json = settings_json
        self.db.commit()
        self.db.refresh(org)
        return org

    def archive(self, org_id: str) -> bool:
        org = self.get_by_id(org_id)
        if not org or org.is_archived:
            return False
        org.is_archived = True
        self.db.commit()
        return True

    def restore(self, org_id: str) -> bool:
        org = self.get_by_id(org_id)
        if not org or not org.is_archived:
            return False
        org.is_archived = False
        self.db.commit()
        return True

    def delete_permanently(self, org_id: str) -> bool:
        org = self.get_by_id(org_id)
        if not org:
            return False
        self.db.delete(org)
        self.db.commit()
        return True
