"""
Point d'entrée principal de l'application FastAPI backend TchueKAM avec sécurité, middlewares et gestionnaire d'erreurs centralisé.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from tchuekam_backend.api.router import api_router
from tchuekam_backend.core.config import _is_production, settings
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


import logging

logger = logging.getLogger("tchuekam_backend.main")


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

    # Start Telegram / Hermes Gateway only when explicitly opted in
    gateway_runner = None
    gateway_task = None
    if settings.TELEGRAM_BOT_TOKEN and os.getenv("TCHUEKAM_ENABLE_EMBEDDED_TELEGRAM", "").strip() == "1":
        try:
            from hermes_cli.env_loader import load_hermes_dotenv
            load_hermes_dotenv()
            from gateway.config import load_gateway_config
            from gateway.run import GatewayRunner
            gw_config = load_gateway_config()
            gateway_runner = GatewayRunner(config=gw_config)

            async def _start_gateway_async():
                try:
                    started = await gateway_runner.start()
                    if started:
                        logger.info("Telegram Bot Gateway (TchuekamCloudbot) connected and started successfully.")
                    else:
                        logger.warning("Telegram Bot Gateway failed to start during lifespan.")
                except Exception as ex:
                    logger.error(f"Error connecting Telegram Bot Gateway: {ex}", exc_info=True)

            gateway_task = asyncio.create_task(_start_gateway_async())
        except Exception as e:
            logger.error(f"Error initializing Telegram Bot Gateway in lifespan: {e}", exc_info=True)

    yield

    # Lifecycle Shutdown
    if gateway_runner:
        try:
            await gateway_runner.stop()
            logger.info("Telegram Bot Gateway stopped cleanly.")
        except Exception as e:
            logger.error(f"Error stopping Telegram Bot Gateway: {e}")


_enable_docs = (not _is_production()) or os.getenv("ENABLE_API_DOCS", "").strip() == "1"

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API REST Enterprise pour TchueKAM SaaS Multi-Tenant.",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if _enable_docs else None,
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    lifespan=lifespan,
)

# 1. GZip Compression Middleware (Minimum response size 1000 bytes)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Structured Logging & Security HTTP Headers Middleware
app.add_middleware(StructuredLoggingAndSecurityHeadersMiddleware)

# 3. Configuration CORS
_cors_origins = list(settings.ALLOWED_ORIGINS)
_cors_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Organization-Id",
        "X-Hermes-Session-Token",
        "X-Requested-With",
    ],
)

# Exception Handlers Centralisés
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Inclusion des routes API REST v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"], response_model=APIResponse[dict])
@app.get(f"{settings.API_V1_STR}/health", tags=["Health"], response_model=APIResponse[dict])
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
