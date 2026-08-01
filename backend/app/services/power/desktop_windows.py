"""Clear the KDE session's screen by minimizing every window.

Driven through KWin's D-Bus interfaces rather than a simulated key press:
ydotool/uinput would need privileges the backend does not have and should not
be given, while the session bus is already in reach - the backend runs under
the session user's uid (see session_env.py), so the same env that lets
kscreen-doctor talk to the session works here too.

Measured on BaluNode (2026-08-01), Plasma 6 on Debian 13, with visible windows::

    $ qdbus6 org.kde.KWin /KWin org.kde.KWin.showingDesktop
    false
    $ qdbus6 org.kde.KWin /KWin org.kde.KWin.showDesktop true    # exit 0
    $ qdbus6 org.kde.KWin /KWin org.kde.KWin.showingDesktop
    false                                    # <- nothing happened, windows up
    $ qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut "Show Desktop"
    $ qdbus6 org.kde.KWin /KWin org.kde.KWin.showingDesktop
    true                                     # <- windows down

So: the ``showDesktop(bool)`` setter accepts the call and does nothing (it is
Q_NOREPLY, so its exit code says only that the message was sent - never mistake
that for an effect). The kglobalaccel shortcut works, and ``showingDesktop``
tracks exactly that path.

That property is read twice here, for two different jobs:

- BEFORE, because the shortcut is a TOGGLE: firing it while the desktop is
  already cleared would bring the windows back. Reading first makes this
  function idempotent without a setter.
- AFTER, as the one honest verification in the whole "end gaming mode" flow.
  Big Picture's own state is not observable (design doc 2026-07-24); this is.

History worth keeping: shipping the setter cost two releases. #497 used it
plus the read-back and reported failure on every run; #499 then removed the
read-back as a "false alarm" - it had been telling the truth. The measurement
above is why both the shortcut and the read-back are here now.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import List, Optional, Tuple

from app.core.config import settings
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

# KWin answers in milliseconds; anything that needs several seconds is broken,
# not slow. Kept well inside the 20s budget of a plugin menu action.
_TIMEOUT_SECONDS = 10

# KWin applies the shortcut asynchronously - the manual measurement needed a
# moment before the property flipped. A single immediate read would sporadically
# report a failure that never happened.
_VERIFY_TIMEOUT_SECONDS = 2.0
_VERIFY_INTERVAL_SECONDS = 0.2

SHOW_DESKTOP_CMD = [
    "qdbus6",
    "org.kde.kglobalaccel",
    "/component/kwin",
    "invokeShortcut",
    "Show Desktop",
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
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("showingDesktop unreadable: %s", exc)
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _wait_until_showing_desktop() -> Optional[bool]:
    """Poll the property until it reads true, or the deadline passes."""
    deadline = time.monotonic() + _VERIFY_TIMEOUT_SECONDS
    while True:
        state = _showing_desktop()
        if state is not False:
            return state  # True, or unreadable - neither contradicts the call
        if time.monotonic() >= deadline:
            return False
        time.sleep(_VERIFY_INTERVAL_SECONDS)


def show_desktop() -> Tuple[bool, str]:
    """Minimize all windows. Blocking - call via asyncio.to_thread.

    Idempotent: when KWin already reports the desktop as shown, the toggling
    shortcut is not fired at all.

    Returns:
        (ok, detail). ok=False only when KWin refused the call or still
        reports the windows as visible afterwards.
    """
    if settings.is_dev_mode:
        # No KWin, no session bus on a Windows dev box.
        return True, "show desktop requested (dev)"

    if _showing_desktop() is True:
        return True, "windows already minimized"

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

    if _wait_until_showing_desktop() is False:
        logger.warning("show desktop: KWin still reports showingDesktop=false")
        return False, "KWin still reports the windows as visible"
    return True, "windows minimized"
