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
from datetime import datetime, timedelta
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
    load_auto_scaling_config,
    save_auto_scaling_config,
    load_dynamic_mode_config,
    save_dynamic_mode_config,
    persist_profile_change,
    persist_demand_log,
)
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
        self._demands: Dict[str, PowerDemandInfo] = {}
        self._current_profile = PowerProfile.IDLE
        self._current_property: Optional[ServicePowerProperty] = ServicePowerProperty.IDLE
        self._last_profile_change: Optional[datetime] = None
        self._history: List[PowerHistoryEntry] = []
        self._max_history = 1000
        self._auto_scaling_config = AutoScalingConfig()
        self._cooldown_until: Optional[datetime] = None
        self._manual_override_until: Optional[datetime] = None
        self._cpu_usage_callback: Optional[Callable[[], Optional[float]]] = None
        self._backend: Optional[CpuPowerBackend] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._profiles = DEFAULT_PROFILES.copy()
        self._state_lock = asyncio.Lock()
        self._dynamic_mode_enabled: bool = False
        self._dynamic_mode_config: Optional[DynamicModeConfig] = None

        logger.info("PowerManagerService initialized")

    async def enable_dynamic_mode(self, config: DynamicModeConfig) -> Tuple[bool, Optional[str]]:
        """
        Enable dynamic mode with kernel governor-based scaling.

        Validates the governor and freq bounds, applies settings directly,
        and pauses profile-based/auto-scaling.
        """
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

        # Record in history
        freq = await self._backend.get_current_frequency_mhz()
        entry = PowerHistoryEntry(
            timestamp=datetime.utcnow(),
            profile=self._current_profile,
            reason="dynamic_mode_enabled",
            source="admin",
            frequency_mhz=freq,
        )
        self._history.append(entry)

        logger.info(f"Dynamic mode enabled: {config.governor}, {config.min_freq_mhz}-{config.max_freq_mhz} MHz")
        return True, None

    async def disable_dynamic_mode(self) -> Tuple[bool, Optional[str]]:
        """Disable dynamic mode and return to profile-based scaling."""
        async with self._state_lock:
            self._dynamic_mode_enabled = False
            self._dynamic_mode_config = None

        # Save disabled state
        saved_config = load_dynamic_mode_config()
        if saved_config:
            saved_config.enabled = False
            save_dynamic_mode_config(saved_config)

        # Recalculate and apply the appropriate profile
        async with self._state_lock:
            await self._recalculate_profile("dynamic_mode_disabled")

        logger.info("Dynamic mode disabled, returned to profile-based scaling")
        return True, None

    async def get_dynamic_mode_config(self) -> DynamicModeConfigResponse:
        """Get dynamic mode configuration and system capabilities."""
        config = self._dynamic_mode_config or load_dynamic_mode_config() or DynamicModeConfig()

        available_governors = []
        sys_min, sys_max = 400, 4600
        if self._backend:
            available_governors = await self._backend.get_available_governors()
            sys_min, sys_max = await self._backend.get_system_freq_range()

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

        Args:
            use_linux: True to use Linux cpufreq, False for dev simulation

        Returns:
            Tuple of (success, previous_backend_name, new_backend_name)
        """
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
                    timestamp=datetime.utcnow(),
                    profile=self._current_profile,
                    reason=f"backend_switch:{new_backend_name.lower()}",
                    source="admin",
                    frequency_mhz=freq
                )
                self._history.append(entry)
            except Exception as e:
                logger.warning(f"Could not record backend switch in history: {e}")

            return True, previous_backend, new_backend_name

    async def start(self) -> None:
        """Start the power management service."""
        if self._is_running:
            logger.warning("PowerManagerService already running")
            return

        # Load configs from database
        self._auto_scaling_config = load_auto_scaling_config()
        dynamic_config = load_dynamic_mode_config()

        self._backend = self._select_backend()
        self._is_running = True

        # Apply initial state: dynamic mode or IDLE profile
        if dynamic_config and dynamic_config.enabled:
            success, error = await self.enable_dynamic_mode(dynamic_config)
            if not success:
                logger.warning(f"Failed to restore dynamic mode on start: {error}, falling back to IDLE")
                await self.apply_profile(PowerProfile.IDLE, reason="service_start")
        else:
            await self.apply_profile(PowerProfile.IDLE, reason="service_start")

        # Start background monitor for demand expiration
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("PowerManagerService started")

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

        logger.info("PowerManagerService stopped")

    async def _monitor_loop(self) -> None:
        """Background loop to handle demand expiration and auto-scaling."""
        while self._is_running:
            try:
                await self._check_expired_demands()
                await self._check_auto_scaling()
            except Exception as e:
                logger.error(f"Error in power monitor loop: {e}")

            await asyncio.sleep(5)  # Check every 5 seconds

    async def _check_expired_demands(self) -> None:
        """Remove expired demands and recalculate profile."""
        async with self._state_lock:
            now = datetime.utcnow()
            expired = [
                source for source, demand in self._demands.items()
                if demand.expires_at and demand.expires_at <= now
            ]

            if expired:
                expired_demands = {source: self._demands[source] for source in expired}
                for source in expired:
                    logger.info(f"Power demand '{source}' expired")
                    del self._demands[source]

                await self._recalculate_profile("demand_expired")

                # Persist expired demands to DB
                for source, demand in expired_demands.items():
                    persist_demand_log(
                        action="expired",
                        source=source,
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

        if self._manual_override_until and datetime.utcnow() < self._manual_override_until:
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
            if self._cooldown_until and datetime.utcnow() < self._cooldown_until:
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
            logger.error("Power backend not initialized")
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
            self._last_profile_change = datetime.utcnow()

            # Set cooldown for downgrades
            if PROFILE_PRIORITY[profile] < PROFILE_PRIORITY[old_profile]:
                self._cooldown_until = datetime.utcnow() + timedelta(
                    seconds=self._auto_scaling_config.cooldown_seconds
                )

            # Record history
            freq = await self._backend.get_current_frequency_mhz()
            entry = PowerHistoryEntry(
                timestamp=datetime.utcnow(),
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

    async def apply_profile(
        self,
        profile: PowerProfile,
        reason: str = "manual",
        duration_seconds: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Manually apply a power profile.

        Args:
            profile: The profile to apply
            reason: Reason for the change
            duration_seconds: How long to hold this profile (None = until changed)

        Returns:
            Tuple of (success, error_message). error_message is None on success.
        """
        async with self._state_lock:
            if duration_seconds:
                self._manual_override_until = datetime.utcnow() + timedelta(seconds=duration_seconds)
            else:
                self._manual_override_until = None

            return await self._apply_profile_internal(profile, reason, "manual")

    async def register_demand(
        self,
        source: str,
        level: PowerProfile,
        power_property: Optional[ServicePowerProperty] = None,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Register a power demand from a source.

        The highest demand across all sources determines the active profile.

        Args:
            source: Unique identifier for this demand (e.g., "backup_create")
            level: Required power level
            power_property: Optional service power property (if using preset system)
            timeout_seconds: Auto-expire after this duration
            description: Human-readable description

        Returns:
            The demand ID (same as source)
        """
        async with self._state_lock:
            expires_at = None
            if timeout_seconds:
                expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)

            # If power_property not provided, derive from level
            if power_property is None:
                power_property = ServicePowerProperty(level.value)

            demand = PowerDemandInfo(
                source=source,
                level=level,
                power_property=power_property,
                registered_at=datetime.utcnow(),
                expires_at=expires_at,
                description=description
            )

            self._demands[source] = demand
            logger.info(f"Registered power demand: {source} -> {level.value} (property: {power_property.value})")

            await self._recalculate_profile(f"demand_registered:{source}")

            # Persist to DB
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
        Remove a power demand.

        Args:
            source: The demand source to remove

        Returns:
            True if demand was found and removed
        """
        async with self._state_lock:
            if source not in self._demands:
                return False

            demand = self._demands[source]
            del self._demands[source]
            logger.info(f"Unregistered power demand: {source}")

            await self._recalculate_profile(f"demand_unregistered:{source}")

            # Persist to DB
            persist_demand_log(
                action="unregistered",
                source=source,
                level=demand.level.value,
                description=demand.description,
                resulting_profile=self._current_profile.value,
            )

        return True

    async def get_power_status(self) -> PowerStatusResponse:
        """Get current power status."""
        freq = None
        if self._backend:
            freq = await self._backend.get_current_frequency_mhz()

        config = self._profiles.get(self._current_profile)
        freq_range = None
        if config and config.min_freq_mhz and config.max_freq_mhz:
            freq_range = f"{config.min_freq_mhz}-{config.max_freq_mhz} MHz"
        elif self._current_profile == PowerProfile.SURGE:
            freq_range = "Full boost (4.6 GHz)"

        cooldown_remaining = None
        if self._cooldown_until:
            remaining = (self._cooldown_until - datetime.utcnow()).total_seconds()
            if remaining > 0:
                cooldown_remaining = int(remaining)

        is_linux = isinstance(self._backend, LinuxCpuPowerBackend)
        linux_available = self.is_linux_backend_available()

        # Get permission status for Linux backend
        permission_status = None
        if is_linux and isinstance(self._backend, LinuxCpuPowerBackend):
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

        return PowerStatusResponse(
            current_profile=self._current_profile,
            current_property=self._current_property,
            current_frequency_mhz=freq,
            target_frequency_range=freq_range,
            active_demands=list(self._demands.values()),
            auto_scaling_enabled=self._auto_scaling_config.enabled,
            is_dev_mode=isinstance(self._backend, DevCpuPowerBackend),
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
        """Get all active power demands."""
        return list(self._demands.values())

    async def get_service_intensities(self) -> ServiceIntensityResponse:
        """
        Get intensity information for all tracked services and processes.

        Delegates to the intensity module.
        """
        return await _get_service_intensities(self._demands, self._current_profile)

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


async def start_power_manager() -> None:
    """Start the power management service."""
    manager = get_power_manager()
    await manager.start()


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
        uptime_seconds = (datetime.utcnow() - manager._last_profile_change).total_seconds()

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
