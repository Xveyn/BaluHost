"""Der Regel-Loop schreibt firmware-verwaltete Luefter nicht an (#480)."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.fans import FanConfig
from app.schemas.fans import FanMode, PwmControl
from app.services.power.fan_control import FanControlService, FanData


class _StubBackend:
    def __init__(self, temperature=70.0):
        self.set_pwm_calls = []
        self.temperature = temperature

    async def get_fans(self):
        return [FanData(
            fan_id="gpu_fw", name="RDNA3 GPU", rpm=0, pwm_percent=0,
            temperature_celsius=self.temperature, mode=FanMode.AUTO,
            min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
            temp_sensor_id=None, curve_points=[], is_active=True,
            is_gpu_fan=True, gpu_vendor="amd",
            pwm_control=PwmControl.FIRMWARE_MANAGED,
        )]

    async def set_pwm(self, fan_id, pwm_percent):
        self.set_pwm_calls.append((fan_id, pwm_percent))
        return True


def _config_row(**overrides):
    # name ist NOT NULL ohne Default (models/fans.py:77).
    base = dict(
        fan_id="gpu_fw", name="RDNA3 GPU", mode=FanMode.AUTO.value, is_active=True,
        min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
        curve_json=json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}]),
        curve_type="graph", hysteresis_celsius=3.0,
    )
    base.update(overrides)
    return FanConfig(**base)


def _service(db_session):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = False
    config.is_dev_mode = True
    config.fan_sample_interval_seconds = 2
    return FanControlService(config, lambda: db_session)


@pytest.mark.asyncio
async def test_loop_does_not_write_firmware_managed_fan(db_session):
    db_session.add(_config_row())
    db_session.commit()

    service = _service(db_session)
    backend = _StubBackend()
    service._backend = backend
    try:
        await service._monitor_and_control_fans()

        assert backend.set_pwm_calls == []
        # Der Sample traegt den TATSAECHLICHEN Wert, nicht den Wunsch.
        assert service._sample_buffer[-1]["pwm_percent"] == 0
    finally:
        FanControlService._instance = None


@pytest.mark.asyncio
async def test_overtemp_does_not_persist_emergency_for_firmware_managed(db_session):
    """Sonst haengt der Luefter dauerhaft in EMERGENCY, ohne dass es etwas nuetzt."""
    # temp_sensor_id ist noetig, sonst bleibt die im Loop gelesene Temperatur
    # None und der Emergency-Zweig wird gar nicht erst erreicht.
    row = _config_row(temp_sensor_id="hwmon:gpu_fw")
    db_session.add(row)
    db_session.commit()

    service = _service(db_session)
    service._registry.get_temp = AsyncMock(return_value=99.0)  # ueber emergency_temp
    service._backend = _StubBackend(temperature=99.0)
    try:
        await service._monitor_and_control_fans()
        # _monitor_and_control_fans nutzt "with self.db_session_factory() as db:",
        # was die (im Test geteilte) Session schliesst -> db_session.refresh(row)
        # wuerde mit "not persistent within this Session" fehlschlagen. Frisch
        # abfragen umgeht das.
        updated = db_session.execute(
            select(FanConfig).where(FanConfig.fan_id == "gpu_fw")
        ).scalar_one()
        assert updated.mode == FanMode.AUTO.value
    finally:
        FanControlService._instance = None
