"""
Centralized exception handlers ensuring uniform JSON error responses across all API endpoints.
"""

import logging
from typing import Any, Dict
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from tchuekam_backend.core.exceptions import AppException

logger = logging.getLogger("tchuekam_backend.exceptions")


def format_error_response(code: str, message: str, details: Any = None) -> Dict[str, Any]:
    """Builds a standardized error envelope dictionary."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else [],
        },
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler for custom application exceptions."""
    logger.warning(
        f"AppException [{exc.error_code}] on {request.method} {request.url.path}: {exc.message}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(exc.error_code, exc.message, exc.details),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handler for standard FastAPI / Starlette HTTPExceptions."""
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")
    msg = exc.detail if isinstance(exc.detail, str) else "Une erreur HTTP est survenue."
    details = exc.detail if isinstance(exc.detail, list) else []

    logger.warning(f"HTTPException [{exc.status_code}] on {request.method} {request.url.path}: {msg}")
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(error_code, msg, details),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for FastAPI Pydantic request validation errors."""
    formatted_details = []
    for err in exc.errors():
        field_loc = " -> ".join([str(loc) for loc in err.get("loc", []) if loc != "body"])
        formatted_details.append({
            "field": field_loc or "body",
            "issue": err.get("msg", "Valeur invalide."),
            "type": err.get("type", "value_error"),
        })

    logger.info(f"ValidationError on {request.method} {request.url.path}: {formatted_details}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=format_error_response(
            code="VALIDATION_ERROR",
            message="Erreur de validation de la requête.",
            details=formatted_details,
        ),
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled server exceptions (prevents leaking stack traces)."""
    logger.exception(f"Unhandled Exception on {request.method} {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Une erreur interne du serveur est survenue. Veuillez contacter le support si le problème persiste.",
            details=[],
        ),
    )
