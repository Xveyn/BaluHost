"""The gaming-mode start sequence, shared by the power-menu action and the launch route.

Displays on, then the lock screen, then Big Picture, then the marker - in that
order, for the reasons in the plugin's CLAUDE.md ("Gaming Mode"). Pulled out of
SteamGamingPlugin.run_menu_action so the launch route runs exactly the same
steps instead of a second copy that would drift.

No outer timeout here or in the callers' route: asyncio.wait_for only cancels
the await, never the thread behind it, so a cut-off unlock would still unlock -
without its audit entry (#643). Each step bounds itself instead.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.plugins.installed.steam_gaming import gaming_state
from app.plugins.installed.steam_gaming.launcher import launch_game, open_big_picture
from app.services.power.desktop import get_desktop_service
from app.services.power.session_lock import unlock_if_permitted

logger = logging.getLogger(__name__)

__all__ = ["GamingModeStart", "launch_game", "start_gaming_mode"]


@dataclass(frozen=True)
class GamingModeStart:
    ok: bool
    failed_step: Optional[Literal["displays", "steam"]]
    detail: str  # never for the launch route's response or the audit trail;
    # the admin menu action shows it in its literal fallback text


async def start_gaming_mode(
    *, user: Optional[Any], client_host: Optional[str], db: Any
) -> GamingModeStart:
    """Run the start sequence. A refused unlock is not a failure."""
    # Displays first: opening Big Picture onto dark screens helps nobody.
    # LinuxDesktopBackend.enable() runs kscreen-doctor in a thread.
    ok, detail = await get_desktop_service().enable()
    if not ok:
        logger.warning("gaming mode: turning the displays on failed: %s", detail)
        return GamingModeStart(ok=False, failed_step="displays", detail=detail)

    # Then the lock screen, under the core's own right + LAN gate and audit.
    # Callers without a user (older menu dispatch) simply do not unlock.
    if user is not None:
        unlocked, unlock_detail = await unlock_if_permitted(
            user=user, client_host=client_host, db=db
        )
        if not unlocked:
            logger.info("gaming mode: session not unlocked: %s", unlock_detail)

    launched, detail = await asyncio.to_thread(open_big_picture)
    if not launched:
        logger.warning("gaming mode: Big Picture did not start: %s", detail)
        return GamingModeStart(ok=False, failed_step="steam", detail=detail)

    # Only now: the marker drives which direction the menu offers, so recording
    # a start that never happened would hide "start" behind a useless "end".
    await asyncio.to_thread(gaming_state.mark_started)
    return GamingModeStart(ok=True, failed_step=None, detail=detail)
