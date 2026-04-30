"""DRM connector status reader."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CONNECTOR_RE = re.compile(r"^card\d+-")


def _count_sync(sysfs_root: Path) -> int:
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return 0
    count = 0
    for entry in drm.iterdir():
        if not _CONNECTOR_RE.match(entry.name):
            continue
        status_file = entry / "status"
        enabled_file = entry / "enabled"
        if not status_file.exists() or not enabled_file.exists():
            continue
        try:
            status = status_file.read_text().strip()
            enabled = enabled_file.read_text().strip()
        except OSError as exc:
            logger.debug("Cannot read %s: %s", entry.name, exc)
            continue
        if status == "connected" and enabled == "enabled":
            count += 1
    return count


async def get_active_display_count(sysfs_root: Path = Path("/")) -> int:
    """Count DRM connectors with status='connected' AND enabled='enabled'.

    `enabled` covers DPMS-off / unused: physically connected but no active mode.
    """
    return await asyncio.to_thread(_count_sync, sysfs_root)
