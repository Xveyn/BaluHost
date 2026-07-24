"""Unlock the graphical KDE session via systemd-logind.

`loginctl unlock-session` emits an Unlock signal that kscreenlocker obeys -
the same path fingerprint readers and smartcards use. Measured on the box: it
works as the session owner WITHOUT sudo, and the backend already runs as that
user, so this needs no sudoers rule and no new root path.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Callable, List, Optional, Protocol, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# kscreenlocker processes the Unlock signal asynchronously - the measurement on
# the box needed roughly two seconds. A single immediate read of LockedHint
# would sporadically still say "yes" and report a failure that never happened.
_POLL_INTERVAL_SECONDS = 0.2
_POLL_TIMEOUT_SECONDS = 3.0
_COMMAND_TIMEOUT_SECONDS = 10


class SessionLockBackend(Protocol):
    def unlock(self) -> Tuple[bool, str]: ...


class DevSessionLockBackend:
    """In-memory backend for dev mode / non-Linux hosts."""

    def __init__(self) -> None:
        self._locked = True

    def unlock(self) -> Tuple[bool, str]:
        self._locked = False
        return True, "session unlocked (dev)"


class LinuxSessionLockBackend:
    """Unlocks the user's graphical session through loginctl.

    Blocking - call via asyncio.to_thread. The runner/sleep/monotonic seams
    exist so tests never touch a real loginctl or a real clock.
    """

    def __init__(
        self,
        uid: Optional[int] = None,
        runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
    ) -> None:
        self._uid = uid if uid is not None else os.getuid()
        self._run = runner or self._default_runner
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic

    @staticmethod
    def _default_runner(cmd: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=_COMMAND_TIMEOUT_SECONDS
        )

    def _graphical_session_id(self) -> Optional[str]:
        """The user's graphical session, or None.

        Primary path is logind's own answer (`show-user -p Display`); the
        fallback scans the session list for a seated session of this user,
        which skips SSH logins (no seat) and the user manager (class != user).
        """
        result = self._run(
            ["loginctl", "show-user", str(self._uid), "-p", "Display", "--value"]
        )
        if result.returncode == 0:
            session_id = (result.stdout or "").strip()
            if session_id:
                return session_id

        result = self._run(["loginctl", "list-sessions", "--no-legend"])
        if result.returncode != 0:
            return None
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            # SESSION UID USER SEAT LEADER CLASS TTY IDLE SINCE
            if len(parts) < 6:
                continue
            session_id, uid, _user, seat, _leader, session_class = parts[:6]
            if uid != str(self._uid) or seat == "-" or session_class != "user":
                continue
            return session_id
        return None

    def _locked_hint(self, session_id: str) -> Optional[bool]:
        result = self._run(
            ["loginctl", "show-session", session_id, "-p", "LockedHint", "--value"]
        )
        if result.returncode != 0:
            return None
        value = (result.stdout or "").strip().lower()
        if value in ("yes", "true"):
            return True
        if value in ("no", "false"):
            return False
        return None

    def unlock(self) -> Tuple[bool, str]:
        """Unlock the graphical session and VERIFY it actually unlocked.

        Returns (ok, detail). ok=True means LockedHint reads "no" afterwards -
        loginctl's exit code alone only says the signal was dispatched.
        """
        try:
            session_id = self._graphical_session_id()
            if not session_id:
                return False, "no graphical session found"

            result = self._run(["loginctl", "unlock-session", session_id])
            if result.returncode != 0:
                detail = (result.stderr or "").strip() or f"exit {result.returncode}"
                return False, detail

            deadline = self._monotonic() + _POLL_TIMEOUT_SECONDS
            while True:
                if self._locked_hint(session_id) is False:
                    return True, f"session {session_id} unlocked"
                if self._monotonic() >= deadline:
                    return False, (
                        f"session {session_id} still reports LockedHint=yes"
                    )
                self._sleep(_POLL_INTERVAL_SECONDS)
        except FileNotFoundError:
            return False, "loginctl not found"
        except subprocess.TimeoutExpired:
            return False, "loginctl timed out"


_backend: Optional[SessionLockBackend] = None


def get_session_lock_backend() -> SessionLockBackend:
    """Process-wide backend, chosen once by mode."""
    global _backend
    if _backend is None:
        _backend = (
            DevSessionLockBackend() if settings.is_dev_mode else LinuxSessionLockBackend()
        )
    return _backend
