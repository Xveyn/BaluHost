"""
Fan control service for PWM fan management.

Supports both Linux hardware (via hwmon sysfs) and development simulation.
Backend implementations are in fan_backend_dev.py and fan_backend_linux.py.
"""
import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, desc, func

from app.core.config import Settings
from app.models.fans import FanConfig, FanSample
from app.schemas.fans import FanMode, FanCurvePoint
from app.services.power.fan_schedule import FanScheduleService
from app.services.power.fan_profiles import FanProfileService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------

@dataclass
class FanData:
    """Current fan state data."""
    fan_id: str
    name: str
    rpm: Optional[int]
    pwm_percent: int
    temperature_celsius: Optional[float]
    mode: FanMode
    min_pwm_percent: int
    max_pwm_percent: int
    emergency_temp_celsius: float
    temp_sensor_id: Optional[str]
    curve_points: List[FanCurvePoint]
    is_active: bool
    hysteresis_celsius: float = 3.0


@dataclass
class HysteresisState:
    """State for hysteresis tracking per fan."""
    last_pwm: int
    last_pwm_temp: float
    last_update: float


@dataclass
class TempSensorData:
    """Temperature sensor information."""
    sensor_id: str
    device_name: str
    label: Optional[str]
    is_cpu_sensor: bool
    current_temp: Optional[float]


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------

