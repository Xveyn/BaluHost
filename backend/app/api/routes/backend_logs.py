"""Admin API routes for backend application log viewing and streaming."""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from app.api import deps
from app.core import security
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.schemas.backend_logs import BackendLogsResponse, LogEntryResponse
from app.services.log_buffer import get_log_buffer_handler

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/admin/backend-logs",
    response_model=BackendLogsResponse,
    tags=["admin"],
    summary="Get buffered backend logs",
)
@user_limiter.limit(get_limit("admin_operations"))
async def get_backend_logs(
    request: Request,
    response: Response,
    since_id: int = Query(0, ge=0, description="Return entries with id > since_id"),
    level: Optional[str] = Query(None, description="Minimum log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)"),
    search: Optional[str] = Query(None, description="Case-insensitive substring search"),
    limit: int = Query(200, ge=1, le=1000, description="Max entries to return"),
    current_user=Depends(deps.get_current_admin),
) -> BackendLogsResponse:
    """
    Return buffered backend log entries with optional filtering.

    Admin only. Entries are from the in-memory ring buffer (last ~1000 logs).
    """
    handler = get_log_buffer_handler()
    entries = handler.get_logs(since_id=since_id, level=level, search=search, limit=limit)
    return BackendLogsResponse(
        entries=[LogEntryResponse(**e) for e in entries],
        latest_id=handler.get_latest_id(),
        total_buffered=handler.get_total_buffered(),
    )


@router.get(
    "/admin/backend-logs/stream",
    tags=["admin"],
    summary="SSE stream of new backend logs",
)
@limiter.limit(get_limit("admin_operations"))
async def stream_backend_logs(
    request: Request,
    response: Response,
    token: str = Query(..., description="Admin JWT access token for SSE auth"),
    level: Optional[str] = Query(None, description="Minimum log level filter"),
) -> EventSourceResponse:
    """
    Server-Sent Events stream for real-time backend log entries.

    Auth via query parameter ``token`` (admin JWT) because EventSource
    does not support custom headers.

    Client usage::

        const es = new EventSource(
            `/api/admin/backend-logs/stream?token=${jwt}`
        );
        es.addEventListener('log', (e) => {
            console.log(JSON.parse(e.data));
        });
    """
    # Validate JWT from query parameter
    try:
        payload = security.decode_token(token, token_type="access")
    except (jwt.PyJWTError, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Ensure admin role
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    level_num = getattr(logging, level.upper(), 0) if level else 0
    handler = get_log_buffer_handler()

    async def event_generator() -> AsyncGenerator[dict, None]:
        queue = handler.subscribe()
        try:
            while True:
                entry = await queue.get()

                # Apply level filter
                if level_num and getattr(logging, entry.get("level", ""), 0) < level_num:
                    continue

                yield {
                    "event": "log",
                    "data": json.dumps(entry),
                }
        except asyncio.CancelledError:
            logger.debug("Backend logs SSE connection closed")
        finally:
            handler.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.delete(
    "/admin/backend-logs",
    tags=["admin"],
    summary="Clear backend log buffer",
)
@user_limiter.limit(get_limit("admin_operations"))
async def clear_backend_logs(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_admin),
) -> dict:
    """
    Clear the in-memory log buffer.

    Admin only. This only clears the ring buffer, not the actual application logs.
    """
    from app.services.audit.logger_db import get_audit_logger_db

    handler = get_log_buffer_handler()
    count = handler.get_total_buffered()
    handler.clear()

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="ADMIN",
        user=current_user.username,
        action="clear_backend_logs",
        resource="log_buffer",
        details={"cleared_entries": count},
        success=True,
    )

    return {"cleared": count}
