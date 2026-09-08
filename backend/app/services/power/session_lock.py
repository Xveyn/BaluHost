"""Lock and unlock the graphical KDE session via systemd-logind.

`loginctl unlock-session` / `loginctl lock-session` emit Unlock/Lock signals
that kscreenlocker obeys - the same path fingerprint readers and smartcards
use. Measured on the box (2026-09-08): both work as the session owner WITHOUT
sudo, and the backend already runs as that user, so this needs no sudoers
rule and no new root path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from typing import Callable, List, Optional, Protocol, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.network_utils import is_private_or_local_ip
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power_permissions import check_permission

logger = logging.getLogger(__name__)

# kscreenlocker processes the Unlock signal asynchronously - the measurement on
# the box needed roughly two seconds. A single immediate read of LockedHint
# would sporadically still say "yes" and report a failure that never happened.
_POLL_INTERVAL_SECONDS = 0.2
_POLL_TIMEOUT_SECONDS = 3.0
# Per COMMAND, and one unlock runs up to four of them (show-user, optionally
# list-sessions, unlock-session, the first show-session). At 10s that is a
# 40s worst case, which would blow the 20s budget of a plugin menu action and
# leave Big Picture unstarted. loginctl answers in milliseconds; anything that
# needs three seconds will not become useful at ten.
_COMMAND_TIMEOUT_SECONDS = 3


class SessionLockBackend(Protocol):
    """Anything that can lock or unlock the user's graphical session."""

    def unlock(self) -> Tuple[bool, str]:
        """Unlock the session; returns (ok, detail)."""
        ...

    def lock(self) -> Tuple[bool, str]:
        """Lock the session; returns (ok, detail)."""
        ...

    def is_locked(self) -> Optional[bool]:
        """Whether the session is locked right now, or None if unknowable."""
        ...


class DevSessionLockBackend:
    """In-memory backend for dev mode / non-Linux hosts."""

    def __init__(self) -> None:
        self._locked = True

    def unlock(self) -> Tuple[bool, str]:
        """Pretend to unlock - there is no logind on a dev box."""
        self._locked = False
        return True, "session unlocked (dev)"

    def lock(self) -> Tuple[bool, str]:
        """Pretend to lock - there is no logind on a dev box."""
        self._locked = True
        return True, "session locked (dev)"

    def is_locked(self) -> Optional[bool]:
        """Start out locked, so the unlock button is reachable in dev mode."""
        return self._locked


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

    def is_locked(self) -> Optional[bool]:
        """Read the lock state without touching the session.

        A pure read: it asks logind and changes nothing. Returns None whenever
        the answer is unknown (no graphical session, unreadable hint, no
        loginctl) - callers must not read that as "not locked", or a UI would
        hide its unlock button on exactly the box where logind is mute.
        """
        try:
            session_id = self._graphical_session_id()
            if not session_id:
                return None
            return self._locked_hint(session_id)
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None

    def _transition(self, verb: str, want_locked: bool) -> Tuple[bool, str]:
        """Run one loginctl verb against the session and VERIFY the outcome.

        Shared by :meth:`lock` and :meth:`unlock` - the two would otherwise be
        near-identical: find the session, run the verb, then poll LockedHint
        until it reads the wanted value. Only the verb and the wanted hint
        differ.

        Returns (ok, detail). ok=True means LockedHint reads the wanted value
        afterwards - loginctl's exit code alone only says the signal was
        dispatched, never that kscreenlocker actually acted on it.
        """
        state_word = "locked" if want_locked else "unlocked"
        try:
            session_id = self._graphical_session_id()
            if not session_id:
                return False, "no graphical session found"

            result = self._run(["loginctl", verb, session_id])
            if result.returncode != 0:
                detail = (result.stderr or "").strip() or f"exit {result.returncode}"
                return False, detail

            deadline = self._monotonic() + _POLL_TIMEOUT_SECONDS
            last_hint: Optional[bool] = None
            while True:
                last_hint = self._locked_hint(session_id)
                if last_hint is want_locked:
                    return True, f"session {session_id} {state_word}"
                if self._monotonic() >= deadline:
                    # Distinguish "still reports the old state" (hint read
                    # fine, just not the wanted value) from "hint could not
                    # be read at all" (the lock state is genuinely unknown).
                    if last_hint is None:
                        reason = "LockedHint could not be read"
                    else:
                        reason = f"still reports LockedHint={'yes' if last_hint else 'no'}"
                    return False, f"session {session_id} {reason}"
                self._sleep(_POLL_INTERVAL_SECONDS)
        except FileNotFoundError:
            return False, "loginctl not found"
        except subprocess.TimeoutExpired:
            return False, "loginctl timed out"

    def unlock(self) -> Tuple[bool, str]:
        """Unlock the graphical session and VERIFY it actually unlocked.

        Returns (ok, detail). ok=True means LockedHint reads "no" afterwards -
        loginctl's exit code alone only says the signal was dispatched.
        """
        return self._transition("unlock-session", want_locked=False)

    def lock(self) -> Tuple[bool, str]:
        """Lock the graphical session and VERIFY it actually locked.

        Returns (ok, detail). ok=True means LockedHint reads "yes" afterwards -
        loginctl's exit code alone only says the signal was dispatched.
        """
        return self._transition("lock-session", want_locked=True)


_backend: Optional[SessionLockBackend] = None


def get_session_lock_backend() -> SessionLockBackend:
    """Process-wide backend, chosen once by mode."""
    global _backend
    if _backend is None:
        _backend = (
            DevSessionLockBackend() if settings.is_dev_mode else LinuxSessionLockBackend()
        )
    return _backend


