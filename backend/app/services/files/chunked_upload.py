"""Chunked upload session manager.

Tracks in-flight chunked uploads, writes chunks to temp files on disk,
and finalises uploads by moving temp files to the target location.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Temp directory lives inside the storage root so the final rename/move
# stays on the same filesystem (atomic where supported).
TMP_UPLOAD_DIR = Path(settings.nas_storage_path).expanduser().resolve() / ".tmp" / "uploads"

# How long an idle session is kept before automatic cleanup.
SESSION_MAX_AGE = timedelta(hours=24)


@dataclass
class ChunkedUploadSession:
    """Tracks a single chunked upload."""

    upload_id: str
    target_path: str          # relative path inside storage root
    filename: str
    total_size: int           # declared total size in bytes
    chunk_size: int           # negotiated chunk size
    received_bytes: int = 0
    next_chunk_index: int = 0
    temp_file_path: Path = field(default_factory=Path)
    user_id: int = 0
    username: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChunkedUploadManager:
    """In-memory session tracker for chunked uploads.

    Designed to be a singleton — one instance per process.
    """

    DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(self) -> None:
        self._sessions: Dict[str, ChunkedUploadSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        target_path: str,
        filename: str,
        total_size: int,
        user_id: int,
        username: str,
        chunk_size: int | None = None,
    ) -> ChunkedUploadSession:
        """Create a new chunked upload session and its temp file."""
        upload_id = str(uuid.uuid4())
        negotiated_chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE

        TMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = TMP_UPLOAD_DIR / upload_id

        session = ChunkedUploadSession(
            upload_id=upload_id,
            target_path=target_path,
            filename=filename,
            total_size=total_size,
            chunk_size=negotiated_chunk_size,
            temp_file_path=temp_path,
            user_id=user_id,
            username=username,
        )

        async with self._lock:
            self._sessions[upload_id] = session

        logger.info(
            "Chunked upload session created: id=%s file=%s size=%d chunk=%d",
            upload_id, filename, total_size, negotiated_chunk_size,
        )
        return session

    def get_session(self, upload_id: str) -> Optional[ChunkedUploadSession]:
        return self._sessions.get(upload_id)

    async def write_chunk(
        self,
        upload_id: str,
        chunk_index: int,
        data: bytes,
    ) -> int:
        """Append *data* to the session's temp file.

        Returns the total received bytes after this chunk.
        Raises ``ValueError`` on sequence errors or unknown sessions.
        """
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None:
                raise ValueError(f"Unknown upload session: {upload_id}")
            if chunk_index != session.next_chunk_index:
                raise ValueError(
                    f"Expected chunk {session.next_chunk_index}, got {chunk_index}"
                )

        # Write outside the lock — IO can be slow.
        # Using sync write is fine: disk IO is fast, the bottleneck is network.
        with open(session.temp_file_path, "ab") as f:
            f.write(data)

        async with self._lock:
            session.received_bytes += len(data)
            session.next_chunk_index += 1

        return session.received_bytes

    async def write_chunk_stream(
        self,
        upload_id: str,
        chunk_index: int,
        stream: "AsyncIterator[bytes]",
    ) -> int:
        """Stream chunk data directly to disk without buffering the whole chunk.

        *stream* is an async iterator yielding raw byte fragments (e.g.
        ``request.stream()``).  Each fragment is appended to the temp file
        immediately, keeping peak memory close to the network read-buffer size
        rather than the full chunk size.

        Returns the total received bytes after this chunk.
        """
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None:
                raise ValueError(f"Unknown upload session: {upload_id}")
            if chunk_index != session.next_chunk_index:
                raise ValueError(
                    f"Expected chunk {session.next_chunk_index}, got {chunk_index}"
                )

        chunk_bytes = 0
        with open(session.temp_file_path, "ab") as f:
            async for part in stream:
                f.write(part)
                chunk_bytes += len(part)

        async with self._lock:
            session.received_bytes += chunk_bytes
            session.next_chunk_index += 1

        return session.received_bytes

    async def complete_session(self, upload_id: str) -> Path:
        """Finalise the upload: return the temp file path.

        The caller (route layer) is responsible for moving the file to its
        final destination, creating metadata, and audit logging.
        After calling this the session is removed.
        """
        async with self._lock:
            session = self._sessions.pop(upload_id, None)
        if session is None:
            raise ValueError(f"Unknown upload session: {upload_id}")

        if not session.temp_file_path.exists():
            raise FileNotFoundError(f"Temp file missing for session {upload_id}")

        logger.info(
            "Chunked upload completed: id=%s file=%s bytes=%d",
            upload_id, session.filename, session.received_bytes,
        )
        return session.temp_file_path

    async def abort_session(self, upload_id: str) -> None:
        """Abort an upload and clean up the temp file."""
        async with self._lock:
            session = self._sessions.pop(upload_id, None)
        if session is None:
            return
        self._remove_temp_file(session.temp_file_path)
        logger.info("Chunked upload aborted: id=%s", upload_id)

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    def start_cleanup_loop(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_loop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Periodically remove stale sessions."""
        try:
            while True:
                await asyncio.sleep(3600)  # every hour
                await self._cleanup_stale()
        except asyncio.CancelledError:
            pass

    async def _cleanup_stale(self) -> None:
        now = datetime.now(timezone.utc)
        stale_ids: list[str] = []
        async with self._lock:
            for uid, session in self._sessions.items():
                if now - session.created_at > SESSION_MAX_AGE:
                    stale_ids.append(uid)
            for uid in stale_ids:
                session = self._sessions.pop(uid)
                self._remove_temp_file(session.temp_file_path)
        if stale_ids:
            logger.info("Cleaned up %d stale chunked upload session(s)", len(stale_ids))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_temp_file(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove temp file %s: %s", path, exc)

    async def shutdown(self) -> None:
        """Gracefully shut down: cancel cleanup, remove all temp files."""
        await self.stop_cleanup_loop()
        async with self._lock:
            for session in self._sessions.values():
                self._remove_temp_file(session.temp_file_path)
            self._sessions.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_manager: Optional[ChunkedUploadManager] = None


def get_chunked_upload_manager() -> ChunkedUploadManager:
    global _manager
    if _manager is None:
        _manager = ChunkedUploadManager()
    return _manager
