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


def get_active_display_count_sync(sysfs_root: Path = Path("/")) -> int:
    """Same count, for callers that cannot await.

    The work is a handful of small sysfs reads - the async variant above only
    wraps it in a thread because it sits on request paths that already are
    async. The plugin UI manifest is built synchronously and needs the same
    answer, and reaching into the private helper from there would make this
    module's public surface a lie.
    """
    return _count_sync(sysfs_root)


def _states_sync(sysfs_root: Path) -> dict[str, bool]:
    """Read, per connector, whether it is actually driving pixels."""
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return {}
    states: dict[str, bool] = {}
    for entry in sorted(drm.iterdir()):
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
        # KWin knows the connector without the "card<N>-" prefix.
        states[_CONNECTOR_RE.sub("", entry.name)] = (
            status == "connected" and enabled == "enabled"
        )
    return states


def get_connector_states_sync(sysfs_root: Path = Path("/")) -> dict[str, bool]:
    """Per-connector 'is this driving pixels?', keyed by the KWin name.

    Same sysfs pass as get_active_display_count(), but keeps the names. The
    display_output plugin needs to say WHICH output is lit, not how many are -
    and a second sysfs reader for the same question would be the worse answer.
    """
    return _states_sync(sysfs_root)


async def get_connector_states(sysfs_root: Path = Path("/")) -> dict[str, bool]:
    """Async variant, for callers already on an event loop."""
    return await asyncio.to_thread(_states_sync, sysfs_root)
