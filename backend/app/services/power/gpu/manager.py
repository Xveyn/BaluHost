"""GPU power management service.

Singleton, async, demand-aware. Mirrors PowerManagerService.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerLog
from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerDemandInfo,
    GpuPowerHistoryEntry,
    GpuPowerState,
    GpuPowerStatus,
)
from app.services.monitoring import shm
from app.services.monitoring.shm import read_shm
from app.services.power.gpu import command_queue
from app.services.power.gpu.config_store import (
    load_gpu_power_config,
    save_gpu_power_config,
)
from app.services.power.gpu.display_detector import get_active_display_count
from app.services.power.gpu.events import (
    emit_deep_idle_entering,
    emit_deep_idle_exiting,
)
from app.services.power.gpu.protocol import GpuPowerBackend
from app.services.power.gpu.runtime_state_store import (
    delete_demand,
    delete_expired_demands,
    list_active_demands,
    load_runtime_state,
    update_runtime_state,
    upsert_demand,
)

logger = logging.getLogger(__name__)


class GpuPowerManagerService:
    """Singleton; create via get_gpu_power_manager()."""

    _instance: Optional["GpuPowerManagerService"] = None
    _new_lock = Lock()

    def __new__(cls) -> "GpuPowerManagerService":
        with cls._new_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._backend: Optional[GpuPowerBackend] = None
        self._config: GpuPowerConfig = GpuPowerConfig()
        self._state: GpuPowerState = GpuPowerState.ACTIVE
        self._idle_since: datetime = datetime.now(timezone.utc)
        self._standby_since: Optional[datetime] = None
        self._last_transition: Optional[datetime] = None
        self._last_reason: Optional[str] = None
        # ``_demands`` is a primary-only cache; secondary workers read
        # from the ``gpu_power_demands`` DB table via list_active_demands().
        self._demands: Dict[str, GpuPowerDemandInfo] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._command_poll_task: Optional[asyncio.Task] = None
        self._is_running: bool = False
        self._primary: bool = True  # set in start()
        self._state_lock = asyncio.Lock()

    # ---- backend selection ----

    def _select_backend(self) -> GpuPowerBackend:
        from app.core.config import settings

        # Try AMD first, then NVIDIA, then dev
        try:
            from app.services.power.gpu.amd_backend import AmdGpuPowerBackend
            amd = AmdGpuPowerBackend()
            if amd.detected:
                return amd
        except Exception as exc:
            logger.debug("AMD GPU power backend init failed: %s", exc)

        try:
            from app.services.power.gpu.nvidia_backend import NvidiaGpuPowerBackend
            nv = NvidiaGpuPowerBackend()
            if nv.detected:
                return nv
        except Exception as exc:
            logger.debug("NVIDIA GPU power backend init failed: %s", exc)

        if getattr(settings, "is_dev_mode", False):
            from app.services.power.gpu.dev_backend import DevGpuPowerBackend
            logger.info("Using DevGpuPowerBackend (dev mode, no real GPU detected)")
            return DevGpuPowerBackend()

        # No-op backend (detected=False) — keeps API consistent
        from app.services.power.gpu.dev_backend import DevGpuPowerBackend
        backend = DevGpuPowerBackend()
        backend._has_permission = False  # signal upstream
        return backend

    # ---- lifecycle ----

    async def start(self, primary: bool = True) -> None:
        """
        Start the GPU power management service.

        Args:
            primary: When True, this worker owns the GPU backend, runs the
                monitor loop, and processes the command queue. When False,
                the worker hydrates state from the DB so reads work and
                routes mutations through the command queue.
        """
        if self._is_running:
            logger.warning("GpuPowerManagerService already running")
            return

        self._primary = primary
        self._hydrate_from_runtime_state()
        self._config = load_gpu_power_config()
        self._is_running = True

        if not primary:
            self._backend = None
            logger.info("GpuPowerManagerService started (follower mode)")
            return

        self._backend = self._select_backend()

        # Publish detection result synchronously so a follower handling a
        # request before the first monitor tick still gets a useful answer.
        try:
            has_write = await self._backend.has_write_permission() if self._backend else False
        except Exception:
            has_write = False
        update_runtime_state(
            current_state=self._state.value,
            detected=bool(self._backend.detected) if self._backend else False,
            vendor=self._backend.vendor if (self._backend and self._backend.detected) else None,
            has_write_permission=bool(has_write),
        )

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._command_poll_task = asyncio.create_task(command_queue.run_poll_loop(self))
        logger.info(
            "GpuPowerManagerService started (primary mode, vendor=%s, enabled=%s)",
            self._backend.vendor if self._backend else "none",
            self._config.enabled,
        )

    def _hydrate_from_runtime_state(self) -> None:
        """Load shared state from ``gpu_power_runtime_state`` into local fields."""
        state = load_runtime_state()
        try:
            self._state = GpuPowerState(state["current_state"])
        except (ValueError, KeyError):
            self._state = GpuPowerState.ACTIVE
        self._last_transition = state.get("last_transition")
        self._last_reason = state.get("last_reason")

    async def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        if self._command_poll_task:
            self._command_poll_task.cancel()
            try:
                await self._command_poll_task
            except asyncio.CancelledError:
                pass
            self._command_poll_task = None
        # Best-effort: return to ACTIVE so the next process boot starts clean
        if self._backend and self._backend.detected:
            try:
                await self._backend.apply_state(GpuPowerState.ACTIVE, self._config)
            except Exception as exc:
                logger.debug("Could not reset GPU to ACTIVE on shutdown: %s", exc)
        logger.info("GpuPowerManagerService stopped")

    # ---- monitor loop ----

    async def _monitor_loop(self) -> None:
        while self._is_running:
            try:
                # Refresh per-tick: config may have been updated by another
                # worker via PUT /api/gpu-power/config.
                self._config = load_gpu_power_config()
                # Refresh demand cache from DB so demands registered on
                # other workers are visible to the tick.
                self._refresh_demand_cache()
                await self._tick()
                self._write_status_shm()
            except Exception as exc:
                logger.error("GPU power monitor tick failed: %s", exc)
            await asyncio.sleep(self._config.monitor_interval_seconds)

    def _refresh_demand_cache(self) -> None:
        """Reload the in-memory demand cache from the DB (primary worker)."""
        try:
            self._demands = {d.source: d for d in list_active_demands()}
        except Exception as exc:
            logger.debug(f"GPU demand cache refresh failed: {exc}")

    def _write_status_shm(self) -> None:
        """SHM snapshot for read-only fields followers fall back to."""
        try:
            shm.write_shm(
                "gpu_status.json",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "display_count": None,  # filled below if backend present
                },
            )
        except Exception as exc:
            logger.debug(f"GPU status SHM write failed: {exc}")

    async def _tick(self) -> None:
        if not self._config.enabled or self._backend is None or not self._backend.detected:
            return

        await self._purge_expired_demands()

        displays = await self._get_displays()
        usage = await self._get_usage_percent()
        has_demand = bool(self._demands)
        is_idle = (
            displays == 0
            and usage < self._config.usage_threshold_percent
            and not has_demand
        )

        now = datetime.now(timezone.utc)
        if not is_idle:
            if self._state != GpuPowerState.ACTIVE:
                await self._transition(GpuPowerState.ACTIVE, "not_idle")
            self._idle_since = now
            self._standby_since = None
            return

        if self._state == GpuPowerState.ACTIVE:
            if now - self._idle_since >= timedelta(seconds=self._config.idle_window_seconds):
                await self._transition(GpuPowerState.STANDBY, "idle_window_elapsed")
                self._standby_since = now
        elif self._state == GpuPowerState.STANDBY:
            assert self._standby_since is not None
            if now - self._standby_since >= timedelta(seconds=self._config.deep_idle_extra_seconds):
                await emit_deep_idle_entering()
                if self._config.deep_idle_grace_seconds > 0:
                    await asyncio.sleep(self._config.deep_idle_grace_seconds)
                await self._transition(GpuPowerState.DEEP_IDLE, "grace_elapsed")
        # DEEP_IDLE → no further forward transitions; only wake-up via is_idle=False above

    # ---- inputs ----

    async def _get_displays(self) -> int:
        return await get_active_display_count()

    async def _get_usage_percent(self) -> float:
        from app.services.monitoring.shm import TELEMETRY_FILE

        # GPU sample lives in monitoring shm under telemetry payload "gpu" key.
        data = read_shm(TELEMETRY_FILE, max_age_seconds=30.0)
        if not data:
            return 0.0
        gpu = data.get("gpu") if isinstance(data, dict) else None
        if not gpu:
            return 0.0
        usage = gpu.get("usage_percent")
        return float(usage) if usage is not None else 0.0

    # ---- transitions ----

    async def _transition(self, target: GpuPowerState, reason: str) -> None:
        if self._state == target:
            return
        if self._backend is None:
            return
        previous = self._state
        ok, err = await self._backend.apply_state(target, self._config)
        if not ok:
            logger.warning(
                "GPU apply_state(%s) failed: %s",
                target.value, err,
            )
            return

        # Fire exiting hook on leaving DEEP_IDLE
        if previous == GpuPowerState.DEEP_IDLE:
            await emit_deep_idle_exiting()

        self._state = target
        self._last_transition = datetime.now(timezone.utc)
        self._last_reason = reason
        self._persist_log(target, previous, reason)
        update_runtime_state(
            current_state=target.value,
            last_transition=self._last_transition,
            last_reason=reason[:64] if reason else None,
        )
        logger.info("GPU power state: %s -> %s (%s)", previous.value, target.value, reason)

    def _persist_log(self, state: GpuPowerState, previous: GpuPowerState, reason: str) -> None:
        try:
            db = SessionLocal()
            try:
                row = GpuPowerLog(
                    timestamp=datetime.now(timezone.utc),
                    state=state.value,
                    previous_state=previous.value if previous else None,
                    reason=reason[:64],
                )
                db.add(row)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Could not persist GpuPowerLog: %s", exc)

    # ---- demands ----

    async def register_demand(
        self,
        source: str,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None,
    ) -> str:
        """
        Register a GPU power demand.

        Always writes to the shared ``gpu_power_demands`` table so any
        worker (and the primary's monitor loop) sees the demand. On the
        primary worker the in-memory cache is updated and the wake-up to
        ACTIVE is forced immediately. On followers the next monitor tick
        on the primary picks up the row (max ~5 s).
        """
        if self._primary:
            return await self._primary_register_demand(
                source=source,
                timeout_seconds=timeout_seconds,
                description=description,
            )

        cmd_id = command_queue.enqueue_command(
            "register_demand",
            payload={
                "source": source,
                "timeout_seconds": timeout_seconds,
                "description": description,
            },
        )
        if cmd_id is None:
            return source  # best-effort: row may already exist
        await command_queue.wait_for_completion(cmd_id)
        return source

    async def _primary_register_demand(
        self,
        source: str,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None,
    ) -> str:
        registered_at = datetime.now(timezone.utc)
        expires_at = (
            registered_at + timedelta(seconds=timeout_seconds)
            if timeout_seconds
            else None
        )
        upsert_demand(
            source=source,
            registered_at=registered_at,
            expires_at=expires_at,
            description=description,
        )
        async with self._state_lock:
            self._demands[source] = GpuPowerDemandInfo(
                source=source,
                registered_at=registered_at,
                expires_at=expires_at,
                description=description,
            )
            logger.info("GPU power demand registered: %s", source)

        if self._state != GpuPowerState.ACTIVE:
            await self._transition(GpuPowerState.ACTIVE, f"demand:{source}")
        return source

    async def unregister_demand(self, source: str) -> bool:
        if self._primary:
            return await self._primary_unregister_demand(source)

        cmd_id = command_queue.enqueue_command(
            "unregister_demand", payload={"source": source}
        )
        if cmd_id is None:
            return False
        success, _ = await command_queue.wait_for_completion(cmd_id)
        return success

    async def _primary_unregister_demand(self, source: str) -> bool:
        removed_db = delete_demand(source)
        async with self._state_lock:
            cached = self._demands.pop(source, None)
            if not removed_db and cached is None:
                return False
            logger.info("GPU power demand unregistered: %s", source)
        return True

    async def _purge_expired_demands(self) -> None:
        expired = delete_expired_demands()
        for demand in expired:
            self._demands.pop(demand.source, None)
            logger.info("GPU power demand expired: %s", demand.source)

    # ---- public read API ----

    async def get_status(self) -> GpuPowerStatus:
        if not self._primary:
            # Followers hydrate from the DB so they answer with the same
            # detected/vendor/has_write_permission as the primary.
            self._hydrate_from_runtime_state()
            self._config = load_gpu_power_config()
            shared = load_runtime_state()
            demands = list_active_demands()

            try:
                display_count = await self._get_displays()
            except Exception:
                display_count = 0
            try:
                usage = await self._get_usage_percent()
            except Exception:
                usage = None

            return GpuPowerStatus(
                enabled=self._config.enabled,
                detected=bool(shared.get("detected")),
                vendor=shared.get("vendor"),
                current_state=GpuPowerState(shared.get("current_state") or "active"),
                last_transition=shared.get("last_transition"),
                last_reason=shared.get("last_reason"),
                active_demands=demands,
                has_write_permission=bool(shared.get("has_write_permission")),
                estimated_power_watts=None,
                display_count=display_count,
                usage_percent=usage,
            )

        if self._backend is None:
            return GpuPowerStatus(
                enabled=self._config.enabled,
                detected=False,
                vendor=None,
                current_state=self._state,
                has_write_permission=False,
                active_demands=list(self._demands.values()),
            )
        return GpuPowerStatus(
            enabled=self._config.enabled,
            detected=self._backend.detected,
            vendor=self._backend.vendor if self._backend.detected else None,
            current_state=self._state,
            last_transition=self._last_transition,
            last_reason=self._last_reason,
            active_demands=list(self._demands.values()),
            has_write_permission=await self._backend.has_write_permission(),
            estimated_power_watts=None,
            display_count=await self._get_displays() if self._backend.detected else 0,
            usage_percent=await self._get_usage_percent() if self._backend.detected else None,
        )

    def get_config(self) -> GpuPowerConfig:
        return self._config

    async def set_config(self, config: GpuPowerConfig) -> Tuple[bool, Optional[str]]:
        if self._primary:
            return await self._primary_set_config(config)

        cmd_id = command_queue.enqueue_command(
            "set_config",
            payload=config.model_dump() if hasattr(config, "model_dump") else config.dict(),
        )
        if cmd_id is None:
            return False, "Failed to enqueue command"
        return await command_queue.wait_for_completion(cmd_id)

    async def _primary_set_config(self, config: GpuPowerConfig) -> Tuple[bool, Optional[str]]:
        async with self._state_lock:
            self._config = config
            save_gpu_power_config(config)
        logger.info("GPU power config updated (enabled=%s)", config.enabled)
        return True, None

    def get_capabilities(self) -> GpuPowerCapabilities:
        if self._backend is None:
            return GpuPowerCapabilities(vendor=None)
        return self._backend.capabilities()

    def get_history(self, limit: int = 100) -> Tuple[List[GpuPowerHistoryEntry], int]:
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import func as sa_func
                total = db.query(sa_func.count(GpuPowerLog.id)).scalar() or 0
                rows = (
                    db.query(GpuPowerLog)
                    .order_by(GpuPowerLog.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                entries = [
                    GpuPowerHistoryEntry(
                        timestamp=row.timestamp,
                        state=GpuPowerState(row.state),
                        previous_state=GpuPowerState(row.previous_state) if row.previous_state else None,
                        reason=row.reason,
                        source=row.source,
                        power_watts_at_transition=row.power_watts_at_transition,
                    )
                    for row in rows
                ]
                return entries, total
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not load gpu power history: %s", exc)
            return [], 0


# Module-level helpers
def get_gpu_power_manager() -> GpuPowerManagerService:
    return GpuPowerManagerService()


async def start_gpu_power_manager(primary: bool = True) -> None:
    """Start the GPU power management service.

    Args:
        primary: When True (default), this worker owns the GPU backend.
            Pass False on secondary Uvicorn workers — the manager runs
            in follower mode and routes mutations through the DB-backed
            command queue.
    """
    await get_gpu_power_manager().start(primary=primary)


async def stop_gpu_power_manager() -> None:
    await get_gpu_power_manager().stop()


def get_status() -> dict:
    """Service-status registry adapter."""
    mgr = get_gpu_power_manager()
    return {
        "is_running": mgr._is_running,
        "started_at": None,
        "uptime_seconds": None,
        "sample_count": 0,
        "error_count": 0,
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": float(mgr._config.monitor_interval_seconds),
        "current_state": mgr._state.value,
        "active_demands": len(mgr._demands),
        "enabled": mgr._config.enabled,
    }
