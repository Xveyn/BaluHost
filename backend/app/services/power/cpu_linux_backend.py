"""
Linux CPU power backend using sysfs interface.

Controls CPU frequency via /sys/devices/system/cpu/cpu*/cpufreq/
Supports amd-pstate (AMD Ryzen) and intel_pstate drivers.

Permission handling:
1. Try direct write (works if user is in cpufreq group)
2. Fallback to sudo tee (works if sudoers configured)
3. Report detailed permission status
"""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.schemas.power import PowerProfileConfig
from app.services.power.cpu_protocol import CpuPowerBackend

logger = logging.getLogger(__name__)


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
