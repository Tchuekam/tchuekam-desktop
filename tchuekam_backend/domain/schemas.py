"""
Schémas Pydantic pour la validation stricte des entrées et sorties d'API (Module 1 + Module 2).
"""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


# --- General Envelope & Pagination Schemas ---

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str
    type: Optional[str] = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: List[Any] = []


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Opération effectuée avec succès."
    data: Optional[T] = None


class PaginatedMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class PaginatedData(BaseModel, Generic[T]):
    items: List[T]
    pagination: PaginatedMeta


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number starting at 1")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")
    search: Optional[str] = Field(default=None, description="Global text search query")
    sort_by: Optional[str] = Field(default=None, description="Field name to sort by")
    sort_order: Optional[str] = Field(default="asc", pattern="^(asc|desc)$", description="Sort direction")


# --- File Upload Schemas ---

class FileRecordResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    storage_path: str
    uploaded_by_id: Optional[str]
    created_at: datetime


# --- Module 1 : Authentification & Utilisateurs ---

class SignUpSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class SignInSchema(BaseModel):
    email: EmailStr
    password: str
    device_name: Optional[str] = "Navigateur Web"
    device_type: Optional[str] = "web"


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_id: str
    email: str
    roles: List[str]


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class ForgotPasswordSchema(BaseModel):
    email: EmailStr


class ResetPasswordSchema(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class UserProfileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    language: Optional[str] = "fr"
    timezone: Optional[str] = "UTC"
    privacy_settings_json: Optional[str] = "{}"
    notification_settings_json: Optional[str] = "{}"
    preferences_json: Optional[str] = "{}"


class UserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    created_at: datetime
    profile: Optional[UserProfileSchema] = None
    roles: List[str] = []


class UserSessionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_name: Optional[str]
    device_type: Optional[str]
    ip_address: Optional[str]
    is_revoked: bool
    created_at: datetime
    last_active_at: datetime


# --- Module 2 : Organisations ---

class OrganizationCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None


class OrganizationUpdateSchema(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None
    settings_json: Optional[str] = None


class OrganizationResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    logo_url: Optional[str]
    custom_domain: Optional[str]
    billing_plan: str
    is_archived: bool
    created_at: datetime


class OrganizationMemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    user_id: str
    role: str
    status: str
    joined_at: datetime
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None


# --- Module 2 : Workspaces ---

class WorkspaceCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = None
    description: Optional[str] = None


class WorkspaceUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings_json: Optional[str] = None


class WorkspaceResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    slug: str
    description: Optional[str]
    is_archived: bool
    created_at: datetime


class WorkspaceMemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    role: str
    joined_at: datetime
    user_email: Optional[str] = None


# --- Module 2 : Équipes ---

class TeamCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    parent_team_id: Optional[str] = None
    leader_id: Optional[str] = None


class TeamUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_team_id: Optional[str] = None
    leader_id: Optional[str] = None


class TeamResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    workspace_id: Optional[str]
    parent_team_id: Optional[str]
    name: str
    description: Optional[str]
    leader_id: Optional[str]
    is_archived: bool
    created_at: datetime


class TeamMemberAddSchema(BaseModel):
    user_id: str
    role: str = "MEMBER"


# --- Module 2 : Invitations ---

class InvitationCreateSchema(BaseModel):
    email: EmailStr
    role: str = "MEMBER"
    workspace_id: Optional[str] = None


class InvitationResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    workspace_id: Optional[str]
    email: EmailStr
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    token: Optional[str] = None  # Retourné lors de la création pour test/intégration


class InvitationAcceptSchema(BaseModel):
    token: str


# --- Module 2 : Clés API ---

class ApiKeyCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    scopes: List[str] = []
    expires_in_days: Optional[int] = None


class ApiKeyResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    user_id: str
    name: str
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    raw_api_key: Optional[str] = None  # Uniquement au moment de la création


# --- OAuth & RBAC Schemas ---

class OAuthAuthorizeResponseSchema(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackSchema(BaseModel):
    code: str
    state: Optional[str] = None
    device_name: Optional[str] = "Connexion Sociale"
    device_type: Optional[str] = "web"


class PermissionCreateSchema(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "users.profile.update"})
    module: str = Field(..., json_schema_extra={"example": "users"})
    resource: str = Field(..., json_schema_extra={"example": "profile"})
    action: str = Field(..., json_schema_extra={"example": "UPDATE"})
    description: Optional[str] = None


class PermissionResponseSchema(PermissionCreateSchema):
    model_config = ConfigDict(from_attributes=True)

    id: str


class RoleCreateSchema(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Developer"})
    description: Optional[str] = None
    permission_ids: List[str] = []


class RoleResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    is_system_role: bool
    permissions: List[PermissionResponseSchema] = []


class UserRoleAssignSchema(BaseModel):
    user_id: str
    role_ids: List[str]


class AuditLogResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str]
    org_id: Optional[str]
    action: str
    resource: Optional[str]
    details_json: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
