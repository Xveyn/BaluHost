"""Clear the KDE session's screen by minimizing every window.

Driven through KWin's global-shortcut D-Bus interface rather than a simulated
key press: ydotool/uinput would need privileges the backend does not have and
should not be given, while the session bus is already in reach - the backend
runs under the session user's uid (see session_env.py), so the same env that
lets kscreen-doctor talk to the session works here too.

Measured on BaluNode (2026-08-01): Plasma 6 on Debian 13 ships ``qdbus6`` and
no plain ``qdbus``, and KWin lists the shortcut under exactly "Show Desktop"
(``org.kde.kglobalaccel.Component.shortcutNames`` on the kwin component).
"""
from __future__ import annotations

import logging
import subprocess
from typing import Tuple

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

# kglobalaccel answers in milliseconds; anything that needs several seconds is
# broken, not slow. Kept well inside the 20s budget of a plugin menu action.
_TIMEOUT_SECONDS = 10

SHOW_DESKTOP_CMD = [
    "qdbus6",
    "org.kde.kglobalaccel",
    "/component/kwin",
    "invokeShortcut",
    "Show Desktop",
]


def show_desktop() -> Tuple[bool, str]:
    """Minimize all windows. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means KWin accepted the shortcut.

    Note this is KWin's TOGGLE, not a setter: invoking it while the desktop is
    already cleared brings the windows back. Callers must fire it as the last
    step of an action the user asked for, never speculatively or on a retry.
    """
    if settings.is_dev_mode:
        # No KWin, no session bus on a Windows dev box.
        return True, "show desktop requested (dev)"

    try:
        result = subprocess.run(  # fixed argv, no shell, no user input
            SHOW_DESKTOP_CMD,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            env=wayland_session_env(),
        )
    except FileNotFoundError:
        return False, "qdbus6 not found (is the desktop session running?)"
    except subprocess.TimeoutExpired:
        return False, "qdbus6 timed out"

    if result.returncode != 0:
        detail = (result.stderr or "").strip() or f"exit {result.returncode}"
        logger.warning("show desktop failed: %s", detail)
        return False, detail
    return True, "windows minimized"
