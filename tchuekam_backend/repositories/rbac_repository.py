"""
Dépôt de données pour la gestion dynamique du RBAC (Rôles & Permissions).
"""

import logging
from typing import List, Optional, Set
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tchuekam_backend.core import rbac_cache
from tchuekam_backend.domain.models import Role, Permission, RolePermission, UserRole, User

logger = logging.getLogger("tchuekam_backend.rbac_repository")


class RbacRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- Roles ---

    def create_role(self, name: str, description: Optional[str] = None, is_system_role: bool = False) -> Role:
        # Pas d'invalidation du cache RBAC : un rôle qui vient d'être créé
        # n'a aucun porteur, donc aucune décision déjà mise en cache ne
        # change. L'attribution du rôle, elle, invalide (voir
        # ``assign_roles_to_user``).
        role = Role(name=name, description=description, is_system_role=is_system_role)
        self.db.add(role)
        try:
            self.db.commit()
        except IntegrityError:
            # ``roles.name`` est unique, et le semis procède en « chercher puis
            # créer » : deux processus qui démarrent ensemble ne trouvent rien
            # tous les deux, créent tous les deux, et le second échoue ici.
            # Le rôle existe alors déjà avec ce nom, ce qui est exactement
            # l'état voulu : on le renvoie au lieu de faire échouer l'appelant
            # (et, au démarrage, le worker entier).
            self.db.rollback()
            existing = self.get_role_by_name(name)
            if existing is None:
                # L'unicité du nom n'est pas en cause : l'erreur est réelle.
                raise
            logger.info("Rôle %s déjà créé par un processus concurrent.", name)
            return existing
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
        # Tous les porteurs du rôle perdent ses permissions : on purge le
        # cache RBAC entier plutôt que d'énumérer ces utilisateurs.
        rbac_cache.invalidate_all()
        return True

    # --- Permissions ---

    def create_permission(self, name: str, module: str, resource: str, action: str, description: Optional[str] = None) -> Permission:
        # Pas d'invalidation : une permission qui vient d'être créée n'est
        # rattachée à aucun rôle, donc elle n'élargit les droits de personne.
        # C'est ``assign_permissions_to_role`` qui invalide.
        permission = Permission(
            name=name,
            module=module.lower(),
            resource=resource.lower(),
            action=action.upper(),
            description=description,
        )
        self.db.add(permission)
        try:
            self.db.commit()
        except IntegrityError:
            # Même course que pour ``create_role``, sur l'unicité de
            # ``permissions.name``.
            self.db.rollback()
            existing = self.get_permission_by_name(name)
            if existing is None:
                raise
            logger.info("Permission %s déjà créée par un processus concurrent.", name)
            return existing
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
        try:
            self.db.commit()
        except IntegrityError:
            # Deux processus ont rejoué cette affectation en même temps : leurs
            # DELETE et INSERT s'entrelacent et le second viole la contrainte
            # d'unicité (role_id, permission_id). ``exclusive_startup_lock``
            # sérialise le semis au démarrage, mais il s'ouvre volontairement
            # (fail-open) quand les verrous consultatifs ne sont pas
            # disponibles — il reste donc un chemin où la course se produit.
            #
            # L'opération est idempotente : l'état visé est « ce rôle porte
            # exactement ces permissions ». Si un concurrent vient de l'écrire,
            # le résultat est déjà correct et l'échec n'a rien à signaler.
            self.db.rollback()
            logger.info(
                "Affectation de permissions concurrente sur le rôle %s ; "
                "l'état écrit par le processus concurrent est conservé.",
                role_id,
            )
        # La définition du rôle a changé : chacun de ses porteurs voit ses
        # permissions effectives changer, d'où une purge complète.
        rbac_cache.invalidate_all()
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
        # Seul cet utilisateur est concerné : invalidation ciblée.
        rbac_cache.invalidate_user(user_id)
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
