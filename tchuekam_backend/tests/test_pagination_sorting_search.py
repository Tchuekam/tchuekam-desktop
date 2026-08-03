"""
Tests unitaires et d'intégration pour la pagination, le filtrage par recherche et le tri.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.organization_repository import OrganizationRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository
from tchuekam_backend.main import app

client = TestClient(app)


def test_user_repository_pagination_search_sort(db_session):
    user_repo = UserRepository(db_session)
    
    # 1. Seeding 3 users
    u1 = user_repo.create("alice@test.com", "Pass123!", True)
    u2 = user_repo.create("bob@test.com", "Pass123!", True)
    u3 = user_repo.create("charlie@test.com", "Pass123!", True)
    user_repo.update_profile(u1.id, full_name="Alice Smith")
    user_repo.update_profile(u2.id, full_name="Bob Jones")
    user_repo.update_profile(u3.id, full_name="Charlie Brown")

    # 2. Paginated retrieve page 1 per_page 2
    items, total = user_repo.list_paginated(page=1, per_page=2)
    assert total >= 3
    assert len(items) == 2

    # 3. Search query
    items_search, total_search = user_repo.list_paginated(search="Alice")
    assert total_search == 1
    assert items_search[0].email == "alice@test.com"

    # 4. Sorting asc vs desc
    items_asc, _ = user_repo.list_paginated(sort_by="email", sort_order="asc", per_page=10)
    emails = [u.email for u in items_asc]
    assert emails == sorted(emails)


def test_organization_repository_pagination(db_session):
    user_repo = UserRepository(db_session)
    org_repo = OrganizationRepository(db_session)

    user = user_repo.create("orgowner@test.com", "Pass123!", True)
    org1 = org_repo.create("Alpha Corp", "alpha-corp")
    org2 = org_repo.create("Beta Inc", "beta-inc")

    from tchuekam_backend.domain.models import OrganizationMembership
    db_session.add(OrganizationMembership(org_id=org1.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    db_session.add(OrganizationMembership(org_id=org2.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    db_session.commit()

    items, total = org_repo.list_paginated_for_user(user.id, page=1, per_page=10, search="Alpha")
    assert total == 1
    assert items[0].name == "Alpha Corp"


def test_audit_repository_pagination(db_session):
    audit_repo = AuditRepository(db_session)
    audit_repo.log(action="USER_LOGIN", details={"method": "jwt"})
    audit_repo.log(action="ORG_CREATED", details={"name": "Org 1"})

    items, total = audit_repo.list_paginated_logs(page=1, per_page=10, search="ORG_CREATED")
    assert total >= 1
    assert items[0].action == "ORG_CREATED"
