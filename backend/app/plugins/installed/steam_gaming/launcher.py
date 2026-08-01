"""Enter and leave Steam's Big Picture mode in the user's desktop session.

On the production box Steam runs permanently (app-steam@autostart.service), so
these hand a steam:// URL to the running instance, which then switches modes;
the invoked process exits immediately.

Both calls are deliberately detached: if Steam is NOT running, the very same
command starts it in the foreground, and an attached child would live for as
long as the gaming session - hanging off the backend process. start_new_session
puts it in its own session/process group and nothing is ever waited on.

That "starts Steam" behaviour is a footgun for the CLOSE direction in
particular - ending gaming mode must not boot Steam - so its caller checks
first that a Steam client is running (see detection.steam_is_running).
"""
from __future__ import annotations

import logging
import subprocess

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

BIG_PICTURE_URL = "steam://open/bigpicture"
CLOSE_BIG_PICTURE_URL = "steam://close/bigpicture"


def _dispatch(url: str, what: str) -> tuple[bool, str]:
    """Hand *url* to Steam, detached. Blocking - call via asyncio.to_thread."""
    if settings.is_dev_mode:
        # No desktop session on a Windows dev box.
        return True, f"{what} requested (dev)"

    try:
        subprocess.Popen(  # fixed argv, no shell, no user input
            ["steam", url],
            env=wayland_session_env(),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, "steam binary not found"
    except OSError as exc:
        logger.warning("failed to dispatch %s: %s", url, exc)
        return False, "could not start steam"

    return True, f"{what} requested"


def open_big_picture() -> tuple[bool, str]:
    """Ask Steam to show Big Picture. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means the request was dispatched, not that Big
        Picture is on screen - the process is detached, so anything beyond the
        spawn is unobservable from here.
    """
    return _dispatch(BIG_PICTURE_URL, "big picture")


def close_big_picture() -> tuple[bool, str]:
    """Ask Steam to leave Big Picture. Blocking - call via asyncio.to_thread.

    Measured on BaluNode (2026-08-01): the running client drops back to the
    windowed UI and keeps running.

    Returns:
        (ok, detail). ok=True means the request was dispatched. Whether Big
        Picture is actually gone stays unobservable - the mode is not
        detectable from the outside at all (see the design doc from
        2026-07-24), which is exactly why there is no verification step here.
    """
    return _dispatch(CLOSE_BIG_PICTURE_URL, "big picture close")
