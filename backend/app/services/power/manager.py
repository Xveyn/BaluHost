"""
Power Management Service for CPU Frequency Scaling.

Manages CPU frequency profiles for optimal power consumption based on workload.
Supports AMD Ryzen (amd-pstate driver) and Intel (intel_pstate) CPUs.

Usage:
    from app.services.power.manager import get_power_manager

    manager = get_power_manager()
    await manager.apply_profile(PowerProfile.SURGE)
    status = await manager.get_power_status()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.power import PowerProfileLog
from app.schemas.power import (
    AutoScalingConfig,
    DynamicModeConfig,
    DynamicModeConfigResponse,
    PermissionStatus,
    PowerDemandInfo,
    PowerHistoryEntry,
    PowerProfile,
    PowerProfileConfig,
    PowerStatusResponse,
    ServiceIntensityResponse,
    ServicePowerProperty,
    PowerPresetSummary,
)

# Re-export extracted symbols for backward compatibility
from app.services.power.cpu_protocol import (
    CpuPowerBackend,
    DEFAULT_PROFILES,
    PROFILE_PRIORITY,
)
from app.services.power.cpu_dev_backend import DevCpuPowerBackend
from app.services.power.cpu_linux_backend import LinuxCpuPowerBackend
from app.services.power.config_store import (
    delete_demand,
    delete_expired_demands,
    list_active_demands,
    load_auto_scaling_config,
    load_dynamic_mode_config,
    load_runtime_state,
    persist_demand_log,
    persist_profile_change,
    save_auto_scaling_config,
    save_dynamic_mode_config,
    update_runtime_state,
    upsert_demand,
)
from app.services.power import command_queue
from app.services.monitoring import shm
from app.services.power.intensity import (
    get_service_intensities as _get_service_intensities,
)

logger = logging.getLogger(__name__)


class PowerManagerService:
    """
    Central service for managing CPU power profiles.

    Implements demand-based power scaling where multiple sources can
    register their power requirements. The highest demand wins.

    Singleton pattern - use get_power_manager() to get the instance.
    """

    _instance: Optional["PowerManagerService"] = None
    _lock = Lock()
    HOLD_FLOOR_MHZ = 400

    def __new__(cls) -> "PowerManagerService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # ``_demands`` is a primary-only cache; secondary workers must
        # call list_active_demands() to read fresh DB rows.
        self._demands: Dict[str, PowerDemandInfo] = {}
        self._current_profile = PowerProfile.IDLE
        self._current_property: Optional[ServicePowerProperty] = ServicePowerProperty.IDLE
        self._last_profile_change: Optional[datetime] = None
        self._history: List[PowerHistoryEntry] = []
        self._max_history = 1000
        self._auto_scaling_config = AutoScalingConfig()  # type: ignore[call-arg]
        self._cooldown_until: Optional[datetime] = None
        self._manual_override_until: Optional[datetime] = None
        self._cpu_usage_callback: Optional[Callable[[], Optional[float]]] = None
        self._backend: Optional[CpuPowerBackend] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._command_poll_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._primary: bool = True  # set in start()
        self._profiles = DEFAULT_PROFILES.copy()
        self._state_lock = asyncio.Lock()
        self._dynamic_mode_enabled: bool = False
        self._dynamic_mode_config: Optional[DynamicModeConfig] = None
        self._boost_max_override: Optional[int] = None  # per-rule SURGE cap (MHz); None = full boost
        self._last_drift: Optional[dict] = None          # {"at", "field", "expected", "found"}
        self._cap_unenforceable: bool = False
        self._in_drift: bool = False                      # within a drift episode (log-once guard)
        self._enforcement_task: Optional[asyncio.Task] = None
        self._watcher_absent_ticks: int = 0
        self._game_demand_active: bool = False

        logger.info("PowerManagerService initialized")

    async def enable_dynamic_mode(self, config: DynamicModeConfig) -> Tuple[bool, Optional[str]]:
        """
        Enable dynamic mode (kernel-governor scaling).

        On the primary worker this dispatches directly to the hardware path.
        On a secondary worker the call is enqueued via the command queue so
        the primary worker performs the actual change.
        """
        if self._primary:
            return await self._primary_enable_dynamic_mode(config)

        cmd_id = command_queue.enqueue_command(
            "enable_dynamic_mode",
            payload=config.model_dump() if hasattr(config, "model_dump") else config.dict(),
        )
        if cmd_id is None:
            return False, "Failed to enqueue command"
        return await command_queue.wait_for_completion(cmd_id)

    async def _primary_enable_dynamic_mode(self, config: DynamicModeConfig) -> Tuple[bool, Optional[str]]:
        """Primary-worker hardware path for ``enable_dynamic_mode``."""
        if self._backend is None:
            return False, "Power backend not initialized"

        # Validate governor
        available = await self._backend.get_available_governors()
        if available and config.governor not in available:
            return False, f"Governor '{config.governor}' not available (available: {', '.join(available)})"

        # Validate freq range
        if config.min_freq_mhz > config.max_freq_mhz:
            return False, "min_freq_mhz must be <= max_freq_mhz"

        # EPP mapping per governor
        epp_map = {
            "schedutil": "balance_performance",
            "conservative": "balance_power",
            "ondemand": "balance_performance",
            "powersave": "balance_power",
            "performance": "performance",
        }
        epp = epp_map.get(config.governor, "balance_performance")

        # Build synthetic profile config and apply
        synthetic = PowerProfileConfig(
            profile=PowerProfile.MEDIUM,  # placeholder
            governor=config.governor,
            energy_performance_preference=epp,
            min_freq_mhz=config.min_freq_mhz,
            max_freq_mhz=config.max_freq_mhz,
            description=f"Dynamic Mode: {config.governor} ({config.min_freq_mhz}-{config.max_freq_mhz} MHz)",
        )

        success, error = await self._backend.apply_profile(synthetic)
        if not success:
            return False, error

        async with self._state_lock:
            self._dynamic_mode_enabled = True
            self._dynamic_mode_config = config

        save_dynamic_mode_config(DynamicModeConfig(
            enabled=True,
            governor=config.governor,
            min_freq_mhz=config.min_freq_mhz,
            max_freq_mhz=config.max_freq_mhz,
        ))
        update_runtime_state(dynamic_mode_enabled=True)

        # Record in history
        freq = await self._backend.get_current_frequency_mhz()
        entry = PowerHistoryEntry(
            timestamp=datetime.now(timezone.utc),
            profile=self._current_profile,
            reason="dynamic_mode_enabled",
            source="admin",
            frequency_mhz=freq,
        )
        self._history.append(entry)

        logger.info(f"Dynamic mode enabled: {config.governor}, {config.min_freq_mhz}-{config.max_freq_mhz} MHz")
        return True, None

    async def disable_dynamic_mode(self) -> Tuple[bool, Optional[str]]:
        """Disable dynamic mode (routes through command queue on followers)."""
        if self._primary:
            return await self._primary_disable_dynamic_mode()

        cmd_id = command_queue.enqueue_command("disable_dynamic_mode")
        if cmd_id is None:
            return False, "Failed to enqueue command"
        return await command_queue.wait_for_completion(cmd_id)

    async def _primary_disable_dynamic_mode(self) -> Tuple[bool, Optional[str]]:
        async with self._state_lock:
            self._dynamic_mode_enabled = False
            self._dynamic_mode_config = None

        # Save disabled state
        saved_config = load_dynamic_mode_config()
        if saved_config:
            saved_config.enabled = False
            save_dynamic_mode_config(saved_config)
        update_runtime_state(dynamic_mode_enabled=False)

        # Recalculate and apply the appropriate profile
        async with self._state_lock:
            await self._recalculate_profile("dynamic_mode_disabled")

        logger.info("Dynamic mode disabled, returned to profile-based scaling")
        return True, None

    async def get_dynamic_mode_config(self) -> DynamicModeConfigResponse:
        """Get dynamic mode configuration and system capabilities.

        Capabilities (available governors + system frequency range) live on the
        backend, which only the primary worker owns. Followers have no backend,
        so they read the primary's SHM snapshot instead. Without this, a follower
        reports ``available_governors=[]``, which leaves the UI governor list
        empty and makes the PUT governor validation 400 on most requests under
        multi-worker deployments.
        """
        config = self._dynamic_mode_config or load_dynamic_mode_config() or DynamicModeConfig()  # type: ignore[call-arg]

        available_governors: List[str] = []
        sys_min, sys_max = 400, 4600
        if self._backend:
            available_governors = await self._backend.get_available_governors()
            sys_min, sys_max = await self._backend.get_system_freq_range()
        else:
            # Follower worker: source capabilities from the primary's snapshot.
            shm_status = None
            try:
                shm_status = shm.read_shm("power_status.json", max_age_seconds=15.0)
            except Exception:
                shm_status = None
            if shm_status:
                available_governors = shm_status.get("available_governors") or []
                sys_min = shm_status.get("system_min_freq_mhz") or sys_min
                sys_max = shm_status.get("system_max_freq_mhz") or sys_max

        return DynamicModeConfigResponse(
            config=config,
            available_governors=available_governors,
            system_min_freq_mhz=sys_min,
            system_max_freq_mhz=sys_max,
        )

    def _select_backend(self, force_linux: Optional[bool] = None) -> CpuPowerBackend:
        """
        Select appropriate backend based on environment and user preference.

        Args:
            force_linux: If True, try Linux backend even in dev mode.
                        If False, use dev backend.
                        If None, use default logic.
        """
        # Check if Linux backend is available (without creating instance)
        linux_available = LinuxCpuPowerBackend._is_available_static()

        # User explicitly requested Linux backend
        if force_linux is True:
            if linux_available:
                logger.info("Using LinuxCpuPowerBackend (user requested)")
                return LinuxCpuPowerBackend()
            else:
                logger.warning("Linux cpufreq not available, falling back to DevCpuPowerBackend")
                return DevCpuPowerBackend()

        # User explicitly requested dev backend
        if force_linux is False:
            logger.info("Using DevCpuPowerBackend (user requested)")
            return DevCpuPowerBackend()

        # Default logic: dev mode uses dev backend
        if settings.is_dev_mode:
            logger.info("Using DevCpuPowerBackend (dev mode default)")
            return DevCpuPowerBackend()

        # Check for force dev backend setting
        if hasattr(settings, 'power_force_dev_backend') and settings.power_force_dev_backend:
            logger.info("Using DevCpuPowerBackend (forced via config)")
            return DevCpuPowerBackend()

        # Try Linux backend
        if linux_available:
            logger.info("Using LinuxCpuPowerBackend (real hardware control)")
            return LinuxCpuPowerBackend()

        # Fallback to dev backend
        logger.warning("Linux cpufreq not available, falling back to DevCpuPowerBackend")
        return DevCpuPowerBackend()

    def is_linux_backend_available(self) -> bool:
        """Check if Linux cpufreq backend is available on this system."""
        return LinuxCpuPowerBackend._is_available_static()

    async def switch_backend(self, use_linux: bool) -> Tuple[bool, str, str]:
        """
        Switch between dev and Linux backends at runtime.

        On followers the command queue dispatches the change to the primary
        worker, which actually owns the backend instance.
        """
        if self._primary:
            return await self._primary_switch_backend(use_linux)

        previous_backend = (load_runtime_state().get("backend_kind") or "unknown").capitalize()
        cmd_id = command_queue.enqueue_command(
            "switch_backend", payload={"use_linux_backend": use_linux}
        )
        if cmd_id is None:
            return False, previous_backend, "unknown"
        success, _err = await command_queue.wait_for_completion(
            cmd_id, timeout_s=command_queue.BACKEND_SWITCH_TIMEOUT_S
        )
        if not success:
            return False, previous_backend, "unknown"
        new_backend = (load_runtime_state().get("backend_kind") or "unknown").capitalize()
        return True, previous_backend, new_backend

    async def _primary_switch_backend(self, use_linux: bool) -> Tuple[bool, str, str]:
        async with self._state_lock:
            # Determine previous backend name
            if self._backend is None:
                previous_backend = "None"
            elif isinstance(self._backend, LinuxCpuPowerBackend):
                previous_backend = "Linux"
            else:
                previous_backend = "Dev"

            # Select new backend
            new_backend = self._select_backend(force_linux=use_linux)
            new_backend_name = "Linux" if isinstance(new_backend, LinuxCpuPowerBackend) else "Dev"

            # If same backend type and backend exists, no change needed
            if self._backend is not None and type(new_backend) == type(self._backend):
                return True, previous_backend, new_backend_name

            self._backend = new_backend
            update_runtime_state(backend_kind=new_backend_name.lower())

            # Re-apply current profile to new backend
            config = self._profiles.get(self._current_profile)
            if config:
                success, _ = await self._backend.apply_profile(config)
                if not success:
                    logger.warning(f"Could not re-apply profile after backend switch")

            logger.info(f"Switched power backend: {previous_backend} -> {new_backend_name}")

            # Record in history
            try:
                freq = await self._backend.get_current_frequency_mhz()
                entry = PowerHistoryEntry(
                    timestamp=datetime.now(timezone.utc),
                    profile=self._current_profile,
                    reason=f"backend_switch:{new_backend_name.lower()}",
                    source="admin",
                    frequency_mhz=freq
                )
                self._history.append(entry)
            except Exception as e:
                logger.warning(f"Could not record backend switch in history: {e}")

            return True, previous_backend, new_backend_name

    async def start(self, primary: bool = True) -> None:
        """
        Start the power management service.

        Args:
            primary: When True, this worker owns the CPU backend, runs the
                monitor loop, and processes the command queue. When False,
                the worker only loads runtime state into local fields so
                read endpoints work, and routes hardware-mutating calls
                through the command queue.
        """
        if self._is_running:
            logger.warning("PowerManagerService already running")
            return

        self._primary = primary

        # Always load shared runtime state so secondary workers also have
        # something useful for in-process reads/fallbacks.
        self._hydrate_from_runtime_state()
        self._auto_scaling_config = load_auto_scaling_config()
        dynamic_config = load_dynamic_mode_config()

        self._is_running = True

        if not primary:
            self._backend = None
            logger.info("PowerManagerService started (follower mode)")
            return

        self._backend = self._select_backend()
        backend_kind = "linux" if isinstance(self._backend, LinuxCpuPowerBackend) else "dev"
        update_runtime_state(backend_kind=backend_kind)

        # Apply initial state: dynamic mode or IDLE profile
        if dynamic_config and dynamic_config.enabled:
            success, error = await self._primary_enable_dynamic_mode(dynamic_config)
            if not success:
                logger.warning(f"Failed to restore dynamic mode on start: {error}, falling back to IDLE")
                await self._primary_apply_profile(PowerProfile.IDLE, reason="service_start")
        else:
            await self._primary_apply_profile(PowerProfile.IDLE, reason="service_start")

        # Recalculate profile based on any demands registered before start()
        active_demands = list_active_demands()
        if active_demands:
            self._demands = {d.source: d for d in active_demands}
            logger.info(f"Applying {len(active_demands)} pre-existing demand(s) from DB")
            await self._recalculate_profile("service_start_catchup")

        # Start background monitor for demand expiration
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._enforcement_task = asyncio.create_task(self._enforcement_loop())
        # Start command queue poll loop for cross-worker mutations
        self._command_poll_task = asyncio.create_task(command_queue.run_poll_loop(self))
        logger.info("PowerManagerService started (primary mode)")

    def _hydrate_from_runtime_state(self) -> None:
        """Load shared mutable state from ``power_runtime_state`` into local fields."""
        state = load_runtime_state()
        try:
            self._current_profile = PowerProfile(state["current_profile"])
        except ValueError:
            self._current_profile = PowerProfile.IDLE
        prop = state.get("current_property")
        try:
            self._current_property = ServicePowerProperty(prop) if prop else ServicePowerProperty(self._current_profile.value)
        except ValueError:
            self._current_property = ServicePowerProperty.IDLE
        self._manual_override_until = state.get("manual_override_until")
        self._cooldown_until = state.get("cooldown_until")
        self._dynamic_mode_enabled = bool(state.get("dynamic_mode_enabled"))
        self._last_profile_change = state.get("last_profile_change")

    async def stop(self) -> None:
        """Stop the power management service."""
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

        if self._enforcement_task:
            self._enforcement_task.cancel()
            try:
                await self._enforcement_task
            except asyncio.CancelledError:
                pass
            self._enforcement_task = None

        if self._command_poll_task:
            self._command_poll_task.cancel()
            try:
                await self._command_poll_task
            except asyncio.CancelledError:
                pass
            self._command_poll_task = None

        logger.info("PowerManagerService stopped")

    async def _monitor_loop(self) -> None:
        """Background loop to handle demand expiration and auto-scaling."""
        while self._is_running:
            try:
                # Refresh per-tick: auto-scaling thresholds may have been
                # updated by another worker via PUT /api/power/auto-scaling.
                self._auto_scaling_config = load_auto_scaling_config()

                # Refresh demand cache from DB so demands registered on
                # other workers are visible to recalculation.
                self._refresh_demand_cache()

                await self._check_expired_demands()
                await self._check_auto_scaling()
                await self._write_status_shm()
            except Exception as e:
                logger.error(f"Error in power monitor loop: {e}")

            await asyncio.sleep(5)  # Check every 5 seconds

    def _refresh_demand_cache(self) -> None:
        """Reload the in-memory demand cache from the DB (primary worker only)."""
        try:
            self._demands = {d.source: d for d in list_active_demands()}
        except Exception as exc:
            logger.debug(f"Demand cache refresh failed: {exc}")

    async def _write_status_shm(self) -> None:
        """
        Write a snapshot of live status to shared memory so secondary workers
        can answer ``GET /api/power/status`` and ``GET /api/power/dynamic-mode``
        without holding their own backend.

        Followers have no backend, so the hardware capabilities (available
        governors + system frequency range) must be published here for them.
        """
        try:
            backend_kind = (
                "linux" if isinstance(self._backend, LinuxCpuPowerBackend) else "dev"
                if self._backend is not None else None
            )
            permission_status = None
            if isinstance(self._backend, LinuxCpuPowerBackend):
                perm_info = self._backend.get_permission_status()
                permission_status = {
                    "user": perm_info.get("user", "unknown"),
                    "groups": perm_info.get("groups", []),
                    "in_cpufreq_group": perm_info.get("in_cpufreq_group", False),
                    "sudo_available": perm_info.get("sudo_available", False),
                    "files": perm_info.get("files", {}),
                    "errors": perm_info.get("errors", []),
                    "has_write_access": self._backend.has_write_permission(),
                }
            available_governors: List[str] = []
            sys_min: Optional[int] = None
            sys_max: Optional[int] = None
            if self._backend is not None:
                available_governors = await self._backend.get_available_governors()
                sys_min, sys_max = await self._backend.get_system_freq_range()
            shm.write_shm(
                "power_status.json",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "backend_kind": backend_kind,
                    "linux_backend_available": LinuxCpuPowerBackend._is_available_static(),
                    "permission_status": permission_status,
                    "available_governors": available_governors,
                    "system_min_freq_mhz": sys_min,
                    "system_max_freq_mhz": sys_max,
                },
            )
        except Exception as exc:
            logger.debug(f"Power status SHM write failed: {exc}")

    async def _check_expired_demands(self) -> None:
        """Remove expired demands (DB-backed) and recalculate profile."""
        async with self._state_lock:
            expired = delete_expired_demands()

            if expired:
                for demand in expired:
                    logger.info(f"Power demand '{demand.source}' expired")
                    self._demands.pop(demand.source, None)

                await self._recalculate_profile("demand_expired")

                for demand in expired:
                    persist_demand_log(
                        action="expired",
                        source=demand.source,
                        level=demand.level.value,
                        description=demand.description,
                        resulting_profile=self._current_profile.value,
                    )

    async def _check_auto_scaling(self) -> None:
        """Auto-scale based on CPU usage if enabled."""
        if self._dynamic_mode_enabled:
            return

        if not self._auto_scaling_config.enabled:
            return

        if not self._auto_scaling_config.use_cpu_monitoring:
            return

        if self._manual_override_until and datetime.now(timezone.utc) < self._manual_override_until:
            return

        # Get CPU usage from callback
        if self._cpu_usage_callback is None:
            return

        cpu_usage = self._cpu_usage_callback()
        if cpu_usage is None:
            return

        # Determine target profile based on CPU usage
        if cpu_usage >= self._auto_scaling_config.cpu_surge_threshold:
            target = PowerProfile.SURGE
        elif cpu_usage >= self._auto_scaling_config.cpu_medium_threshold:
            target = PowerProfile.MEDIUM
        elif cpu_usage >= self._auto_scaling_config.cpu_low_threshold:
            target = PowerProfile.LOW
        else:
            target = PowerProfile.IDLE

        # Don't downgrade if cooldown active
        if PROFILE_PRIORITY[target] < PROFILE_PRIORITY[self._current_profile]:
            if self._cooldown_until and datetime.now(timezone.utc) < self._cooldown_until:
                return

        # Apply if different (but only if no higher demand registered)
        async with self._state_lock:
            highest_demand = self._get_highest_demand_profile()
            if PROFILE_PRIORITY[target] > PROFILE_PRIORITY[highest_demand]:
                await self._apply_profile_internal(target, "auto_scaling_cpu")

    def _get_highest_demand_profile(self) -> PowerProfile:
        """Get the highest priority demanded profile."""
        if not self._demands:
            return PowerProfile.IDLE

        highest = PowerProfile.IDLE
        for demand in self._demands.values():
            if PROFILE_PRIORITY[demand.level] > PROFILE_PRIORITY[highest]:
                highest = demand.level

        return highest

    async def _recalculate_profile(self, reason: str) -> None:
        """Recalculate and apply the appropriate profile based on demands."""
        target = self._get_highest_demand_profile()
        await self._apply_profile_internal(target, reason)

    async def _apply_profile_internal(
        self,
        profile: PowerProfile,
        reason: str,
        source: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Internal method to apply a profile. Returns (success, error_message)."""
        if self._backend is None:
            logger.warning("Power backend not yet initialized, skipping profile change")
            return False, "Power backend not initialized"

        # Skip profile changes while dynamic mode is active
        if self._dynamic_mode_enabled:
            logger.debug(f"Skipping profile change to {profile.value} - dynamic mode active")
            return True, None

        if profile == self._current_profile:
            return True, None

        # Try to get clock settings from active preset
        power_property = ServicePowerProperty(profile.value)
        config = await self._get_profile_config_from_preset(power_property)

        if config is None:
            # Fallback to default profiles
            config = self._profiles.get(profile)
            if not config:
                logger.error(f"Unknown profile: {profile}")
                return False, f"Unknown profile: {profile}"

        # Validate governor against available governors
        available_governors = await self._backend.get_available_governors()
        if available_governors and config.governor not in available_governors:
            fallback = "powersave" if "powersave" in available_governors else available_governors[0]
            logger.warning(
                f"Governor '{config.governor}' not available (available: {available_governors}). "
                f"Falling back to '{fallback}'"
            )
            config = PowerProfileConfig(
                profile=config.profile,
                governor=fallback,
                energy_performance_preference=config.energy_performance_preference,
                min_freq_mhz=config.min_freq_mhz,
                max_freq_mhz=config.max_freq_mhz,
                description=config.description,
            )

        # Apply to hardware
        success, error_msg = await self._backend.apply_profile(config)

        if success:
            old_profile = self._current_profile
            self._current_profile = profile
            self._current_property = power_property
            self._last_profile_change = datetime.now(timezone.utc)

            # Set cooldown for downgrades
            if PROFILE_PRIORITY[profile] < PROFILE_PRIORITY[old_profile]:
                self._cooldown_until = datetime.now(timezone.utc) + timedelta(
                    seconds=self._auto_scaling_config.cooldown_seconds
                )

            # Persist new state so other workers see the change
            update_runtime_state(
                current_profile=profile.value,
                current_property=power_property.value,
                last_profile_change=self._last_profile_change,
                cooldown_until=self._cooldown_until,
                manual_override_until=self._manual_override_until,
            )

            # Record history
            freq = await self._backend.get_current_frequency_mhz()
            entry = PowerHistoryEntry(
                timestamp=datetime.now(timezone.utc),
                profile=profile,
                reason=reason,
                source=source,
                frequency_mhz=freq
            )
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history.pop(0)

            logger.info(f"Profile changed: {old_profile.value} -> {profile.value} ({reason})")

            # Persist to DB
            persist_profile_change(
                profile=profile,
                previous_profile=old_profile,
                reason=reason,
                source=source,
                frequency_mhz=freq,
            )

            return True, None

        return False, error_msg

    async def _enforce_current_profile(self) -> None:
        """Re-assert the desired hardware state; correct + log external drift.

        Runs every enforcement tick (primary only). Does NOT change the logical
        profile or write profile-change history — it only keeps the hardware
        aligned with what the current profile demands.
        """
        if self._backend is None or self._dynamic_mode_enabled:
            return

        desired = await self._desired_config_for(self._current_profile)
        if desired is None:
            return

        found_gov, found_max = await self._backend.read_enforcement_state()
        gov_drift = found_gov is not None and found_gov != desired.governor
        max_drift = (
            desired.max_freq_mhz is not None
            and found_max is not None
            and found_max != desired.max_freq_mhz
        )

        if not gov_drift and not max_drift:
            self._cap_unenforceable = False
            self._in_drift = False
            return

        self._last_drift = {
            "at": datetime.now(timezone.utc).isoformat(),
            "field": "governor" if gov_drift else "max_freq",
            "expected": f"{desired.governor}/{desired.max_freq_mhz}",
            "found": f"{found_gov}/{found_max}",
        }
        # Keep re-asserting every tick (authority must win), but log only once
        # per drift episode so a persistent external override / kernel clamp
        # does not spam the log every 2 seconds.
        if not self._in_drift:
            logger.warning(
                "CPU cap drift detected (external override?): expected %s/%s, found %s/%s — re-asserting",
                desired.governor, desired.max_freq_mhz, found_gov, found_max,
            )
        self._in_drift = True

        success, error_msg = await self._backend.apply_profile(desired)

        if not success:
            # Write rejected outright (permission/I-O error) — cap is not enforceable.
            logger.warning("CPU cap re-assert failed (backend error): %s", error_msg)
            self._cap_unenforceable = True
            return

        # Write accepted — verify it actually stuck (kernel may silently clamp).
        vg, vm = await self._backend.read_enforcement_state()
        still_off = (vg is not None and vg != desired.governor) or (
            desired.max_freq_mhz is not None and vm is not None and vm != desired.max_freq_mhz
        )
        self._cap_unenforceable = bool(still_off)
        if still_off:
            logger.warning("CPU cap still not enforced after re-write (kernel clamp?)")

    def _authority_active(self) -> bool:
        """True when BaluHost should enforce the cap (external authority enabled)."""
        try:
            from app.services.power.config_store import load_authority_config
            return bool(load_authority_config().get("external_authority_enabled"))
        except Exception:
            return False

    def _active_boost_rules(self) -> list[dict]:
        """Return enabled boost rules from config_store, or [] if boost rules are disabled."""
        from app.services.power.config_store import load_authority_config, list_boost_rules
        if not load_authority_config().get("boost_rules_enabled", True):
            return []
        return list_boost_rules(enabled_only=True)

    async def _watch_tick(self) -> None:
        """One enforcement tick: check running processes against boost rules and update game-session demand."""
        from app.services.power import process_watcher
        rules = self._active_boost_rules()
        if not rules:
            if self._game_demand_active:
                await self.unregister_demand("game-session")
                self._game_demand_active = False
                self._boost_max_override = None
            self._watcher_absent_ticks = 0
            return

        procs = process_watcher.snapshot_processes()
        hit, target = process_watcher.match_boost_rules(procs, rules)

        if hit:
            self._watcher_absent_ticks = 0
            if not self._game_demand_active or self._boost_max_override != target:
                self._boost_max_override = target
                await self.register_demand(
                    "game-session", PowerProfile.SURGE,
                    max_freq_override=target, description="Boost-Allowlist",
                )
                self._game_demand_active = True
        elif self._game_demand_active:
            self._watcher_absent_ticks += 1
            if self._watcher_absent_ticks >= 2:
                await self.unregister_demand("game-session")
                self._game_demand_active = False
                self._boost_max_override = None
                self._watcher_absent_ticks = 0

    async def _enforcement_loop(self) -> None:
        """2-second primary-only loop: enforce cap + watch for boost processes."""
        while self._is_running:
            try:
                if self._primary and self._authority_active():
                    await self._watch_tick()
                    await self._enforce_current_profile()
            except Exception as e:
                logger.error(f"Error in enforcement loop: {e}")
            await asyncio.sleep(2)

    async def _get_profile_config_from_preset(
        self,
        power_property: ServicePowerProperty
    ) -> Optional[PowerProfileConfig]:
        """
        Get profile config based on active preset and power property.

        Args:
            power_property: The service power property to get config for.

        Returns:
            PowerProfileConfig with clock settings from preset, or None if no preset active.
        """
        try:
            from app.services.power.presets import get_preset_service

            preset_service = get_preset_service()
            preset = await preset_service.get_active_preset()

            if preset is None:
                return None

            # Get clock speed from preset
            target_clock = preset_service.get_clock_for_property(preset, power_property)

            # Calculate min/max frequency (±15% range for better responsiveness)
            min_freq = int(target_clock * 0.85)
            max_freq = target_clock

            # Get governor based on power property
            governor = preset_service.get_governor_for_property(power_property)
            epp = preset_service.get_epp_for_property(power_property)

            # For SURGE, allow full boost (no max limit)
            if power_property == ServicePowerProperty.SURGE:
                max_freq = None
                min_freq = int(target_clock * 0.8)  # Just set a high minimum

            config = PowerProfileConfig(
                profile=PowerProfile(power_property.value),
                governor=governor,
                energy_performance_preference=epp,
                min_freq_mhz=min_freq,
                max_freq_mhz=max_freq,
                description=f"Preset: {preset.name}, Property: {power_property.value}"
            )

            logger.debug(f"Config from preset '{preset.name}': {power_property.value} -> {target_clock} MHz")
            return config

        except Exception as e:
            logger.warning(f"Error getting preset config: {e}, falling back to defaults")
            return None

    async def _desired_config_for(self, profile: PowerProfile) -> Optional[PowerProfileConfig]:
        """Build the config that *should* be enforced for ``profile``.

        - Hold profiles (idle/low/medium): cap floored to HOLD_FLOOR_MHZ.
        - SURGE: if a per-rule boost override is set, use it as scaling_max;
          otherwise keep full boost (max_freq_mhz=None).
        Falls back to the static default profile when no preset is active.
        """
        power_property = ServicePowerProperty(profile.value)
        config = await self._get_profile_config_from_preset(power_property)
        if config is None:
            config = self._profiles.get(profile)
            if config is None:
                return None

        if profile == PowerProfile.SURGE:
            max_freq = self._boost_max_override  # None = full boost
            min_freq = config.min_freq_mhz
        else:
            floored = max(config.max_freq_mhz or self.HOLD_FLOOR_MHZ, self.HOLD_FLOOR_MHZ)
            max_freq = floored
            min_freq = int(floored * 0.85)

        return PowerProfileConfig(
            profile=config.profile,
            governor=config.governor,
            energy_performance_preference=config.energy_performance_preference,
            min_freq_mhz=min_freq,
            max_freq_mhz=max_freq,
            description=config.description,
        )

    async def apply_profile(
        self,
        profile: PowerProfile,
        reason: str = "manual",
        duration_seconds: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Manually apply a power profile.

        On followers the call is enqueued via the command queue so the
        primary worker performs the hardware change. The early-return on
        ``profile == self._current_profile`` is intentionally evaluated on
        the primary side only — secondary workers may have a stale local
        cache. This is what eliminated the duplicate Surge-log symptom.
        """
        if self._primary:
            return await self._primary_apply_profile(profile, reason=reason, duration_seconds=duration_seconds)

        cmd_id = command_queue.enqueue_command(
            "apply_profile",
            payload={
                "profile": profile.value,
                "reason": reason,
                "duration_seconds": duration_seconds,
            },
        )
        if cmd_id is None:
            return False, "Failed to enqueue command"
        return await command_queue.wait_for_completion(cmd_id)

    async def _primary_apply_profile(
        self,
        profile: PowerProfile,
        reason: str = "manual",
        duration_seconds: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Primary-worker hardware path for ``apply_profile``."""
        async with self._state_lock:
            if duration_seconds:
                self._manual_override_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            else:
                self._manual_override_until = None

            return await self._apply_profile_internal(profile, reason, "manual")

    async def register_demand(
        self,
        source: str,
        level: PowerProfile,
        power_property: Optional[ServicePowerProperty] = None,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None,
        max_freq_override: Optional[int] = None,
    ) -> str:
        """
        Register a power demand from a source.

        Writes to the shared ``power_demands`` table so any worker (and the
        primary's monitor loop) can see the demand. On the primary worker
        the in-memory cache is updated and the profile recalculated
        immediately; on followers the next monitor tick on the primary
        picks up the new row.
        """
        registered_at = datetime.now(timezone.utc)
        expires_at = None
        if timeout_seconds:
            expires_at = registered_at + timedelta(seconds=timeout_seconds)
        if power_property is None:
            power_property = ServicePowerProperty(level.value)

        demand = PowerDemandInfo(
            source=source,
            level=level,
            power_property=power_property,
            registered_at=registered_at,
            expires_at=expires_at,
            description=description,
        )

        # The override only feeds _desired_config_for / enforcement, which run
        # on the primary worker only. Setting it on a follower would leave
        # stale in-memory state on a singleton that never enforces.
        if self._primary and (max_freq_override is not None or level == PowerProfile.SURGE):
            self._boost_max_override = max_freq_override

        upsert_demand(
            source=source,
            level=level,
            power_property=power_property,
            registered_at=registered_at,
            expires_at=expires_at,
            description=description,
        )

        async with self._state_lock:
            self._demands[source] = demand
            logger.info(f"Registered power demand: {source} -> {level.value} (property: {power_property.value})")

            if self._primary:
                await self._recalculate_profile(f"demand_registered:{source}")

            persist_demand_log(
                action="registered",
                source=source,
                level=level.value,
                description=description,
                timeout_seconds=timeout_seconds,
                resulting_profile=self._current_profile.value,
            )

        return source

    async def unregister_demand(self, source: str) -> bool:
        """
        Remove a power demand from the shared DB and the local cache.

        Returns True if a row was actually removed, False if the source was
        not registered. Followers do not trigger recalculation locally; the
        primary worker's monitor loop will pick up the change on the next
        tick.
        """
        async with self._state_lock:
            removed_db = delete_demand(source)
            cached = self._demands.pop(source, None)

            if not removed_db and cached is None:
                return False

            logger.info(f"Unregistered power demand: {source}")

            if self._primary:
                await self._recalculate_profile(f"demand_unregistered:{source}")

            level_value = cached.level.value if cached is not None else "unknown"
            description = cached.description if cached is not None else None
            persist_demand_log(
                action="unregistered",
                source=source,
                level=level_value,
                description=description,
                resulting_profile=self._current_profile.value,
            )

        return True

    async def get_power_status(self) -> PowerStatusResponse:
        """Get current power status (read-only, safe on follower workers)."""
        # Hydrate from shared state so a follower returns the same answer
        # as the primary, regardless of which worker handles the request.
        if not self._primary:
            self._hydrate_from_runtime_state()
            self._auto_scaling_config = load_auto_scaling_config()
            self._demands = {d.source: d for d in list_active_demands()}

        freq = None
        if self._backend:
            freq = await self._backend.get_current_frequency_mhz()

        desired = await self._desired_config_for(self._current_profile)
        freq_range = None
        if desired and desired.min_freq_mhz and desired.max_freq_mhz:
            freq_range = f"{desired.min_freq_mhz}-{desired.max_freq_mhz} MHz"
        elif self._current_profile == PowerProfile.SURGE:
            freq_range = "Full boost"

        cooldown_remaining = None
        if self._cooldown_until:
            remaining = (self._cooldown_until - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                cooldown_remaining = int(remaining)

        # Read backend metadata: prefer local on primary, fall back to SHM
        # snapshot on followers (written by the primary's monitor loop).
        shm_status = None
        if not self._primary:
            try:
                shm_status = shm.read_shm("power_status.json", max_age_seconds=15.0)
            except Exception:
                shm_status = None

        is_linux = isinstance(self._backend, LinuxCpuPowerBackend)
        if not self._primary and shm_status:
            is_linux = shm_status.get("backend_kind") == "linux"
        linux_available = self.is_linux_backend_available()
        if not self._primary and shm_status and "linux_backend_available" in shm_status:
            linux_available = bool(shm_status["linux_backend_available"])

        # Get permission status for Linux backend
        permission_status = None
        if isinstance(self._backend, LinuxCpuPowerBackend):
            perm_info = self._backend.get_permission_status()
            permission_status = PermissionStatus(
                user=perm_info.get("user", "unknown"),
                groups=perm_info.get("groups", []),
                in_cpufreq_group=perm_info.get("in_cpufreq_group", False),
                sudo_available=perm_info.get("sudo_available", False),
                files=perm_info.get("files", {}),
                errors=perm_info.get("errors", []),
                has_write_access=self._backend.has_write_permission()
            )
        elif not self._primary and shm_status and shm_status.get("permission_status"):
            ps = shm_status["permission_status"]
            permission_status = PermissionStatus(
                user=ps.get("user", "unknown"),
                groups=ps.get("groups", []),
                in_cpufreq_group=ps.get("in_cpufreq_group", False),
                sudo_available=ps.get("sudo_available", False),
                files=ps.get("files", {}),
                errors=ps.get("errors", []),
                has_write_access=ps.get("has_write_access", False),
            )

        # Get active preset info
        active_preset = None
        try:
            from app.services.power.presets import get_preset_service
            preset_service = get_preset_service()
            preset = await preset_service.get_active_preset()
            if preset:
                active_preset = PowerPresetSummary(
                    id=preset.id,
                    name=preset.name,
                    is_system_preset=preset.is_system_preset,
                    is_active=preset.is_active
                )
                # Update freq_range based on preset
                if self._current_property:
                    target_clock = preset_service.get_clock_for_property(preset, self._current_property)
                    if self._current_property == ServicePowerProperty.SURGE:
                        freq_range = f"Full boost ({target_clock} MHz+)"
                    else:
                        min_clock = int(target_clock * 0.85)
                        freq_range = f"{min_clock}-{target_clock} MHz"
        except Exception as e:
            logger.debug(f"Could not get active preset: {e}")

        # Override display when dynamic mode is active
        if self._dynamic_mode_enabled and self._dynamic_mode_config:
            dm = self._dynamic_mode_config
            freq_range = f"{dm.min_freq_mhz}-{dm.max_freq_mhz} MHz"

        is_dev_mode = isinstance(self._backend, DevCpuPowerBackend)
        if not self._primary and shm_status:
            is_dev_mode = shm_status.get("backend_kind") == "dev"

        return PowerStatusResponse(
            current_profile=self._current_profile,
            current_property=self._current_property,
            current_frequency_mhz=freq,
            target_frequency_range=freq_range,
            active_demands=list(self._demands.values()),
            auto_scaling_enabled=self._auto_scaling_config.enabled,
            is_dev_mode=is_dev_mode,
            is_using_linux_backend=is_linux,
            linux_backend_available=linux_available,
            can_switch_backend=linux_available or is_linux,
            permission_status=permission_status,
            last_profile_change=self._last_profile_change,
            cooldown_remaining_seconds=cooldown_remaining,
            active_preset=active_preset,
            dynamic_mode_enabled=self._dynamic_mode_enabled,
            dynamic_mode_config=self._dynamic_mode_config,
        )

    def get_profiles(self) -> Dict[PowerProfile, PowerProfileConfig]:
        """Get all configured profiles."""
        return self._profiles.copy()

    def get_history(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[PowerHistoryEntry], int]:
        """
        Get profile change history from DB (with in-memory fallback).

        Args:
            limit: Maximum entries to return
            offset: Offset for pagination

        Returns:
            Tuple of (entries, total_count)
        """
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import func as sa_func
                total = db.query(sa_func.count(PowerProfileLog.id)).scalar() or 0

                rows = (
                    db.query(PowerProfileLog)
                    .order_by(PowerProfileLog.timestamp.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

                entries = [
                    PowerHistoryEntry(
                        timestamp=row.timestamp,
                        profile=PowerProfile(row.profile),
                        reason=row.reason,
                        source=row.source,
                        frequency_mhz=row.frequency_mhz,
                    )
                    for row in rows
                ]
                return entries, total
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to read history from DB, falling back to in-memory: {e}")
            total = len(self._history)
            entries = list(reversed(self._history))[offset:offset + limit]
            return entries, total

    def get_active_demands(self) -> List[PowerDemandInfo]:
        """Get all active power demands (DB-backed, fresh on every call)."""
        return list_active_demands()

    async def get_service_intensities(self) -> ServiceIntensityResponse:
        """
        Get intensity information for all tracked services and processes.

        Delegates to the intensity module.
        """
        demands = {d.source: d for d in list_active_demands()}
        return await _get_service_intensities(demands, self._current_profile)

    def set_cpu_usage_callback(self, callback: Callable[[], Optional[float]]) -> None:
        """Set callback to get current CPU usage for auto-scaling."""
        self._cpu_usage_callback = callback

    def get_auto_scaling_config(self) -> AutoScalingConfig:
        """Get current auto-scaling configuration."""
        return self._auto_scaling_config

    def set_auto_scaling_config(self, config: AutoScalingConfig) -> None:
        """Update auto-scaling configuration and save to database."""
        self._auto_scaling_config = config
        save_auto_scaling_config(config)
        logger.info(f"Auto-scaling config updated: enabled={config.enabled}")


# Singleton instance
_power_manager: Optional[PowerManagerService] = None


def get_power_manager() -> PowerManagerService:
    """Get the singleton PowerManagerService instance."""
    global _power_manager
    if _power_manager is None:
        _power_manager = PowerManagerService()
    return _power_manager


async def start_power_manager(primary: bool = True) -> None:
    """Start the power management service.

    Args:
        primary: When True (default), this worker owns the CPU backend.
            Pass False on secondary Uvicorn workers — the manager will
            run in follower mode and route hardware mutations through
            the DB-backed command queue.
    """
    manager = get_power_manager()
    await manager.start(primary=primary)


async def stop_power_manager() -> None:
    """Stop the power management service."""
    manager = get_power_manager()
    await manager.stop()


async def check_and_notify_permissions() -> None:
    """
    Check power management permissions and create notification if limited.
    Called once during server startup.
    """
    manager = get_power_manager()

    # Only for Linux backend
    if not isinstance(manager._backend, LinuxCpuPowerBackend):
        return

    # Skip if we have write permission
    if manager._backend.has_write_permission():
        return

    # Create notification for admins
    try:
        from app.core.database import SessionLocal
        from app.services.notifications.service import get_notification_service

        db = SessionLocal()
        try:
            notification_service = get_notification_service()
            await notification_service.create(
                db=db,
                user_id=None,  # System-wide for all admins
                category="system",
                notification_type="warning",
                title="CPU Power Management: Eingeschränkte Berechtigungen",
                message=(
                    "Der Server hat keinen Schreibzugriff auf CPU-Frequenzeinstellungen. "
                    "Starten Sie den Server mit 'sudo' oder fügen Sie den Benutzer zur 'cpufreq'-Gruppe hinzu."
                ),
                action_url="/system-control",
                priority=1,
            )
            logger.warning("Created startup notification: power management permissions limited")
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not create power permission notification: {e}")


def get_status() -> dict:
    """
    Get power manager service status.

    Returns:
        Dict with service status information for admin dashboard
    """
    manager = get_power_manager()

    is_running = manager._is_running and manager._monitor_task is not None

    started_at = None
    uptime_seconds = None
    if manager._last_profile_change is not None:
        started_at = manager._last_profile_change
        uptime_seconds = (datetime.now(timezone.utc) - manager._last_profile_change).total_seconds()

    return {
        "is_running": is_running,
        "started_at": started_at,
        "uptime_seconds": uptime_seconds,
        "sample_count": len(manager._history),
        "error_count": 0,  # Power manager doesn't track errors separately
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": 5.0,  # Check every 5 seconds
        "current_profile": manager._current_profile.value if manager._current_profile else None,
        "active_demands": len(manager._demands),
        "auto_scaling_enabled": manager._auto_scaling_config.enabled if manager._auto_scaling_config else False,
    }
