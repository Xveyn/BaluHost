"""DRM connector status reader."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

_CONNECTOR_RE = re.compile(r"^card\d+-")


def _iter_connector_states(sysfs_root: Path) -> Iterator[tuple[str, bool]]:
    """Yield (KWin name, is-lit) for every DRM connector under sysfs_root.

    The single place that knows how to walk /sys/class/drm and what "lit"
    means - a connector is lit when status='connected' AND enabled='enabled'
    (`enabled` covers DPMS-off / unused: physically connected but no active
    mode). Both the count and the per-connector map derive from this
    generator, so they cannot drift apart.

    Names are KWin-style (the "card<N>-" prefix stripped), and this can
    yield the same name more than once: two cards can expose the same
    connector name (card0-DP-1 and card1-DP-1 both strip to "DP-1"). Callers
    that need a count must count entries, not distinct names - collapsing
    them would undercount real displays.
    """
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return
    seen: set[str] = set()
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
        name = _CONNECTOR_RE.sub("", entry.name)
        if name in seen:
            logger.warning(
                "Multiple DRM connectors strip to the same KWin name %r; "
                "the KWin-name-to-connector mapping is ambiguous.",
                name,
            )
        seen.add(name)
        yield name, (status == "connected" and enabled == "enabled")


def _states_sync(sysfs_root: Path) -> dict[str, bool]:
    """Per-connector 'is this lit?', keyed by the KWin name.

    When a name is ambiguous (see `_iter_connector_states`), last-wins.
    """
    return dict(_iter_connector_states(sysfs_root))


def _count_sync(sysfs_root: Path) -> int:
    """Count of lit connectors.

    Counts entries, not distinct names: two cards can expose the same
    connector name, and collapsing them via `_states_sync`'s dict would
    undercount real displays.
    """
    return sum(1 for _, lit in _iter_connector_states(sysfs_root) if lit)


async def get_active_display_count(sysfs_root: Path = Path("/")) -> int:
    """Count DRM connectors that are actually driving pixels.

    See `_iter_connector_states` for what "lit" means.
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


def get_connector_states_sync(sysfs_root: Path = Path("/")) -> dict[str, bool]:
    """Per-connector 'is this driving pixels?', keyed by the KWin name.

    The display_output plugin needs to say WHICH output is lit, not how many
    are - and a second sysfs reader for the same question would be the worse
    answer, so this just exposes `_states_sync`.
    """
    return _states_sync(sysfs_root)


async def get_connector_states(sysfs_root: Path = Path("/")) -> dict[str, bool]:
    """Async variant, for callers already on an event loop."""
    return await asyncio.to_thread(_states_sync, sysfs_root)
