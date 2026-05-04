"""
Cross-worker command queue for power management hardware operations.

Background
----------
``PowerManagerService`` initialises its CPU backend only on the primary
Uvicorn worker (see ``core/lifespan.py``). Any route handler that tries
to mutate hardware state from a secondary worker would hit
``self._backend is None`` and fail.

This module fills that gap with a small DB-backed queue:

1. Secondary workers call :func:`enqueue_command` to insert a
   ``power_commands`` row with ``status='pending'`` and then poll
   :func:`wait_for_completion` until the primary worker marks it done.
2. The primary worker's :func:`run_poll_loop` task picks up pending
   rows every ``POLL_INTERVAL_S`` seconds, dispatches them via the
   manager-internal helpers, and writes the result back to the row.

DB sessions are deliberately short-lived (one ``SessionLocal()`` per
poll iteration) so the route's request session is not held across the
``await asyncio.sleep`` waits — that would exhaust the pool under load.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Tuple

from app.core.database import SessionLocal
from app.models.power import PowerCommand
from app.schemas.power import DynamicModeConfig, PowerProfile

if TYPE_CHECKING:  # pragma: no cover
    from app.services.power.manager import PowerManagerService

logger = logging.getLogger(__name__)


POLL_INTERVAL_S: float = 0.5
DEFAULT_TIMEOUT_S: float = 3.0
BACKEND_SWITCH_TIMEOUT_S: float = 10.0


# ---------------------------------------------------------------------------
# Public API — used by routes / manager fallback paths on secondary workers
# ---------------------------------------------------------------------------


def enqueue_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
) -> Optional[int]:
    """
    Insert a pending command row.

    Returns the row id, or None if the DB write failed.
    """
    payload_json = json.dumps(payload) if payload is not None else None
    try:
        db = SessionLocal()
        try:
            row = PowerCommand(
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
            logger.warning(f"Failed to enqueue power command '{command}': {exc}")
            return None
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for command enqueue: {exc}")
        return None


async def wait_for_completion(
    command_id: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Tuple[bool, Optional[str]]:
    """
    Poll a command row until it leaves the 'pending' state or the timeout fires.

    Each iteration opens a *fresh* DB session — never holds one across
    ``asyncio.sleep``. Returns ``(success, error_message)``.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        status, error = _read_status(command_id)
        if status == "applied":
            return True, None
        if status == "failed":
            return False, error or "Command failed"
        if status is None:
            return False, "Command not found"

        if asyncio.get_event_loop().time() >= deadline:
            _mark_timed_out(command_id)
            return False, f"Command timed out after {timeout_s:.1f}s"

        await asyncio.sleep(POLL_INTERVAL_S)


def _read_status(command_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Open a short session, read status + error, close. Returns (status, error)."""
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerCommand).filter(PowerCommand.id == command_id).first()
            if row is None:
                return None, None
            return row.status, row.error_message
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"Status read failed for command {command_id}: {exc}")
        return None, None


def _mark_timed_out(command_id: int) -> None:
    """Best-effort: mark a stuck command as failed so the poller doesn't pick it up."""
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerCommand).filter(PowerCommand.id == command_id).first()
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


# ---------------------------------------------------------------------------
# Primary-worker poll loop — invoked from PowerManagerService.start()
# ---------------------------------------------------------------------------


async def run_poll_loop(manager: "PowerManagerService") -> None:
    """
    Continuously process pending power commands.

    Started by the primary worker only. Stops when the manager is no
    longer running (``manager._is_running`` flips to False).
    """
    logger.info("power command-queue poll loop started")
    try:
        while manager._is_running:
            try:
                processed = await _process_one_pending(manager)
                if not processed:
                    await asyncio.sleep(POLL_INTERVAL_S)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"power command poll iteration failed: {exc}", exc_info=True)
                await asyncio.sleep(POLL_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("power command-queue poll loop cancelled")
        raise


async def _process_one_pending(manager: "PowerManagerService") -> bool:
    """
    Pick the oldest pending command, dispatch it, and write the result back.

    Returns True if a command was processed (caller can poll again
    immediately), False if the queue was empty.
    """
    pending = _claim_pending()
    if pending is None:
        return False

    command_id, command, payload_json = pending
    payload: dict[str, Any] = {}
    if payload_json:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            _finish(command_id, success=False, error=f"invalid payload_json: {exc}")
            return True

    try:
        success, error = await _dispatch(manager, command, payload)
    except Exception as exc:
        logger.exception(f"power command '{command}' (id={command_id}) raised")
        success = False
        error = f"unhandled exception: {exc}"

    _finish(command_id, success=success, error=error)
    return True


def _claim_pending() -> Optional[Tuple[int, str, Optional[str]]]:
    """
    Return ``(id, command, payload_json)`` of the oldest pending command, or None.

    NB: We do not lock the row — only the primary worker runs this loop,
    so there is no contention.
    """
    try:
        db = SessionLocal()
        try:
            row = (
                db.query(PowerCommand)
                .filter(PowerCommand.status == "pending")
                .order_by(PowerCommand.requested_at.asc(), PowerCommand.id.asc())
                .first()
            )
            if row is None:
                return None
            return int(row.id), row.command, row.payload_json
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"claim_pending failed: {exc}")
        return None


def _finish(command_id: int, *, success: bool, error: Optional[str]) -> None:
    """Mark a command as applied or failed."""
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerCommand).filter(PowerCommand.id == command_id).first()
            if row is None:
                return
            row.status = "applied" if success else "failed"
            row.error_message = None if success else (error or "unknown error")
            row.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to finalise command {command_id}: {exc}")
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for command finalise: {exc}")


# ---------------------------------------------------------------------------
# Dispatch — translate command rows into manager-internal calls
# ---------------------------------------------------------------------------


async def _dispatch(
    manager: "PowerManagerService",
    command: str,
    payload: dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    if command == "apply_profile":
        try:
            profile = PowerProfile(payload["profile"])
        except (KeyError, ValueError) as exc:
            return False, f"invalid profile payload: {exc}"
        reason = payload.get("reason", "queued")
        duration = payload.get("duration_seconds")
        return await manager._primary_apply_profile(profile, reason=reason, duration_seconds=duration)

    if command == "enable_dynamic_mode":
        try:
            cfg = DynamicModeConfig(**payload)
        except Exception as exc:
            return False, f"invalid dynamic-mode payload: {exc}"
        return await manager._primary_enable_dynamic_mode(cfg)

    if command == "disable_dynamic_mode":
        return await manager._primary_disable_dynamic_mode()

    if command == "switch_backend":
        use_linux = bool(payload.get("use_linux_backend"))
        success, prev, new = await manager._primary_switch_backend(use_linux)
        if success:
            return True, None
        return False, f"backend switch failed (prev={prev}, target={new})"

    return False, f"unknown command: {command}"
