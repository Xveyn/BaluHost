"""
Cross-worker command queue for GPU power management.

Mirrors ``app.services.power.command_queue`` (CPU manager) for the GPU
manager. Secondary Uvicorn workers cannot drive the GPU backend directly;
they enqueue ``gpu_power_commands`` rows and poll for completion. The
primary worker's poll loop dispatches the rows via the manager-internal
``_primary_*`` helpers.

Commands:
- ``set_config`` — payload is a serialized ``GpuPowerConfig``
- ``register_demand`` — payload: source, timeout_seconds, description
- ``unregister_demand`` — payload: source

State transitions stay inside the primary's ``_tick`` and are not
exposed via the queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Tuple

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerCommand
from app.schemas.gpu_power import GpuPowerConfig

if TYPE_CHECKING:  # pragma: no cover
    from app.services.power.gpu.manager import GpuPowerManagerService

logger = logging.getLogger(__name__)


POLL_INTERVAL_S: float = 0.5
DEFAULT_TIMEOUT_S: float = 3.0


# ---------------------------------------------------------------------------
# Public API — used by manager's follower path
# ---------------------------------------------------------------------------


def enqueue_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
) -> Optional[int]:
    """Insert a pending command row. Returns row id or None on DB error."""
    payload_json = json.dumps(payload) if payload is not None else None
    try:
        db = SessionLocal()
        try:
            row = GpuPowerCommand(
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
            logger.warning(f"Failed to enqueue gpu power command '{command}': {exc}")
            return None
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for gpu command enqueue: {exc}")
        return None


async def wait_for_completion(
    command_id: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Tuple[bool, Optional[str]]:
    """
    Poll a command row until it leaves the 'pending' state or times out.

    Each iteration uses a fresh ``SessionLocal()`` — never holds a session
    across ``asyncio.sleep``.
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
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerCommand).filter(GpuPowerCommand.id == command_id).first()
            if row is None:
                return None, None
            return row.status, row.error_message
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"GPU command status read failed for id={command_id}: {exc}")
        return None, None


def _mark_timed_out(command_id: int) -> None:
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerCommand).filter(GpuPowerCommand.id == command_id).first()
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
# Primary-worker poll loop
# ---------------------------------------------------------------------------


async def run_poll_loop(manager: "GpuPowerManagerService") -> None:
    """Continuously process pending GPU power commands. Started by primary only."""
    logger.info("gpu power command-queue poll loop started")
    try:
        while manager._is_running:
            try:
                processed = await _process_one_pending(manager)
                if not processed:
                    await asyncio.sleep(POLL_INTERVAL_S)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"gpu power command poll iteration failed: {exc}", exc_info=True)
                await asyncio.sleep(POLL_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("gpu power command-queue poll loop cancelled")
        raise


async def _process_one_pending(manager: "GpuPowerManagerService") -> bool:
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
        logger.exception(f"gpu power command '{command}' (id={command_id}) raised")
        success = False
        error = f"unhandled exception: {exc}"

    _finish(command_id, success=success, error=error)
    return True


def _claim_pending() -> Optional[Tuple[int, str, Optional[str]]]:
    try:
        db = SessionLocal()
        try:
            row = (
                db.query(GpuPowerCommand)
                .filter(GpuPowerCommand.status == "pending")
                .order_by(GpuPowerCommand.requested_at.asc(), GpuPowerCommand.id.asc())
                .first()
            )
            if row is None:
                return None
            return int(row.id), row.command, row.payload_json
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"gpu claim_pending failed: {exc}")
        return None


def _finish(command_id: int, *, success: bool, error: Optional[str]) -> None:
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerCommand).filter(GpuPowerCommand.id == command_id).first()
            if row is None:
                return
            row.status = "applied" if success else "failed"
            row.error_message = None if success else (error or "unknown error")
            row.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to finalise gpu command {command_id}: {exc}")
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for gpu command finalise: {exc}")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def _dispatch(
    manager: "GpuPowerManagerService",
    command: str,
    payload: dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    if command == "set_config":
        try:
            cfg = GpuPowerConfig(**payload)
        except Exception as exc:
            return False, f"invalid config payload: {exc}"
        return await manager._primary_set_config(cfg)

    if command == "register_demand":
        source = payload.get("source")
        if not source:
            return False, "missing 'source' in payload"
        timeout_seconds = payload.get("timeout_seconds")
        description = payload.get("description")
        try:
            await manager._primary_register_demand(
                source=source,
                timeout_seconds=timeout_seconds,
                description=description,
            )
            return True, None
        except Exception as exc:
            return False, str(exc)

    if command == "unregister_demand":
        source = payload.get("source")
        if not source:
            return False, "missing 'source' in payload"
        try:
            removed = await manager._primary_unregister_demand(source)
            if removed:
                return True, None
            return False, "no demand with that source"
        except Exception as exc:
            return False, str(exc)

    return False, f"unknown command: {command}"
