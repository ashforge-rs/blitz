from __future__ import annotations

from fastapi import HTTPException


class AppError(Exception):
    """
    Base class for all application domain errors.

    Raise subclasses from service methods; the ``DomainError`` handler in
    ``errors/handlers.py`` converts them to HTTP responses automatically.

    Example::

        raise NotFoundError("Order", order_id)  # → 404
        raise ConflictError("email already registered")  # → 409
    """

    status_code: int = 500
    default_message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)

    def as_http_exception(self) -> HTTPException:
        return HTTPException(status_code=self.status_code, detail=self.message)


# ---------------------------------------------------------------------------
# 4xx — Client errors
# ---------------------------------------------------------------------------


class NotFoundError(AppError):
    """Resource does not exist. → 404"""

    status_code = 404
    default_message = "Resource not found"

    def __init__(self, resource: str | None = None, identifier: object = None) -> None:
        if resource and identifier is not None:
            message = f"{resource} '{identifier}' not found"
        elif resource:
            message = f"{resource} not found"
        else:
            message = self.default_message
        super().__init__(message)


class ConflictError(AppError):
    """Duplicate / state conflict. → 409"""

    status_code = 409
    default_message = "Conflict"


class ValidationError(AppError):
    """Business-logic validation failure (distinct from Pydantic schema errors). → 422"""

    status_code = 422
    default_message = "Validation error"


class UnauthorizedError(AppError):
    """Missing or invalid credentials. → 401"""

    status_code = 401
    default_message = "Unauthorized"


class ForbiddenError(AppError):
    """Authenticated but not permitted. → 403"""

    status_code = 403
    default_message = "Forbidden"


class RateLimitedError(AppError):
    """Client exceeded allowed request rate. → 429"""

    status_code = 429
    default_message = "Too many requests"


# ---------------------------------------------------------------------------
# 5xx — Server errors
# ---------------------------------------------------------------------------


class ServiceUnavailableError(AppError):
    """Downstream dependency unavailable. → 503"""

    status_code = 503
    default_message = "Service unavailable"


class ExternalServiceError(AppError):
    """Unexpected failure from an external dependency. → 502"""

    status_code = 502
    default_message = "Bad gateway"
