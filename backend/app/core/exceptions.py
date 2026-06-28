"""Domain exceptions that map to safe HTTP responses.

A ``ServiceError`` carries a client-safe ``public_message`` (never the raw
exception text) and the HTTP status the global handler should emit. Raise these
instead of ``HTTPException(500, detail=str(e))`` so internal details never reach
API clients (OWASP Sensitive Data Exposure).
"""
from __future__ import annotations


class ServiceError(Exception):
    """Base domain error → mapped HTTP status + client-safe message."""

    http_status: int = 500
    public_message: str = "Internal server error"

    def __init__(self, public_message: str | None = None) -> None:
        if public_message is not None:
            self.public_message = public_message
        super().__init__(self.public_message)


class NotFoundError(ServiceError):
    http_status = 404
    public_message = "Resource not found"


class ForbiddenError(ServiceError):
    http_status = 403
    public_message = "Operation not permitted"


class BadRequestError(ServiceError):
    http_status = 400
    public_message = "Invalid request"


class ConflictError(ServiceError):
    http_status = 409
    public_message = "Conflict with current state"


class UnprocessableError(ServiceError):
    http_status = 422
    public_message = "Invalid request"


class BadGatewayError(ServiceError):
    http_status = 502
    public_message = "Bad gateway"


class ServiceUnavailableError(ServiceError):
    http_status = 503
    public_message = "Service temporarily unavailable"
