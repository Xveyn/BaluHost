"""
DB-backed command queue between Uvicorn workers — the shared mechanics.

Background
----------
Hardware-driving services initialise their backend only on the primary
Uvicorn worker (see ``core/lifespan.py``). A route handler that lands on a
secondary worker cannot mutate hardware state itself. It hands the operation
to the primary through a small table:

1. The secondary worker calls :meth:`DbCommandQueue.enqueue` to insert a row
   with ``status='pending'`` and then polls
   :meth:`DbCommandQueue.wait_for_completion` until the row leaves that state.
2. The primary worker's :meth:`DbCommandQueue.run_poll_loop` task picks up
   pending rows every ``poll_interval_s`` seconds, runs them through the
   queue's ``dispatch`` function and writes the result back to the row.

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
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


POLL_INTERVAL_S: float = 0.5
DEFAULT_TIMEOUT_S: float = 3.0

#: ``(manager, command, payload) -> (success, error_message)``
Dispatch = Callable[[Any, str, dict[str, Any]], Awaitable[Tuple[bool, Optional[str]]]]


class DbCommandQueue:
    """One cross-worker command queue on one table.

    Args:
        model: ORM model of the queue table. Required columns: ``id``,
            ``command``, ``payload_json``, ``requested_by``, ``requested_at``,
            ``status`` (``pending`` | ``applied`` | ``failed``),
            ``error_message``, ``completed_at``.
        label: Short name used in log lines (``"power"``, ``"gpu power"``).
        dispatch: Coroutine function that executes one command on the primary
            and returns ``(success, error_message)``. It may raise; that is
            recorded as a failed command.
        session_factory: Callable returning a new DB session; defaults to
            ``SessionLocal``.
        poll_interval_s: Sleep between polls, for the primary's loop and for
            a waiting caller alike.
        default_timeout_s: How long :meth:`wait_for_completion` waits when
            the caller gives no timeout.
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
    ) -> None:
        self._model = model
        self._label = label
        self._dispatch = dispatch
        self._session_factory = session_factory
        self._poll_interval_s = poll_interval_s
        self._default_timeout_s = default_timeout_s

    # ------------------------------------------------------------------
    # Caller side — used on secondary workers
    # ------------------------------------------------------------------

    def enqueue(
        self,
        command: str,
        payload: Optional[dict[str, Any]] = None,
        requested_by: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a pending command row.

        Returns the row id, or None if the DB write failed.
        """
        payload_json = json.dumps(payload) if payload is not None else None
        try:
            db = self._session_factory()
            try:
                row = self._model(
                    command=command,
                    payload_json=payload_json,
                    requested_by=requested_by or f"pid={os.getpid()}",
                    status="pending",
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return int(row.id)
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
        """Poll a command row until it leaves 'pending' or the timeout fires.

        Each iteration opens a *fresh* DB session — never holds one across
        ``asyncio.sleep``. Returns ``(success, error_message)``. On timeout the
        row is marked failed so the primary does not execute it afterwards.
        """
        if timeout_s is None:
            timeout_s = self._default_timeout_s
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            status, error = self._read_status(command_id)
            if status == "applied":
                return True, None
            if status == "failed":
                return False, error or "Command failed"
            if status is None:
                return False, "Command not found"

            if loop.time() >= deadline:
                self._mark_timed_out(command_id)
                return False, f"Command timed out after {timeout_s:.1f}s"

            await asyncio.sleep(self._poll_interval_s)

    def _read_status(self, command_id: int) -> Tuple[Optional[str], Optional[str]]:
        """Open a short session, read status + error, close. Returns (status, error)."""
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
            return None, None

    def _mark_timed_out(self, command_id: int) -> None:
        """Best-effort: mark a stuck command as failed so the poller doesn't pick it up."""
        try:
            db = self._session_factory()
            try:
                row = db.query(self._model).filter(self._model.id == command_id).first()
                if row is None or row.status != "pending":
                    return
                row.status = "failed"
                row.error_message = "timed out (caller gave up)"
                row.completed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Primary side — the poll loop
    # ------------------------------------------------------------------

    async def run_poll_loop(self, manager: Any) -> None:
        """Continuously process pending commands.

        Started by the primary worker only. Stops when the manager is no
        longer running (``manager._is_running`` flips to False).
        """
        logger.info(f"{self._label} command-queue poll loop started")
        try:
            while manager._is_running:
                try:
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
        """Pick the oldest pending command, dispatch it, write the result back.

        Returns True if a command was processed (the caller can poll again
        immediately), False if the queue was empty.
        """
        # The SELECT opens its own session (connect / pool ping) — keep it off
        # the event loop; it runs every poll interval on the primary (#797).
        pending = await asyncio.to_thread(self.claim_pending)
        if pending is None:
            return False

        command_id, command, payload_json = pending
        payload: dict[str, Any] = {}
        if payload_json:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                self.finish(command_id, success=False, error=f"invalid payload_json: {exc}")
                return True

        try:
            success, error = await self._dispatch(manager, command, payload)
        except Exception as exc:
            logger.exception(f"{self._label} command '{command}' (id={command_id}) raised")
            success = False
            error = f"unhandled exception: {exc}"

        self.finish(command_id, success=success, error=error)
        return True

    def claim_pending(self) -> Optional[Tuple[int, str, Optional[str]]]:
        """Return ``(id, command, payload_json)`` of the oldest pending command, or None.

        NB: The row is not locked — only the primary worker runs the loop, so
        there is no contention.
        """
        try:
            db = self._session_factory()
            try:
                row = (
                    db.query(self._model)
                    .filter(self._model.status == "pending")
                    .order_by(self._model.requested_at.asc(), self._model.id.asc())
                    .first()
                )
                if row is None:
                    return None
                return int(row.id), row.command, row.payload_json
            finally:
                db.close()
        except Exception as exc:
            logger.debug(f"{self._label} claim_pending failed: {exc}")
            return None

    def finish(self, command_id: int, *, success: bool, error: Optional[str]) -> None:
        """Mark a command as applied or failed."""
        try:
            db = self._session_factory()
            try:
                row = db.query(self._model).filter(self._model.id == command_id).first()
                if row is None:
                    return
                row.status = "applied" if success else "failed"
                row.error_message = None if success else (error or "unknown error")
                row.completed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning(f"Failed to finalise {self._label} command {command_id}: {exc}")
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Failed to open session for {self._label} command finalise: {exc}")
