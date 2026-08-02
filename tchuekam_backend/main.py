"""
Point d'entrée principal de l'application FastAPI backend TchueKAM.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.database import SessionLocal, init_db
from tchuekam_backend.services.rbac_service import RbacService
from tchuekam_backend.api.router import api_router


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
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routes API
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de contrôle de santé (Health Check)."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Gestionnaire centralisé des erreurs non gérées."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Une erreur interne du serveur est survenue.", "error": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tchuekam_backend.main:app", host="0.0.0.0", port=8000, reload=True)