class FanControlBackend(ABC):
    """Abstract base class for fan control backends."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        pass

    @abstractmethod
    async def get_fans(self) -> List[FanData]:
        """Get list of all available fans with current state."""
        pass

    @abstractmethod
    async def set_pwm(self, fan_id: str, pwm_percent: int) -> bool:
        """
        Set PWM value for a fan.

        Args:
            fan_id: Fan identifier
            pwm_percent: PWM percentage (0-100)

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get temperature reading from a sensor."""
        pass

    @abstractmethod
    async def get_available_temp_sensors(self) -> List[TempSensorData]:
        """List all available temperature sensors."""
        pass


# Re-export backend classes for backward compatibility
from app.services.power.fan_backend_dev import DevFanControlBackend  # noqa: E402
from app.services.power.fan_backend_linux import LinuxFanControlBackend  # noqa: E402


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FanControlService:
    """Singleton service for managing fan control."""

    _instance: Optional["FanControlService"] = None
    _lock = asyncio.Lock()

    def __init__(self, config: Settings, db_session_factory):
        if FanControlService._instance is not None:
            raise RuntimeError("FanControlService already initialized. Use get_instance().")

        self.config = config
        self.db_session_factory = db_session_factory
        self._backend: Optional[FanControlBackend] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._sample_buffer: deque = deque(maxlen=120)  # 10 minutes at 5s interval
        self._is_running = False
        self._use_linux_backend = False
        self._hysteresis_state: Dict[str, HysteresisState] = {}  # Track hysteresis per fan
        self._schedule = FanScheduleService(db_session_factory)
        self._profiles = FanProfileService(db_session_factory)

        FanControlService._instance = self

    @property
    def schedule(self) -> FanScheduleService:
        """Access the fan schedule service."""
        return self._schedule

    @property
    def profiles(self) -> FanProfileService:
        """Access the fan profile service."""
        return self._profiles

    @classmethod
    async def get_instance(cls, config: Optional[Settings] = None, db_session_factory=None) -> "FanControlService":
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                if config is None or db_session_factory is None:
                    raise RuntimeError("FanControlService not initialized")
                cls._instance = cls(config, db_session_factory)
            return cls._instance

    async def start(self, monitoring: bool = True):
        """Start fan control service.

        Args:
            monitoring: If True, start the monitoring loop (primary worker).
                        If False, only initialize backend + configs (secondary workers).
        """
        if not self.config.fan_control_enabled:
            logger.info("Fan control disabled in config")
            return

        # Initialize backend
        await self._initialize_backend()

        if not self._backend:
            logger.warning("No fan control backend available")
            return

        # Load fan configs from database
        await self._load_fan_configs()

        if monitoring:
            # Start monitoring loop (primary worker only)
            self._is_running = True
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Fan control service started (monitoring=%s)", monitoring)

    async def stop(self):
        """Stop fan control service."""
        self._is_running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Fan control service stopped")

    async def _initialize_backend(self):
        """Initialize appropriate backend."""
        # Check if forcing dev backend
        if self.config.fan_force_dev_backend or self.config.is_dev_mode:
            logger.info("Using dev fan control backend (simulated)")
            self._backend = DevFanControlBackend(self.config)
            self._use_linux_backend = False
            return

        # Try Linux backend
        linux_backend = LinuxFanControlBackend(self.config)
        if await linux_backend.is_available():
            logger.info("Using Linux fan control backend (hardware)")
            self._backend = linux_backend
            self._use_linux_backend = True
        else:
            logger.info("Linux backend unavailable, using dev backend")
            self._backend = DevFanControlBackend(self.config)
            self._use_linux_backend = False

    async def _load_fan_configs(self):
        """Load fan configurations from database.

        Also auto-corrects temp_sensor_id if it points to a non-CPU sensor
        and a CPU sensor is available (fixes board sensor ~26°C bug).
        """
        if not self._backend:
            return

        fans = await self._backend.get_fans()

        # Determine best CPU sensor for auto-correction
        cpu_sensor_id: Optional[str] = None
        sensors: List[TempSensorData] = []
        try:
            sensors = await self._backend.get_available_temp_sensors()
            for s in sensors:
                if s.is_cpu_sensor:
                    cpu_sensor_id = s.sensor_id
                    break
        except Exception:
            pass

        # Build set of known CPU sensor IDs for checking existing configs
        cpu_sensor_ids: set = set()
        if cpu_sensor_id:
            for s in sensors:
                if s.is_cpu_sensor:
                    cpu_sensor_ids.add(s.sensor_id)

        with self.db_session_factory() as db:
            for fan in fans:
                existing = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()

                if not existing:
                    # Create new config with CPU sensor if available
                    config = FanConfig(
                        fan_id=fan.fan_id,
                        name=fan.name,
                        mode=FanMode.AUTO.value,
                        curve_json=json.dumps([p.model_dump() for p in fan.curve_points]),
                        min_pwm_percent=fan.min_pwm_percent,
                        max_pwm_percent=fan.max_pwm_percent,
                        emergency_temp_celsius=fan.emergency_temp_celsius,
                        temp_sensor_id=cpu_sensor_id or fan.temp_sensor_id,
                        is_active=True,
                    )
                    db.add(config)
                elif cpu_sensor_id and existing.temp_sensor_id not in cpu_sensor_ids:
                    # Auto-correct: existing config uses non-CPU sensor
                    old_sensor = existing.temp_sensor_id
                    existing.temp_sensor_id = cpu_sensor_id
                    logger.info(
                        f"Auto-corrected {fan.fan_id} temp sensor: "
                        f"{old_sensor} → {cpu_sensor_id}"
                    )

            db.commit()

        logger.info(f"Loaded {len(fans)} fan configuration(s)")

    async def _monitoring_loop(self):
        """Background monitoring loop."""
        logger.info("Fan control monitoring loop started")
        sample_count = 0

        while self._is_running:
            try:
                await self._monitor_and_control_fans()

                sample_count += 1

                # Persist to DB every 12 samples (1 minute at 5s interval)
                if sample_count % 12 == 0:
                    await self._persist_samples()

                await asyncio.sleep(self.config.fan_sample_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in fan monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.config.fan_sample_interval_seconds)

    async def _monitor_and_control_fans(self):
        """Monitor and control fans based on configuration."""
        if not self._backend:
            return

        fans = await self._backend.get_fans()

        with self.db_session_factory() as db:
            for fan in fans:
                # Get config from DB
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()

                if not config or not config.is_active:
                    continue

                mode = FanMode(config.mode)
                temperature = await self._backend.get_temperature(config.temp_sensor_id)

                # Determine target PWM
                target_pwm = fan.pwm_percent

                if mode in (FanMode.AUTO, FanMode.SCHEDULED):
                    if temperature is not None:
                        # Check emergency condition
                        if temperature >= config.emergency_temp_celsius:
                            target_pwm = 100
                            mode = FanMode.EMERGENCY
                            # Clear hysteresis state on emergency
                            if fan.fan_id in self._hysteresis_state:
                                del self._hysteresis_state[fan.fan_id]
                            # Emit critical temperature notification
                            try:
                                from app.services.notifications.events import emit_temperature_critical_sync
                                emit_temperature_critical_sync(
                                    config.temp_sensor_id or fan.fan_id,
                                    temperature,
                                )
                            except Exception:
                                pass
                        elif temperature >= config.emergency_temp_celsius - 10:
                            # Warning threshold: 10 degrees below emergency
                            try:
                                from app.services.notifications.events import emit_temperature_high_sync
                                emit_temperature_high_sync(
                                    config.temp_sensor_id or fan.fan_id,
                                    temperature,
                                )
                            except Exception:
                                pass
                        else:
                            # Resolve curve: scheduled mode uses time-based curve, auto uses default
                            if FanMode(config.mode) == FanMode.SCHEDULED:
                                curve_points, _ = self._schedule.resolve_active_curve(
                                    fan.fan_id, config.curve_json, db
                                )
                            else:
                                curve_points = json.loads(config.curve_json) if config.curve_json else []

                            hysteresis = getattr(config, 'hysteresis_celsius', 3.0)
                            target_pwm = self._calculate_pwm_with_hysteresis(
                                fan.fan_id,
                                temperature,
                                curve_points,
                                hysteresis,
                                fan.pwm_percent
                            )

                # Apply minimum PWM
                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                # Set PWM if changed
                if target_pwm != fan.pwm_percent:
                    await self._backend.set_pwm(fan.fan_id, target_pwm)

                # Update mode in config if emergency
                if mode == FanMode.EMERGENCY and config.mode != FanMode.EMERGENCY.value:
                    config.mode = FanMode.EMERGENCY.value
                    db.commit()

                # Add sample to buffer
                self._sample_buffer.append({
                    "timestamp": datetime.now(timezone.utc),
                    "fan_id": fan.fan_id,
                    "pwm_percent": target_pwm,
                    "rpm": fan.rpm,
                    "temperature_celsius": temperature,
                    "mode": mode.value,
                })

    def _calculate_pwm_from_curve(self, temperature: float, curve_points: List[dict]) -> int:
        """Calculate PWM from temperature using curve interpolation."""
        if not curve_points or len(curve_points) < 2:
            return 50  # Default

        # Sort points by temperature
        points = sorted(curve_points, key=lambda p: p["temp"])

        # Below minimum temp
        if temperature <= points[0]["temp"]:
            return points[0]["pwm"]

        # Above maximum temp
        if temperature >= points[-1]["temp"]:
            return points[-1]["pwm"]

        # Linear interpolation
        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i + 1]

            if p1["temp"] <= temperature <= p2["temp"]:
                # Linear interpolation
                temp_ratio = (temperature - p1["temp"]) / (p2["temp"] - p1["temp"])
                pwm = p1["pwm"] + (p2["pwm"] - p1["pwm"]) * temp_ratio
                return round(pwm)

        return 50  # Fallback

    def _calculate_pwm_with_hysteresis(
        self,
        fan_id: str,
        temperature: float,
        curve_points: List[dict],
        hysteresis: float,
        current_pwm: int
    ) -> int:
        """
        Calculate PWM with hysteresis to prevent oscillation.

        Args:
            fan_id: Fan identifier for state tracking
            temperature: Current temperature
            curve_points: Fan curve definition
            hysteresis: Hysteresis value in Celsius
            current_pwm: Current PWM percentage

        Returns:
            Target PWM percentage with hysteresis applied
        """
        target_pwm = self._calculate_pwm_from_curve(temperature, curve_points)
        current_time = time.time()

        # Get or initialize hysteresis state
        if fan_id not in self._hysteresis_state:
            self._hysteresis_state[fan_id] = HysteresisState(
                last_pwm=current_pwm,
                last_pwm_temp=temperature,
                last_update=current_time
            )
            return target_pwm

        state = self._hysteresis_state[fan_id]

        if target_pwm > state.last_pwm:
            # Temperature rising - respond immediately for safety
            state.last_pwm = target_pwm
            state.last_pwm_temp = temperature
            state.last_update = current_time
            return target_pwm

        elif target_pwm < state.last_pwm:
            # Temperature falling - only reduce PWM if temp dropped by hysteresis amount
            if temperature <= (state.last_pwm_temp - hysteresis):
                state.last_pwm = target_pwm
                state.last_pwm_temp = temperature
                state.last_update = current_time
                return target_pwm
            else:
                # Keep current PWM (within hysteresis deadband)
                return state.last_pwm

        # PWM unchanged
        return state.last_pwm

    async def _persist_samples(self):
        """Persist buffered samples to database."""
        if not self._sample_buffer:
            return

        samples_to_save = list(self._sample_buffer)
        self._sample_buffer.clear()

        with self.db_session_factory() as db:
            for sample in samples_to_save:
                db_sample = FanSample(**sample)
                db.add(db_sample)

            db.commit()

        logger.debug(f"Persisted {len(samples_to_save)} fan sample(s)")

    async def get_status(self) -> Dict:
        """Get current fan status."""
        if not self._backend:
            return {
                "fans": [],
                "is_dev_mode": self.config.is_dev_mode,
                "is_using_linux_backend": self._use_linux_backend,
                "permission_status": "unavailable",
                "backend_available": False,
            }

        fans = await self._backend.get_fans()

        # Load configs from DB
        with self.db_session_factory() as db:
            fan_data_list = []

            for fan in fans:
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()

                if config:
                    curve_points = json.loads(config.curve_json) if config.curve_json else []

                    # Use config's temp sensor for display (may differ from scan sensor)
                    display_temp = fan.temperature_celsius
                    if config.temp_sensor_id:
                        try:
                            sensor_temp = await self._backend.get_temperature(config.temp_sensor_id)
                            if sensor_temp is not None:
                                display_temp = sensor_temp
                        except Exception:
                            pass  # Keep fan.temperature_celsius as fallback

                    fan_entry = {
                        "fan_id": fan.fan_id,
                        "name": config.name,
                        "rpm": fan.rpm,
                        "pwm_percent": fan.pwm_percent,
                        "temperature_celsius": display_temp,
                        "mode": config.mode,
                        "is_active": config.is_active,
                        "min_pwm_percent": config.min_pwm_percent,
                        "max_pwm_percent": config.max_pwm_percent,
                        "emergency_temp_celsius": config.emergency_temp_celsius,
                        "temp_sensor_id": config.temp_sensor_id,
                        "curve_points": curve_points,
                        "hysteresis_celsius": getattr(config, 'hysteresis_celsius', 3.0),
                    }

                    # Add schedule info for scheduled mode
                    if config.mode == FanMode.SCHEDULED.value:
                        _, active_entry = self._schedule.resolve_active_curve(
                            fan.fan_id, config.curve_json, db
                        )
                        if active_entry:
                            fan_entry["active_schedule"] = {
                                "id": active_entry.id,
                                "name": active_entry.name,
                                "start_time": active_entry.start_time,
                                "end_time": active_entry.end_time,
                            }

                    fan_data_list.append(fan_entry)
                else:
                    # No DB config yet (first discovery or hwmon index changed)
                    # Include with defaults so the fan isn't silently dropped
                    fan_data_list.append({
                        "fan_id": fan.fan_id,
                        "name": fan.name,
                        "rpm": fan.rpm,
                        "pwm_percent": fan.pwm_percent,
                        "temperature_celsius": fan.temperature_celsius,
                        "mode": FanMode.MANUAL.value,
                        "is_active": True,
                        "min_pwm_percent": 0,
                        "max_pwm_percent": 100,
                        "emergency_temp_celsius": 85.0,
                        "temp_sensor_id": fan.temp_sensor_id,
                        "curve_points": [],
                        "hysteresis_celsius": 3.0,
                    })

        # Determine permission status
        permission_status = "ok"
        if self._use_linux_backend:
            if isinstance(self._backend, LinuxFanControlBackend):
                permission_status = "ok" if self._backend._has_write_permission else "readonly"

        return {
            "fans": fan_data_list,
            "is_dev_mode": self.config.is_dev_mode,
            "is_using_linux_backend": self._use_linux_backend,
            "permission_status": permission_status,
            "backend_available": True,
        }

    async def set_fan_mode(self, fan_id: str, mode: FanMode) -> bool:
        """Set fan operation mode."""
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                logger.warning(f"Fan config not found: {fan_id}")
                return False

            config.mode = mode.value
            db.commit()

        logger.info(f"Set {fan_id} mode to {mode.value}")
        return True

    async def set_fan_pwm(self, fan_id: str, pwm_percent: int) -> Tuple[bool, Optional[int]]:
        """Set manual PWM value."""
        if not self._backend:
            return False, None

        # Check if in manual mode
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return False, None

            if config.mode != FanMode.MANUAL.value:
                logger.warning(f"Cannot set PWM for {fan_id} in {config.mode} mode")
                return False, None

            # Apply min/max limits
            pwm_percent = max(config.min_pwm_percent, min(config.max_pwm_percent, pwm_percent))

        # Set PWM
        success = await self._backend.set_pwm(fan_id, pwm_percent)

        # Read back RPM
        rpm = None
        if success:
            fans = await self._backend.get_fans()
            for fan in fans:
                if fan.fan_id == fan_id:
                    rpm = fan.rpm
                    break

        return success, rpm

    async def update_fan_curve(self, fan_id: str, curve_points: List[FanCurvePoint]) -> bool:
        """Update fan temperature curve."""
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return False

            # Serialize curve
            curve_json = json.dumps([p.model_dump() for p in curve_points])
            config.curve_json = curve_json
            db.commit()

        logger.info(f"Updated curve for {fan_id} with {len(curve_points)} point(s)")
        return True

    async def get_available_temp_sensors(self) -> List["TempSensorData"]:
        """Get all available temperature sensors from the backend."""
        if not self._backend:
            return []
        return await self._backend.get_available_temp_sensors()

    async def get_history(
        self,
        fan_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[FanSample], int]:
        """Get historical fan samples."""
        with self.db_session_factory() as db:
            query = select(FanSample)

            if fan_id:
                query = query.where(FanSample.fan_id == fan_id)

            # Get total count
            count_query = select(FanSample)
            if fan_id:
                count_query = count_query.where(FanSample.fan_id == fan_id)
            total_count = db.execute(select(func.count()).select_from(count_query.subquery())).scalar()

            # Get samples
            query = query.order_by(desc(FanSample.timestamp)).limit(limit).offset(offset)
            samples = db.execute(query).scalars().all()

            return list(samples), total_count or 0

    async def switch_backend(self, use_linux: bool) -> Tuple[bool, bool]:
        """
        Switch between Linux and dev backend.

        Returns:
            (success, is_using_linux_backend)
        """
        if use_linux:
            # Try to switch to Linux backend
            linux_backend = LinuxFanControlBackend(self.config)
            if await linux_backend.is_available():
                self._backend = linux_backend
                self._use_linux_backend = True
                await self._load_fan_configs()
                logger.info("Switched to Linux fan control backend")
                return True, True
            else:
                logger.warning("Linux backend not available")
                return False, self._use_linux_backend
        else:
            # Switch to dev backend
            self._backend = DevFanControlBackend(self.config)
            self._use_linux_backend = False
            await self._load_fan_configs()
            logger.info("Switched to dev fan control backend")
            return True, False

    # --- Delegating methods for backward compatibility ---

    async def get_schedule_entries(self, fan_id: str):
        return await self._schedule.get_schedule_entries(fan_id)

    async def create_schedule_entry(self, fan_id: str, name: str, start_time: str, end_time: str, **kwargs):
        return await self._schedule.create_schedule_entry(fan_id, name, start_time, end_time, **kwargs)

    async def update_schedule_entry(self, fan_id: str, entry_id: int, **kwargs):
        return await self._schedule.update_schedule_entry(fan_id, entry_id, **kwargs)

    async def delete_schedule_entry(self, fan_id: str, entry_id: int) -> bool:
        return await self._schedule.delete_schedule_entry(fan_id, entry_id)

    async def get_active_schedule_entry(self, fan_id: str):
        return await self._schedule.get_active_schedule_entry(fan_id)

    async def list_profiles(self):
        return await self._profiles.list_profiles()

    async def get_profile(self, profile_id: int):
        return await self._profiles.get_profile(profile_id)

    async def create_profile(self, name: str, curve_points, description=None):
        return await self._profiles.create_profile(name, curve_points, description)

    async def update_profile(self, profile_id: int, **kwargs):
        return await self._profiles.update_profile(profile_id, **kwargs)

    async def delete_profile(self, profile_id: int) -> bool:
        return await self._profiles.delete_profile(profile_id)

    async def apply_profile_to_fan(self, fan_id: str, profile_id: int):
        result = await self._profiles.apply_profile_to_fan(fan_id, profile_id)
        if result[0] and fan_id in self._hysteresis_state:
            del self._hysteresis_state[fan_id]
        return result

    async def apply_preset(self, fan_id: str, preset_name: str):
        result = await self._profiles.apply_preset(fan_id, preset_name)
        if result[0] and fan_id in self._hysteresis_state:
            del self._hysteresis_state[fan_id]
        return result

    async def update_fan_config(
        self,
        fan_id: str,
        hysteresis_celsius: Optional[float] = None,
        min_pwm_percent: Optional[int] = None,
        max_pwm_percent: Optional[int] = None,
        emergency_temp_celsius: Optional[float] = None,
        temp_sensor_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Update fan configuration.

        Args:
            fan_id: Fan identifier
            hysteresis_celsius: Temperature hysteresis (0-15°C)
            min_pwm_percent: Minimum PWM percentage
            max_pwm_percent: Maximum PWM percentage
            emergency_temp_celsius: Emergency temperature threshold
            temp_sensor_id: Temperature sensor to use for this fan

        Returns:
            Updated configuration dict or None if fan not found
        """
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return None

            # Update provided values
            if hysteresis_celsius is not None:
                config.hysteresis_celsius = hysteresis_celsius
                # Clear hysteresis state when hysteresis value changes
                if fan_id in self._hysteresis_state:
                    del self._hysteresis_state[fan_id]

            if min_pwm_percent is not None:
                config.min_pwm_percent = min_pwm_percent

            if max_pwm_percent is not None:
                config.max_pwm_percent = max_pwm_percent

            if emergency_temp_celsius is not None:
                config.emergency_temp_celsius = emergency_temp_celsius

            if temp_sensor_id is not None:
                config.temp_sensor_id = temp_sensor_id

            db.commit()

            logger.info(f"Updated config for {fan_id}: hysteresis={config.hysteresis_celsius}°C")

            return {
                "fan_id": fan_id,
                "hysteresis_celsius": config.hysteresis_celsius,
                "min_pwm_percent": config.min_pwm_percent,
                "max_pwm_percent": config.max_pwm_percent,
                "emergency_temp_celsius": config.emergency_temp_celsius,
                "temp_sensor_id": config.temp_sensor_id,
            }


