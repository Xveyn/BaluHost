"""Open Steam's Big Picture mode in the user's desktop session.

On the production box Steam runs permanently (app-steam@autostart.service), so
this hands a steam:// URL to the running instance, which then switches to Big
Picture and the invoked process exits immediately.

The call is deliberately detached: if Steam is NOT running, the very same
command starts it in the foreground, and an attached child would live for as
long as the gaming session - hanging off the backend process. start_new_session
puts it in its own session/process group and nothing is ever waited on.
"""
from __future__ import annotations

import logging
import subprocess

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

BIG_PICTURE_URL = "steam://open/bigpicture"


def open_big_picture() -> tuple[bool, str]:
    """Ask Steam to show Big Picture. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means the request was dispatched, not that Big
        Picture is on screen - the process is detached, so anything beyond the
        spawn is unobservable from here.
    """
    if settings.is_dev_mode:
        # No desktop session on a Windows dev box.
        return True, "big picture requested (dev)"

    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
            ["steam", BIG_PICTURE_URL],
            env=wayland_session_env(),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, "steam binary not found"
    except OSError as exc:
        logger.warning("failed to launch Big Picture: %s", exc)
        return False, "could not start steam"

    return True, "big picture requested"
