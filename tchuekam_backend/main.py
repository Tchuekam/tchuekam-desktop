"""
Point d'entrée principal de l'application FastAPI backend TchueKAM avec sécurité, middlewares et gestionnaire d'erreurs centralisé.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from tchuekam_backend.api.router import api_router
from tchuekam_backend.core.config import settings
from tchuekam_backend.core.database import SessionLocal, init_db
from tchuekam_backend.core.exception_handlers import (
    app_exception_handler,
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from tchuekam_backend.core.exceptions import AppException
from tchuekam_backend.core.logging_middleware import StructuredLoggingAndSecurityHeadersMiddleware
from tchuekam_backend.domain.schemas import APIResponse
from tchuekam_backend.services.rbac_service import RbacService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifecycle Startup: Initialisation DB et seeding RBAC
    init_db()
    db = SessionLocal()
    try:
        rbac_service = RbacService(db)
        rbac_service.seed_default_roles_and_permissions()
    finally:
        db.close()
    yield
    # Lifecycle Shutdown
    pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API REST Enterprise pour TchueKAM SaaS Multi-Tenant.",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 1. GZip Compression Middleware (Minimum response size 1000 bytes)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Structured Logging & Security HTTP Headers Middleware
app.add_middleware(StructuredLoggingAndSecurityHeadersMiddleware)

# 3. Configuration CORS
#
# Garde-fou : Starlette, avec ``allow_origins=["*"]`` ET
# ``allow_credentials=True``, renvoie l'origine de la requête accompagnée de
# ``Access-Control-Allow-Credentials: true`` — n'importe quel site peut alors
# lire des réponses authentifiées. Les deux sont donc mutuellement exclusifs :
# si une configuration réintroduit le joker, on désactive les credentials
# plutôt que d'ouvrir l'API.
_cors_origins = list(settings.ALLOWED_ORIGINS)
_cors_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers Centralisés
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Inclusion des routes API REST v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"], response_model=APIResponse[dict])
def health_check():
    """Endpoint de contrôle de santé (Health Check)."""
    return APIResponse(
        message="Service opérationnel.",
        data={
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tchuekam_backend.main:app", host="0.0.0.0", port=8000, reload=True)
