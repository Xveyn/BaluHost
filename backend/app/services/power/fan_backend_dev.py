"""
Development backend for fan control with simulated fans.
"""
import random
import time
import logging
from typing import Dict, List, Optional

from app.core.config import Settings
from app.schemas.fans import FanMode, FanCurvePoint
from app.services.power.fan_control import FanControlBackend, FanData, TempSensorData

logger = logging.getLogger(__name__)


class DevFanControlBackend(FanControlBackend):
    """Development backend with simulated fans."""

    def __init__(self, config: Settings):
        self.config = config
        self._fans: Dict[str, Dict] = {}
        self._temps: Dict[str, float] = {}
        self._initialize_simulated_fans()

    def _initialize_simulated_fans(self):
        """Initialize 3 simulated PWM fans."""
        self._fans = {
            "dev_cpu_fan": {
                "name": "CPU Fan (Simulated)",
                "pwm_percent": 50,
                "target_rpm": 2000,
                "current_rpm": 2000,
                "min_rpm": 1000,
                "max_rpm": 3000,
                "temp_sensor_id": "dev_cpu_temp",
                "last_update": time.time(),
            },
            "dev_case_fan_1": {
                "name": "Case Fan 1 (Simulated)",
                "pwm_percent": 40,
                "target_rpm": 1200,
                "current_rpm": 1200,
                "min_rpm": 800,
                "max_rpm": 2000,
                "temp_sensor_id": "dev_package_temp",
                "last_update": time.time(),
            },
            "dev_case_fan_2": {
                "name": "Case Fan 2 (Simulated)",
                "pwm_percent": 40,
                "target_rpm": 1200,
                "current_rpm": 1200,
                "min_rpm": 800,
                "max_rpm": 2000,
                "temp_sensor_id": "dev_ambient_temp",
                "last_update": time.time(),
            },
        }

        # Initialize simulated temperatures
        self._temps = {
            "dev_cpu_temp": 45.0,
            "dev_package_temp": 42.0,
            "dev_ambient_temp": 35.0,
        }

    async def is_available(self) -> bool:
        """Dev backend is always available."""
        return True

    async def get_fans(self) -> List[FanData]:
        """Get simulated fans."""
        self._update_simulated_state()

        fans = []
        for fan_id, fan_data in self._fans.items():
            # Get default curve if not configured
            curve_points = self._get_default_curve()

            fans.append(FanData(
                fan_id=fan_id,
                name=fan_data["name"],
                rpm=fan_data["current_rpm"],
                pwm_percent=fan_data["pwm_percent"],
                temperature_celsius=self._temps.get(fan_data["temp_sensor_id"]),
                mode=FanMode.AUTO,  # Default mode
                min_pwm_percent=self.config.fan_min_pwm_percent,
                max_pwm_percent=100,
                emergency_temp_celsius=self.config.fan_emergency_temp_celsius,
                temp_sensor_id=fan_data["temp_sensor_id"],
                curve_points=curve_points,
                is_active=True,
            ))

        return fans

    async def set_pwm(self, fan_id: str, pwm_percent: int) -> bool:
        """Set simulated PWM value."""
        if fan_id not in self._fans:
            logger.warning(f"Fan {fan_id} not found")
            return False

        pwm_percent = max(0, min(100, pwm_percent))
        fan = self._fans[fan_id]
        fan["pwm_percent"] = pwm_percent

        # Calculate target RPM
        pwm_ratio = pwm_percent / 100.0
        fan["target_rpm"] = int(fan["min_rpm"] + (fan["max_rpm"] - fan["min_rpm"]) * pwm_ratio)
        fan["last_update"] = time.time()

        logger.debug(f"Set {fan_id} PWM to {pwm_percent}% (target RPM: {fan['target_rpm']})")
        return True

    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get simulated temperature."""
        return self._temps.get(sensor_id)

    async def get_available_temp_sensors(self) -> List[TempSensorData]:
        """List simulated temperature sensors."""
        self._update_simulated_state()
        return [
            TempSensorData(
                sensor_id="dev_cpu_temp",
                device_name="k10temp (Simulated)",
                label="Tctl",
                is_cpu_sensor=True,
                current_temp=self._temps.get("dev_cpu_temp"),
            ),
            TempSensorData(
                sensor_id="dev_package_temp",
                device_name="k10temp (Simulated)",
                label="Tccd1",
                is_cpu_sensor=True,
                current_temp=self._temps.get("dev_package_temp"),
            ),
            TempSensorData(
                sensor_id="dev_ambient_temp",
                device_name="it8688e (Simulated)",
                label="Board",
                is_cpu_sensor=False,
                current_temp=self._temps.get("dev_ambient_temp"),
            ),
        ]

    def _update_simulated_state(self):
        """Update simulated fan RPM and temperatures with realistic behavior."""
        current_time = time.time()

        # Simulate temperature fluctuations based on CPU usage
        base_cpu_temp = 45.0 + random.uniform(-3, 5)
        self._temps["dev_cpu_temp"] = base_cpu_temp
        self._temps["dev_package_temp"] = base_cpu_temp - 3 + random.uniform(-2, 2)
        self._temps["dev_ambient_temp"] = 35.0 + random.uniform(-1, 2)

        # Update fan RPM with latency and fluctuation
        for fan_id, fan_data in self._fans.items():
            elapsed = current_time - fan_data["last_update"]

            # Gradual RPM transition (2-3 second lag)
            if fan_data["current_rpm"] != fan_data["target_rpm"]:
                rpm_diff = fan_data["target_rpm"] - fan_data["current_rpm"]
                rpm_change = rpm_diff * min(elapsed / 2.5, 1.0)  # 2.5s to reach target
                fan_data["current_rpm"] = int(fan_data["current_rpm"] + rpm_change)

            # Add realistic RPM fluctuation (±30 RPM)
            fluctuation = random.randint(-30, 30)
            fan_data["current_rpm"] = max(
                fan_data["min_rpm"],
                min(fan_data["max_rpm"], fan_data["current_rpm"] + fluctuation)
            )

    def _get_default_curve(self) -> List[FanCurvePoint]:
        """Get default temperature-PWM curve."""
        return [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
            FanCurvePoint(temp=70, pwm=80),
            FanCurvePoint(temp=85, pwm=100),
        ]
