"""Upload progress SSE endpoint with scoped token auth."""
import asyncio
import json
import logging
from typing import AsyncGenerator

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api import deps
from app.core import security
from app.schemas.user import UserPublic
from app.services.upload_progress import get_upload_progress_manager
from app.core.rate_limiter import limiter, user_limiter, get_limit

logger = logging.getLogger(__name__)
router = APIRouter()


class SSETokenResponse(BaseModel):
    token: str


@router.post("/progress-token/{upload_id}", response_model=SSETokenResponse)
@user_limiter.limit(get_limit("file_chunked"))
async def create_progress_token(
    request: Request,
    response: Response,
    upload_id: str,
    user: UserPublic = Depends(deps.get_current_user),
) -> SSETokenResponse:
    """Issue a short-lived, scoped token for the SSE progress stream.

    The returned token is valid for 60 seconds and only grants access
    to the progress stream for the specified ``upload_id``.  Pass it as
    the ``token`` query parameter when opening the EventSource.
    """
    manager = get_upload_progress_manager()
    progress = manager.get_progress(upload_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found",
        )

    token = security.create_sse_token(user_id=user.id, upload_id=upload_id)
    return SSETokenResponse(token=token)


@router.get("/progress/{upload_id}")
@limiter.limit(get_limit("file_chunked"))
async def upload_progress_stream(
    request: Request,
    response: Response,
    upload_id: str,
    token: str = Query(..., description="Scoped SSE token from POST /progress-token/{upload_id}"),
) -> EventSourceResponse:
    """
    Server-Sent Events endpoint for real-time upload progress.

    Requires a scoped SSE token (60 s TTL) obtained via
    ``POST /api/files/progress-token/{upload_id}``.  The token is
    intentionally short-lived so that it is safe to pass as a query
    parameter (which may appear in server access logs).

    Client usage::

        // 1. Obtain scoped token (normal Bearer auth)
        const res = await api.post(`/files/progress-token/${uploadId}`);
        const sseToken = res.data.token;

        // 2. Open SSE stream
        const es = new EventSource(
            `/api/files/progress/${uploadId}?token=${sseToken}`
        );
        es.addEventListener('progress', (e) => {
            console.log(JSON.parse(e.data));
        });
    """
    # Validate scoped SSE token
    try:
        payload = security.decode_token(token, token_type="sse")
    except (jwt.PyJWTError, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired SSE token",
        )

    # Ensure the token was issued for this specific upload
    if payload.get("upload_id") != upload_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token not valid for this upload",
        )

    manager = get_upload_progress_manager()

    # Verify upload exists
    progress = manager.get_progress(upload_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found",
        )

    async def event_generator() -> AsyncGenerator[dict, None]:
        queue = await manager.subscribe(upload_id)
        try:
            while True:
                # Wait for progress update
                progress = await queue.get()

                # None signals end of stream
                if progress is None:
                    break

                # Send progress update as SSE event
                yield {
                    "event": "progress",
                    "data": json.dumps(progress.to_dict()),
                }

                # Stop streaming after completion or failure
                if progress.status in ("completed", "failed"):
                    break

        except asyncio.CancelledError:
            logger.debug("SSE connection cancelled for upload %s", upload_id)
        finally:
            await manager.unsubscribe(upload_id, queue)

    return EventSourceResponse(event_generator())
