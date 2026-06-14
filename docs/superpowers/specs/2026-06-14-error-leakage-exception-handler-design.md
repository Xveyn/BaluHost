# Globaler Exception-Handler + Error-Leakage-Elimination — Design

- **Datum:** 2026-06-14
- **Audit-Befund:** GAP-10 (Error-Leakage / kein globaler Exception-Handler),
  Security-Audit 2026-06-14. Knüpft an Backlog-Item **B3**
  (`docs/superpowers/plans/2026-05-08-backend-refactor-backlog.md`, Tasks 6.1–6.4).
- **Status:** Design genehmigt.

## Problem

Zwei verbundene Schwächen:

1. **Kein globales Sicherheitsnetz.** Eine wirklich *unhandled* Exception wird
   zwar von FastAPI/Starlette (bei `debug=False`) generisch zu 500 ohne Body, aber
   ohne konsistente, strukturierte JSON-Antwort und ohne garantiertes Logging.
2. **Explizite Leakage.** **109** Stellen bauen `HTTPException(500, detail=str(e))`
   bzw. `detail=f"…{e}"` — sie fangen die Exception ab und leaken die interne
   Fehlermeldung an den Client (OWASP *Sensitive Data Exposure*). Davon **86 in 28
   Dateien unter `backend/app/api/routes/`** (verifiziert per Inventur 2026-06-14;
   `fans.py` 22, `cloud.py` 8, `plugins_marketplace.py` 6, `vpn.py` 6, `benchmark.py`
   4, …). Diese umgehen jedes globale Sicherheitsnetz, weil sie ihre eigene Response
   bauen — sie müssen pro Stelle angefasst werden.

## Scope

- **In Scope:** Fundament (ServiceError-Hierarchie + globale Handler + main.py +
  Tests) **und** Migration **aller 86** expliziten `detail=str(e)`-Leak-Stellen in
  `backend/app/api/routes/`.
- **Out of Scope (Folge-Issue):** `app/plugins/installed/optical_drive/__init__.py`
  (22 Stellen, Plugin-Code) und `app/services/plugin_marketplace.py` (1 Stelle).
- **Bewusst NICHT angefasst:** die ~811 `except Exception`-Blöcke pauschal — nur
  jene, die `detail=str(e)` an Clients leaken.

## Design

### 1. `backend/app/core/exceptions.py` — ServiceError-Hierarchie

```python
class ServiceError(Exception):
    """Base for domain errors that map to a safe HTTP response.

    Carries a client-safe ``public_message`` (never the raw exception text)
    and the HTTP status the global handler should emit.
    """
    http_status: int = 500
    public_message: str = "Internal server error"

    def __init__(self, public_message: str | None = None):
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

The caller may override `public_message` per raise (e.g.
`raise ServiceUnavailableError("Device offline")`) — but it must remain a curated,
client-safe string, never `str(e)`.

### 2. `backend/app/core/exception_handlers.py` — Handler

```python
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    logger.warning("ServiceError on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=exc.http_status, content={"detail": exc.public_message})


async def _bare_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error_handler)
    # Catch-all for genuinely unhandled exceptions. FastAPI's HTTPException is
    # processed by the framework's own handler and never reaches here.
    app.add_exception_handler(Exception, _bare_exception_handler)
```

### 3. `backend/app/main.py` — Wiring

After the existing `RateLimitExceeded` / `RequestValidationError` handlers are
registered in `create_app()`, add:

```python
from app.core.exception_handlers import register_exception_handlers
register_exception_handlers(app)
```

More specific handlers (`RateLimitExceeded`, `RequestValidationError`,
`HTTPException`) take precedence over the `Exception` catch-all — no conflict.

### 4. Migration of the 86 route leak sites (decision tree per site)

For each `try: <body> except Exception as e: [log] raise HTTPException(500, …str(e)…)`:

- **Generic 500-leak (the common case)** → **delete the whole `try/except`**. The
  exception propagates to `_bare_exception_handler` → generic 500 + full trace
  logged. This is usually a net simplification.
- **`except HTTPException: raise` present** → preserved (or, after deleting the
  wrapper, HTTPExceptions raised inside propagate correctly anyway).
- **A specific exception type mapped to a meaningful status** (e.g.
  `except FanNotFoundError: raise HTTPException(404, …)`) → **keep** the targeted
  handler (optionally convert to the matching `ServiceError` subclass).
- **User-actionable condition** (e.g. "device offline", "no space") → convert to a
  `ServiceError` subclass with a curated `public_message` — **never** `str(e)`. This
  is the part that needs per-site judgment so the frontend keeps a useful toast.
- Redundant per-route `logger.error(...; exc_info=True)` that only duplicates the
  global handler's logging may be dropped; context-rich logging is kept.

### 5. Tests

- New `backend/tests/api/test_exception_handlers.py`: fault-injection routes assert
  `ServiceError` → mapped status + `public_message`; a bare `RuntimeError("…secret…")`
  → 500 with `{"detail": "Internal server error"}` and **no** leaked substring.
- **Assertion-drift remediation:** existing error-path tests that assert on the old
  raw `detail` string must be updated to expect the generic 500 / curated message.
  The plan migrates **file by file** (route file → its tests → suite green) so drift
  is caught incrementally and each step stays reviewable.

## Behaviour change (intentional)

- Unexpected 500s now return generic `{"detail": "Internal server error"}` instead
  of the raw exception text. Correct for genuine internal errors.
- Genuinely user-actionable failures are preserved via `ServiceError` subclasses
  with curated messages, so the web UI keeps meaningful feedback. Identifying these
  is the core judgement of the migration.
- Full tracebacks remain in the server logs (`logger.exception`).

## Risks

- **Test-drift** across many suites is the main risk — mitigated by the file-by-file
  migration with a suite run after each file.
- **Over-deletion**: dropping a `try/except` that also performed cleanup or mapped a
  specific status. Mitigated by the decision tree (keep targeted handlers) and tests.
- **Large change set** (28 files) — one spec, but the plan sequences it so the
  foundation (exceptions + handlers + tests) lands first and is independently
  correct, then each route file is migrated as its own commit.

## Plan sequencing (preview, detailed in the plan)

1. `core/exceptions.py` + tests.
2. `core/exception_handlers.py` + `main.py` wiring + `test_exception_handlers.py`.
3. Migrate route files one per commit, descending by leak count (`fans.py` first),
   updating each file's tests, suite green after each.
4. Full suite + PR.
