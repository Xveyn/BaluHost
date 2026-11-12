"""
Cross-worker command queue for manual sleep actions (#823).

Only the primary Uvicorn worker runs the sleep state machine
(``SleepManagerService`` started with ``monitoring=True``). A follower that
serves ``POST /api/system/sleep/{soft,wake,suspend}`` or an auto-wake must
not run a second, private state machine; it enqueues a ``sleep_commands`` row
and waits for the primary's poll loop to execute it. The queue mechanics live
in :mod:`app.services.power.db_command_queue`; this module contributes the
table, the timeouts and the dispatch into the primary's methods.

Commands (every payload carries ``issued_at``, the caller's UTC wall-clock
time as ISO string):

- ``soft`` — ``{"reason"}`` → ``enter_soft_sleep(reason, MANUAL)``
- ``wake`` — ``{"reason"}`` → ``exit_soft_sleep(reason)``
- ``suspend`` — ``{"reason", "wake_at"}`` → ``enter_true_suspend(reason,
  MANUAL, wake_at=...)``; ``wake_at`` is ``datetime.isoformat()`` or null

A state-machine refusal (the method returned False) is reported as
``(False, REFUSED)``, so the caller can tell it apart from a queue failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Tuple

from app.models.sleep import SleepCommand
from app.schemas.sleep import SleepTrigger
from app.services.power.db_command_queue import DbCommandQueue

if TYPE_CHECKING:  # pragma: no cover
    from app.services.power.sleep import SleepManagerService

__all__ = [
    "COMMAND_SOFT",
    "COMMAND_SUSPEND",
    "COMMAND_WAKE",
    "PICKUP_TIMEOUT_S",
    "QUEUE",
    "REFUSED",
    "RUNNING_GRACE_S",
    "STALE_AFTER_S",
    "issued_now",
    "run_poll_loop",
    "submit_command",
]

#: The primary must pick a command up within this time; otherwise the caller
#: cancels it (or the primary expires it at claim).
PICKUP_TIMEOUT_S: float = 5.0
#: Once a command is running, the caller waits this much longer for the real
#: result — waking spins disks up, which takes a while.
RUNNING_GRACE_S: float = 60.0
#: A command whose ``issued_at`` is older than this at dispatch is dropped.
STALE_AFTER_S: float = 15.0

#: Error text of a command the state machine refused (the method returned False).
REFUSED = "refused"

COMMAND_SOFT = "soft"
COMMAND_WAKE = "wake"
COMMAND_SUSPEND = "suspend"


def issued_now() -> str:
    """The ``issued_at`` value for a payload: UTC wall-clock time, ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _stale_error(issued_at: Any) -> Optional[str]:
    """Why a command issued at *issued_at* must not run now, or None if it may.

    The queue guarantees a command is never *claimed* after its deadline. A
    process frozen between claim and dispatch (a system suspend) would still
    execute it after resume — and a suspend executed hours late is the one
    thing that must not happen. So the dispatch checks the age itself.

    Wall clock on purpose: it jumps forward across a suspend; a monotonic
    clock would not, and the command would look fresh after resume.
    """
    if not isinstance(issued_at, str):
        return "stale command (issued at an unknown time); not executed"
    try:
        issued = datetime.fromisoformat(issued_at)
    except ValueError:
        return "stale command (issued at an unknown time); not executed"
    if issued.tzinfo is None:
        # Not what a caller writes (`issued_now()` is aware); refuse rather
        # than guess the zone.
        return "stale command (issued at an unknown time); not executed"
    age = (datetime.now(timezone.utc) - issued).total_seconds()
    if age > STALE_AFTER_S:
        return f"stale command (issued {age:.0f}s ago); not executed"
    return None


def _reason(payload: dict[str, Any]) -> Optional[str]:
    reason = payload.get("reason")
    return reason if isinstance(reason, str) and reason else None


async def _dispatch(
    manager: "SleepManagerService",
    command: str,
    payload: dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    stale = _stale_error(payload.get("issued_at"))
    if stale is not None:
        return False, stale

    if command not in (COMMAND_SOFT, COMMAND_WAKE, COMMAND_SUSPEND):
        return False, f"unknown command: {command}"

    reason = _reason(payload)
    if reason is None:
        return False, "missing 'reason' in payload"

    if command == COMMAND_SOFT:
        ok = await manager.enter_soft_sleep(reason, SleepTrigger.MANUAL)
    elif command == COMMAND_WAKE:
        ok = await manager.exit_soft_sleep(reason)
    else:
        raw_wake_at = payload.get("wake_at")
        wake_at: Optional[datetime] = None
        if raw_wake_at is not None:
            try:
                wake_at = datetime.fromisoformat(raw_wake_at)
            except (TypeError, ValueError) as exc:
                return False, f"invalid wake_at: {exc}"
        # Awaited to the end: on a real box this returns after resume.
        ok = await manager.enter_true_suspend(reason, SleepTrigger.MANUAL, wake_at=wake_at)

    return (True, None) if ok else (False, REFUSED)


QUEUE = DbCommandQueue(
    SleepCommand,
    label="sleep",
    dispatch=_dispatch,
    default_timeout_s=PICKUP_TIMEOUT_S,
    running_grace_s=RUNNING_GRACE_S,
)


async def submit_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Hand a sleep action to the primary and wait for its result.

    The primary has ``PICKUP_TIMEOUT_S`` to pick the command up and then up to
    ``RUNNING_GRACE_S`` more to finish it. Returns ``(success, error)``;
    ``error == REFUSED`` means the primary's state machine said no.
    """
    return await QUEUE.submit(command, payload=payload, requested_by=requested_by)


async def run_poll_loop(manager: "SleepManagerService") -> None:
    """Execute pending sleep commands until the manager stops. Primary only."""
    await QUEUE.run_poll_loop(manager)
