"""One tray per desktop session.

The lock lives in $XDG_RUNTIME_DIR: session scoped and gone at logout. It is
never unlinked before opening — that is exactly the race where two processes
each lock their own inode and both believe they are the only one.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class AlreadyRunning(Exception):
    """Another process already holds this lock in this session."""


_handles: list = []


def _lock_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)
    return Path.home() / ".baluhost"


def acquire(name: str = "baluhost-tray") -> object:
    """Take the session lock. Keep the returned handle alive for the process.

    The name is a parameter so pairing can use its own: `--pair` has to work
    while the service is running, otherwise re-pairing would require stopping
    the unit first.
    """
    directory = _lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.lock"

    handle = open(path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise AlreadyRunning(f"another process holds {path}") from exc

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _handles.append(handle)  # keep the fd open for the process lifetime
    return handle
