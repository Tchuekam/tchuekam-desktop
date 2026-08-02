"""
Dépôt de données pour la gestion dynamique du RBAC (Rôles & Permissions).
"""

from typing import List, Optional, Set
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import Role, Permission, RolePermission, UserRole, User


class RbacRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- Roles ---

    def create_role(self, name: str, description: Optional[str] = None, is_system_role: bool = False) -> Role:
        role = Role(name=name, description=description, is_system_role=is_system_role)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_role_by_id(self, role_id: str) -> Optional[Role]:
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_role_by_name(self, name: str) -> Optional[Role]:
        return self.db.query(Role).filter(Role.name == name).first()

    def list_roles(self) -> List[Role]:
        return self.db.query(Role).all()

    def delete_role(self, role_id: str) -> bool:
        role = self.get_role_by_id(role_id)
        if not role or role.is_system_role:
            return False
        self.db.delete(role)
        self.db.commit()
        return True

    # --- Permissions ---

    def create_permission(self, name: str, module: str, resource: str, action: str, description: Optional[str] = None) -> Permission:
        permission = Permission(
            name=name,
            module=module.lower(),
            resource=resource.lower(),
            action=action.upper(),
            description=description,
        )
        self.db.add(permission)
        self.db.commit()
        self.db.refresh(permission)
        return permission

    def get_permission_by_id(self, permission_id: str) -> Optional[Permission]:
        return self.db.query(Permission).filter(Permission.id == permission_id).first()

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        return self.db.query(Permission).filter(Permission.name == name).first()

    def list_permissions(self) -> List[Permission]:
        return self.db.query(Permission).all()

    # --- Role-Permission Mappings ---

    def assign_permissions_to_role(self, role_id: str, permission_ids: List[str]) -> bool:
        role = self.get_role_by_id(role_id)
        if not role:
            return False
        # Supprimer les anciennes associations
        self.db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        for p_id in set(permission_ids):
            mapping = RolePermission(role_id=role_id, permission_id=p_id)
            self.db.add(mapping)
        self.db.commit()
        return True

    def get_role_permissions(self, role_id: str) -> List[Permission]:
        return (
            self.db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role_id)
            .all()
        )

    # --- User-Role Mappings ---

    def assign_roles_to_user(self, user_id: str, role_ids: List[str]) -> bool:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for r_id in set(role_ids):
            user_role = UserRole(user_id=user_id, role_id=r_id)
            self.db.add(user_role)
        self.db.commit()
        return True

    def get_user_permissions(self, user_id: str) -> List[Permission]:
        """Récupère l'ensemble dédoublonné des permissions associées à l'ensemble des rôles de l'utilisateur."""
        return (
            self.db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
