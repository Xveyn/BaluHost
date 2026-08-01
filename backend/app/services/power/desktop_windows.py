"""Clear the KDE session's screen by minimizing every window.

Driven through KWin's own D-Bus interface rather than a simulated key press:
ydotool/uinput would need privileges the backend does not have and should not
be given, while the session bus is already in reach - the backend runs under
the session user's uid (see session_env.py), so the same env that lets
kscreen-doctor talk to the session works here too.

Measured on BaluNode (2026-08-01), Plasma 6 on Debian 13:

- the binary is ``qdbus6``; there is no plain ``qdbus``
- ``org.kde.KWin.showDesktop(bool)`` on ``/KWin`` minimizes every window and
  exits 0. It takes a bool rather than toggling, so calling it twice leaves
  the windows down - unlike kglobalaccel's "Show Desktop" shortcut, where a
  second invocation brings them back.
- ``org.kde.KWin.showingDesktop`` reads **false** one second after that same
  successful call, with the windows visibly down. It tracks KWin's temporary
  show-desktop MODE, not "are the windows minimized". **Do not use it to
  verify this call** - the first version of this module did, and every
  successful run reported "the windows stayed up" to the user.

So there is no verification step here: like everything else in ending gaming
mode, the effect is not observable (Big Picture's own state is not either, see
the design doc from 2026-07-24). A non-zero exit is the only failure this
module can honestly report.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Tuple

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

# KWin answers in milliseconds; anything that needs several seconds is broken,
# not slow. Kept well inside the 20s budget of a plugin menu action.
_TIMEOUT_SECONDS = 10

SHOW_DESKTOP_CMD = [
    "qdbus6",
    "org.kde.KWin",
    "/KWin",
    "org.kde.KWin.showDesktop",
    "true",
]


def show_desktop() -> Tuple[bool, str]:
    """Minimize all windows. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means KWin accepted the call. Safe to repeat:
        the call sets the state instead of toggling it.
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
