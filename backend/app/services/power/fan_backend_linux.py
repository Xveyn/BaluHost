"""
Linux hardware backend for fan control using hwmon sysfs.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import Settings
from app.schemas.fans import FanMode, FanCurvePoint
from app.services.power.fan_control import FanControlBackend, FanData, TempSensorData

logger = logging.getLogger(__name__)


class LinuxFanControlBackend(FanControlBackend):
    """Linux hardware backend using hwmon sysfs."""

    def __init__(self, config: Settings):
        self.config = config
        self._hwmon_base = Path("/sys/class/hwmon")
        self._fan_cache: Dict[str, Dict] = {}
        self._has_write_permission = False

    async def is_available(self) -> bool:
        """Check if hwmon is available."""
        if not self._hwmon_base.exists():
            logger.info("hwmon not available (not on Linux or no sensors)")
            return False

        # Scan for PWM fans
        fans = await self._scan_pwm_fans()
        if not fans:
            logger.info("No PWM fans found in hwmon")
            return False

        logger.info(f"Found {len(fans)} PWM fan(s) in hwmon")
        await self._check_write_permission()
        return True

    async def _check_write_permission(self) -> None:
        """Proactively test write permission on first PWM file."""
        if not self._fan_cache:
            return

        first_fan = next(iter(self._fan_cache.values()))
        pwm_path = first_fan["pwm_path"]

        # Fast check: direct write permission
        if os.access(pwm_path, os.W_OK):
            self._has_write_permission = True
            logger.info("Fan control: direct write permission available")
            return

        # Fallback: test sudo tee (read current value, write it back unchanged)
        current = await self._read_hwmon_file(pwm_path)
        if current is not None:
            try:
                result = subprocess.run(
                    ["sudo", "-n", "tee", str(pwm_path)],
                    input=str(current).encode(),
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._has_write_permission = True
                    logger.info("Fan control: write permission available via sudo tee")
                    return
            except Exception:
                pass

        logger.info("Fan control: no write permission (readonly mode)")

    async def get_fans(self) -> List[FanData]:
        """Get hardware fans from hwmon (uses cache from startup scan)."""

        fans = []
        for fan_id, fan_info in self._fan_cache.items():
            # Read current state
            pwm_value = await self._read_hwmon_file(fan_info["pwm_path"])
            pwm_percent = self._pwm_to_percent(pwm_value) if pwm_value is not None else 0

            rpm_value = await self._read_hwmon_file(fan_info["fan_input_path"])
            rpm = int(rpm_value) if rpm_value is not None else None

            temp_celsius = None
            if fan_info.get("temp_path"):
                temp_value = await self._read_hwmon_file(fan_info["temp_path"])
                if temp_value is not None:
                    temp_celsius = float(temp_value) / 1000.0  # millidegrees to degrees

            fans.append(FanData(
                fan_id=fan_id,
                name=fan_info["name"],
                rpm=rpm,
                pwm_percent=pwm_percent,
                temperature_celsius=temp_celsius,
                mode=FanMode.AUTO,  # Will be overridden by service from DB
                min_pwm_percent=self.config.fan_min_pwm_percent,
                max_pwm_percent=100,
                emergency_temp_celsius=self.config.fan_emergency_temp_celsius,
                temp_sensor_id=fan_info.get("temp_sensor_id"),
                curve_points=self._get_default_curve(),
                is_active=True,
            ))

        return fans

    async def set_pwm(self, fan_id: str, pwm_percent: int) -> bool:
        """Set hardware PWM value."""
        if fan_id not in self._fan_cache:
            logger.warning(f"Fan {fan_id} not found in cache")
            return False

        fan_info = self._fan_cache[fan_id]
        pwm_path = fan_info["pwm_path"]
        pwm_enable_path = fan_info.get("pwm_enable_path")

        # Clamp to valid range
        pwm_percent = max(0, min(100, pwm_percent))
        pwm_value = self._percent_to_pwm(pwm_percent)

        # First, set PWM enable to manual mode (1)
        if pwm_enable_path:
            success = await self._write_hwmon_file(pwm_enable_path, "1")
            if not success:
                logger.warning(f"Failed to set PWM enable for {fan_id}")

        # Write PWM value
        success = await self._write_hwmon_file(pwm_path, str(pwm_value))
        if success:
            logger.debug(f"Set {fan_id} PWM to {pwm_percent}% ({pwm_value}/255)")
            return True
        else:
            logger.error(f"Failed to write PWM for {fan_id}")
            return False

    # CPU temperature driver names (same keywords as hardware/sensors.py)
    _CPU_SENSOR_DRIVERS = {"k10temp", "coretemp", "cpu_thermal", "acpi"}

    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get temperature from hwmon sensor."""
        if not sensor_id:
            return None

        # sensor_id format: "hwmon0_temp1"
        parts = sensor_id.split("_")
        if len(parts) != 2:
            return None

        hwmon_name, temp_name = parts
        temp_path = self._hwmon_base / hwmon_name / f"{temp_name}_input"

        temp_value = await self._read_hwmon_file(temp_path)
        if temp_value is not None:
            return float(temp_value) / 1000.0

        return None

    def _find_cpu_temp_sensor(self) -> Optional[Tuple[str, Path]]:
        """Find CPU temperature sensor across all hwmon directories.

        Searches for known CPU temperature drivers (k10temp, coretemp, etc.)
        in any hwmon directory, not just the one containing the PWM fan.

        Returns:
            Tuple of (sensor_id, temp_path) or None if not found
        """
        if not self._hwmon_base.exists():
            return None

        for hwmon_dir in sorted(self._hwmon_base.iterdir()):
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            name_file = hwmon_dir / "name"
            if not name_file.exists():
                continue

            try:
                driver_name = name_file.read_text().strip()
            except Exception:
                continue

            if driver_name not in self._CPU_SENSOR_DRIVERS:
                continue

            # Found a CPU sensor driver — use its first temp input
            for temp_file in sorted(hwmon_dir.glob("temp*_input")):
                temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                sensor_id = f"{hwmon_dir.name}_temp{temp_num}"
                logger.info(
                    f"Found CPU temp sensor: {sensor_id} (driver={driver_name})"
                )
                return sensor_id, temp_file

        return None

    async def get_available_temp_sensors(self) -> List[TempSensorData]:
        """List all available temperature sensors across all hwmon directories."""
        sensors: List[TempSensorData] = []

        if not self._hwmon_base.exists():
            return sensors

        for hwmon_dir in sorted(self._hwmon_base.iterdir()):
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            name_file = hwmon_dir / "name"
            device_name = "Unknown"
            if name_file.exists():
                try:
                    device_name = name_file.read_text().strip()
                except Exception:
                    pass

            is_cpu = device_name in self._CPU_SENSOR_DRIVERS

            for temp_file in sorted(hwmon_dir.glob("temp*_input")):
                temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                sensor_id = f"{hwmon_dir.name}_temp{temp_num}"

                # Try to read label
                label = None
                label_file = hwmon_dir / f"temp{temp_num}_label"
                if label_file.exists():
                    try:
                        label = label_file.read_text().strip()
                    except Exception:
                        pass

                # Read current temperature
                current_temp = None
                temp_value = await self._read_hwmon_file(temp_file)
                if temp_value is not None:
                    current_temp = float(temp_value) / 1000.0

                sensors.append(TempSensorData(
                    sensor_id=sensor_id,
                    device_name=device_name,
                    label=label,
                    is_cpu_sensor=is_cpu,
                    current_temp=current_temp,
                ))

        return sensors

    async def _scan_pwm_fans(self) -> Dict[str, Dict]:
        """Scan hwmon for PWM fans.

        Builds a new dict from sysfs. Only replaces the cache if the scan
        found at least one fan (or the cache was empty), preventing
        transient sysfs I/O failures from clearing known fans.

        Prefers CPU temperature sensor (k10temp, coretemp) over local
        board sensors for fan control.
        """
        new_cache: Dict[str, Dict] = {}

        if not self._hwmon_base.exists():
            if not self._fan_cache:
                return {}
            logger.debug("hwmon base missing but cache exists, keeping cached fans")
            return self._fan_cache

        # Find CPU temp sensor across all hwmon directories
        cpu_sensor = self._find_cpu_temp_sensor()
        cpu_sensor_id = cpu_sensor[0] if cpu_sensor else None
        cpu_temp_path = cpu_sensor[1] if cpu_sensor else None

        for hwmon_dir in self._hwmon_base.iterdir():
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            # Read hwmon name
            name_file = hwmon_dir / "name"
            hwmon_name_value = "Unknown"
            if name_file.exists():
                try:
                    hwmon_name_value = name_file.read_text().strip()
                except Exception:
                    pass

            # Find PWM files
            for pwm_file in hwmon_dir.glob("pwm[0-9]*"):
                if "_" in pwm_file.name:  # Skip pwm1_enable, etc
                    continue

                pwm_num = pwm_file.name.replace("pwm", "")
                fan_id = f"{hwmon_dir.name}_pwm{pwm_num}"

                # Find corresponding fan input
                fan_input_path = hwmon_dir / f"fan{pwm_num}_input"
                if not fan_input_path.exists():
                    continue

                # Find PWM enable
                pwm_enable_path = hwmon_dir / f"pwm{pwm_num}_enable"

                # Prefer CPU sensor over local board sensor
                if cpu_sensor_id:
                    temp_sensor_id = cpu_sensor_id
                    temp_path = cpu_temp_path
                else:
                    # Fallback: use first temp sensor in same hwmon dir
                    temp_sensor_id = None
                    temp_path = None
                    for temp_file in hwmon_dir.glob("temp*_input"):
                        temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                        temp_sensor_id = f"{hwmon_dir.name}_temp{temp_num}"
                        temp_path = temp_file
                        break

                new_cache[fan_id] = {
                    "name": f"{hwmon_name_value} PWM{pwm_num}",
                    "pwm_path": pwm_file,
                    "pwm_enable_path": pwm_enable_path if pwm_enable_path.exists() else None,
                    "fan_input_path": fan_input_path,
                    "temp_path": temp_path,
                    "temp_sensor_id": temp_sensor_id,
                }

        if new_cache or not self._fan_cache:
            self._fan_cache = new_cache
            logger.info(f"Scanned hwmon: found {len(self._fan_cache)} PWM fan(s)")
        else:
            logger.warning(
                f"hwmon scan found 0 fans but cache has {len(self._fan_cache)}, keeping cached fans"
            )

        return self._fan_cache

    async def _read_hwmon_file(self, path: Path) -> Optional[int]:
        """Read integer value from hwmon sysfs file."""
        if not path or not path.exists():
            return None

        try:
            value = path.read_text().strip()
            return int(value)
        except Exception as e:
            logger.debug(f"Failed to read {path}: {e}")
            return None

    async def _write_hwmon_file(self, path: Path, value: str) -> bool:
        """Write value to hwmon sysfs file."""
        if not path or not path.exists():
            return False

        try:
            # Try direct write first
            path.write_text(value + "\n")
            self._has_write_permission = True
            return True
        except PermissionError:
            # Try with sudo tee fallback
            try:
                cmd = ["sudo", "tee", str(path)]
                result = subprocess.run(
                    cmd,
                    input=value.encode(),
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self._has_write_permission = True
                    logger.debug(f"Wrote to {path} via sudo tee")
                    return True
                else:
                    logger.warning(f"sudo tee failed for {path}: {result.stderr.decode()}")
                    return False
            except Exception as e:
                logger.error(f"Failed to write {path} with sudo: {e}")
                return False
        except Exception as e:
            logger.error(f"Failed to write {path}: {e}")
            return False

    def _pwm_to_percent(self, pwm_value: int) -> int:
        """Convert PWM value (0-255) to percentage (0-100)."""
        return round(pwm_value * 100 / 255)

    def _percent_to_pwm(self, percent: int) -> int:
        """Convert percentage (0-100) to PWM value (0-255)."""
        return round(percent * 255 / 100)

    def _get_default_curve(self) -> List[FanCurvePoint]:
        """Get default temperature-PWM curve."""
        return [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
            FanCurvePoint(temp=70, pwm=80),
            FanCurvePoint(temp=85, pwm=100),
        ]
