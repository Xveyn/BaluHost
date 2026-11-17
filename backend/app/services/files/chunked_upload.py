"""Chunked upload session manager.

Tracks in-flight chunked uploads, writes chunks to temp files on disk,
and finalises uploads by moving temp files to the target location.

Sessions live on disk, next to the data
------------------------------------
Production runs several API processes, and a chunked upload is one request
per chunk — each may land on a different process. A session kept in one
process's memory answered every other with "Upload session not found". So a
session is three files in ``TMP_UPLOAD_DIR``:

- ``<upload_id>``       the data received so far
- ``<upload_id>.json``  the session (target, owner, progress), replaced
                        atomically after every chunk
- ``<upload_id>.lock``  held (``flock``) for the length of one operation

The lock makes "check the chunk index, append, record progress" one step
across processes: a repeated or concurrent chunk is rejected instead of
written twice, and an abort waits for a write in progress instead of
overtaking it and leaving a temp file behind.

What the session file may decide
--------------------------------
Nothing that needs trust. The directory is group-writable (two service users
share it), so a session file is input, not a credential:

- the upload id comes from the URL and becomes a file name — only a canonical
  lower-case UUID is ever turned into a path;
- every field is type-checked on load, a malformed file is an unknown session;
- neither the session file nor the data file is ever opened through a symlink;
- the route re-derives authorization from the authenticated user at every
  step, and validates target and file name again before it moves the file
  (`routes/chunked_upload.py`).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import stat
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Optional, Sequence

from app.core.config import settings
from app.services.files.storage_permissions import STORAGE_FILE_MODE

try:  # POSIX only; dev mode on Windows runs a single process
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows
    _fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Temp directory lives inside the storage root so the final rename/move
# stays on the same filesystem (atomic where supported).
TMP_UPLOAD_DIR = Path(settings.nas_storage_path).expanduser().resolve() / ".tmp" / "uploads"

# How long a session without a new chunk is kept before automatic cleanup.
SESSION_MAX_AGE = timedelta(hours=24)

# Session and lock files hold a user name, a file name and a target path:
# not for "other". The data file gets the mode of the finished file.
_META_FILE_MODE = 0o660

_UPLOAD_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_HASH_READ_SIZE = 4 * 1024 * 1024
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

# Without flock (Windows) one lock per process is all there is to exclude.
_process_lock = threading.Lock()


def _is_upload_id(value: object) -> bool:
    """Whether *value* may be used as a file name in the upload directory."""
    return isinstance(value, str) and _UPLOAD_ID_RE.fullmatch(value) is not None


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:  # not ours, or Windows — the content matters more
        logger.debug("chmod %o on %s failed: %s", mode, path, exc)


def _append_to_data_file(path: Path, parts: Sequence[bytes]) -> int:
    """Append *parts* to the data file; returns the bytes written.

    Never through a symlink: whoever can write to the upload directory must
    not be able to redirect a chunk into another file.
    """
    existed = path.exists() or path.is_symlink()
    fd = os.open(
        path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW, STORAGE_FILE_MODE,
    )
    written = 0
    with os.fdopen(fd, "ab") as f:
        for part in parts:
            f.write(part)
            written += len(part)
    if not existed:
        _chmod(path, STORAGE_FILE_MODE)  # os.open applied the umask
    return written


@dataclass
class ChunkedUploadSession:
    """A single chunked upload — a snapshot of its session file.

    Not live: read it again with `get_session()` to see later progress.
    """

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
    last_activity: float = 0.0  # epoch seconds of creation or the last chunk


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_time(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class ChunkedUploadManager:
    """File-backed session tracker for chunked uploads.

    One instance per process; all instances on the same `TMP_UPLOAD_DIR`
    serve the same sessions.

    Args:
        clock: Wall clock (`time.time`) for `last_activity` — wall time,
            because it is compared across processes and restarts.
    """

    DEFAULT_CHUNK_SIZE = 32 * 1024 * 1024  # 32 MB
    MAX_CONCURRENT_WRITES_PER_USER = 16    # per process
    _MAX_RUNNING_HASHES = 64

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._cleanup_task: Optional[asyncio.Task] = None
        self._user_semaphores: dict[int, asyncio.Semaphore] = {}
        # upload_id -> (running SHA-256, bytes it has seen). Only good while
        # this process has seen every byte; see `_feed_hash()`.
        self._running_hashes: dict[str, tuple[Any, int]] = {}

    def _get_user_semaphore(self, user_id: int) -> asyncio.Semaphore:
        """Return (or create) the per-user write semaphore."""
        sem = self._user_semaphores.get(user_id)
        if sem is None:
            sem = asyncio.Semaphore(self.MAX_CONCURRENT_WRITES_PER_USER)
            self._user_semaphores[user_id] = sem
        return sem

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    @staticmethod
    def _data_path(upload_id: str) -> Path:
        return TMP_UPLOAD_DIR / upload_id

    @staticmethod
    def _meta_path(upload_id: str) -> Path:
        return TMP_UPLOAD_DIR / f"{upload_id}.json"

    @staticmethod
    def _lock_path(upload_id: str) -> Path:
        return TMP_UPLOAD_DIR / f"{upload_id}.lock"

    @contextlib.contextmanager
    def _locked(self, upload_id: str) -> Iterator[bool]:
        """Hold the session's lock; yields False if there is no lock file.

        Blocking — call from a worker thread. The lock file is created with
        the session and removed with it, so "no lock file" means "no such
        session". Someone still waiting on a removed lock file gets the lock
        on the unlinked inode and then finds no session file.
        """
        try:
            fd = os.open(self._lock_path(upload_id), os.O_RDONLY | _O_NOFOLLOW)
        except OSError:
            yield False
            return
        try:
            if _fcntl is not None:
                _fcntl.flock(fd, _fcntl.LOCK_EX)
                try:
                    yield True
                finally:
                    _fcntl.flock(fd, _fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows
                with _process_lock:
                    yield True
        finally:
            os.close(fd)

    def _load(self, upload_id: str) -> Optional[ChunkedUploadSession]:
        """Read and validate a session file; None for anything not in order."""
        if not _is_upload_id(upload_id):
            return None
        try:
            fd = os.open(self._meta_path(upload_id), os.O_RDONLY | _O_NOFOLLOW)
            with os.fdopen(fd, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("upload_id") != upload_id:
            return None
        strings = ("target_path", "filename", "username")
        counts = ("total_size", "chunk_size", "received_bytes", "next_chunk_index", "user_id")
        times = ("created_at", "last_activity")
        if not all(isinstance(data.get(k), str) for k in strings) \
                or not all(_is_count(data.get(k)) for k in counts) \
                or not all(_is_time(data.get(k)) for k in times):
            logger.warning("Ignoring malformed chunked upload session file: %s", upload_id)
            return None
        try:
            created_at = datetime.fromtimestamp(float(data["created_at"]), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return ChunkedUploadSession(
            upload_id=upload_id,
            target_path=data["target_path"],
            filename=data["filename"],
            total_size=data["total_size"],
            chunk_size=data["chunk_size"],
            received_bytes=data["received_bytes"],
            next_chunk_index=data["next_chunk_index"],
            temp_file_path=self._data_path(upload_id),
            user_id=data["user_id"],
            username=data["username"],
            created_at=created_at,
            last_activity=float(data["last_activity"]),
        )

    def _save(self, session: ChunkedUploadSession) -> None:
        """Replace the session file atomically."""
        payload = {
            "upload_id": session.upload_id,
            "target_path": session.target_path,
            "filename": session.filename,
            "total_size": session.total_size,
            "chunk_size": session.chunk_size,
            "received_bytes": session.received_bytes,
            "next_chunk_index": session.next_chunk_index,
            "user_id": session.user_id,
            "username": session.username,
            "created_at": session.created_at.timestamp(),
            "last_activity": session.last_activity,
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(TMP_UPLOAD_DIR), prefix=f"{session.upload_id}.json.", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            _chmod(Path(tmp_path), _META_FILE_MODE)
            os.replace(tmp_path, self._meta_path(session.upload_id))
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _remove_files(self, upload_id: str, *, keep_data: bool = False) -> None:
        """Remove a session's files. The lock file goes last."""
        paths = [self._meta_path(upload_id)]
        if not keep_data:
            paths.append(self._data_path(upload_id))
        paths.append(self._lock_path(upload_id))
        for path in paths:
            self._remove_temp_file(path)
        self._running_hashes.pop(upload_id, None)

    # ------------------------------------------------------------------
    # Running checksum
    # ------------------------------------------------------------------

    def _feed_hash(self, upload_id: str, chunk_index: int, before: int, parts: Sequence[bytes]) -> None:
        """Keep a running SHA-256 as long as this process sees every byte.

        *before* is the session's `received_bytes` ahead of this chunk. If it
        is not what the running hash has seen, another process wrote in
        between and the hash is dropped. That only saves hashing for nothing:
        whether a running hash may be used is decided in `_checksum()`, which
        compares what it has seen with what the session received.
        """
        if chunk_index == 0:
            while len(self._running_hashes) >= self._MAX_RUNNING_HASHES:
                self._running_hashes.pop(next(iter(self._running_hashes)))
            self._running_hashes[upload_id] = (hashlib.sha256(), 0)
        entry = self._running_hashes.get(upload_id)
        if entry is None:
            return
        hasher, seen = entry
        if seen != before:
            del self._running_hashes[upload_id]
            return
        for part in parts:
            hasher.update(part)
            seen += len(part)
        self._running_hashes[upload_id] = (hasher, seen)

    def _checksum(self, session: ChunkedUploadSession) -> str:
        entry = self._running_hashes.get(session.upload_id)
        if entry is not None and entry[1] == session.received_bytes:
            return entry[0].hexdigest()
        hasher = hashlib.sha256()
        fd = os.open(session.temp_file_path, os.O_RDONLY | _O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            while block := f.read(_HASH_READ_SIZE):
                hasher.update(block)
        return hasher.hexdigest()

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
        """Create a new chunked upload session."""
        upload_id = str(uuid.uuid4())
        now = self._clock()
        session = ChunkedUploadSession(
            upload_id=upload_id,
            target_path=target_path,
            filename=filename,
            total_size=total_size,
            chunk_size=chunk_size or self.DEFAULT_CHUNK_SIZE,
            temp_file_path=self._data_path(upload_id),
            user_id=user_id,
            username=username,
            created_at=datetime.fromtimestamp(now, tz=timezone.utc),
            last_activity=now,
        )

        def _create() -> None:
            TMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            lock_path = self._lock_path(upload_id)
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _META_FILE_MODE)
            os.close(fd)
            _chmod(lock_path, _META_FILE_MODE)
            self._save(session)

        await asyncio.to_thread(_create)

        logger.info(
            "Chunked upload session created: id=%s file=%s size=%d chunk=%d",
            upload_id, filename, total_size, session.chunk_size,
        )
        return session

    def get_session(self, upload_id: str) -> Optional[ChunkedUploadSession]:
        """The session as stored right now, or None. Reads a file: from async
        code call it through `asyncio.to_thread`."""
        return self._load(upload_id)

    def _require(self, upload_id: str, chunk_index: int) -> ChunkedUploadSession:
        session = self._load(upload_id)
        if session is None:
            raise ValueError(f"Unknown upload session: {upload_id}")
        if chunk_index != session.next_chunk_index:
            raise ValueError(
                f"Expected chunk {session.next_chunk_index}, got {chunk_index}"
            )
        return session

    def _write_locked(self, upload_id: str, chunk_index: int, parts: Sequence[bytes]) -> int:
        """Check, append and record one chunk as a single step (blocking)."""
        with self._locked(upload_id) as held:
            if not held:
                raise ValueError(f"Unknown upload session: {upload_id}")
            session = self._require(upload_id, chunk_index)

            incoming = sum(len(p) for p in parts)
            if session.received_bytes + incoming > session.total_size:
                self._remove_files(upload_id)
                logger.info("Chunked upload aborted (overflow): id=%s", upload_id)
                raise ValueError(
                    "Upload exceeds declared total_size "
                    f"({session.total_size} bytes) for session {upload_id}"
                )

            try:
                written = _append_to_data_file(session.temp_file_path, parts)
            except OSError as exc:
                raise ValueError(f"Cannot write chunk for session {upload_id}: {exc}") from exc
            self._feed_hash(upload_id, chunk_index, session.received_bytes, parts)

            session.received_bytes += written
            session.next_chunk_index += 1
            session.last_activity = self._clock()
            self._save(session)
            return session.received_bytes

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
        session = await asyncio.to_thread(self._require, upload_id, chunk_index)
        async with self._get_user_semaphore(session.user_id):
            return await asyncio.to_thread(self._write_locked, upload_id, chunk_index, [data])

    async def write_chunk_stream(
        self,
        upload_id: str,
        chunk_index: int,
        stream: "AsyncIterator[bytes]",
    ) -> int:
        """Receive one chunk from *stream* and append it to the temp file.

        *stream* is an async iterator yielding raw byte fragments (e.g.
        ``request.stream()``). Sequence errors are raised before the stream
        is read. The fragments are collected first and written in one step
        under the session lock, so memory overhead is one chunk.

        Returns the total received bytes after this chunk.
        """
        session = await asyncio.to_thread(self._require, upload_id, chunk_index)

        parts: list[bytes] = []
        async for part in stream:
            parts.append(part)

        async with self._get_user_semaphore(session.user_id):
            return await asyncio.to_thread(self._write_locked, upload_id, chunk_index, parts)

    def _complete_locked(self, upload_id: str) -> tuple[Path, str, ChunkedUploadSession]:
        with self._locked(upload_id) as held:
            session = self._load(upload_id) if held else None
            if session is None:
                raise ValueError(f"Unknown upload session: {upload_id}")
            try:
                mode = os.lstat(session.temp_file_path).st_mode
            except OSError:
                self._remove_files(upload_id)
                raise FileNotFoundError(f"Temp file missing for session {upload_id}") from None
            if not stat.S_ISREG(mode):
                # Moving a link into the user's folder would hand out read
                # access to whatever it points at.
                self._remove_files(upload_id)
                raise ValueError(f"Temp file of session {upload_id} is not a regular file")
            sha256_hex = self._checksum(session)
            self._remove_files(upload_id, keep_data=True)
            return session.temp_file_path, sha256_hex, session

    async def complete_session(self, upload_id: str) -> tuple[Path, str]:
        """Finalise the upload: return the temp file path and SHA-256 hex digest.

        The caller (route layer) is responsible for moving the file to its
        final destination, creating metadata, and audit logging.
        After calling this the session is removed; the data file stays.

        The digest comes from the running hash if this process received every
        chunk, otherwise from one read of the file.
        """
        if not _is_upload_id(upload_id):
            raise ValueError(f"Unknown upload session: {upload_id}")
        temp_path, sha256_hex, session = await asyncio.to_thread(self._complete_locked, upload_id)
        logger.info(
            "Chunked upload completed: id=%s file=%s bytes=%d",
            upload_id, session.filename, session.received_bytes,
        )
        return temp_path, sha256_hex

    def _abort_locked(self, upload_id: str) -> bool:
        with self._locked(upload_id) as held:
            existed = held and self._meta_path(upload_id).exists()
            # Also without a lock file: whatever is left of that id goes.
            self._remove_files(upload_id)
            return existed

    async def abort_session(self, upload_id: str) -> None:
        """Abort an upload and clean up its files. Waits for a write in progress."""
        if not _is_upload_id(upload_id):
            return
        if await asyncio.to_thread(self._abort_locked, upload_id):
            logger.info("Chunked upload aborted: id=%s", upload_id)

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    def start_cleanup_loop(self) -> None:
        """Start the periodic cleanup. One process is enough — the primary."""
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
        """Periodically remove stale sessions: soon after start, then hourly."""
        try:
            await asyncio.sleep(60)
            while True:
                try:
                    await self._cleanup_stale()
                except Exception as exc:
                    logger.warning("Chunked upload cleanup failed: %s", exc)
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    def _cleanup_stale_sync(self) -> tuple[int, int]:
        """Remove stale sessions and old leftovers; returns both counts."""
        try:
            names = sorted(p.name for p in TMP_UPLOAD_DIR.iterdir())
        except OSError:
            return 0, 0
        max_age = SESSION_MAX_AGE.total_seconds()
        now = self._clock()
        ids = {name[:36] for name in names if _is_upload_id(name[:36])}
        stale = leftovers = 0
        for upload_id in ids:
            session = self._load(upload_id)
            if session is not None:
                if now - session.last_activity > max_age:
                    with self._locked(upload_id):
                        # Read again under the lock: a chunk may just have arrived.
                        current = self._load(upload_id)
                        if current is None or now - current.last_activity > max_age:
                            self._remove_files(upload_id)
                            stale += 1
                continue
            # No readable session: a completed upload the route has not moved
            # yet, the remains of a crash, or a file from before sessions
            # were stored on disk. Only once it has been untouched that long.
            for name in names:
                if name[:36] != upload_id:
                    continue
                path = TMP_UPLOAD_DIR / name
                try:
                    if now - os.lstat(path).st_mtime > max_age:
                        path.unlink()
                        leftovers += 1
                except OSError:
                    continue
        return stale, leftovers

    async def _cleanup_stale(self) -> None:
        stale, leftovers = await asyncio.to_thread(self._cleanup_stale_sync)
        if stale or leftovers:
            logger.info(
                "Cleaned up %d stale chunked upload session(s) and %d leftover file(s)",
                stale, leftovers,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_temp_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove temp file %s: %s", path, exc)

    async def shutdown(self) -> None:
        """Stop the cleanup loop. Sessions stay: they belong to every worker,
        and a client can carry on after a restart."""
        await self.stop_cleanup_loop()
        self._running_hashes.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_manager: Optional[ChunkedUploadManager] = None


def get_chunked_upload_manager() -> ChunkedUploadManager:
    global _manager
    if _manager is None:
        _manager = ChunkedUploadManager()
    return _manager
