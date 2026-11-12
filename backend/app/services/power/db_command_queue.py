"""
DB-backed command queue between Uvicorn workers — the shared mechanics.

Background
----------
Hardware-driving services initialise their backend only on the primary
Uvicorn worker (see ``core/lifespan.py``). A route handler that lands on a
secondary worker cannot mutate hardware state itself. It hands the operation
to the primary through a small table:

1. The secondary worker calls :meth:`DbCommandQueue.submit`: it inserts a row
   with ``status='pending'`` and a deadline, then polls until the row reaches
   a final state.
2. The primary worker's :meth:`DbCommandQueue.run_poll_loop` task picks up
   pending rows every ``poll_interval_s`` seconds, marks each ``running``,
   runs it through the queue's ``dispatch`` function and writes the result
   back to the row.

Row life cycle::

    pending ──claim──▶ running ──finish──▶ applied | failed
       │                  │
       │                  └─ primary stops mid-command ─▶ failed  "interrupted (…)"
       ├─ caller gives up ─────────────▶ failed  "timed out (caller gave up)"
       └─ deadline passed at claim ────▶ failed  "expired (…)"

Guarantees (#829):

- **Never claimed after its deadline.** A row carries the deadline of its
  caller (``expires_at``). The primary fails a pending row past its deadline
  instead of executing it — a caller that died mid-wait (deploy: every worker
  restarts at once) used to leave a row the next primary executed whenever
  it came up. The deadline is part of the claiming UPDATE itself, with the
  time taken immediately before it. Not covered: a command already
  ``running`` is not bounded (a dispatch that must not act late has to check
  for itself), and the deadline is wall-clock time, so a backward clock step
  extends it by the step.
- **At most once.** Claiming is a guarded ``pending → running`` update. A
  ``running`` row is never claimed again, also not after a primary crash.
- **The result on the row is the primary's.** A caller can only cancel a
  ``pending`` row, by the same kind of guarded update — of claim and cancel
  exactly one wins. If the caller's timeout fires while the command is
  ``running`` it waits ``running_grace_s`` longer and otherwise reports
  "outcome unknown"; it no longer writes ``failed`` over a command that is
  being applied. A caller that cannot read the database reports "unknown"
  too, never "timed out".
- **``running`` is not a resting state.** A primary that is stopped
  mid-command marks the row interrupted; the next poll loop does the same
  for rows a crashed primary left behind.
- **No session on the event loop.** Every database access of the async paths
  runs in a worker thread; each one opens its own session (#797).
- **Bounded table.** The poll loop deletes finished rows older than
  ``retention_s``, once at start and then every ``purge_interval_s``.

This module knows nothing about *what* is being commanded. A concrete queue
is one instance: a table (any ORM model with the columns listed at
:class:`DbCommandQueue`), a label for log lines, and a dispatch function.
``power/command_queue.py`` and ``power/gpu/command_queue.py`` are the two
instances; they used to be line-for-line copies of this code (#313).

DB sessions are deliberately short-lived (one session per operation) so a
route's request session is never held across the ``await asyncio.sleep``
waits — that would exhaust the pool under load.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


POLL_INTERVAL_S: float = 0.5
DEFAULT_TIMEOUT_S: float = 3.0
#: Extra wait for a command that is already executing when the timeout fires.
RUNNING_GRACE_S: float = 3.0
#: Finished rows are kept this long for inspection, then deleted.
RETENTION_S: float = 24 * 3600.0
PURGE_INTERVAL_S: float = 3600.0

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"

ERROR_EXPIRED = "expired (not picked up before its deadline)"
ERROR_CALLER_GAVE_UP = "timed out (caller gave up)"
ERROR_INTERRUPTED = "interrupted (primary stopped mid-command); outcome unknown"

# `_read_status()` result when the database could not be asked. Distinct from
# None ("no such row"): an unreadable status says nothing about the command.
_STATUS_UNREADABLE = "unreadable"

# Upper bound for rows one `claim_pending()` call skips (expired, or cancelled
# by their caller between our SELECT and UPDATE). Purely defensive — each
# skipped row has left 'pending', so the loop ends on its own.
_MAX_SKIPPED_PER_CLAIM = 200

#: ``(manager, command, payload) -> (success, error_message)``
Dispatch = Callable[[Any, str, dict[str, Any]], Awaitable[Tuple[bool, Optional[str]]]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns ``DateTime(timezone=True)`` values naive; they are UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class DbCommandQueue:
    """One cross-worker command queue on one table.

    Args:
        model: ORM model of the queue table. Required columns: ``id``,
            ``command``, ``payload_json``, ``requested_by``, ``requested_at``,
            ``status`` (``pending`` | ``running`` | ``applied`` | ``failed``),
            ``error_message``, ``completed_at``, ``expires_at``.
        label: Short name used in log lines (``"power"``, ``"gpu power"``).
        dispatch: Coroutine function that executes one command on the primary
            and returns ``(success, error_message)``. It may raise; that is
            recorded as a failed command.
        session_factory: Callable returning a new DB session; defaults to
            ``SessionLocal``.
        poll_interval_s: Sleep between polls, for the primary's loop and for
            a waiting caller alike.
        default_timeout_s: Deadline of a command whose caller gives no
            timeout — how long the caller waits and how long the row stays
            executable.
        running_grace_s: How much longer a caller waits when its timeout
            fires while the command is already executing.
        retention_s: Age (by ``requested_at``) after which a finished row is
            deleted.
        purge_interval_s: Time between two purges in the poll loop.
    """

    def __init__(
        self,
        model: Any,
        *,
        label: str,
        dispatch: Dispatch,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_interval_s: float = POLL_INTERVAL_S,
        default_timeout_s: float = DEFAULT_TIMEOUT_S,
        running_grace_s: float = RUNNING_GRACE_S,
        retention_s: float = RETENTION_S,
        purge_interval_s: float = PURGE_INTERVAL_S,
    ) -> None:
        self._model = model
        self._label = label
        self._dispatch = dispatch
        self._session_factory = session_factory
        self._poll_interval_s = poll_interval_s
        self._default_timeout_s = default_timeout_s
        self._running_grace_s = running_grace_s
        self._retention_s = retention_s
        self._purge_interval_s = purge_interval_s
        # Last claim failure that was logged; only the poll loop's claim
        # (one call at a time) touches it.
        self._logged_claim_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Caller side — used on secondary workers
    # ------------------------------------------------------------------

    async def submit(
        self,
        command: str,
        payload: Optional[dict[str, Any]] = None,
        requested_by: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Enqueue a command and wait for its result.

        One timeout for both halves: the row's deadline and the time this
        call waits. Returns ``(success, error_message)``.
        """
        if timeout_s is None:
            timeout_s = self._default_timeout_s
        command_id = await asyncio.to_thread(
            self.enqueue, command, payload, requested_by, timeout_s
        )
        if command_id is None:
            return False, "Failed to enqueue command"
        return await self.wait_for_completion(command_id, timeout_s=timeout_s)

    def enqueue(
        self,
        command: str,
        payload: Optional[dict[str, Any]] = None,
        requested_by: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Optional[int]:
        """Insert a pending command row that stays executable for *timeout_s*.

        Synchronous (opens a session) — from async code use :meth:`submit`.
        Returns the row id, or None if the DB write failed.
        """
        if timeout_s is None:
            timeout_s = self._default_timeout_s
        payload_json = json.dumps(payload) if payload is not None else None
        try:
            db = self._session_factory()
            try:
                row = self._model(
                    command=command,
                    payload_json=payload_json,
                    requested_by=requested_by or f"pid={os.getpid()}",
                    status=STATUS_PENDING,
                    expires_at=_utcnow() + timedelta(seconds=timeout_s),
                )
                db.add(row)
                # The id comes from the flush, before the commit: once the row
                # is committed it is executable, and a failing read after
                # that must not turn into "enqueue failed".
                db.flush()
                command_id = int(row.id)
                db.commit()
                return command_id
            except Exception as exc:
                db.rollback()
                logger.warning(f"Failed to enqueue {self._label} command '{command}': {exc}")
                return None
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Failed to open session for {self._label} command enqueue: {exc}")
            return None

    async def wait_for_completion(
        self,
        command_id: int,
        timeout_s: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Poll a command row until it is finished or the timeout fires.

        Returns ``(success, error_message)``. What a timeout means depends on
        how far the command got:

        - still ``pending``: the row is cancelled (marked failed), so the
          primary will not execute it afterwards;
        - already ``running``: it cannot be taken back. The call waits up to
          ``running_grace_s`` longer for the real result and then reports
          that the outcome is unknown — without touching the row;
        - not readable (database error on this side): no verdict either way.
          The call keeps trying until the end of the grace period and then
          reports the outcome as unknown. It never says "timed out" for a
          command it could not cancel.
        """
        if timeout_s is None:
            timeout_s = self._default_timeout_s
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        grace_deadline = deadline + self._running_grace_s
        waited = timeout_s + self._running_grace_s
        claimed = False  # the primary has (or had) the command
        while True:
            status, error = await asyncio.to_thread(self._read_status, command_id)
            if status == STATUS_APPLIED:
                return True, None
            if status == STATUS_FAILED:
                return False, error or "Command failed"
            if status is None:
                return False, "Command not found"
            if status == STATUS_RUNNING:
                claimed = True

            now = loop.time()
            if now >= deadline and not claimed:
                cancelled = await asyncio.to_thread(self._cancel_pending, command_id)
                if cancelled is True:
                    return False, f"Command timed out after {timeout_s:.1f}s"
                if cancelled is False:
                    # The row left 'pending' between the read and the cancel:
                    # the primary claimed or finished it. Read its real state.
                    claimed = True
                # None: the database cannot be asked — no verdict, try again.

            if now >= grace_deadline:
                if claimed:
                    return False, (
                        f"Command still running after {waited:.1f}s; outcome unknown"
                    )
                return False, (
                    f"Command outcome unknown after {waited:.1f}s: "
                    f"its state could not be read"
                )

            await asyncio.sleep(self._poll_interval_s)

    def _read_status(self, command_id: int) -> Tuple[Optional[str], Optional[str]]:
        """Open a short session, read status + error, close.

        Returns ``(status, error)``; ``(None, None)`` if the row does not
        exist, ``(_STATUS_UNREADABLE, None)`` if the database failed.
        """
        try:
            db = self._session_factory()
            try:
                row = db.query(self._model).filter(self._model.id == command_id).first()
                if row is None:
                    return None, None
                return row.status, row.error_message
            finally:
                db.close()
        except Exception as exc:
            logger.debug(f"Status read failed for {self._label} command {command_id}: {exc}")
            return _STATUS_UNREADABLE, None

    def _cancel_pending(self, command_id: int) -> Optional[bool]:
        """Fail a command its caller stopped waiting for — if it is still pending.

        Returns True if the row was cancelled, False if it was no longer
        pending (claimed or finished meanwhile), None if the database failed.
        """
        try:
            db = self._session_factory()
            try:
                cancelled = (
                    db.query(self._model)
                    .filter(
                        self._model.id == command_id,
                        self._model.status == STATUS_PENDING,
                    )
                    .update(
                        {
                            self._model.status: STATUS_FAILED,
                            self._model.error_message: ERROR_CALLER_GAVE_UP,
                            self._model.completed_at: _utcnow(),
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()
                return bool(cancelled)
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.debug(f"Cancel failed for {self._label} command {command_id}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Primary side — the poll loop
    # ------------------------------------------------------------------

    async def run_poll_loop(self, manager: Any) -> None:
        """Continuously process pending commands.

        Started by the primary worker only. Stops when the manager is no
        longer running (``manager._is_running`` flips to False). At start it
        fails the rows a previous primary left ``running``; it purges old
        finished rows at start and then every ``purge_interval_s``.
        """
        logger.info(f"{self._label} command-queue poll loop started")
        loop = asyncio.get_running_loop()
        next_purge = loop.time()
        try:
            # Only this loop executes commands, so a row that is 'running'
            # before the first claim belongs to a primary that is gone.
            await asyncio.to_thread(self.fail_interrupted)
            while manager._is_running:
                try:
                    if loop.time() >= next_purge:
                        # Advance first: a purge that raises must not be
                        # retried on every poll.
                        next_purge = loop.time() + self._purge_interval_s
                        await asyncio.to_thread(self.purge_finished)
                    processed = await self.process_one_pending(manager)
                    if not processed:
                        await asyncio.sleep(self._poll_interval_s)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        f"{self._label} command poll iteration failed: {exc}", exc_info=True
                    )
                    await asyncio.sleep(self._poll_interval_s)
        except asyncio.CancelledError:
            logger.info(f"{self._label} command-queue poll loop cancelled")
            raise

    async def process_one_pending(self, manager: Any) -> bool:
        """Claim the oldest executable command, dispatch it, write the result back.

        Returns True if a command was processed (the caller can poll again
        immediately), False if there was nothing to execute.
        """
        # Every database access opens its own session (connect / pool ping) —
        # keep them off the event loop; the claim runs every poll interval on
        # the primary (#797).
        pending = await asyncio.to_thread(self.claim_pending)
        if pending is None:
            return False

        command_id, command, payload_json = pending
        payload: dict[str, Any] = {}
        if payload_json:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                await asyncio.to_thread(
                    self.finish, command_id, success=False, error=f"invalid payload_json: {exc}"
                )
                return True

        try:
            success, error = await self._dispatch(manager, command, payload)
        except asyncio.CancelledError:
            # The primary is being stopped mid-command. Say so on the row —
            # synchronously: awaiting anything here could be cancelled again,
            # and a moment of blocking no longer matters at shutdown.
            self.finish(command_id, success=False, error=ERROR_INTERRUPTED)
            raise
        except Exception as exc:
            logger.exception(f"{self._label} command '{command}' (id={command_id}) raised")
            success = False
            error = f"unhandled exception: {exc}"

        await asyncio.to_thread(self.finish, command_id, success=success, error=error)
        return True

    def _is_expired(self, row: Any, now: datetime) -> bool:
        """Whether *row*'s caller has stopped waiting for it.

        Rows written before the ``expires_at`` column existed (or by an older
        process during a deploy) carry no deadline; they fall back to their
        age against the default timeout.
        """
        deadline = _as_utc(row.expires_at)
        if deadline is None:
            requested_at = _as_utc(row.requested_at)
            if requested_at is None:
                return False
            deadline = requested_at + timedelta(seconds=self._default_timeout_s)
        return now >= deadline

    def _still_executable(self, now: datetime) -> Any:
        """SQL condition: the row's deadline has not passed at *now*.

        The same rule as :meth:`_is_expired`, as part of the claiming UPDATE.
        """
        legacy_cutoff = now - timedelta(seconds=self._default_timeout_s)
        return or_(
            and_(self._model.expires_at.isnot(None), self._model.expires_at > now),
            and_(self._model.expires_at.is_(None), self._model.requested_at > legacy_cutoff),
        )

    def claim_pending(self) -> Optional[Tuple[int, str, Optional[str]]]:
        """Claim the oldest executable pending command.

        Marks it ``running`` and returns ``(id, command, payload_json)``, or
        None if nothing is executable. Pending rows past their deadline are
        failed on the way and never returned.

        The transition out of ``pending`` is a guarded UPDATE: a caller
        cancelling the row at the same moment and this claim cannot both win.
        The UPDATE that claims also carries the deadline, with the time taken
        right before it — a process that stalls between looking at the row
        and claiming it (suspend, SIGSTOP) does not claim an expired row.
        """
        try:
            db = self._session_factory()
            try:
                for _ in range(_MAX_SKIPPED_PER_CLAIM):
                    row = (
                        db.query(self._model)
                        .filter(self._model.status == STATUS_PENDING)
                        .order_by(self._model.requested_at.asc(), self._model.id.asc())
                        .first()
                    )
                    if row is None:
                        self._logged_claim_error = None
                        return None
                    command_id, command, payload_json = int(row.id), row.command, row.payload_json
                    expired = self._is_expired(row, _utcnow())
                    still_pending = and_(
                        self._model.id == command_id,
                        self._model.status == STATUS_PENDING,
                    )
                    now = _utcnow()
                    if expired:
                        won = (
                            db.query(self._model)
                            .filter(still_pending)
                            .update(
                                {
                                    self._model.status: STATUS_FAILED,
                                    self._model.error_message: ERROR_EXPIRED,
                                    self._model.completed_at: now,
                                },
                                synchronize_session=False,
                            )
                        )
                    else:
                        won = (
                            db.query(self._model)
                            .filter(still_pending, self._still_executable(now))
                            .update(
                                {self._model.status: STATUS_RUNNING},
                                synchronize_session=False,
                            )
                        )
                    db.commit()
                    if won and expired:
                        logger.warning(
                            f"{self._label} command '{command}' (id={command_id}) expired "
                            f"before it was picked up; not executed"
                        )
                    if won and not expired:
                        self._logged_claim_error = None
                        return command_id, command, payload_json
                    # Expired, cancelled by its caller first, or its deadline
                    # passed between the check and the claim (the next round
                    # fails it as expired): look at the queue again.
                self._logged_claim_error = None
                return None
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            # A claim that keeps failing means the queue is dead. Say so —
            # once per distinct error, not on every poll. Only the first
            # line: SQLAlchemy appends the statement and its parameters.
            summary = f"{type(exc).__name__}: {(str(exc).splitlines() or [''])[0][:200]}"
            if summary != self._logged_claim_error:
                self._logged_claim_error = summary
                logger.warning(
                    f"{self._label} command queue cannot claim commands "
                    f"(logged once until it changes or recovers): {summary}"
                )
            return None

    def fail_interrupted(self) -> int:
        """Fail every ``running`` row; call before the first claim of a loop.

        Such a row belongs to a primary that stopped or died mid-command.
        Whether the command took effect is not known, and the row says so.
        Returns the number of rows; 0 on a database failure.
        """
        try:
            db = self._session_factory()
            try:
                interrupted = (
                    db.query(self._model)
                    .filter(self._model.status == STATUS_RUNNING)
                    .update(
                        {
                            self._model.status: STATUS_FAILED,
                            self._model.error_message: ERROR_INTERRUPTED,
                            self._model.completed_at: _utcnow(),
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Could not check for interrupted {self._label} commands: {exc}")
            return 0
        if interrupted:
            logger.warning(
                f"{interrupted} {self._label} command(s) were left running by a previous "
                f"primary; marked as interrupted"
            )
        return int(interrupted)

    def finish(self, command_id: int, *, success: bool, error: Optional[str]) -> None:
        """Mark a command as applied or failed."""
        try:
            db = self._session_factory()
            try:
                row = db.query(self._model).filter(self._model.id == command_id).first()
                if row is None:
                    return
                row.status = STATUS_APPLIED if success else STATUS_FAILED
                row.error_message = None if success else (error or "unknown error")
                row.completed_at = _utcnow()
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning(f"Failed to finalise {self._label} command {command_id}: {exc}")
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Failed to open session for {self._label} command finalise: {exc}")

    def purge_finished(self) -> int:
        """Delete rows older than the retention that are no longer pending.

        Returns the number of deleted rows; 0 on a database failure. Old
        pending rows are left alone — the next claim fails them as expired,
        and a later purge removes them.
        """
        cutoff = _utcnow() - timedelta(seconds=self._retention_s)
        try:
            db = self._session_factory()
            try:
                removed = (
                    db.query(self._model)
                    .filter(
                        self._model.status != STATUS_PENDING,
                        self._model.requested_at < cutoff,
                    )
                    .delete(synchronize_session=False)
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Purging old {self._label} commands failed: {exc}")
            return 0
        if removed:
            logger.info(f"Purged {removed} finished {self._label} command(s)")
        return int(removed)
