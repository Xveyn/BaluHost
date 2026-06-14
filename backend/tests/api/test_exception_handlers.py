"""Tests for the ServiceError hierarchy and global exception handlers."""
from app.core.exceptions import (
    ServiceError,
    NotFoundError,
    ForbiddenError,
    BadRequestError,
    ConflictError,
    UnprocessableError,
    ServiceUnavailableError,
)


def test_subclass_status_codes():
    assert ServiceError().http_status == 500
    assert NotFoundError().http_status == 404
    assert ForbiddenError().http_status == 403
    assert BadRequestError().http_status == 400
    assert ConflictError().http_status == 409
    assert UnprocessableError().http_status == 422
    assert ServiceUnavailableError().http_status == 503


def test_default_public_messages_are_generic():
    assert ServiceError().public_message == "Internal server error"
    assert NotFoundError().public_message == "Resource not found"
    assert ForbiddenError().public_message == "Operation not permitted"


def test_public_message_override_is_used():
    exc = ServiceUnavailableError("Device offline")
    assert exc.public_message == "Device offline"
    assert str(exc) == "Device offline"
