"""Gaming as a suspend suppressor.

The fourth suppressor next to always-awake, core uptime and presence
(`presence.py`). Presence answers "is a human in the web app?" by reading
heartbeats; this module answers "is a human at the box, playing?".

Why this exists: `SleepManagerService._is_system_idle()` decides whether a
human is around by looking at NAS load — CPU percent, disk I/O, HTTP requests.
A game produces none of those reliably, and on 2026-09-08 that cost a running
session: the box suspended out from under DiRT Rally 2.0 sixteen minutes after
the core-uptime window ended. Asking the game detector is a direct answer to
the question the load metrics were being asked to guess at.

Two signals, because Big Picture mode itself is not observable from outside
(measured on 2026-07-24, see the steam_gaming design doc):

- a running game — a `/proc` scan for Steam's `SteamLaunch AppId=` wrapper.
  Blocks suspend unconditionally.
- gaming mode on screen — BaluHost started Big Picture and has not ended it,
  AND a display is lit. Governed by `block_suspend_in_gaming_mode`.

This module is the only place the sleep service knows about the steam_gaming
plugin, so a move or rename of the plugin lands here and nowhere else.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from app.core.config import settings
from app.services.power.gpu.display_detector import get_active_display_count_sync

logger = logging.getLogger(__name__)

# The bundled plugin is removable, and a missing plugin must not stop the
# backend from booting — the sleep service imports this module at startup.
# `detector` is a dependency-free /proc scanner, so importing it pulls in no
# plugin framework.
detect_running_app_id: Optional[Callable[[], Optional[str]]]
try:
    from app.plugins.installed.steam_gaming.detector import detect_running_app_id
except ImportError:  # pragma: no cover - only when the plugin is deleted
    detect_running_app_id = None
    logger.warning(
        "steam_gaming detector unavailable — a running game will NOT block suspend"
    )


def _marker_is_active() -> bool:
    """Whether BaluHost started Big Picture and has not ended it.

    Imported lazily: `gaming_state` reads the storage root through settings,
    which the detector does not, and this keeps that cost off the import path.
    """
    try:
        from app.plugins.installed.steam_gaming import gaming_state
    except ImportError:  # pragma: no cover - only when the plugin is deleted
        return False
    return gaming_state.is_active()


def displays_on() -> bool:
    """True while at least one display is lit.

    Unreadable sysfs counts as "off". For the gaming gate that is the harmless
    direction: it lets a suspend through rather than pinning the box awake on a
    reading nobody can verify.
    """
    if settings.is_dev_mode:
        # No DRM connectors on a Windows dev box, so the count would be 0
        # forever and the Big Picture branch could never be tried locally.
        return True
    try:
        return get_active_display_count_sync() > 0
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("display count unreadable: %s", exc)
        return False


def game_is_running() -> bool:
    """True while a Steam game is running.

    Deliberately calls the raw detector rather than
    `detection.current_app_id()`: that wrapper substitutes a placeholder AppID
    on a box without `/proc`, which would make every dev machine claim a game
    is running and never sleep.

    Fails toward energy saving, matching `SleepManagerService._is_user_present`
    — a broken detector must not pin the box awake indefinitely.
    """
    if detect_running_app_id is None:
        return False
    try:
        return detect_running_app_id() is not None
    except Exception as exc:
        logger.warning("Game detection failed (allowing suspend): %s", exc)
        return False


def gaming_mode_on_screen() -> bool:
    """True while Big Picture is up as far as we can tell.

    The marker alone would survive a Big Picture that was left running and
    then abandoned; requiring a lit display is what lets that stale state
    expire on its own.
    """
    return _marker_is_active() and displays_on()


def blocks_suspend(config) -> bool:
    """Whether gaming activity should suppress an automatic suspend.

    A running game always blocks. Big Picture without a game blocks only when
    `block_suspend_in_gaming_mode` is set.
    """
    if game_is_running():
        return True
    raw = getattr(config, "block_suspend_in_gaming_mode", None)
    # None covers both a missing config row and a SleepConfig built without
    # the column; either way the column's database default applies.
    enabled = True if raw is None else bool(raw)
    return enabled and gaming_mode_on_screen()
