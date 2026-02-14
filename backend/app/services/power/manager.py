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
import platform
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.power import PowerProfileLog, PowerDemandLog
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
    ServiceIntensityInfo,
    ServiceIntensityResponse,
    ServicePowerProperty,
    PowerPresetSummary,
)

logger = logging.getLogger(__name__)

# Default profile configurations
DEFAULT_PROFILES: Dict[PowerProfile, PowerProfileConfig] = {
    PowerProfile.IDLE: PowerProfileConfig(
        profile=PowerProfile.IDLE,
        governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=400,
        max_freq_mhz=800,
        description="Minimal power consumption for idle NAS"
    ),
    PowerProfile.LOW: PowerProfileConfig(
        profile=PowerProfile.LOW,
        governor="powersave",
        energy_performance_preference="balance_power",
        min_freq_mhz=800,
        max_freq_mhz=1200,
        description="Light workloads: auth, basic CRUD operations"
    ),
    PowerProfile.MEDIUM: PowerProfileConfig(
        profile=PowerProfile.MEDIUM,
        governor="powersave",
        energy_performance_preference="balance_performance",
        min_freq_mhz=1500,
        max_freq_mhz=2500,
        description="File operations, sync, SMART scans"
    ),
    PowerProfile.SURGE: PowerProfileConfig(
        profile=PowerProfile.SURGE,
        governor="performance",
        energy_performance_preference="performance",
        min_freq_mhz=None,  # No limit
        max_freq_mhz=None,  # Full boost
        description="Maximum performance: backup, RAID rebuild"
    ),
}

# Profile priority (higher = more demanding)
PROFILE_PRIORITY = {
    PowerProfile.IDLE: 0,
    PowerProfile.LOW: 1,
    PowerProfile.MEDIUM: 2,
    PowerProfile.SURGE: 3,
}


class CpuPowerBackend(ABC):
    """Abstract base class for CPU power control backends."""

    @abstractmethod
    async def apply_profile(self, config: PowerProfileConfig) -> Tuple[bool, Optional[str]]:
        """Apply a power profile to the CPU. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def get_current_frequency_mhz(self) -> Optional[float]:
        """Get the current CPU frequency in MHz."""
        pass

    @abstractmethod
    async def get_available_governors(self) -> List[str]:
        """Get list of available CPU governors."""
        pass

    @abstractmethod
    async def get_current_governor(self) -> Optional[str]:
        """Get the currently active governor."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend can be used on the current system."""
        pass

    async def get_system_freq_range(self) -> Tuple[int, int]:
        """Get system min/max CPU frequency in MHz. Returns (min_mhz, max_mhz)."""
        return (400, 4600)


class DevCpuPowerBackend(CpuPowerBackend):
    """
    Development/simulation backend for CPU power management.

    Simulates CPU frequency changes without actual hardware control.
    Used for development on Windows/macOS or when running without root.
    """

    def __init__(self):
        self._current_profile: PowerProfile = PowerProfile.IDLE
        self._simulated_freq_mhz: float = 800.0
        self._current_governor: str = "powersave"
        logger.info("DevCpuPowerBackend initialized (simulation mode)")

    async def apply_profile(self, config: PowerProfileConfig) -> Tuple[bool, Optional[str]]:
        """Simulate applying a power profile."""
        self._current_governor = config.governor
        self._current_profile = config.profile

        # Simulate realistic frequency based on profile
        if config.profile == PowerProfile.IDLE:
            self._simulated_freq_mhz = random.uniform(400, 800)
        elif config.profile == PowerProfile.LOW:
            self._simulated_freq_mhz = random.uniform(800, 1200)
        elif config.profile == PowerProfile.MEDIUM:
            self._simulated_freq_mhz = random.uniform(1500, 2500)
        elif config.profile == PowerProfile.SURGE:
            self._simulated_freq_mhz = random.uniform(4200, 4600)  # AMD Ryzen 5600GT boost

        logger.info(
            f"[DEV] Applied profile '{config.profile.value}': "
            f"governor={config.governor}, freq={self._simulated_freq_mhz:.0f}MHz"
        )
        return True, None

    async def get_current_frequency_mhz(self) -> Optional[float]:
        """Return simulated frequency with small variations."""
        variation = random.uniform(-50, 50)
        return round(self._simulated_freq_mhz + variation, 1)

    async def get_available_governors(self) -> List[str]:
        """Return typical Linux governors for simulation."""
        return ["powersave", "performance", "schedutil", "conservative", "ondemand"]

    async def get_current_governor(self) -> Optional[str]:
        """Return the simulated current governor."""
        return self._current_governor

    def is_available(self) -> bool:
        """Dev backend is always available."""
        return True


