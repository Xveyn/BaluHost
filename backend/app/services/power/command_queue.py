"""
Cross-worker command queue for power management hardware operations.

Background
----------
``PowerManagerService`` initialises its CPU backend only on the primary
Uvicorn worker (see ``core/lifespan.py``). Any route handler that tries
to mutate hardware state from a secondary worker would hit
``self._backend is None`` and fail.

Secondary workers therefore enqueue a ``power_commands`` row and wait for
the primary worker's poll loop to execute it. The queue mechanics (enqueue,
claim, write the result back, caller timeout) live in
:mod:`app.services.power.db_command_queue`; this module contributes the
table and the translation of command rows into manager calls.

Commands: ``apply_profile`` | ``enable_dynamic_mode`` |
``disable_dynamic_mode`` | ``switch_backend``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Tuple

from app.models.power import PowerCommand
from app.schemas.power import DynamicModeConfig, PowerProfile
from app.services.power.db_command_queue import (
    DEFAULT_TIMEOUT_S,
    POLL_INTERVAL_S,
    DbCommandQueue,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.power.manager import PowerManagerService

__all__ = [
    "BACKEND_SWITCH_TIMEOUT_S",
    "DEFAULT_TIMEOUT_S",
    "POLL_INTERVAL_S",
    "QUEUE",
    "enqueue_command",
    "run_poll_loop",
    "submit_command",
    "wait_for_completion",
]

BACKEND_SWITCH_TIMEOUT_S: float = 10.0


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


QUEUE = DbCommandQueue(PowerCommand, label="power", dispatch=_dispatch)


# ---------------------------------------------------------------------------
# Public API — used by routes / manager fallback paths on secondary workers
# ---------------------------------------------------------------------------


async def submit_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Enqueue a command and wait for the primary's result.

    The way to hand a command over from async code: nothing here touches the
    database on the event loop, and one timeout (default
    ``DEFAULT_TIMEOUT_S``) governs both how long the row stays executable and
    how long this call waits. Returns ``(success, error_message)``.
    """
    return await QUEUE.submit(
        command, payload=payload, requested_by=requested_by, timeout_s=timeout_s
    )


def enqueue_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> Optional[int]:
    """Insert a pending command row that stays executable for *timeout_s*
    (default ``DEFAULT_TIMEOUT_S``).

    Synchronous — from async code use :func:`submit_command`.
    Returns the row id, or None on DB error.
    """
    return QUEUE.enqueue(
        command, payload=payload, requested_by=requested_by, timeout_s=timeout_s
    )


async def wait_for_completion(
    command_id: int,
    timeout_s: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Wait until the command is finished or the timeout fires.

    Returns ``(success, error_message)``. *timeout_s* must be the one the
    command was enqueued with; :func:`submit_command` keeps the two together.
    """
    return await QUEUE.wait_for_completion(command_id, timeout_s=timeout_s)


async def run_poll_loop(manager: "PowerManagerService") -> None:
    """Process pending power commands until the manager stops. Primary only."""
    await QUEUE.run_poll_loop(manager)
