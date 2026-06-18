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


import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers

# Fault-injection routes mounted on a dedicated test app (test-only, no auth).
_fault_router = APIRouter()


@_fault_router.get("/__test__/service-error")
def _raise_service_error():
    raise NotFoundError("widget 42 not found")


@_fault_router.get("/__test__/service-unavailable")
def _raise_unavailable():
    raise ServiceUnavailableError("Device offline")


@_fault_router.get("/__test__/bare")
def _raise_bare():
    raise RuntimeError("internal detail secret=hunter2")


@_fault_router.get("/__test__/http-500")
def _raise_http_500():
    raise HTTPException(status_code=500, detail="raw db error secret=hunter2")


@_fault_router.get("/__test__/http-400")
def _raise_http_400():
    raise HTTPException(status_code=400, detail="bad filename ../x")


@pytest.fixture
def raw_client():
    # Dedicated app instance so the test does not depend on (or mutate) the
    # global app's middleware stack — which is built lazily on the first request
    # and cached, making any `app.debug` toggle order-dependent under xdist.
    # A fresh FastAPI() defaults to debug=False, the production configuration in
    # which Starlette's ServerErrorMiddleware actually routes to our custom
    # Exception handler (in debug mode it returns a traceback instead).
    # raise_server_exceptions=False so the catch-all 500 response is returned to
    # the test instead of being re-raised by TestClient.
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(_fault_router)
    return TestClient(test_app, raise_server_exceptions=False)


def test_service_error_maps_status_and_public_message(raw_client):
    r = raw_client.get("/__test__/service-error")
    assert r.status_code == 404
    assert r.json()["detail"] == "widget 42 not found"


def test_service_unavailable_maps_503(raw_client):
    r = raw_client.get("/__test__/service-unavailable")
    assert r.status_code == 503
    assert r.json()["detail"] == "Device offline"


def test_bare_exception_returns_generic_500_no_leak(raw_client):
    r = raw_client.get("/__test__/bare")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal server error"
    assert "hunter2" not in r.text
    assert "secret" not in r.text


def test_http_500_detail_is_scrubbed(raw_client):
    r = raw_client.get("/__test__/http-500")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal server error"
    assert "hunter2" not in r.text


def test_http_400_detail_passes_through(raw_client):
    r = raw_client.get("/__test__/http-400")
    assert r.status_code == 400
    assert r.json()["detail"] == "bad filename ../x"
