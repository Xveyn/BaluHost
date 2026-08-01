"""Clear the KDE session's screen by minimizing every window.

Driven through KWin's own D-Bus interface rather than a simulated key press:
ydotool/uinput would need privileges the backend does not have and should not
be given, while the session bus is already in reach - the backend runs under
the session user's uid (see session_env.py), so the same env that lets
kscreen-doctor talk to the session works here too.

Measured on BaluNode (2026-08-01): Plasma 6 on Debian 13 ships ``qdbus6`` and
no plain ``qdbus``, and ``org.kde.KWin`` on ``/KWin`` exposes both halves this
module needs::

    method Q_NOREPLY void org.kde.KWin.showDesktop(bool showing)
    property read bool org.kde.KWin.showingDesktop

The setter is used deliberately instead of kglobalaccel's "Show Desktop"
shortcut, which is a TOGGLE: a second invocation would bring the windows back,
so a retry or a double click would undo the action. ``showDesktop(true)`` is
idempotent. The property makes this the one step of ending gaming mode whose
effect can actually be verified - Big Picture's own state cannot be (see the
design doc from 2026-07-24).
"""
from __future__ import annotations

import logging
import subprocess
from typing import List, Optional, Tuple

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

SHOWING_DESKTOP_CMD = [
    "qdbus6",
    "org.kde.KWin",
    "/KWin",
    "org.kde.KWin.showingDesktop",
]


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # fixed argv, no shell, no user input
        cmd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        env=wayland_session_env(),
    )


def _showing_desktop() -> Optional[bool]:
    """KWin's own answer, or None when it cannot be read."""
    try:
        result = _run(SHOWING_DESKTOP_CMD)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def show_desktop() -> Tuple[bool, str]:
    """Minimize all windows. Blocking - call via asyncio.to_thread.

    Returns:
        (ok, detail). ok=True means KWin accepted the call and did not
        contradict it afterwards. Safe to call repeatedly: unlike the
        "Show Desktop" shortcut this sets the state instead of toggling it.
    """
    if settings.is_dev_mode:
        # No KWin, no session bus on a Windows dev box.
        return True, "show desktop requested (dev)"

    try:
        result = _run(SHOW_DESKTOP_CMD)
    except FileNotFoundError:
        return False, "qdbus6 not found (is the desktop session running?)"
    except subprocess.TimeoutExpired:
        return False, "qdbus6 timed out"

    if result.returncode != 0:
        detail = (result.stderr or "").strip() or f"exit {result.returncode}"
        logger.warning("show desktop failed: %s", detail)
        return False, detail

    # Only an explicit contradiction counts as a failure. A property that
    # cannot be read says nothing about the windows, and turning that into a
    # red toast would report a problem that may not exist.
    if _showing_desktop() is False:
        logger.warning("show desktop: KWin still reports showingDesktop=false")
        return False, "KWin still reports the windows as visible"
    return True, "windows minimized"
