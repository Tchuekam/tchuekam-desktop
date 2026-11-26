"""
Service de contrôle d'accès basé sur les rôles et permissions dynamiques (RBAC).
"""

from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from tchuekam_backend.core import rbac_cache
from tchuekam_backend.core.cache import cache_service
from tchuekam_backend.domain.models import Role, Permission
from tchuekam_backend.repositories.rbac_repository import RbacRepository
from tchuekam_backend.repositories.user_repository import UserRepository
from tchuekam_backend.repositories.audit_repository import AuditRepository


class RbacService:
    def __init__(self, db: Session):
        self.db = db
        self.rbac_repo = RbacRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)

    def seed_default_roles_and_permissions(self) -> None:
        """Initialise les rôles et permissions par défaut en base de données."""
        # 1. Liste des permissions système
        system_permissions = [
            ("users.read", "users", "profile", "READ", "Consulter les utilisateurs"),
            ("users.create", "users", "profile", "CREATE", "Créer un utilisateur"),
            ("users.update", "users", "profile", "UPDATE", "Modifier un utilisateur"),
            ("users.delete", "users", "profile", "DELETE", "Supprimer un utilisateur"),
            ("rbac.manage", "rbac", "roles", "UPDATE", "Gérer les rôles et permissions"),
            ("audit.read", "audit", "logs", "READ", "Consulter les journaux d'audit"),
            ("ai_agent.execute", "ai_agent", "runtime", "EXECUTE", "Exécuter l'agent IA TchueKAM"),
        ]

        created_perms: Dict[str, Permission] = {}
        for name, module, resource, action, desc in system_permissions:
            perm = self.rbac_repo.get_permission_by_name(name)
            if not perm:
                perm = self.rbac_repo.create_permission(name, module, resource, action, desc)
            created_perms[name] = perm

        # 2. Liste des rôles par défaut
        roles_config = [
            ("Super Admin", "Accès administrateur complet et sans restriction", True, list(created_perms.keys())),
            ("Admin", "Administration de la plateforme et gestion utilisateurs", True, ["users.read", "users.create", "users.update", "users.delete", "rbac.manage", "audit.read", "ai_agent.execute"]),
            ("Team Owner", "Propriétaire d'équipe SaaS et gestion d'organisation", True, ["users.read", "users.create", "users.update", "ai_agent.execute"]),
            ("Manager", "Gestionnaire d'équipe et de projets", True, ["users.read", "ai_agent.execute"]),
            ("Developer", "Développeur et intégrateur d'outils / agents", True, ["users.read", "ai_agent.execute"]),
            ("Support", "Support technique et assistance utilisateur", True, ["users.read", "audit.read"]),
            ("User", "Utilisateur standard de la plateforme TchueKAM", True, ["ai_agent.execute"]),
        ]

        for role_name, desc, is_sys, perm_names in roles_config:
            role = self.rbac_repo.get_role_by_name(role_name)
            if not role:
                role = self.rbac_repo.create_role(role_name, desc, is_system_role=is_sys)
            
            p_ids = [created_perms[pname].id for pname in perm_names if pname in created_perms]
            self.rbac_repo.assign_permissions_to_role(role.id, p_ids)

    @staticmethod
    def _permission_token(module: str, resource: str, action: str) -> str:
        """Forme canonique d'une permission, pour une comparaison en O(1)."""
        return f"{module.lower()}:{resource.lower()}:{action.upper()}"

    def _load_user_authz(self, user_id: str) -> dict:
        """Lit en base les rôles et permissions d'un utilisateur.

        Deux requêtes, dont une jointure sur trois tables : c'est précisément
        ce que le cache évite de refaire à chaque requête HTTP.
        """
        return {
            "roles": [r.name for r in self.user_repo.get_user_roles(user_id)],
            "perms": sorted(
                {
                    self._permission_token(p.module, p.resource, p.action)
                    for p in self.rbac_repo.get_user_permissions(user_id)
                }
            ),
        }

    def get_user_authz(self, user_id: str) -> dict:
        """Rôles et permissions d'un utilisateur, en passant par le cache."""
        if not rbac_cache.is_enabled():
            return self._load_user_authz(user_id)

        key = rbac_cache.user_key(str(user_id))
        cached = cache_service.get(key)
        if isinstance(cached, dict) and "roles" in cached and "perms" in cached:
            return cached

        authz = self._load_user_authz(user_id)
        cache_service.set(key, authz, ttl_seconds=rbac_cache.cache_ttl_seconds())
        return authz

    def has_permission(self, user_id: str, module: str, resource: str, action: str) -> bool:
        """Évalue si un utilisateur possède la permission requise."""
        authz = self.get_user_authz(user_id)

        if "Super Admin" in authz.get("roles", ()):
            return True

        return self._permission_token(module, resource, action) in set(authz.get("perms", ()))

    def create_role(self, name: str, description: Optional[str] = None, permission_ids: List[str] = None) -> Role:
        role = self.rbac_repo.create_role(name, description, is_system_role=False)
        if permission_ids:
            self.rbac_repo.assign_permissions_to_role(role.id, permission_ids)
        self.audit_repo.log("RBAC_CREATE_ROLE", resource=role.name)
        return role

    def assign_user_roles(self, user_id: str, role_ids: List[str]) -> bool:
        success = self.rbac_repo.assign_roles_to_user(user_id, role_ids)
        if success:
            self.audit_repo.log("RBAC_ASSIGN_USER_ROLES", user_id=user_id, details={"role_ids": role_ids})
        return success
