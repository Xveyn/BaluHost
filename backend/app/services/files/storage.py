"""Quota calculation, used-bytes cache, and SSD cache invalidation.

Imports ``path_utils`` as a *module* (not individual names) so that
``monkeypatch.setattr(path_utils, "ROOT_DIR", …)`` in tests reaches
all consumers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.files import path_utils

logger = logging.getLogger(__name__)

# ── Used-bytes cache state ────────────────────────────────────────────────────

_used_bytes_cache: dict[str, tuple[int, float]] = {}  # {"value": (bytes, timestamp)}
_used_bytes_cache_lock = threading.Lock()
_used_bytes_inflight: threading.Event | None = None  # stampede protection
_USED_BYTES_CACHE_TTL = 30.0  # Cache for 30 seconds

_user_root_usage_cache: dict[str, tuple[dict[str, int], float]] = {}
_user_root_usage_cache_lock = threading.Lock()
_USER_ROOT_USAGE_CACHE_TTL = 30.0


# ── SSD cache invalidation ───────────────────────────────────────────────────

def _invalidate_ssd_cache(source_path: str, db: Optional[Session] = None) -> None:
    """Invalidate SSD cache entry for a file path across all arrays. Never raises."""
    if not db:
        return
    try:
        from app.services.cache.ssd_file_cache import SSDFileCacheService
        configs = SSDFileCacheService.get_all_configs(db)
        for cfg in configs:
            if cfg.is_enabled:
                svc = SSDFileCacheService(db, str(cfg.array_name))
                svc.invalidate_entry(source_path)
    except Exception:
        logger.debug("SSD cache invalidation failed for %s", source_path, exc_info=True)


# ── Filesystem scan ──────────────────────────────────────────────────────────

def _calculate_used_bytes_uncached() -> int:
    """Internal: Actually scan the filesystem. Called by calculate_used_bytes().

    Uses recursive os.scandir() for efficiency — DirEntry.stat() reuses
    cached inode data from the directory listing (no extra syscall), and
    system directories are skipped at the root level without descending.
    """
    if not path_utils.ROOT_DIR.exists():
        return 0

    def _walk(path: str, skip_system: bool) -> int:
        total = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if skip_system and path_utils.is_system_directory(entry.name):
                                continue
                            total += _walk(entry.path, skip_system=False)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass
        return total

    return _walk(str(path_utils.ROOT_DIR), skip_system=True)


def _calculate_path_size(path: str) -> int:
    """Recursively calculate size for a specific path. Never raises."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        total += _calculate_path_size(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        return 0
    return total


# ── Cached used-bytes ────────────────────────────────────────────────────────

def calculate_used_bytes() -> int:
    """Calculate total used bytes in storage.

    Uses a 30-second TTL cache to avoid expensive filesystem scans on every request.
    Includes stampede protection: if a scan is already in-flight, concurrent callers
    wait for it instead of launching their own.
    """
    global _used_bytes_cache, _used_bytes_inflight

    now = time.time()
    event = None

    with _used_bytes_cache_lock:
        if "value" in _used_bytes_cache:
            cached_value, cached_time = _used_bytes_cache["value"]
            if now - cached_time < _USED_BYTES_CACHE_TTL:
                return cached_value
        # Check if another thread is already scanning
        if _used_bytes_inflight is not None:
            event = _used_bytes_inflight

    # Another thread is scanning — wait for it then return cached value
    if event is not None:
        event.wait(timeout=60.0)
        with _used_bytes_cache_lock:
            if "value" in _used_bytes_cache:
                return _used_bytes_cache["value"][0]

    # We'll do the scan — set inflight flag
    done_event = threading.Event()
    with _used_bytes_cache_lock:
        _used_bytes_inflight = done_event

    try:
        total = _calculate_used_bytes_uncached()
        with _used_bytes_cache_lock:
            _used_bytes_cache["value"] = (total, time.time())
        return total
    finally:
        with _used_bytes_cache_lock:
            _used_bytes_inflight = None
        done_event.set()


def invalidate_used_bytes_cache() -> None:
    """Invalidate the used_bytes cache. Call after file uploads/deletions."""
    global _used_bytes_cache, _user_root_usage_cache
    with _used_bytes_cache_lock:
        _used_bytes_cache.clear()
    with _user_root_usage_cache_lock:
        _user_root_usage_cache.clear()


def calculate_user_root_usage_excluding_vcl(user_id: int, username: str, db: Session) -> dict[str, int]:
    """Return home-directory usage for one user while excluding VCL usage."""
    cache_key = f"{user_id}:{username}"
    now = time.time()

    with _user_root_usage_cache_lock:
        cached = _user_root_usage_cache.get(cache_key)
        if cached is not None:
            cached_value, cached_time = cached
            if now - cached_time < _USER_ROOT_USAGE_CACHE_TTL:
                return cached_value

    home_path = path_utils.ROOT_DIR / username
    home_total_bytes = _calculate_path_size(str(home_path)) if home_path.exists() else 0

    vcl_bytes = 0
    try:
        from app.models.vcl import VCLSettings

        settings_row = db.query(VCLSettings).filter(VCLSettings.user_id == user_id).first()
        if settings_row:
            vcl_bytes = int(settings_row.current_usage_bytes)
    except Exception:
        logger.debug("Failed to read VCL usage for user_id=%s", user_id, exc_info=True)

    result = {
        "user_root_used_bytes": max(0, home_total_bytes - vcl_bytes),
        "home_total_bytes": home_total_bytes,
        "vcl_bytes": max(0, vcl_bytes),
    }

    with _user_root_usage_cache_lock:
        _user_root_usage_cache[cache_key] = (result, now)

    return result


# ── Available bytes ──────────────────────────────────────────────────────────

def calculate_available_bytes() -> int:
    """Calculate remaining storage capacity.

    When a quota is configured (dev mode), returns ``quota - used``.
    When no quota is set (production), returns actual free disk space
    via ``shutil.disk_usage()`` on the storage root.
    """
    quota = settings.nas_quota_bytes
    if quota is not None:
        used = calculate_used_bytes()
        return max(0, quota - used)
    # No quota — check real disk space on the storage path
    import shutil
    try:
        usage = shutil.disk_usage(path_utils.ROOT_DIR)
        return usage.free
    except OSError:
        return 0


# ── Async wrappers ───────────────────────────────────────────────────────────

async def calculate_used_bytes_async() -> int:
    """Async wrapper for calculate_used_bytes() — runs in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(calculate_used_bytes)


async def calculate_available_bytes_async() -> int:
    """Async wrapper for calculate_available_bytes() — runs in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(calculate_available_bytes)
