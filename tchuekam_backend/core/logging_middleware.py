"""
Middleware for structured HTTP logging and enforcement of HTTP security headers.
"""

import logging
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("tchuekam_backend.http")


class StructuredLoggingAndSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Logs structured HTTP requests and applies enterprise security headers to all responses."""

    SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "set-cookie"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        url_path = request.url.path

        # Log request incoming
        logger.info(f"--> {method} {url_path} from {client_ip}")

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"<-- {method} {url_path} 500 Internal Error ({duration_ms:.2f}ms) - {str(exc)}")
            raise exc

        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        logger.info(f"<-- {method} {url_path} {status_code} ({duration_ms:.2f}ms)")

        # Inject enterprise HTTP security headers
        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; object-src 'none';"

        return response
