"""
Hierarchy of domain exceptions for standardized API error handling.
"""

from typing import Any, List, Optional


class AppException(Exception):
    """Base exception for application-level errors."""
    status_code: int = 400
    error_code: str = "BAD_REQUEST"

    def __init__(
        self,
        message: str = "Une erreur est survenue.",
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[List[Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.details = details or []


class ValidationError(AppException):
    """Exception raised when input validation fails."""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class NotFoundError(AppException):
    """Exception raised when a requested resource is not found."""
    status_code = 404
    error_code = "NOT_FOUND"


class UnauthorizedError(AppException):
    """Exception raised when authentication fails or credentials are missing."""
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    """Exception raised when an authenticated user lacks required permissions."""
    status_code = 403
    error_code = "FORBIDDEN"


class ConflictError(AppException):
    """Exception raised when a resource conflict occurs (e.g. duplicate unique key)."""
    status_code = 409
    error_code = "CONFLICT"


class RateLimitError(AppException):
    """Exception raised when client exceeds allowed rate limits."""
    status_code = 429
    error_code = "TOO_MANY_REQUESTS"


class SecurityError(AppException):
    """Exception raised for security violations."""
    status_code = 400
    error_code = "SECURITY_VIOLATION"


class FileUploadError(AppException):
    """Exception raised for invalid or rejected file uploads."""
    status_code = 400
    error_code = "FILE_UPLOAD_ERROR"
