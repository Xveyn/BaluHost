"""Upload progress SSE endpoint."""
import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.services import auth as auth_service
from app.services import users as user_service
from app.services.upload_progress import get_upload_progress_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress/{upload_id}")
async def upload_progress_stream(
    upload_id: str,
    token: str = Query(..., description="JWT auth token (EventSource cannot send headers)"),
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    """
    Server-Sent Events endpoint for real-time upload progress.

    Uses query-param token auth because the browser EventSource API
    cannot send custom HTTP headers (Authorization: Bearer).

    Client usage:
    ```javascript
    const token = localStorage.getItem('token');
    const eventSource = new EventSource(`/api/files/progress/{upload_id}?token=${token}`);
    eventSource.addEventListener('progress', (event) => {
        const progress = JSON.parse(event.data);
        console.log(`Progress: ${progress.progress_percentage}%`);
    });
    ```
    """
    # Manually validate JWT (EventSource can't send Authorization header)
    try:
        payload = auth_service.decode_token(token)
    except auth_service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = user_service.get_user(payload.sub, db=db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    manager = get_upload_progress_manager()
    
    # Verify upload exists
    progress = manager.get_progress(upload_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
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
                    "data": json.dumps(progress.to_dict())
                }
                
                # Stop streaming after completion or failure
                if progress.status in ('completed', 'failed'):
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"SSE connection cancelled for upload {upload_id}")
        finally:
            await manager.unsubscribe(upload_id, queue)

    return EventSourceResponse(event_generator())
