"""Terminate leftover processes - but only the ones that belong to THIS checkout.

Shared by ``start_dev.py``, ``kill_dev.py``, ``start_prod.py`` and
``kill_prod.py``. All four used to run ``pkill -f
<pattern>``, which matches the entire command line and knows neither user nor
directory. On a host where the production services run under the same user as
the dev workspace (``/opt/baluhost`` next to ``~/projects/BaluHost``) that shot
production down (and a prod launcher would have shot a dev instance), and it
also hit unrelated tools whose command line merely
contained ``vite`` or ``uvicorn`` (#763).

A process is terminated only if BOTH hold:

* its command line matches one of the patterns, and
* it belongs to this checkout: its working directory, or an absolute path in its
  command line, lies under ``root``.

Anything that cannot be decided is left alone. That is not hypothetical: the
production backend's main process refuses ``/proc/<pid>/cwd`` even to its own
user, so the working directory alone cannot be the rule.

Linux only (it reads ``/proc``). Where there is no ``/proc`` (macOS) the cleanup
is skipped with a message - falling back to ``pkill -f`` would bring the bug back.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import time
from pathlib import Path
from typing import Iterable, List, Optional, Set

PROC = Path("/proc")


def _is_inside(path: str, root: Path) -> bool:
    """Whether ``path`` lies under ``root``, compared by path component.

    ``normpath`` collapses ``..`` without touching the filesystem on purpose: a
    venv's ``python`` is a symlink into ``/usr/bin``, and resolving it would push
    every venv process out of the checkout. A string-prefix check would call
    ``/x/BaluHost-old`` part of ``/x/BaluHost``.
    """
    return Path(os.path.normpath(path)).is_relative_to(root)


def is_owned(cwd: Optional[Path], argv: List[str], root: Path) -> bool:
    """Whether a process belongs to the checkout at ``root``.

    ``cwd`` is None when it could not be read; relative arguments are never
    resolved against anything, so such a process is only ours if an absolute path
    in its command line says so.
    """
    if cwd is not None and _is_inside(str(cwd), root):
        return True
    return any(os.path.isabs(arg) and _is_inside(arg, root) for arg in argv)


def _read_argv(pid: int) -> List[str]:
    raw = (PROC / str(pid) / "cmdline").read_bytes()
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


def _read_cwd(pid: int) -> Optional[Path]:
    try:
        return Path(os.readlink(PROC / str(pid) / "cwd"))
    except OSError:
        return None


def _parent_of(pid: int) -> Optional[int]:
    try:
        stat = (PROC / str(pid) / "stat").read_text()
        # "pid (comm) state ppid ..." - comm may contain spaces and parentheses.
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _self_and_ancestors() -> Set[int]:
    pids: Set[int] = set()
    pid: Optional[int] = os.getpid()
    while pid and pid not in pids:
        pids.add(pid)
        pid = _parent_of(pid)
    return pids


def find_owned_processes(patterns: Iterable[str], root: Path) -> List[int]:
    """PIDs of this user's processes that match a pattern and belong to ``root``."""
    if not PROC.is_dir():
        return []

    compiled = [re.compile(p) for p in patterns]
    skip = _self_and_ancestors()
    uid = os.getuid()
    found: List[int] = []

    for entry in os.listdir(PROC):
        if not entry.isdigit() or int(entry) in skip:
            continue
        pid = int(entry)
        try:
            if (PROC / entry).stat().st_uid != uid:
                continue
            argv = _read_argv(pid)
        except OSError:
            continue  # gone, or not ours to read
        if not argv:
            continue  # kernel thread or zombie
        cmdline = " ".join(argv)
        if not any(p.search(cmdline) for p in compiled):
            continue
        if is_owned(_read_cwd(pid), argv, root):
            found.append(pid)
    return found


def _signal_all(pids: Iterable[int], sig: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"[warning] Permission denied for PID {pid}")


def terminate_owned_processes(
    patterns: Iterable[str], root: Path, grace_seconds: float = 3
) -> int:
    """SIGTERM, wait ``grace_seconds``, then SIGKILL what is left - owned only.

    Returns how many processes were sent SIGTERM (0 without ``/proc``).
    """
    if not PROC.is_dir():
        print("[info] No /proc here - skipping cleanup of leftover processes")
        return 0

    patterns = list(patterns)
    pids = find_owned_processes(patterns, root)
    if not pids:
        print("[info] No leftover processes of this checkout found")
        return 0

    print(f"[info] Terminating {len(pids)} process(es) of this checkout: {pids}")
    _signal_all(pids, signal.SIGTERM)
    time.sleep(grace_seconds)

    # Look again instead of trusting the first list: PIDs get reused.
    remaining = find_owned_processes(patterns, root)
    if remaining:
        print(f"[warning] Forcing kill for remaining processes: {remaining}")
        _signal_all(remaining, signal.SIGKILL)
    return len(pids)


def _remove_lock_if_unheld(lock_path: Path) -> bool:
    """Delete a flock-based lock file only if nobody holds the lock.

    The kernel releases a flock when its holder dies, so a leftover file with no
    holder blocks nothing - removing it is tidiness. Removing a HELD one is
    harm: the holder keeps the lock on the old inode, the next process creates a
    new one and locks that, and two processes believe they are the primary (see
    ``_try_become_primary`` in app/core/lifespan.py). Probing with a
    non-blocking flock asks the kernel instead of guessing from a PID.
    """
    try:
        import fcntl  # POSIX only; the launchers are Linux-only anyway
    except ImportError:
        return False
    try:
        # No O_CREAT: probing must never create the file it is looking for.
        fd = os.open(lock_path, os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError as exc:
        print(f"[cleanup] Cannot inspect {lock_path}: {exc}")
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"[cleanup] {lock_path} is held by a running process - leaving it")
            return False
        try:
            lock_path.unlink()
        except OSError as exc:
            print(f"[cleanup] Could not remove {lock_path}: {exc}")
            return False
        return True
    finally:
        os.close(fd)


def clean_stale_state(
    lock_path: Path, shm_dir: Path, shm_writer_patterns: Iterable[str]
) -> "tuple[bool, bool]":
    """Remove the primary-worker lock and the SHM dir - only if they are orphaned.

    ``start_prod.py`` used to delete both unconditionally. ``PrivateTmp`` hides
    the production unit's lock file from the host, but it does NOT cover
    ``/dev/shm``: that directory is per host, so a launcher started from another
    checkout wiped the telemetry, heartbeat and command files the live
    ``monitoring_worker`` was writing.

    The lock goes only if no process holds it. The SHM dir goes only if no
    process matching ``shm_writer_patterns`` is running - of ANY install, since
    the directory is shared. ``read_shm`` already discards files older than 30s,
    so skipping the removal costs nothing but a few stale files; deleting live
    ones is what hurt. When in doubt it leaves things alone.

    Returns ``(lock_removed, shm_removed)``.
    """
    lock_removed = _remove_lock_if_unheld(lock_path)

    shm_removed = False
    if shm_dir.exists():
        # root "/" = every readable process of this user: whoever writes there owns it.
        writers = find_owned_processes(shm_writer_patterns, Path("/"))
        if writers:
            print(f"[cleanup] {shm_dir} is in use by PID(s) {writers} - leaving it")
        else:
            shutil.rmtree(shm_dir, ignore_errors=True)
            shm_removed = True
    return lock_removed, shm_removed
