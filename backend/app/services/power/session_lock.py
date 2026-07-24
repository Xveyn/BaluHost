"""Unlock the graphical KDE session via systemd-logind.

`loginctl unlock-session` emits an Unlock signal that kscreenlocker obeys -
the same path fingerprint readers and smartcards use. Measured on the box: it
works as the session owner WITHOUT sudo, and the backend already runs as that
user, so this needs no sudoers rule and no new root path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from typing import Callable, List, Optional, Protocol, Tuple

from app.core.config import settings
from app.core.network_utils import is_private_or_local_ip
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power_permissions import check_permission

logger = logging.getLogger(__name__)

# kscreenlocker processes the Unlock signal asynchronously - the measurement on
# the box needed roughly two seconds. A single immediate read of LockedHint
# would sporadically still say "yes" and report a failure that never happened.
_POLL_INTERVAL_SECONDS = 0.2
_POLL_TIMEOUT_SECONDS = 3.0
_COMMAND_TIMEOUT_SECONDS = 10


class SessionLockBackend(Protocol):
    """Anything that can unlock the user's graphical session."""

    def unlock(self) -> Tuple[bool, str]:
        """Unlock the session; returns (ok, detail)."""
        ...


class DevSessionLockBackend:
    """In-memory backend for dev mode / non-Linux hosts."""

    def __init__(self) -> None:
        self._locked = True

    def unlock(self) -> Tuple[bool, str]:
        """Pretend to unlock - there is no logind on a dev box."""
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
            last_hint: Optional[bool] = None
            while True:
                last_hint = self._locked_hint(session_id)
                if last_hint is False:
                    return True, f"session {session_id} unlocked"
                if self._monotonic() >= deadline:
                    reason = (
                        "still reports LockedHint=yes"
                        if last_hint is True
                        else "LockedHint could not be read"
                    )
                    return False, f"session {session_id} {reason}"
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


def _may_unlock(user, db) -> bool:
    """Admins pass by role, like every other power permission."""
    if getattr(user, "role", None) == "admin":
        return True
    return check_permission(db, user.id, "unlock_session")


async def unlock_if_permitted(*, user, client_host: Optional[str], db) -> Tuple[bool, str]:
    """Unlock the desktop session if BOTH gates allow it.

    This is the only place the gates are evaluated and the only place the audit
    entry is written - so no caller can unlock without leaving a trace, not
    even a plugin.

    Args:
        user: The authenticated caller (needs .id, .username, .role).
        client_host: The request's client IP, or None.
        db: SQLAlchemy session.

    Returns:
        (unlocked, detail). ``unlocked`` describes the state afterwards; on a
        refused gate loginctl is never called and the real lock state is
        unknown, so it is False with the reason in ``detail``.
    """
    if not _may_unlock(user, db):
        return False, "permission required: power:unlock_session"
    if not is_private_or_local_ip(client_host):
        return False, "not permitted from this network"

    ok, detail = await asyncio.to_thread(get_session_lock_backend().unlock)
    if not ok:
        logger.warning("session unlock failed for %s: %s", user.username, detail)
        return False, detail

    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="desktop_unlock_session",
        user=user.username,
        resource="desktop",
        success=True,
        details={"message": detail},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="unlock_session",
            details={"action": "desktop_unlock_session"},
            success=True,
        )
    return True, detail
