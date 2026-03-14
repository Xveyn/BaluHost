"""Recursive folder size calculation with TTL cache.

Follows the same caching pattern as ``_used_bytes_cache`` in ``operations.py``.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

# Cache: absolute path string → (size_bytes, timestamp)
_folder_size_cache: dict[str, tuple[int, float]] = {}
_folder_size_cache_lock = threading.Lock()
_FOLDER_SIZE_CACHE_TTL = 300.0  # 5 minutes
_FOLDER_SIZE_CACHE_MAX_ENTRIES = 2048  # prevent unbounded growth


def get_folder_size(path: Path) -> int:
    """Return total size of all files inside *path* (recursive).

    Results are cached for 5 minutes.  Uses ``os.scandir()`` for speed and
    ``follow_symlinks=False`` to avoid loops.
    """
    key = str(path)
    now = time.time()

    with _folder_size_cache_lock:
        cached = _folder_size_cache.get(key)
        if cached is not None:
            size, ts = cached
            if now - ts < _FOLDER_SIZE_CACHE_TTL:
                return size

    total = _scan_size(path)

    with _folder_size_cache_lock:
        # Evict expired entries when cache exceeds max size
        if len(_folder_size_cache) >= _FOLDER_SIZE_CACHE_MAX_ENTRIES:
            expired = [k for k, (_, ts) in _folder_size_cache.items()
                       if now - ts >= _FOLDER_SIZE_CACHE_TTL]
            for k in expired:
                del _folder_size_cache[k]
            # If still over limit, drop oldest half
            if len(_folder_size_cache) >= _FOLDER_SIZE_CACHE_MAX_ENTRIES:
                sorted_keys = sorted(_folder_size_cache, key=lambda k: _folder_size_cache[k][1])
                for k in sorted_keys[:len(sorted_keys) // 2]:
                    del _folder_size_cache[k]
        _folder_size_cache[key] = (total, now)

    return total


def _scan_size(path: Path) -> int:
    """Walk *path* recursively and sum file sizes."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        total += _scan_size(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return total


def invalidate_folder_sizes_for_path(path: Path, root: Path) -> None:
    """Invalidate cache for *path* and all its parents up to *root*."""
    with _folder_size_cache_lock:
        current = path
        while True:
            _folder_size_cache.pop(str(current), None)
            if current == root or current.parent == current:
                break
            current = current.parent


def invalidate_all_folder_sizes() -> None:
    """Clear the entire folder size cache."""
    with _folder_size_cache_lock:
        _folder_size_cache.clear()
