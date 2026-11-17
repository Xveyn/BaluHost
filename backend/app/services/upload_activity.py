"""Uploads in flight across all API processes (#834).

Idle detection runs in the primary alone, but an upload runs in whichever
process serves the request — and a chunked upload in several, one request
after the other. A per-process count therefore let the primary go to sleep
while another worker was still receiving a file, and adding counts up would
count a chunked upload once per worker that touched it.

So each process publishes *which* uploads it touched last and whether they are
still running: ``upload_activity_<pid>.json`` in the SHM directory holds
``{upload_id: [timestamp, active]}``. The reader merges its own entries with
those of every other process — per upload the latest report wins, a "finished"
beating a "running" of the same instant — and counts what is running.

- `touch(upload_id)`: the upload is in flight (session created, progress,
  chunk received).
- `finish(upload_id)`: it ended (completed, failed, aborted) — in whichever
  process that happened.

A report counts for ``ACTIVE_WINDOW_SECONDS`` only. An upload whose client went
away is never finished by anyone, and without that window it would keep the
box from ever going idle again. A live upload reports with every piece of
progress and stays well inside the window — except a chunked upload slower
than one 32 MB chunk per window (about 430 kbit/s), which drops out between
two chunks. That is accepted: the next chunk request wakes the box again.

SHM rather than the upload directory on purpose: the status endpoint reads
this on every poll, and it must not spin up the data disks during soft sleep.

Nothing here may ever fail an upload: every SHM error is swallowed.
"""
from __future__ import annotations

import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.shm_process_files import read_other_process_files, write_process_file

logger = logging.getLogger(__name__)

#: How long a report counts. Bounds how long an abandoned upload can hold off
#: idle sleep (and stay in the status bar).
ACTIVE_WINDOW_SECONDS = 600.0
#: A mere refresh of a known upload is written at most this often; a new
#: upload or a finish is written at once.
WRITE_INTERVAL_SECONDS = 2.0
#: Files older than this belong to a process that is gone and are removed.
STALE_FILE_SECONDS = 3600.0
#: Upper bound on entries taken from one file; a process never has that many.
_MAX_ENTRIES_PER_FILE = 1000

_FILE_PREFIX = "upload_activity_"

# (timestamp, active)
_Entry = tuple[float, bool]


def _default_shm_dir() -> Path:
    # Resolved per call so a patched `shm.SHM_DIR` (tests) is honoured.
    from app.services.monitoring import shm

    return Path(shm.SHM_DIR)


def _newer(candidate: _Entry, current: Optional[_Entry]) -> bool:
    """Whether *candidate* replaces *current*: later wins, finished wins a tie."""
    if current is None:
        return True
    return (candidate[0], not candidate[1]) > (current[0], not current[1])


class UploadActivityTracker:
    """This process's upload reports, shared through an SHM file.

    Args:
        clock: Wall clock (`time.time`); wall time, not monotonic, because
            report times are compared across processes.
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
        self._entries: dict[str, _Entry] = {}
        self._last_write: Optional[float] = None

    def _current_pid(self) -> int:
        return self._pid if self._pid is not None else os.getpid()

    def _dir(self) -> Path:
        return self._shm_dir if self._shm_dir is not None else _default_shm_dir()

    @staticmethod
    def _in_window(timestamp: float, now: float) -> bool:
        # A time in the future (a clock set back) is not "recent": it would
        # stay inside the window for as long as the clock lags.
        return 0.0 <= now - timestamp <= ACTIVE_WINDOW_SECONDS

    # --- write side ---

    def touch(self, upload_id: str) -> None:
        """Report that *upload_id* is in flight."""
        self._record(upload_id, active=True)

    def finish(self, upload_id: str) -> None:
        """Report that *upload_id* ended — completed, failed or aborted."""
        self._record(upload_id, active=False)

    def reset(self) -> None:
        """Forget every report of this process (tests)."""
        self._entries.clear()
        self._last_write = None

    def _record(self, upload_id: str, *, active: bool) -> None:
        try:
            now = self._clock()
            previous = self._entries.get(upload_id)
            self._entries[upload_id] = (now, active)
            # Outside the window an entry decides nothing any more: a finish
            # that old only ever overrode reports that are older still.
            for key in [k for k, (ts, _) in self._entries.items()
                        if not self._in_window(ts, now)]:
                del self._entries[key]
            changed = previous is None or previous[1] != active
            if changed or self._last_write is None \
                    or now - self._last_write >= WRITE_INTERVAL_SECONDS:
                self._last_write = now
                write_process_file(
                    self._dir(), _FILE_PREFIX, self._current_pid(),
                    {
                        "pid": self._current_pid(),
                        "written_at": now,
                        "uploads": {k: [ts, act] for k, (ts, act) in self._entries.items()},
                    },
                )
        except Exception as exc:  # never fail an upload over a counter
            logger.debug("Upload activity report failed: %s", exc)

    # --- read side ---

    def active_uploads(self) -> int:
        """Uploads in flight across all processes. Never raises."""
        try:
            now = self._clock()
            merged: dict[str, _Entry] = dict(self._entries)
            for data in read_other_process_files(
                self._dir(), _FILE_PREFIX, self._current_pid(), now, STALE_FILE_SECONDS,
            ):
                for upload_id, entry in self._entries_of(data):
                    if _newer(entry, merged.get(upload_id)):
                        merged[upload_id] = entry
            return sum(
                1 for ts, active in merged.values() if active and self._in_window(ts, now)
            )
        except Exception as exc:
            logger.debug("Upload activity read failed: %s", exc)
            return 0

    @staticmethod
    def _entries_of(data: dict[str, Any]) -> list[tuple[str, _Entry]]:
        """The well-formed entries of another process's file."""
        uploads = data.get("uploads")
        if not isinstance(uploads, dict):
            return []
        entries: list[tuple[str, _Entry]] = []
        for upload_id, raw in list(uploads.items())[:_MAX_ENTRIES_PER_FILE]:
            if not isinstance(upload_id, str) or not isinstance(raw, list) or len(raw) != 2:
                continue
            ts, active = raw
            if isinstance(ts, bool) or not isinstance(ts, (int, float)) \
                    or not math.isfinite(ts) or not isinstance(active, bool):
                continue
            entries.append((upload_id, (float(ts), active)))
        return entries


_tracker = UploadActivityTracker()


def touch(upload_id: str) -> None:
    """Report that *upload_id* is in flight (module-level tracker)."""
    _tracker.touch(upload_id)


def finish(upload_id: str) -> None:
    """Report that *upload_id* ended (module-level tracker)."""
    _tracker.finish(upload_id)


def active_uploads() -> int:
    """Uploads in flight, across all API processes."""
    return _tracker.active_uploads()
