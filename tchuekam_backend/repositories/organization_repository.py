"""
Dépôt de données pour les Organisations et leurs paramètres Multi-Tenant.
"""

from typing import List, Optional, Tuple
from sqlalchemy import or_
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

    def list_paginated_for_user(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> Tuple[List[Organization], int]:
        """Returns paginated organizations accessible to a user."""
        query = (
            self.db.query(Organization)
            .join(OrganizationMembership, OrganizationMembership.org_id == Organization.id)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "ACTIVE",
                Organization.is_archived == False,
            )
        )

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Organization.name.ilike(search_pattern),
                    Organization.slug.ilike(search_pattern),
                )
            )

        total = query.count()

        sort_attr = getattr(Organization, sort_by, Organization.created_at) if hasattr(Organization, sort_by or "") else Organization.created_at
        if sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())

        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        return items, total

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
