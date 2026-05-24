"""
Fan control service for PWM fan management.

Supports both Linux hardware (via hwmon sysfs) and development simulation.
Backend implementations are in fan_backend_dev.py and fan_backend_linux.py.
"""
import asyncio
import json
import logging
import time
import time as _time
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
from app.services.power.fan_sources import (
    TempSourceRegistry, HwmonTempSource, GpuTempSource, DiskTempSource, MixTempSource,
)
from app.services.power.fan_curve_eval import evaluate_curve

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
    # GPU recognition + write diagnostics
    is_gpu_fan: bool = False
    gpu_vendor: Optional[str] = None
    device_driver: Optional[str] = None
    last_write_error: Optional[str] = None


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
        self._registry: TempSourceRegistry = TempSourceRegistry()
        self._last_pwm_by_fan: Dict[str, int] = {}
        self._last_tick_ts: float = 0.0

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

        await self._rebuild_registry()

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

        For new fans (first discovery), assigns the best available CPU sensor
        as the default temp_sensor_id. Existing configs are NOT modified —
        user-chosen sensors (including composite sensors) survive service restarts.
        """
        if not self._backend:
            return

        fans = await self._backend.get_fans()

        # Determine best CPU sensor for new fan defaults only
        cpu_sensor_id: Optional[str] = None
        try:
            sensors = await self._backend.get_available_temp_sensors()
            for s in sensors:
                if s.is_cpu_sensor:
                    cpu_sensor_id = s.sensor_id
                    break
        except Exception:
            pass

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

            db.commit()

        logger.info(f"Loaded {len(fans)} fan configuration(s)")

    async def _rebuild_registry(self) -> None:
        """(Re)populate the registry with all current sources."""
        self._registry.clear()
        if not self._backend:
            return

        # hwmon sensors (from backend). amdgpu/nouveau entries are skipped —
        # the same physical sensors are exposed via the gpu:* namespace below,
        # which is the canonical source. Listing both would show every GPU
        # temperature twice in the SensorsPanel.
        _GPU_DRIVERS = {"amdgpu", "nouveau"}
        try:
            hwmon_sensors = await self._backend.get_available_temp_sensors()
            for s in hwmon_sensors:
                if s.device_name in _GPU_DRIVERS:
                    continue
                sid = s.sensor_id
                src = HwmonTempSource(
                    sensor_id=sid,
                    device_name=s.device_name,
                    backend_label=s.label,
                    is_cpu_sensor=s.is_cpu_sensor,
                    read_fn=self._make_hwmon_reader(sid),
                )
                self._registry.register(src)
        except Exception as exc:
            logger.debug("hwmon source registration failed: %s", exc)

        # GPU sources from monitoring SHM
        for channel in ("edge", "junction", "mem"):
            self._registry.register(GpuTempSource(
                channel=channel,
                read_fn=self._make_gpu_reader(channel),
            ))

        # Disk sources from SMART cache
        for device in await self._list_smart_devices():
            self._registry.register(DiskTempSource(
                device=device,
                read_fn=self._make_disk_reader(device),
            ))

        # Composite sensors from DB
        await self._register_composites_from_db()

        # Custom labels from DB
        await self._load_sensor_labels()

    def _make_hwmon_reader(self, sensor_id: str):
        async def _read():
            try:
                return await self._backend.get_temperature(sensor_id)
            except Exception:
                return None
        return _read

    def _make_gpu_reader(self, channel: str):
        async def _read():
            from app.services.monitoring.shm import read_shm, TELEMETRY_FILE
            data = read_shm(TELEMETRY_FILE, max_age_seconds=30.0)
            if not data:
                return None
            gpu = data.get("gpu") if isinstance(data, dict) else None
            if not gpu:
                return None
            key = {
                "edge": "temperature_edge_celsius",
                "junction": "temperature_junction_celsius",
                "mem": "temperature_memory_celsius",
            }[channel]
            v = gpu.get(key)
            return float(v) if v is not None else None
        return _read

    def _read_smart_summary(self) -> Dict[str, float]:
        """Read disk SMART summary from SHM, return {device_name: temp_celsius}.

        Empty dict when SHM file missing, stale, or malformed. The monitoring
        worker publishes this file every 60s via _write_smart_summary_snapshot.
        """
        try:
            from app.services.monitoring.shm import read_shm, SMART_SUMMARY_FILE
            payload = read_shm(SMART_SUMMARY_FILE, max_age_seconds=180.0)
            if not payload:
                return {}
            out: Dict[str, float] = {}
            for d in payload.get("devices", []) or []:
                name = d.get("name")
                temp = d.get("temperature_celsius")
                if name and temp is not None:
                    out[name] = float(temp)
            return out
        except Exception:
            return {}

    def _make_disk_reader(self, device: str):
        async def _read():
            return self._read_smart_summary().get(device)
        return _read

    async def _list_smart_devices(self) -> List[str]:
        return list(self._read_smart_summary().keys())

    async def _refresh_disk_sources(self) -> None:
        """Reconcile disk:* registry entries with the current SMART summary.

        Adds new disks that appeared and removes ones that vanished, without
        touching hwmon/gpu/mix sources. Called from the sensor-list endpoint
        so the UI reflects fresh data without a full registry rebuild.
        """
        desired = set(self._read_smart_summary().keys())
        current = {
            s.id for s in self._registry.all_sources() if s.kind == "disk"
        }

        for device in desired:
            sid = f"disk:{device}"
            if sid not in current:
                self._registry.register(DiskTempSource(
                    device=device,
                    read_fn=self._make_disk_reader(device),
                ))

        for sid in current - {f"disk:{d}" for d in desired}:
            self._registry.unregister(sid)

    async def _register_composites_from_db(self) -> None:
        from app.models.fans import CompositeTempSensor
        with self.db_session_factory() as db:
            rows = db.execute(select(CompositeTempSensor)).scalars().all()
            for row in rows:
                try:
                    source_ids = json.loads(row.source_ids_json)
                except Exception:
                    continue
                self._registry.register(MixTempSource(
                    composite_id=row.id,
                    name=row.name,
                    function=row.function,
                    source_ids=source_ids,
                    registry=self._registry,
                ))

    async def _load_sensor_labels(self) -> None:
        from app.models.fans import TempSensorLabel
        with self.db_session_factory() as db:
            for row in db.execute(select(TempSensorLabel)).scalars().all():
                self._registry.set_label(row.sensor_id, row.custom_label)

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
        now_ts = _time.time()
        dt = (now_ts - self._last_tick_ts) if self._last_tick_ts else self.config.fan_sample_interval_seconds
        self._last_tick_ts = now_ts

        # Map for sync curve type
        other_fan_pwms = {f.fan_id: f.pwm_percent for f in fans}

        with self.db_session_factory() as db:
            for fan in fans:
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()
                if not config or not config.is_active:
                    continue

                mode = FanMode(config.mode)
                temperature = await self._registry.get_temp(config.temp_sensor_id) if config.temp_sensor_id else None

                target_pwm = fan.pwm_percent

                if mode in (FanMode.AUTO, FanMode.SCHEDULED):
                    if temperature is not None and temperature >= config.emergency_temp_celsius:
                        target_pwm = 100
                        mode = FanMode.EMERGENCY
                        if fan.fan_id in self._hysteresis_state:
                            del self._hysteresis_state[fan.fan_id]
                        try:
                            from app.services.notifications.events import emit_temperature_critical_sync
                            emit_temperature_critical_sync(config.temp_sensor_id or fan.fan_id, temperature)
                        except Exception:
                            pass
                    else:
                        if temperature is not None and temperature >= config.emergency_temp_celsius - 10:
                            try:
                                from app.services.notifications.events import emit_temperature_high_sync
                                emit_temperature_high_sync(config.temp_sensor_id or fan.fan_id, temperature)
                            except Exception:
                                pass

                        # Schedule override of curve_json (graph mode only)
                        curve_json = config.curve_json
                        if FanMode(config.mode) == FanMode.SCHEDULED:
                            scheduled_pts, _ = self._schedule.resolve_active_curve(
                                fan.fan_id, config.curve_json, db
                            )
                            curve_json = json.dumps([p if isinstance(p, dict) else p.model_dump() for p in scheduled_pts]) if scheduled_pts else config.curve_json

                        eval_cfg = type("CfgView", (), {
                            **{c.name: getattr(config, c.name) for c in config.__table__.columns},
                            "curve_json": curve_json,
                        })()

                        prev = self._last_pwm_by_fan.get(fan.fan_id, fan.pwm_percent)

                        def _profile_loader(pid: Optional[int]) -> List[dict]:
                            if pid is None:
                                return []
                            from app.models.fans import FanCurveProfile
                            row = db.execute(select(FanCurveProfile).where(FanCurveProfile.id == pid)).scalar_one_or_none()
                            if row is None or not row.curve_json:
                                return []
                            try:
                                return json.loads(row.curve_json)
                            except Exception:
                                return []

                        target_pwm = evaluate_curve(
                            eval_cfg, temperature, prev, other_fan_pwms, _profile_loader, dt,
                        )
                        # Hysteresis layered on top (existing helper, only for graph-like outputs)
                        target_pwm = self._calculate_pwm_with_hysteresis(
                            fan.fan_id, temperature or 0.0, [],
                            getattr(config, "hysteresis_celsius", 3.0), target_pwm,
                        ) if eval_cfg.curve_type == "graph" else target_pwm

                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                if target_pwm != fan.pwm_percent:
                    await self._backend.set_pwm(fan.fan_id, target_pwm)
                self._last_pwm_by_fan[fan.fan_id] = target_pwm

                if mode == FanMode.EMERGENCY and config.mode != FanMode.EMERGENCY.value:
                    config.mode = FanMode.EMERGENCY.value
                    db.commit()

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
                        "is_gpu_fan": fan.is_gpu_fan,
                        "gpu_vendor": fan.gpu_vendor,
                        "last_write_error": fan.last_write_error,
                        "curve_type": getattr(config, "curve_type", "graph"),
                        "flat_pwm_percent": getattr(config, "flat_pwm_percent", None),
                        "target_temp_celsius": getattr(config, "target_temp_celsius", None),
                        "target_pwm_percent": getattr(config, "target_pwm_percent", None),
                        "mix_curve_a_id": getattr(config, "mix_curve_a_id", None),
                        "mix_curve_b_id": getattr(config, "mix_curve_b_id", None),
                        "mix_function": getattr(config, "mix_function", None),
                        "sync_fan_id": getattr(config, "sync_fan_id", None),
                        "start_pwm_percent": getattr(config, "start_pwm_percent", None),
                        "stop_below_temp_celsius": getattr(config, "stop_below_temp_celsius", None),
                        "response_time_seconds": getattr(config, "response_time_seconds", 0.0),
                        "pwm_steps": getattr(config, "pwm_steps", 1),
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
                        "is_gpu_fan": fan.is_gpu_fan,
                        "gpu_vendor": fan.gpu_vendor,
                        "last_write_error": fan.last_write_error,
                        "curve_type": "graph",
                        "flat_pwm_percent": None,
                        "target_temp_celsius": None,
                        "target_pwm_percent": None,
                        "mix_curve_a_id": None,
                        "mix_curve_b_id": None,
                        "mix_function": None,
                        "sync_fan_id": None,
                        "start_pwm_percent": None,
                        "stop_below_temp_celsius": None,
                        "response_time_seconds": 0.0,
                        "pwm_steps": 1,
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
        curve_type: Optional[str] = None,
        flat_pwm_percent: Optional[int] = None,
        target_temp_celsius: Optional[float] = None,
        target_pwm_percent: Optional[int] = None,
        mix_curve_a_id: Optional[int] = None,
        mix_curve_b_id: Optional[int] = None,
        mix_function: Optional[str] = None,
        sync_fan_id: Optional[str] = None,
        start_pwm_percent: Optional[int] = None,
        stop_below_temp_celsius: Optional[float] = None,
        response_time_seconds: Optional[float] = None,
        pwm_steps: Optional[int] = None,
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
            curve_type: Curve type (graph|flat|target|mix|sync)
            flat_pwm_percent: Fixed PWM percent for flat curve type
            target_temp_celsius: Target temperature for target curve type
            target_pwm_percent: Target PWM percent for target curve type
            mix_curve_a_id: First profile ID for mix curve type
            mix_curve_b_id: Second profile ID for mix curve type
            mix_function: Mix function (max|sum)
            sync_fan_id: Fan ID to sync with for sync curve type
            start_pwm_percent: Minimum PWM at fan start
            stop_below_temp_celsius: Temperature below which fan stops
            response_time_seconds: PWM response time in seconds (0-60)
            pwm_steps: PWM step size (1, 5, 10, or 25)

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

            if curve_type is not None:
                config.curve_type = curve_type

            if flat_pwm_percent is not None:
                config.flat_pwm_percent = flat_pwm_percent

            if target_temp_celsius is not None:
                config.target_temp_celsius = target_temp_celsius

            if target_pwm_percent is not None:
                config.target_pwm_percent = target_pwm_percent

            if mix_curve_a_id is not None:
                config.mix_curve_a_id = mix_curve_a_id

            if mix_curve_b_id is not None:
                config.mix_curve_b_id = mix_curve_b_id

            if mix_function is not None:
                config.mix_function = mix_function

            if sync_fan_id is not None:
                config.sync_fan_id = sync_fan_id

            if start_pwm_percent is not None:
                config.start_pwm_percent = start_pwm_percent

            if stop_below_temp_celsius is not None:
                config.stop_below_temp_celsius = stop_below_temp_celsius

            if response_time_seconds is not None:
                config.response_time_seconds = response_time_seconds

            if pwm_steps is not None:
                config.pwm_steps = pwm_steps

            db.commit()

            logger.info(f"Updated config for {fan_id}: hysteresis={config.hysteresis_celsius}°C, curve_type={config.curve_type}")

            return {
                "fan_id": fan_id,
                "hysteresis_celsius": config.hysteresis_celsius,
                "min_pwm_percent": config.min_pwm_percent,
                "max_pwm_percent": config.max_pwm_percent,
                "emergency_temp_celsius": config.emergency_temp_celsius,
                "temp_sensor_id": config.temp_sensor_id,
                "curve_type": config.curve_type,
                "flat_pwm_percent": config.flat_pwm_percent,
                "target_temp_celsius": config.target_temp_celsius,
                "target_pwm_percent": config.target_pwm_percent,
                "mix_curve_a_id": config.mix_curve_a_id,
                "mix_curve_b_id": config.mix_curve_b_id,
                "mix_function": config.mix_function,
                "sync_fan_id": config.sync_fan_id,
                "start_pwm_percent": config.start_pwm_percent,
                "stop_below_temp_celsius": config.stop_below_temp_celsius,
                "response_time_seconds": config.response_time_seconds,
                "pwm_steps": config.pwm_steps,
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