class LinuxCpuPowerBackend(CpuPowerBackend):
    """
    Linux CPU power backend using sysfs interface.

    Controls CPU frequency via /sys/devices/system/cpu/cpu*/cpufreq/
    Supports amd-pstate (AMD Ryzen) and intel_pstate drivers.

    Permission handling:
    1. Try direct write (works if user is in cpufreq group)
    2. Fallback to sudo tee (works if sudoers configured)
    3. Report detailed permission status
    """

    CPUFREQ_PATH = Path("/sys/devices/system/cpu")
    SCALING_GOVERNOR = "cpufreq/scaling_governor"
    SCALING_MIN_FREQ = "cpufreq/scaling_min_freq"
    SCALING_MAX_FREQ = "cpufreq/scaling_max_freq"
    SCALING_CUR_FREQ = "cpufreq/scaling_cur_freq"
    EPP_PATH = "cpufreq/energy_performance_preference"
    AVAILABLE_GOVERNORS = "cpufreq/scaling_available_governors"

    # Files we need write access to
    WRITABLE_FILES = [
        "scaling_governor",
        "scaling_min_freq",
        "scaling_max_freq",
        "energy_performance_preference",
    ]

    def __init__(self):
        self._cpu_count = self._detect_cpu_count()
        self._use_sudo = False  # Will be set if direct write fails
        self._sudo_available = self._check_sudo_available()
        self._permission_errors: List[str] = []
        logger.info(f"LinuxCpuPowerBackend initialized with {self._cpu_count} CPUs, sudo available: {self._sudo_available}")

    def _detect_cpu_count(self) -> int:
        """Detect number of CPU cores with cpufreq support."""
        count = 0
        try:
            for cpu_dir in self.CPUFREQ_PATH.iterdir():
                if cpu_dir.name.startswith("cpu") and cpu_dir.name[3:].isdigit():
                    if (cpu_dir / "cpufreq").exists():
                        count += 1
        except Exception as e:
            logger.error(f"Error detecting CPU count: {e}")
        return count

    def _check_sudo_available(self) -> bool:
        """Check if passwordless sudo is available for tee to cpufreq paths."""
        import subprocess
        try:
            # Test if we can run sudo tee on a cpufreq path without password
            # We read the current governor and write it back (no-op)
            test_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"

            # First read current value
            with open(test_path, "r") as f:
                current_value = f.read().strip()

            # Try to write it back with sudo tee
            result = subprocess.run(
                ["sudo", "-n", "tee", test_path],
                input=current_value.encode(),
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"sudo check failed: {e}")
            return False

    def _get_cpu_paths(self) -> List[Path]:
        """Get paths to all CPU cpufreq directories."""
        paths = []
        for i in range(self._cpu_count):
            cpu_path = self.CPUFREQ_PATH / f"cpu{i}" / "cpufreq"
            if cpu_path.exists():
                paths.append(cpu_path)
        return paths

    def check_permissions(self) -> Dict[str, bool]:
        """
        Check write permissions for all required cpufreq files.

        Returns dict mapping file names to whether they're writable.
        """
        import os
        permissions = {}
        cpu0_path = self.CPUFREQ_PATH / "cpu0" / "cpufreq"

        for filename in self.WRITABLE_FILES:
            filepath = cpu0_path / filename
            if filepath.exists():
                permissions[filename] = os.access(filepath, os.W_OK)
            else:
                permissions[filename] = None  # File doesn't exist

        return permissions

    def get_permission_status(self) -> Dict[str, any]:
        """Get detailed permission status for diagnostics."""
        import os
        import grp
        import pwd

        status = {
            "user": pwd.getpwuid(os.getuid()).pw_name,
            "groups": [grp.getgrgid(g).gr_name for g in os.getgroups()],
            "in_cpufreq_group": False,
            "sudo_available": self._sudo_available,
            "files": self.check_permissions(),
            "errors": self._permission_errors.copy(),
        }

        # Check if user is in cpufreq group
        try:
            cpufreq_gid = grp.getgrnam("cpufreq").gr_gid
            status["in_cpufreq_group"] = cpufreq_gid in os.getgroups()
        except KeyError:
            status["cpufreq_group_exists"] = False

        return status

    async def _write_sysfs(self, path: Path, value: str) -> Tuple[bool, Optional[str]]:
        """
        Write a value to a sysfs file with fallback to sudo.

        Returns:
            Tuple of (success, error_type). error_type is None on success,
            'permission_denied' for permission errors, 'not_found' if file missing,
            or 'error' for other errors.
        """
        import subprocess

        # Try direct write first
        try:
            def _write():
                with open(path, "w") as f:
                    f.write(value)

            await asyncio.get_event_loop().run_in_executor(None, _write)
            return True, None

        except PermissionError:
            # Try sudo fallback if available
            if self._sudo_available:
                try:
                    def _sudo_write():
                        result = subprocess.run(
                            ["sudo", "-n", "tee", str(path)],
                            input=value.encode(),
                            capture_output=True,
                            timeout=5
                        )
                        return result.returncode == 0

                    success = await asyncio.get_event_loop().run_in_executor(None, _sudo_write)
                    if success:
                        if not self._use_sudo:
                            logger.info("Using sudo for cpufreq writes")
                            self._use_sudo = True
                        return True, None
                    else:
                        error_msg = f"sudo tee failed for {path}"
                        self._permission_errors.append(error_msg)
                        return False, "permission_denied"

                except Exception as e:
                    error_msg = f"sudo fallback failed for {path}: {e}"
                    self._permission_errors.append(error_msg)
                    return False, "permission_denied"
            else:
                # Only log once per apply_profile call (first CPU)
                if len(self._permission_errors) == 0:
                    logger.warning(f"Permission denied for cpufreq writes (sudo not available)")
                self._permission_errors.append(f"Permission denied: {path.name}")
                return False, "permission_denied"

        except FileNotFoundError:
            logger.debug(f"Sysfs path not found: {path}")
            return False, "not_found"

        except Exception as e:
            error_msg = f"Error writing to {path}: {e}"
            logger.error(error_msg)
            self._permission_errors.append(error_msg)
            return False, "error"

    async def _read_sysfs(self, path: Path) -> Optional[str]:
        """Read a value from a sysfs file."""
        try:
            def _read():
                with open(path, "r") as f:
                    return f.read().strip()

            return await asyncio.get_event_loop().run_in_executor(None, _read)
        except Exception as e:
            logger.debug(f"Error reading {path}: {e}")
            return None

    async def _apply_profile_to_cpu(
        self, cpu_path: Path, config: PowerProfileConfig
    ) -> Tuple[bool, bool]:
        """
        Apply power profile to a single CPU core.

        Returns:
            Tuple of (cpu_success, permission_denied)
        """
        cpu_success = True
        permission_denied = False

        # Set governor
        governor_path = cpu_path / "scaling_governor"
        result = await self._write_sysfs(governor_path, config.governor)
        if not result[0]:
            cpu_success = False
            if result[1] == "permission_denied":
                permission_denied = True

        # Set EPP if supported (amd-pstate or intel_pstate)
        epp_path = cpu_path / "energy_performance_preference"
        if epp_path.exists():
            result = await self._write_sysfs(epp_path, config.energy_performance_preference)
            if not result[0]:
                cpu_success = False

        # Set frequency limits if specified
        if config.min_freq_mhz is not None:
            min_freq_path = cpu_path / "scaling_min_freq"
            freq_khz = str(config.min_freq_mhz * 1000)
            result = await self._write_sysfs(min_freq_path, freq_khz)
            if not result[0]:
                cpu_success = False

        if config.max_freq_mhz is not None:
            max_freq_path = cpu_path / "scaling_max_freq"
            freq_khz = str(config.max_freq_mhz * 1000)
            result = await self._write_sysfs(max_freq_path, freq_khz)
            if not result[0]:
                cpu_success = False
        else:
            # Reset to maximum available
            max_avail_path = cpu_path / "cpuinfo_max_freq"
            max_avail = await self._read_sysfs(max_avail_path)
            if max_avail:
                max_freq_path = cpu_path / "scaling_max_freq"
                await self._write_sysfs(max_freq_path, max_avail)

        return cpu_success, permission_denied

    async def apply_profile(self, config: PowerProfileConfig) -> Tuple[bool, Optional[str]]:
        """
        Apply power profile to all CPU cores in parallel.

        Returns:
            Tuple of (success, error_message). error_message is None on success.
        """
        cpu_paths = self._get_cpu_paths()
        if not cpu_paths:
            logger.error("No CPU cpufreq paths found")
            return False, "No CPU cpufreq paths found"

        self._permission_errors.clear()

        # Apply to all cores in parallel
        results = await asyncio.gather(
            *(self._apply_profile_to_cpu(cpu_path, config) for cpu_path in cpu_paths),
            return_exceptions=True,
        )

        failed_cpus = []
        permission_denied = False

        for cpu_path, result in zip(cpu_paths, results):
            if isinstance(result, Exception):
                logger.error(f"Exception applying profile to {cpu_path.parent.name}: {result}")
                failed_cpus.append(cpu_path.parent.name)
                continue
            cpu_success, perm_denied = result
            if not cpu_success:
                failed_cpus.append(cpu_path.parent.name)
                if perm_denied:
                    permission_denied = True

        if not failed_cpus:
            logger.info(
                f"Applied profile '{config.profile.value}': "
                f"governor={config.governor}, EPP={config.energy_performance_preference}"
                + (f" (using sudo)" if self._use_sudo else "")
            )
            return True, None
        else:
            if permission_denied:
                error_msg = f"Permission denied for cpufreq control on {len(failed_cpus)} CPUs. " \
                           f"Configure cpufreq group or passwordless sudo."
                logger.error(error_msg)
                return False, error_msg
            else:
                error_msg = f"Failed to apply profile to CPUs: {', '.join(failed_cpus[:3])}{'...' if len(failed_cpus) > 3 else ''}"
                logger.error(error_msg)
                return False, error_msg

    async def get_current_frequency_mhz(self) -> Optional[float]:
        """Get average current frequency across all cores."""
        cpu_paths = self._get_cpu_paths()
        if not cpu_paths:
            return None

        frequencies = []
        for cpu_path in cpu_paths:
            freq_path = cpu_path / "scaling_cur_freq"
            freq_str = await self._read_sysfs(freq_path)
            if freq_str and freq_str.isdigit():
                frequencies.append(int(freq_str) / 1000)  # kHz to MHz

        if frequencies:
            return round(sum(frequencies) / len(frequencies), 1)
        return None

    async def get_available_governors(self) -> List[str]:
        """Get available governors from CPU0."""
        cpu0_path = self.CPUFREQ_PATH / "cpu0" / "cpufreq" / "scaling_available_governors"
        governors_str = await self._read_sysfs(cpu0_path)
        if governors_str:
            return governors_str.split()
        return []

    async def get_current_governor(self) -> Optional[str]:
        """Get current governor from CPU0."""
        cpu0_path = self.CPUFREQ_PATH / "cpu0" / "cpufreq" / "scaling_governor"
        return await self._read_sysfs(cpu0_path)

    def is_available(self) -> bool:
        """Check if cpufreq interface is available."""
        return self._is_available_static()

    @classmethod
    def _is_available_static(cls) -> bool:
        """Static check if cpufreq interface is available (no instance needed)."""
        if platform.system() != "Linux":
            return False
        cpu0_path = cls.CPUFREQ_PATH / "cpu0" / "cpufreq"
        return cpu0_path.exists()

    async def get_system_freq_range(self) -> Tuple[int, int]:
        """Get system min/max CPU frequency from sysfs."""
        cpu0_path = self.CPUFREQ_PATH / "cpu0" / "cpufreq"
        min_str = await self._read_sysfs(cpu0_path / "cpuinfo_min_freq")
        max_str = await self._read_sysfs(cpu0_path / "cpuinfo_max_freq")
        min_mhz = int(min_str) // 1000 if min_str and min_str.isdigit() else 400
        max_mhz = int(max_str) // 1000 if max_str and max_str.isdigit() else 4600
        return (min_mhz, max_mhz)

    def has_write_permission(self) -> bool:
        """Check if we have write permission (direct or via sudo)."""
        perms = self.check_permissions()
        # Check if at least governor is writable
        return perms.get("scaling_governor", False) or self._sudo_available


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

    def _load_auto_scaling_config_from_db(self) -> AutoScalingConfig:
        """Load auto-scaling config from database."""
        try:
            from app.models.power import PowerAutoScalingConfig

            db = SessionLocal()
            try:
                db_config = db.query(PowerAutoScalingConfig).filter(
                    PowerAutoScalingConfig.id == 1
                ).first()

                if db_config:
                    config = AutoScalingConfig(
                        enabled=db_config.enabled,
                        cpu_surge_threshold=db_config.cpu_surge_threshold,
                        cpu_medium_threshold=db_config.cpu_medium_threshold,
                        cpu_low_threshold=db_config.cpu_low_threshold,
                        cooldown_seconds=db_config.cooldown_seconds,
                        use_cpu_monitoring=db_config.use_cpu_monitoring
                    )
                    logger.info(f"Loaded auto-scaling config from DB: enabled={config.enabled}")
                    return config
                else:
                    # No config in DB yet, use defaults
                    logger.info("No auto-scaling config in DB, using defaults")
                    return AutoScalingConfig()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error loading auto-scaling config from DB: {e}")
            return AutoScalingConfig()

    def _save_auto_scaling_config_to_db(self, config: AutoScalingConfig) -> bool:
        """Save auto-scaling config to database."""
        try:
            from app.models.power import PowerAutoScalingConfig

            db = SessionLocal()
            try:
                db_config = db.query(PowerAutoScalingConfig).filter(
                    PowerAutoScalingConfig.id == 1
                ).first()

                if db_config:
                    # Update existing config
                    db_config.enabled = config.enabled
                    db_config.cpu_surge_threshold = config.cpu_surge_threshold
                    db_config.cpu_medium_threshold = config.cpu_medium_threshold
                    db_config.cpu_low_threshold = config.cpu_low_threshold
                    db_config.cooldown_seconds = config.cooldown_seconds
                    db_config.use_cpu_monitoring = config.use_cpu_monitoring
                else:
                    # Create new config (singleton)
                    db_config = PowerAutoScalingConfig(
                        id=1,
                        enabled=config.enabled,
                        cpu_surge_threshold=config.cpu_surge_threshold,
                        cpu_medium_threshold=config.cpu_medium_threshold,
                        cpu_low_threshold=config.cpu_low_threshold,
                        cooldown_seconds=config.cooldown_seconds,
                        use_cpu_monitoring=config.use_cpu_monitoring
                    )
                    db.add(db_config)

                db.commit()
                logger.info(f"Saved auto-scaling config to DB: enabled={config.enabled}")
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving auto-scaling config to DB: {e}")
                return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error saving auto-scaling config to DB: {e}")
            return False

    def _load_dynamic_mode_config_from_db(self) -> Optional[DynamicModeConfig]:
        """Load dynamic mode config from database."""
        try:
            from app.models.power import PowerDynamicModeConfig

            db = SessionLocal()
            try:
                db_config = db.query(PowerDynamicModeConfig).filter(
                    PowerDynamicModeConfig.id == 1
                ).first()

                if db_config:
                    config = DynamicModeConfig(
                        enabled=db_config.enabled,
                        governor=db_config.governor,
                        min_freq_mhz=db_config.min_freq_mhz,
                        max_freq_mhz=db_config.max_freq_mhz,
                    )
                    logger.info(f"Loaded dynamic mode config from DB: enabled={config.enabled}")
                    return config
                else:
                    logger.info("No dynamic mode config in DB, using defaults")
                    return DynamicModeConfig()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error loading dynamic mode config from DB: {e}")
            return DynamicModeConfig()

    def _save_dynamic_mode_config_to_db(self, config: DynamicModeConfig) -> bool:
        """Save dynamic mode config to database."""
        try:
            from app.models.power import PowerDynamicModeConfig

            db = SessionLocal()
            try:
                db_config = db.query(PowerDynamicModeConfig).filter(
                    PowerDynamicModeConfig.id == 1
                ).first()

                if db_config:
                    db_config.enabled = config.enabled
                    db_config.governor = config.governor
                    db_config.min_freq_mhz = config.min_freq_mhz
                    db_config.max_freq_mhz = config.max_freq_mhz
                else:
                    db_config = PowerDynamicModeConfig(
                        id=1,
                        enabled=config.enabled,
                        governor=config.governor,
                        min_freq_mhz=config.min_freq_mhz,
                        max_freq_mhz=config.max_freq_mhz,
                    )
                    db.add(db_config)

                db.commit()
                logger.info(f"Saved dynamic mode config to DB: enabled={config.enabled}")
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving dynamic mode config to DB: {e}")
                return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error saving dynamic mode config to DB: {e}")
            return False

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

        self._save_dynamic_mode_config_to_db(DynamicModeConfig(
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
        saved_config = self._load_dynamic_mode_config_from_db()
        if saved_config:
            saved_config.enabled = False
            self._save_dynamic_mode_config_to_db(saved_config)

        # Recalculate and apply the appropriate profile
        async with self._state_lock:
            await self._recalculate_profile("dynamic_mode_disabled")

        logger.info("Dynamic mode disabled, returned to profile-based scaling")
        return True, None

    async def get_dynamic_mode_config(self) -> DynamicModeConfigResponse:
        """Get dynamic mode configuration and system capabilities."""
        config = self._dynamic_mode_config or self._load_dynamic_mode_config_from_db() or DynamicModeConfig()

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
        self._auto_scaling_config = self._load_auto_scaling_config_from_db()
        dynamic_config = self._load_dynamic_mode_config_from_db()

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
                try:
                    db = SessionLocal()
                    try:
                        for source, demand in expired_demands.items():
                            log = PowerDemandLog(
                                action="expired",
                                source=source,
                                level=demand.level.value,
                                description=demand.description,
                                resulting_profile=self._current_profile.value,
                            )
                            db.add(log)
                        db.commit()
                    except Exception as db_err:
                        db.rollback()
                        logger.warning(f"Failed to persist expired demands to DB: {db_err}")
                    finally:
                        db.close()
                except Exception as db_err:
                    logger.warning(f"Failed to create DB session for expired demand logs: {db_err}")

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
            try:
                db = SessionLocal()
                try:
                    log = PowerProfileLog(
                        profile=profile.value,
                        previous_profile=old_profile.value,
                        reason=reason,
                        source=source,
                        frequency_mhz=freq,
                    )
                    db.add(log)
                    db.commit()
                except Exception as db_err:
                    db.rollback()
                    logger.warning(f"Failed to persist profile change to DB: {db_err}")
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to create DB session for profile log: {db_err}")

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
            try:
                db = SessionLocal()
                try:
                    log = PowerDemandLog(
                        action="registered",
                        source=source,
                        level=level.value,
                        description=description,
                        timeout_seconds=timeout_seconds,
                        resulting_profile=self._current_profile.value,
                    )
                    db.add(log)
                    db.commit()
                except Exception as db_err:
                    db.rollback()
                    logger.warning(f"Failed to persist demand registration to DB: {db_err}")
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to create DB session for demand log: {db_err}")

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
            try:
                db = SessionLocal()
                try:
                    log = PowerDemandLog(
                        action="unregistered",
                        source=source,
                        level=demand.level.value,
                        description=demand.description,
                        resulting_profile=self._current_profile.value,
                    )
                    db.add(log)
                    db.commit()
                except Exception as db_err:
                    db.rollback()
                    logger.warning(f"Failed to persist demand unregistration to DB: {db_err}")
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(f"Failed to create DB session for demand log: {db_err}")

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

    def _cpu_to_intensity(self, cpu_percent: float) -> ServicePowerProperty:
        """
        Convert CPU usage percentage to intensity level.

        Thresholds:
        - >= 60%: SURGE
        - >= 30%: MEDIUM
        - >= 10%: LOW
        - < 10%: IDLE
        """
        if cpu_percent >= 60.0:
            return ServicePowerProperty.SURGE
        elif cpu_percent >= 30.0:
            return ServicePowerProperty.MEDIUM
        elif cpu_percent >= 10.0:
            return ServicePowerProperty.LOW
        return ServicePowerProperty.IDLE

    def _get_display_name(self, source: str) -> str:
        """
        Get a human-readable display name for a source identifier.

        Maps internal identifiers to user-friendly names.
        """
        display_names = {
            # Power demand sources
            "backup_create": "Backup erstellen",
            "backup_restore": "Backup wiederherstellen",
            "raid_rebuild": "RAID Rebuild",
            "raid_scrub": "RAID Scrub",
            "file_upload": "Datei-Upload",
            "file_download": "Datei-Download",
            "smart_scan": "SMART Scan",
            "sync_operation": "Sync Operation",
            # Process tracker names
            "baluhost-backend": "BaluHost Backend",
            "baluhost-frontend": "BaluHost Frontend",
            "baluhost-tui": "BaluHost TUI",
        }
        return display_names.get(source, source.replace("_", " ").replace("-", " ").title())

    def _service_state_to_intensity(self, is_running: bool, has_error: bool = False) -> ServicePowerProperty:
        """
        Convert service state to intensity level.

        Running services are considered LOW intensity (background work).
        Stopped services are IDLE, errored services are also shown as IDLE.
        """
        if has_error:
            return ServicePowerProperty.IDLE
        if is_running:
            return ServicePowerProperty.LOW
        return ServicePowerProperty.IDLE

    async def get_service_intensities(self) -> ServiceIntensityResponse:
        """
        Get intensity information for all tracked services and processes.

        Combines data from four sources:
        1. Active power demands (services that have registered power requirements)
        2. Registered background services (from service_status registry)
        3. Process tracker metrics (BaluHost processes with CPU/RAM usage)
        4. Inferred intensity from CPU usage (for processes without demands)

        Returns:
            ServiceIntensityResponse with list of all services and their intensity levels
        """
        services: List[ServiceIntensityInfo] = []
        seen_sources: set = set()
        highest_intensity = ServicePowerProperty.IDLE

        # Priority order for intensity comparison
        intensity_priority = {
            ServicePowerProperty.IDLE: 0,
            ServicePowerProperty.LOW: 1,
            ServicePowerProperty.MEDIUM: 2,
            ServicePowerProperty.SURGE: 3,
        }

        # 1. Add services from active power demands
        for source, demand in self._demands.items():
            seen_sources.add(source)

            intensity = demand.power_property or ServicePowerProperty(demand.level.value)

            if intensity_priority[intensity] > intensity_priority[highest_intensity]:
                highest_intensity = intensity

            service_info = ServiceIntensityInfo(
                name=source,
                display_name=self._get_display_name(source),
                intensity_level=intensity,
                intensity_source="demand",
                has_active_demand=True,
                demand_description=demand.description,
                demand_registered_at=demand.registered_at,
                demand_expires_at=demand.expires_at,
                is_alive=True,
            )
            services.append(service_info)

        # 2. Add registered background services from service_status
        try:
            from app.services.service_status import _service_registry

            for service_name, registry in _service_registry.items():
                # Skip if already added from demands
                if service_name in seen_sources:
                    continue
                seen_sources.add(service_name)

                # Get service status
                status_fn = registry.get("get_status")
                display_name = registry.get("display_name", service_name)

                is_running = False
                has_error = False

                if status_fn:
                    try:
                        status_data = status_fn()
                        is_running = status_data.get("is_running", False)
                        has_error = status_data.get("has_error", False)
                    except Exception:
                        pass

                # Derive intensity from service state
                intensity = self._service_state_to_intensity(is_running, has_error)

                if intensity_priority[intensity] > intensity_priority[highest_intensity]:
                    highest_intensity = intensity

                service_info = ServiceIntensityInfo(
                    name=service_name,
                    display_name=display_name,
                    intensity_level=intensity,
                    intensity_source="service",
                    has_active_demand=False,
                    is_alive=is_running,
                )
                services.append(service_info)

        except Exception as e:
            logger.warning(f"Could not get registered services: {e}")

        # 3. Add services from process tracker
        try:
            from app.services.monitoring.orchestrator import MonitoringOrchestrator

            orchestrator = MonitoringOrchestrator.get_instance()
            process_status = orchestrator.process_tracker.get_current_status()

            for process_name, sample in process_status.items():
                if sample is None:
                    continue

                # Skip if already added from demands or services
                if process_name in seen_sources:
                    continue
                seen_sources.add(process_name)

                # Derive intensity from CPU usage
                intensity = self._cpu_to_intensity(sample.cpu_percent)

                if intensity_priority[intensity] > intensity_priority[highest_intensity]:
                    highest_intensity = intensity

                service_info = ServiceIntensityInfo(
                    name=process_name,
                    display_name=self._get_display_name(process_name),
                    intensity_level=intensity,
                    intensity_source="cpu_usage",
                    has_active_demand=False,
                    cpu_percent=sample.cpu_percent,
                    memory_mb=sample.memory_mb,
                    pid=sample.pid,
                    is_alive=sample.is_alive,
                )
                services.append(service_info)

        except Exception as e:
            logger.warning(f"Could not get process tracker data: {e}")

        # Sort by intensity level (highest first), then by name
        services.sort(
            key=lambda s: (-intensity_priority[s.intensity_level], s.display_name.lower())
        )

        return ServiceIntensityResponse(
            services=services,
            timestamp=datetime.utcnow(),
            total_services=len(services),
            active_demands_count=sum(1 for s in services if s.has_active_demand),
            highest_intensity=highest_intensity,
        )

    def set_cpu_usage_callback(self, callback: Callable[[], Optional[float]]) -> None:
        """Set callback to get current CPU usage for auto-scaling."""
        self._cpu_usage_callback = callback

    def get_auto_scaling_config(self) -> AutoScalingConfig:
        """Get current auto-scaling configuration."""
        return self._auto_scaling_config

    def set_auto_scaling_config(self, config: AutoScalingConfig) -> None:
        """Update auto-scaling configuration and save to database."""
        self._auto_scaling_config = config
        self._save_auto_scaling_config_to_db(config)
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
