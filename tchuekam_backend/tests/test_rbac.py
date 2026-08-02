"""
Tests unitaires et d'intégration pour le moteur RBAC dynamique.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.main import app
from tchuekam_backend.services.rbac_service import RbacService
from tchuekam_backend.services.auth_service import AuthService

client = TestClient(app)


def test_seed_roles_and_permissions(db_session):
    rbac_service = RbacService(db_session)
    roles = rbac_service.rbac_repo.list_roles()
    role_names = [r.name for r in roles]

    assert "Super Admin" in role_names
    assert "Admin" in role_names
    assert "Team Owner" in role_names
    assert "Manager" in role_names
    assert "Developer" in role_names
    assert "Support" in role_names
    assert "User" in role_names


def test_dynamic_permission_evaluation(db_session):
    auth_service = AuthService(db_session)
    rbac_service = RbacService(db_session)

    # 1. Inscription utilisateur
    auth_service.sign_up("dev@tchuekam.com", "Password123!", full_name="Dev User")
    user = auth_service.user_repo.get_by_email("dev@tchuekam.com")

    # 2. Vérification permission standard utilisateur
    has_exec = rbac_service.has_permission(user.id, "ai_agent", "runtime", "EXECUTE")
    assert has_exec is True

    has_manage_rbac = rbac_service.has_permission(user.id, "rbac", "roles", "UPDATE")
    assert has_manage_rbac is False

    # 3. Attribution du rôle Admin
    admin_role = rbac_service.rbac_repo.get_role_by_name("Admin")
    rbac_service.assign_user_roles(user.id, [admin_role.id])

    # 4. Vérification après changement dynamique de rôle
    has_manage_rbac_admin = rbac_service.has_permission(user.id, "rbac", "roles", "UPDATE")
    assert has_manage_rbac_admin is True
