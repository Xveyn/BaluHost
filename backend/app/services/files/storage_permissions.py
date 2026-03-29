"""Storage permission constants and helpers.

Aligns backend file/directory permissions with the Samba configuration
(create mask = 0664, directory mask = 0775) so that all processes
(backend, Samba) can read/write files regardless of which one created them.

The setgid bit (2xxx) on directories ensures new subdirectories inherit
the parent's group automatically.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_DIR_MODE = 0o2775    # rwxrwsr-x  (setgid + group write)
STORAGE_FILE_MODE = 0o0664   # rw-rw-r--
STORAGE_UMASK = 0o002        # complement of 0775/0664


def set_storage_dir_permissions(path: Path) -> None:
    """Set standard storage directory permissions (2775) on *path*.

    Silently skips non-existent paths (e.g. race with deletion).
    """
    try:
        os.chmod(path, STORAGE_DIR_MODE)
    except FileNotFoundError:
        pass


def set_storage_file_permissions(path: Path) -> None:
    """Set standard storage file permissions (0664) on *path*.

    Silently skips non-existent paths.
    """
    try:
        os.chmod(path, STORAGE_FILE_MODE)
    except FileNotFoundError:
        pass


def ensure_dir_with_permissions(path: Path) -> None:
    """Create *path* (and parents) with storage directory permissions.

    Equivalent to ``path.mkdir(parents=True, exist_ok=True)`` followed
    by ``chmod 2775`` on every newly created segment.
    """
    path.mkdir(parents=True, exist_ok=True)

    # Walk from the deepest new directory upward and fix permissions.
    # Stop at the first directory that already has the correct mode to
    # avoid unnecessary syscalls on long-existing parent directories.
    current = path
    while True:
        try:
            mode = os.stat(current).st_mode & 0o7777
            if mode != STORAGE_DIR_MODE:
                os.chmod(current, STORAGE_DIR_MODE)
            else:
                break  # already correct — parents are likely fine too
        except (FileNotFoundError, PermissionError):
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
