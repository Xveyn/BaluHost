"""
Cross-worker command queue for GPU power management.

Secondary Uvicorn workers cannot drive the GPU backend directly; they
enqueue ``gpu_power_commands`` rows and wait for completion. The primary
worker's poll loop dispatches the rows via the manager-internal
``_primary_*`` helpers. The queue mechanics live in
:mod:`app.services.power.db_command_queue`, shared with the CPU power
queue (``app.services.power.command_queue``); this module contributes the
table and the dispatch.

Commands:
- ``set_config`` — payload is a serialized ``GpuPowerConfig``
- ``register_demand`` — payload: source, timeout_seconds, description
- ``unregister_demand`` — payload: source

State transitions stay inside the primary's ``_tick`` and are not
exposed via the queue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Tuple

from app.models.gpu_power import GpuPowerCommand
from app.schemas.gpu_power import GpuPowerConfig
from app.services.power.db_command_queue import (
    DEFAULT_TIMEOUT_S,
    POLL_INTERVAL_S,
    DbCommandQueue,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.power.gpu.manager import GpuPowerManagerService

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "POLL_INTERVAL_S",
    "QUEUE",
    "enqueue_command",
    "run_poll_loop",
    "wait_for_completion",
]


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


QUEUE = DbCommandQueue(GpuPowerCommand, label="gpu power", dispatch=_dispatch)


# ---------------------------------------------------------------------------
# Public API — used by the manager's follower path
# ---------------------------------------------------------------------------


def enqueue_command(
    command: str,
    payload: Optional[dict[str, Any]] = None,
    requested_by: Optional[str] = None,
) -> Optional[int]:
    """Insert a pending command row. Returns the row id, or None on DB error."""
    return QUEUE.enqueue(command, payload=payload, requested_by=requested_by)


async def wait_for_completion(
    command_id: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Tuple[bool, Optional[str]]:
    """Wait until the command leaves 'pending' or the timeout fires.

    Returns ``(success, error_message)``.
    """
    return await QUEUE.wait_for_completion(command_id, timeout_s=timeout_s)


async def run_poll_loop(manager: "GpuPowerManagerService") -> None:
    """Process pending GPU power commands until the manager stops. Primary only."""
    await QUEUE.run_poll_loop(manager)
