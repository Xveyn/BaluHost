"""HTTP requests per minute across all API processes (#823).

Idle detection runs in the primary alone, but requests are spread over every
API process (production: four `baluhost-backend` workers plus two
`baluhost-backend-local`). A per-process counter therefore saw only a fraction
of the traffic and compared `idle_http_threshold` against too small a value.

Each process counts its requests in 10-second buckets and writes its buckets
to ``http_activity_<pid>.json`` in the SHM directory — at most every two
seconds. The reader adds its own buckets (from memory) to those of every
other process (from their files). Requests of a process that stops receiving
traffic less than two seconds after its last write never reach the file;
that undercount is bounded and accepted in exchange for not writing on every
request.

Nothing here may ever fail a request: every SHM error is swallowed.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 10
KEEP_BUCKETS = 12
WINDOW_SECONDS = 60.0
WRITE_INTERVAL_SECONDS = 2.0
STALE_FILE_SECONDS = 600.0

_FILE_PREFIX = "http_activity_"
_FILE_NAME_RE = re.compile(r"http_activity_\d+\.json")


def _default_shm_dir() -> Path:
    # Resolved per call so a patched `shm.SHM_DIR` (tests) is honoured.
    from app.services.monitoring import shm

    return Path(shm.SHM_DIR)


class HttpActivityCounter:
    """Per-process request buckets, shared through SHM files.

    Args:
        clock: Wall clock (`time.time`); wall time, not monotonic, because
            bucket times are compared across processes.
        pid: This process's id; None means `os.getpid()` at each call.
        shm_dir: Directory for the files; None means `shm.SHM_DIR`.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        pid: Optional[int] = None,
        shm_dir: Optional[Path] = None,
    ) -> None:
        self._clock = clock
        self._pid = pid
        self._shm_dir = Path(shm_dir) if shm_dir is not None else None
        self._buckets: dict[int, int] = {}
        self._last_write: Optional[float] = None

    # --- helpers ---

    def _current_pid(self) -> int:
        return self._pid if self._pid is not None else os.getpid()

    def _dir(self) -> Path:
        return self._shm_dir if self._shm_dir is not None else _default_shm_dir()

    @staticmethod
    def _bucket_of(now: float) -> int:
        return int(now // BUCKET_SECONDS)

    @staticmethod
    def _count_recent(buckets: dict[int, int], now: float) -> int:
        """Sum the buckets that started within the last minute."""
        cutoff = now - WINDOW_SECONDS
        return sum(n for b, n in buckets.items() if b * BUCKET_SECONDS >= cutoff)

    # --- write side ---

    def record(self) -> None:
        """Count one request; publish this process's buckets if due."""
        try:
            now = self._clock()
            current = self._bucket_of(now)
            self._buckets[current] = self._buckets.get(current, 0) + 1
            oldest = current - KEEP_BUCKETS + 1
            for b in [b for b in self._buckets if b < oldest]:
                del self._buckets[b]
            if self._last_write is None or now - self._last_write >= WRITE_INTERVAL_SECONDS:
                self._last_write = now
                self._write(now)
        except Exception as exc:  # never fail a request over a counter
            logger.debug("HTTP activity record failed: %s", exc)

    def _write(self, now: float) -> None:
        directory = self._dir()
        payload = {
            "pid": self._current_pid(),
            "written_at": now,
            "buckets": {str(b): n for b, n in self._buckets.items()},
        }
        try:
            directory.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(payload, f)
                os.replace(tmp_path, str(directory / f"{_FILE_PREFIX}{self._current_pid()}.json"))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:
            logger.debug("HTTP activity write failed: %s", exc)

    # --- read side ---

    def requests_per_minute(self) -> float:
        """Requests of the last minute, this process plus all others."""
        now = self._clock()
        total = self._count_recent(self._buckets, now)
        try:
            total += self._count_other_processes(now)
        except Exception as exc:
            logger.debug("HTTP activity read failed: %s", exc)
        return float(total)

    def _count_other_processes(self, now: float) -> int:
        directory = self._dir()
        own_name = f"{_FILE_PREFIX}{self._current_pid()}.json"
        total = 0
        try:
            entries = list(directory.iterdir())
        except OSError:
            return 0
        for path in entries:
            name = path.name
            if not _FILE_NAME_RE.fullmatch(name) or name == own_name:
                continue
            try:
                if path.is_symlink():
                    # We only ever write regular files; never follow a link
                    # out of the directory, neither to read nor to judge age.
                    continue
                if now - path.stat().st_mtime > STALE_FILE_SECONDS:
                    # Left behind by a process that is gone. Best effort.
                    path.unlink(missing_ok=True)
                    continue
                with open(path, "r") as f:
                    data = json.load(f)
                buckets = {int(b): int(n) for b, n in data["buckets"].items()}
            except Exception as exc:
                logger.debug("Ignoring unreadable %s: %s", name, exc)
                continue
            total += self._count_recent(buckets, now)
        return total


_counter = HttpActivityCounter()


def record() -> None:
    """Count one request of this process (module-level counter)."""
    _counter.record()


def requests_per_minute() -> float:
    """Requests per minute summed over all API processes."""
    return _counter.requests_per_minute()
