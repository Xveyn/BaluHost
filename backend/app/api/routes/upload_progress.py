"""Upload progress SSE endpoint."""
import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.api import deps
from app.schemas.user import UserPublic
from app.services.upload_progress import get_upload_progress_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress/{upload_id}")
async def upload_progress_stream(
    upload_id: str,
    user: UserPublic = Depends(deps.get_current_user),
) -> EventSourceResponse:
    """
    Server-Sent Events endpoint for real-time upload progress.
    
    Client usage:
    ```javascript
    const eventSource = new EventSource('/api/files/progress/{upload_id}');
    eventSource.onmessage = (event) => {
        const progress = JSON.parse(event.data);
        console.log(`Progress: ${progress.progress_percentage}%`);
    };
    ```
    """
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
