# Error-Leakage AP0 — Foundation + 5xx Net — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ServiceError` exception hierarchy and global FastAPI exception handlers (ServiceError → mapped safe response, a 5xx `HTTPException` scrubber, and a catch-all → generic 500) so internal error strings never leak to API clients.

**Architecture:** Two new modules under `backend/app/core/` plus three handler registrations in `main.py`. The 5xx scrubber centrally neutralises every `HTTPException(500, detail=str(e))` leak the moment this lands — including in route files not yet migrated — while `ServiceError` (its own handler) and 4xx responses are untouched. This is **AP0** of the error-leakage work (audit GAP-10 / backlog B3); per-file route migration (AP1..N) follows in separate plans.

**Tech Stack:** FastAPI, Starlette exception handlers, pytest + Starlette `TestClient`.

**Spec:** `docs/superpowers/specs/2026-06-14-error-leakage-exception-handler-design.md`

---

## File Structure

- Create `backend/app/core/exceptions.py` — `ServiceError` base + 6 subclasses (status + safe `public_message`). One responsibility: domain-error → safe-HTTP-shape data.
- Create `backend/app/core/exception_handlers.py` — three handlers + `register_exception_handlers(app)`. One responsibility: turn exceptions into safe JSON responses + server-side logging.
- Modify `backend/app/main.py` — call `register_exception_handlers(app)` in `create_app()`.
- Create `backend/tests/api/test_exception_handlers.py` — class assertions + integration tests via fault-injection routes.

---

## Task 1: ServiceError hierarchy

**Files:**
- Create: `backend/app/core/exceptions.py`
- Create (tests): `backend/tests/api/test_exception_handlers.py`

- [ ] **Step 1: Write the failing class tests**

Create `backend/tests/api/test_exception_handlers.py` with:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_exception_handlers.py -q -p no:warnings`
Expected: collection/import error — `ModuleNotFoundError: No module named 'app.core.exceptions'`.

- [ ] **Step 3: Create the exceptions module**

Create `backend/app/core/exceptions.py`:

```python
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


class ServiceUnavailableError(ServiceError):
    http_status = 503
    public_message = "Service temporarily unavailable"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_exception_handlers.py -q -p no:warnings`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/exceptions.py backend/tests/api/test_exception_handlers.py
git commit -m "feat(core): add ServiceError exception hierarchy (B3)"
```

---

## Task 2: Global exception handlers + wiring

**Files:**
- Create: `backend/app/core/exception_handlers.py`
- Modify: `backend/app/main.py` (after line 100, the `RequestValidationError` registration)
- Modify (tests): `backend/tests/api/test_exception_handlers.py` (append integration tests)

- [ ] **Step 1: Append the failing integration tests**

Append to `backend/tests/api/test_exception_handlers.py`:

```python
import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from app.main import app

# Fault-injection routes registered once on the shared app (test-only, no auth).
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


app.include_router(_fault_router)


@pytest.fixture
def raw_client():
    # raise_server_exceptions=False so the catch-all 500 response is returned
    # to the test instead of being re-raised by TestClient.
    return TestClient(app, raise_server_exceptions=False)


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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/api/test_exception_handlers.py -q -p no:warnings`
Expected: import error (`app.core.exception_handlers` missing) or, once that exists, the scrubber/catch-all assertions fail because handlers aren't registered yet. Either way: red.

- [ ] **Step 3: Create the handlers module**

Create `backend/app/core/exception_handlers.py`:

