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