async def current_lock_state() -> Optional[bool]:
    """Whether the desktop session is locked, or None if that cannot be told.

    Deliberately ungated: the answer is a single bit about the machine's own
    screen, no more revealing than the desktop on/off state next to it, and
    every caller is already authenticated. Acting on it still runs the full
    gates in :func:`unlock_if_permitted`.
    """
    try:
        return await asyncio.to_thread(get_session_lock_backend().is_locked)
    except Exception:
        # A status endpoint must not 5xx because logind hiccupped.
        logger.exception("session lock state could not be read")
        return None


def _may_operate_session_lock(user: UserPublic, db: Session) -> bool:
    """Admins pass by role, like every other power permission.

    One capability gates both directions - ``can_unlock_session`` covers
    locking too. Whoever is trusted to dismiss the lock screen is trusted to
    put it back up.
    """
    if user.role == "admin":
        return True
    return check_permission(db, user.id, "unlock_session")


def _audit_session_lock_action(
    *, action: str, user: UserPublic, client_host: Optional[str], ok: bool, detail: str
) -> None:
    """Shared audit-writing tail for :func:`lock_if_permitted` and
    :func:`unlock_if_permitted`.

    A REFUSED gate stays unaudited on purpose - the caller decides that
    *before* reaching here, and auditing every refusal would drown the real
    entries. An ATTEMPTED action (the gates were passed) always gets an entry,
    both outcomes, so nothing on the trail requires cross-referencing loginctl
    logs to know whether it worked. The ``delegated_power_action`` security
    event fires only for a non-admin AND only on success, mirroring the
    sibling desktop routes.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="desktop",
        success=ok,
        ip_address=client_host,
        details={"message": detail},
    )
    if ok and user.role != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="unlock_session",
            details={"action": action, "client_host": client_host},
            success=True,
            ip_address=client_host,
        )


async def unlock_if_permitted(
    *, user: UserPublic, client_host: Optional[str], db: Session
) -> Tuple[bool, str]:
    """Unlock the desktop session if BOTH gates allow it.

    This is the only place the gates are evaluated and the only place the audit
    entry is written - so no caller can unlock without leaving a trace, not
    even a plugin.

    Args:
        user: The authenticated caller.
        client_host: The request's client IP, or None.
        db: SQLAlchemy session.

    Returns:
        (unlocked, detail). ``unlocked`` describes the state afterwards; on a
        refused gate loginctl is never called and the real lock state is
        unknown, so it is False with the reason in ``detail``.
    """
    # Cheap gate first: a WAN request should not cost a database query.
    if not is_private_or_local_ip(client_host):
        return False, "not permitted from this network"

    try:
        permitted = _may_operate_session_lock(user, db)
    except Exception:
        # A database hiccup must not turn "displays on" into a 500, and it is
        # not an unlock attempt - so it stays out of the audit trail, like any
        # other refused gate.
        logger.exception("session unlock: permission check failed for %s", user.username)
        return False, "permission check failed"
    if not permitted:
        return False, "permission required: power:unlock_session"

    try:
        ok, detail = await asyncio.to_thread(get_session_lock_backend().unlock)
    except Exception:
        # The backend catches FileNotFoundError and TimeoutExpired itself, but
        # not an OSError from a failing fork, a PermissionError or a decode
        # error. Neither caller may die of it: the route already reported the
        # displays as on, and the gaming mode still has to launch Big Picture.
        logger.exception("session unlock raised for %s", user.username)
        ok, detail = False, "unlock failed unexpectedly"

    _audit_session_lock_action(
        action="desktop_unlock_session", user=user, client_host=client_host, ok=ok, detail=detail
    )
    if not ok:
        logger.warning("session unlock failed for %s: %s", user.username, detail)
        return False, detail
    return True, detail


async def lock_if_permitted(
    *, user: UserPublic, client_host: Optional[str], db: Session
) -> Tuple[bool, str]:
    """Lock the desktop session if the permission gate allows it.

    Deliberately asymmetric with :func:`unlock_if_permitted`: there is NO
    network gate here. The LAN/VPN check on unlock exists so a stolen web
    account cannot OPEN a physical desktop from the internet - locking is the
    safe direction, it only CLOSES the desktop, and the situation that calls
    for a remote lock (forgot to lock before leaving, reacting to a
    compromised account) is exactly the case of NOT being in front of the
    machine. Do not "fix" this into symmetry with unlock; the asymmetry is
    the point. ``client_host`` is still accepted and still recorded in the
    audit entry - it just never decides anything here.

    Args:
        user: The authenticated caller.
        client_host: The request's client IP, or None. Audited only.
        db: SQLAlchemy session.

    Returns:
        (locked, detail). ``locked`` describes the state afterwards; on a
        refused gate loginctl is never called and the real lock state is
        unknown, so it is False with the reason in ``detail``.
    """
    try:
        permitted = _may_operate_session_lock(user, db)
    except Exception:
        # A database hiccup must not become a 500, and it is not a lock
        # attempt - so it stays out of the audit trail, like any other
        # refused gate.
        logger.exception("session lock: permission check failed for %s", user.username)
        return False, "permission check failed"
    if not permitted:
        return False, "permission required: power:unlock_session"

    try:
        ok, detail = await asyncio.to_thread(get_session_lock_backend().lock)
    except Exception:
        # Same defensive posture as unlock: the backend catches
        # FileNotFoundError/TimeoutExpired itself, but not e.g. an OSError
        # from a failing fork. The caller must not die of it.
        logger.exception("session lock raised for %s", user.username)
        ok, detail = False, "lock failed unexpectedly"

    _audit_session_lock_action(
        action="desktop_lock_session", user=user, client_host=client_host, ok=ok, detail=detail
    )
    if not ok:
        logger.warning("session lock failed for %s: %s", user.username, detail)
        return False, detail
    return True, detail
