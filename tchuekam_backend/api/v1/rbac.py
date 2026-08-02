"""
Endpoints REST pour la Gestion Dynamique des Rôles et Permissions (RBAC).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.schemas import (
    PermissionCreateSchema,
    PermissionResponseSchema,
    RoleCreateSchema,
    RoleResponseSchema,
    UserRoleAssignSchema,
)
from tchuekam_backend.services.rbac_service import RbacService
from tchuekam_backend.api.dependencies import require_permission

router = APIRouter(prefix="/rbac", tags=["Dynamic RBAC Engine"])


@router.get("/roles", response_model=List[RoleResponseSchema])
def list_roles(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("rbac", "roles", "READ")),
):
    rbac_service = RbacService(db)
    roles = rbac_service.rbac_repo.list_roles()
    result = []
    for r in roles:
        perms = rbac_service.rbac_repo.get_role_permissions(r.id)
        result.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_system_role": r.is_system_role,
            "permissions": perms,
        })
    return result


@router.post("/roles", response_model=RoleResponseSchema, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreateSchema,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("rbac", "roles", "UPDATE")),
):
    rbac_service = RbacService(db)
    existing = rbac_service.rbac_repo.get_role_by_name(payload.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Un rôle avec ce nom existe déjà.")

    role = rbac_service.create_role(
        name=payload.name,
        description=payload.description,
        permission_ids=payload.permission_ids,
    )
    perms = rbac_service.rbac_repo.get_role_permissions(role.id)
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system_role": role.is_system_role,
        "permissions": perms,
    }


@router.get("/permissions", response_model=List[PermissionResponseSchema])
def list_permissions(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("rbac", "roles", "READ")),
):
    rbac_service = RbacService(db)
    return rbac_service.rbac_repo.list_permissions()


@router.post("/permissions", response_model=PermissionResponseSchema, status_code=status.HTTP_201_CREATED)
def create_permission(
    payload: PermissionCreateSchema,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("rbac", "roles", "UPDATE")),
):
    rbac_service = RbacService(db)
    existing = rbac_service.rbac_repo.get_permission_by_name(payload.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Une permission avec ce nom existe déjà.")

    perm = rbac_service.rbac_repo.create_permission(
        name=payload.name,
        module=payload.module,
        resource=payload.resource,
        action=payload.action,
        description=payload.description,
    )
    return perm


@router.post("/user-roles")
def assign_user_roles(
    payload: UserRoleAssignSchema,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("rbac", "roles", "UPDATE")),
):
    rbac_service = RbacService(db)
    success = rbac_service.assign_user_roles(user_id=payload.user_id, role_ids=payload.role_ids)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur non trouvé.")
    return {"message": "Rôles attribués avec succès à l'utilisateur."}
