"""Compute storage usage breakdown (cache vs VCL vs user files).

When the SSD file cache or VCL blob storage resides on the same filesystem
as the storage mountpoint, their usage is included in ``psutil.disk_usage().used``.
This module detects same-device overlap via ``os.stat().st_dev`` and returns a
breakdown so the frontend can show how much space is cache, VCL, and actual
user files.
"""

import logging
import os
from pathlib import Path
from typing import Optional, cast

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.storage import StorageBreakdown

logger = logging.getLogger(__name__)


def _get_device_id(path: str) -> Optional[int]:
    """Return the st_dev for *path*, falling back to parent directories."""
    p = Path(path)
    for candidate in [p, *p.parents]:
        try:
            return os.stat(str(candidate)).st_dev
        except OSError:
            continue
    return None


def compute_storage_breakdown(
    mountpoint_path: str,
    used_bytes: int,
    db: Session,
) -> Optional[StorageBreakdown]:
    """Return a StorageBreakdown if cache or VCL share the mountpoint's device.

    Returns ``None`` when neither cache nor VCL overlaps with the mountpoint
    filesystem (or when both contribute 0 bytes).
    """
    mp_dev = _get_device_id(mountpoint_path)
    if mp_dev is None:
        return None

    cache_bytes = 0
    cache_enabled = False
    vcl_bytes = 0

    # --- SSD File Cache ---
    try:
        from app.models.ssd_file_cache import SSDCacheConfig

        configs = db.query(SSDCacheConfig).all()
        for cfg in configs:
            cache_path = cast(str, cfg.cache_path) or ""
            if not cache_path:
                continue
            cache_dev = _get_device_id(cache_path)
            if cache_dev == mp_dev:
                cache_bytes += cast(int, cfg.current_size_bytes) or 0
                if cast(bool, cfg.is_enabled):
                    cache_enabled = True
    except Exception:
        logger.debug("Failed to query SSD cache configs", exc_info=True)

    # --- VCL Blob Storage ---
    try:
        from app.models.vcl import VCLStats

        vcl_base = settings.vcl_storage_path.strip()
        if vcl_base:
            vcl_path = vcl_base
        else:
            vcl_path = str(Path(settings.nas_storage_path) / ".system" / "versions")

        vcl_dev = _get_device_id(vcl_path)
        if vcl_dev == mp_dev:
            stats = db.query(VCLStats).first()
            if stats:
                vcl_bytes = cast(int, stats.total_compressed_bytes) or 0
    except Exception:
        logger.debug("Failed to query VCL stats", exc_info=True)

    # Only return a breakdown if there's something to break down
    if cache_bytes == 0 and vcl_bytes == 0:
        return None

    user_files_bytes = max(0, used_bytes - cache_bytes - vcl_bytes)

    return StorageBreakdown(
        cache_bytes=cache_bytes,
        cache_enabled=cache_enabled,
        vcl_bytes=vcl_bytes,
        user_files_bytes=user_files_bytes,
    )
