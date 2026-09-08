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

    This generator does not warn about ambiguous names and does not resolve
    them - it just yields every entry as measured. `_count_sync` runs
    through here once per monitoring tick and does not care about the
    name-to-connector mapping at all; a warning placed here would fire every
    tick, forever, from a path that has no use for it. The one caller that
    *does* need unambiguous names (`_states_sync`) does that resolution and
    the warning itself.
    """
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return
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
        yield name, (status == "connected" and enabled == "enabled")


def _states_sync(sysfs_root: Path) -> dict[str, bool]:
    """Per-connector 'is this lit?', keyed by the KWin name.

    When a name is ambiguous - two DRM connectors strip to the same KWin
    name - the mapping cannot say which connector "DP-1" in KWin's world
    actually refers to. Reporting the last one seen (last-wins) would turn
    an unresolvable question into a confident True/False, which is exactly
    the false-statement pattern this feature exists to avoid (spec 5): the
    name is removed from the map entirely instead, so a caller's
    `states.get(name)` answers `None` - "not resolvable", the honest
    answer.
    """
    states: dict[str, bool] = {}
    ambiguous: set[str] = set()
    for name, lit in _iter_connector_states(sysfs_root):
        if name in ambiguous:
            continue
        if name in states:
            logger.warning(
                "Multiple DRM connectors strip to the same KWin name %r; "
                "the KWin-name-to-connector mapping is ambiguous.",
                name,
            )
            ambiguous.add(name)
            del states[name]
            continue
        states[name] = lit
    return states


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
