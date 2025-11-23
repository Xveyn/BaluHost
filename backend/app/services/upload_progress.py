"""Upload progress tracking service using Server-Sent Events (SSE)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class UploadProgress:
    """Upload progress information."""
    upload_id: str
    filename: str
    total_bytes: int
    uploaded_bytes: int
    status: str  # 'uploading', 'completed', 'failed'
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_bytes == 0:
            return 0.0
        return (self.uploaded_bytes / self.total_bytes) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['progress_percentage'] = self.progress_percentage
        return data


class UploadProgressManager:
    """Manages upload progress tracking and SSE connections."""

    def __init__(self):
        self._progress: Dict[str, UploadProgress] = {}
        self._listeners: Dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    def create_upload_session(self, filename: str, total_bytes: int) -> str:
        """Create a new upload session and return upload_id."""
        upload_id = str(uuid.uuid4())
        progress = UploadProgress(
            upload_id=upload_id,
            filename=filename,
            total_bytes=total_bytes,
            uploaded_bytes=0,
            status='uploading',
            started_at=datetime.now(timezone.utc).isoformat()
        )
        self._progress[upload_id] = progress
        self._listeners[upload_id] = []
        logger.info(f"Created upload session {upload_id} for {filename} ({total_bytes} bytes)")
        return str(upload_id)

    async def update_progress(self, upload_id: str, uploaded_bytes: int) -> None:
        """Update upload progress and notify listeners."""
        async with self._lock:
            if upload_id not in self._progress:
                logger.warning(f"Upload ID {upload_id} not found")
                return

            progress = self._progress[upload_id]
            progress.uploaded_bytes = uploaded_bytes

            # Notify all listeners
            await self._notify_listeners(upload_id, progress)

    async def complete_upload(self, upload_id: str) -> None:
        """Mark upload as completed."""
        async with self._lock:
            if upload_id not in self._progress:
                return

            progress = self._progress[upload_id]
            progress.status = 'completed'
            progress.completed_at = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"Upload {upload_id} completed: {progress.filename}")
            
            # Notify listeners
            await self._notify_listeners(upload_id, progress)

            # Clean up after a delay
            asyncio.create_task(self._cleanup_upload(upload_id))

    async def fail_upload(self, upload_id: str, error: str) -> None:
        """Mark upload as failed."""
        async with self._lock:
            if upload_id not in self._progress:
                return

            progress = self._progress[upload_id]
            progress.status = 'failed'
            progress.error = error
            progress.completed_at = datetime.now(timezone.utc).isoformat()
            
            logger.error(f"Upload {upload_id} failed: {error}")
            
            # Notify listeners
            await self._notify_listeners(upload_id, progress)

            # Clean up after a delay
            asyncio.create_task(self._cleanup_upload(upload_id))

    async def subscribe(self, upload_id: str) -> asyncio.Queue:
        """Subscribe to upload progress updates."""
        async with self._lock:
            if upload_id not in self._listeners:
                self._listeners[upload_id] = []
            
            queue: asyncio.Queue = asyncio.Queue()
            self._listeners[upload_id].append(queue)
            
            # Send current state immediately if available
            if upload_id in self._progress:
                await queue.put(self._progress[upload_id])
            
            logger.debug(f"New subscriber for upload {upload_id}")
            return queue

    async def unsubscribe(self, upload_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from upload progress updates."""
        async with self._lock:
            if upload_id in self._listeners:
                try:
                    self._listeners[upload_id].remove(queue)
                    logger.debug(f"Unsubscribed from upload {upload_id}")
                except ValueError:
                    pass

    async def _notify_listeners(self, upload_id: str, progress: UploadProgress) -> None:
        """Notify all listeners about progress update."""
        if upload_id not in self._listeners:
            return

        dead_queues = []
        for queue in self._listeners[upload_id]:
            try:
                await queue.put(progress)
            except Exception as e:
                logger.warning(f"Failed to notify listener: {e}")
                dead_queues.append(queue)

        # Remove dead queues
        for queue in dead_queues:
            try:
                self._listeners[upload_id].remove(queue)
            except ValueError:
                pass

    async def _cleanup_upload(self, upload_id: str, delay: float = 60.0) -> None:
        """Clean up upload session after delay."""
        await asyncio.sleep(delay)
        async with self._lock:
            if upload_id in self._progress:
                del self._progress[upload_id]
                logger.debug(f"Cleaned up upload session {upload_id}")
            if upload_id in self._listeners:
                # Close all remaining queues
                for queue in self._listeners[upload_id]:
                    try:
                        queue.put_nowait(None)  # Signal end
                    except asyncio.QueueFull:
                        pass
                del self._listeners[upload_id]

    def get_progress(self, upload_id: str) -> Optional[UploadProgress]:
        """Get current progress for an upload."""
        return self._progress.get(upload_id)


# Global instance
_manager: Optional[UploadProgressManager] = None


def get_upload_progress_manager() -> UploadProgressManager:
    """Get the global upload progress manager instance."""
    global _manager
    if _manager is None:
        _manager = UploadProgressManager()
    return _manager