```python
"""Global exception handlers — keep internal error strings out of API responses.

- ServiceError       → mapped HTTP status + public_message
- HTTPException 5xx   → scrubbed to a generic body (defense-in-depth net);
                        4xx delegates to FastAPI's default handler
- Exception (catch-all) → generic 500; full traceback logged server-side
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    logger.warning("ServiceError on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=exc.http_status, content={"detail": exc.public_message})


async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 5xx scrubber: a route that built HTTPException(500, detail=str(e)) would
    # otherwise leak the raw message. Log it server-side, return a generic body.
    # 4xx (often legitimately user-facing) falls through to the default handler.
    if exc.status_code >= 500:
        logger.error(
            "HTTP %s on %s %s (detail scrubbed): %s",
            exc.status_code, request.method, request.url.path, exc.detail,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": "Internal server error"})
    return await http_exception_handler(request, exc)


async def _bare_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _bare_exception_handler)
```

- [ ] **Step 4: Wire it into `main.py`**

In `backend/app/main.py`, immediately after the existing line 100:

```python
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
```

insert:

```python

    # Global exception handlers: ServiceError → safe mapped response; HTTPException
    # 5xx scrubber; catch-all → generic 500. Keeps internal error strings out of
    # API responses (audit GAP-10 / B3).
    from app.core.exception_handlers import register_exception_handlers
    register_exception_handlers(app)
```

(The import is local to `create_app()` to avoid a circular import at module load.)

- [ ] **Step 5: Run the exception-handler tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_exception_handlers.py -q -p no:warnings`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/exception_handlers.py backend/app/main.py backend/tests/api/test_exception_handlers.py
git commit -m "feat(core): global exception handlers + 5xx scrubber net (B3 / GAP-10)"
```

---

## Task 3: Full-suite verification + 5xx assertion-drift fix

The 5xx scrubber changes **every** 5xx response app-wide to `{"detail": "Internal server error"}`. Existing tests that asserted on a raw 5xx `detail` string will now fail. This task finds and fixes that drift. (4xx responses are unchanged, so 4xx-asserting tests are unaffected.)

**Files:**
- Modify (tests): whichever existing test files assert on raw 5xx `detail` strings (discovered by running the suite).

- [ ] **Step 1: Run the full backend suite and collect failures**

Run: `cd backend && python -m pytest -q -p no:warnings`
Expected: the new exception-handler tests pass; some pre-existing tests may fail. The only **acceptable** failures here are assertion drifts where a test checked a 5xx response's `detail` text (e.g. `assert "Failed to ..." in r.json()["detail"]` or `assert r.json()["detail"] == "<raw message>"` on a 500/503). Note each failing test's file and line.

- [ ] **Step 2: Fix each 5xx-detail assertion**

For every failure that is a 5xx-detail drift, update the assertion to the new contract:
- If the test asserted a substring/equality of the 5xx `detail`, change it to `assert r.json()["detail"] == "Internal server error"` (or assert only the status code if the message is irrelevant to the test's intent).
- Do **not** change the asserted **status code** — only the detail text.
- Do **not** "fix" a failure that is NOT a 5xx-detail drift (a genuine regression means a handler bug — stop and re-check Task 2).

Example transformation:

```python
# before
assert resp.status_code == 500
assert "Failed to get fan status" in resp.json()["detail"]
# after
assert resp.status_code == 500
assert resp.json()["detail"] == "Internal server error"
```

- [ ] **Step 3: Re-run the full suite**

Run: `cd backend && python -m pytest -q -p no:warnings`
Expected: all pass (0 failed). If a non-drift failure remains, it indicates a handler-interaction bug — investigate before proceeding.

- [ ] **Step 4: Commit**

```bash
git add backend/tests
git commit -m "test: update 5xx detail assertions for scrubbed error responses (B3)"
```

---

## Done criteria for AP0

- `python -m pytest tests/api/test_exception_handlers.py -q` → 8 passed.
- `python -m pytest -q` (full backend suite) → all pass.
- Every 5xx response now returns `{"detail": "Internal server error"}` (verified by the scrubber test); 4xx detail unchanged; `ServiceError` maps to its `public_message`.

After AP0 ships, the 5xx leak is closed centrally. AP1 (`fans.py`) and the remaining route files are migrated in follow-up plans to remove the dead `try/except` anti-pattern and convert user-actionable cases to `ServiceError`.
