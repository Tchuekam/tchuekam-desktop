"""
Agrégateur complet des routes API REST v1 et WebSocket (Module 1 + Module 2 + Files).
"""

from fastapi import APIRouter
from tchuekam_backend.api.v1.auth import router as auth_router
from tchuekam_backend.api.v1.oauth import router as oauth_router
from tchuekam_backend.api.v1.users import router as users_router
from tchuekam_backend.api.v1.rbac import router as rbac_router
from tchuekam_backend.api.v1.audit import router as audit_router
from tchuekam_backend.api.v1.organizations import router as organizations_router
from tchuekam_backend.api.v1.workspaces import router as workspaces_router
from tchuekam_backend.api.v1.teams import router as teams_router
from tchuekam_backend.api.v1.invitations import router as invitations_router
from tchuekam_backend.api.v1.profiles import router as profiles_router
from tchuekam_backend.api.v1.api_keys import router as api_keys_router
from tchuekam_backend.api.v1.files import router as files_router
from tchuekam_backend.api.ws.notifications import router as ws_router

api_router = APIRouter()

# Module 1
api_router.include_router(auth_router)
api_router.include_router(oauth_router)
api_router.include_router(users_router)
api_router.include_router(rbac_router)
api_router.include_router(audit_router)

# Module 2
api_router.include_router(organizations_router)
api_router.include_router(workspaces_router)
api_router.include_router(teams_router)
api_router.include_router(invitations_router)
api_router.include_router(profiles_router)
api_router.include_router(api_keys_router)
api_router.include_router(files_router)

# WebSockets
api_router.include_router(ws_router)
