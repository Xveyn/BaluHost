"""Domain exceptions that map to safe HTTP responses.

A ``ServiceError`` carries a client-safe ``public_message`` (never the raw
exception text) and the HTTP status the global handler should emit. Raise these
instead of ``HTTPException(500, detail=str(e))`` so internal details never reach
API clients (OWASP Sensitive Data Exposure).
"""
from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Base domain error → mapped HTTP status + client-safe message."""

    http_status: int = 500
    public_message: str = "Internal server error"

    def __init__(
        self,
        public_message: str | None = None,
        *,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            public_message: Client-safe text; becomes the response ``detail``.
            detail: A structured client-safe payload to send as ``detail``
                instead of the text - for a documented contract a client
                parses (e.g. the sync-sleep 503). Must never hold exception
                text.
            headers: Response headers, e.g. ``Retry-After``.
        """
        if public_message is not None:
            self.public_message = public_message
        self.public_detail = detail
        self.headers = headers
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


class InsufficientStorageError(ServiceError):
    http_status = 507
    public_message = "Not enough storage space"