# Global service instance
_fan_control_service: Optional[FanControlService] = None


def get_fan_control_service() -> FanControlService:
    """Get the singleton FanControlService instance."""
    global _fan_control_service
    if _fan_control_service is None:
        from app.core.config import get_settings
        from app.core.database import SessionLocal
        settings = get_settings()
        _fan_control_service = FanControlService(settings, SessionLocal)
    return _fan_control_service


async def start_fan_control(monitoring: bool = True) -> None:
    """Start the fan control service.

    Args:
        monitoring: If True, start the monitoring loop (primary worker).
                    If False, only initialize backend + configs (secondary workers).
    """
    service = get_fan_control_service()
    await service.start(monitoring=monitoring)


async def stop_fan_control() -> None:
    """Stop the fan control service."""
    global _fan_control_service
    if _fan_control_service is not None:
        await _fan_control_service.stop()
        _fan_control_service = None


def get_service_status() -> dict:
    """
    Get fan control service status for admin dashboard.

    Returns:
        Dict with service status information
    """
    from app.core.config import get_settings

    settings = get_settings()

    if _fan_control_service is None:
        return {
            "is_running": False,
            "started_at": None,
            "uptime_seconds": None,
            "sample_count": 0,
            "error_count": 0,
            "last_error": None,
            "last_error_at": None,
            "interval_seconds": settings.fan_sample_interval_seconds,
            "config_enabled": settings.fan_control_enabled,
        }

    service = _fan_control_service
    is_running = service._is_running and service._monitoring_task is not None

    return {
        "is_running": is_running,
        "started_at": None,  # Not tracked by fan control service
        "uptime_seconds": None,
        "sample_count": len(service._sample_buffer),
        "error_count": 0,  # Not tracked separately
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": service.config.fan_sample_interval_seconds,
        "config_enabled": service.config.fan_control_enabled,
        "backend_type": "linux" if service._use_linux_backend else "dev",
    }
