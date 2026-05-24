"""
Regression test: user-chosen sensor must not be overwritten on service restart.

This test would FAIL if the auto-correction branch were re-added to
_load_fan_configs (the branch that changes existing.temp_sensor_id to the CPU
sensor when it points anywhere else).
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.fans import FanConfig
from app.schemas.fans import FanMode, FanCurvePoint
from app.services.power.fan_control import FanControlService, FanData, TempSensorData


class MockSettings:
    """Minimal settings mock for FanControlService."""
    is_dev_mode = True
    fan_control_enabled = True
    fan_min_pwm_percent = 30
    fan_emergency_temp_celsius = 90.0
    fan_force_dev_backend = True


def _make_service(mock_backend, existing_sensor_id: str) -> FanControlService:
    """Construct a bare FanControlService (bypassing singleton) with a pre-seeded DB config."""
    mock_config = MagicMock(spec=FanConfig)
    mock_config.fan_id = "hwmon0_pwm1"
    mock_config.temp_sensor_id = existing_sensor_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config

    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)

    service = FanControlService.__new__(FanControlService)
    service.config = MockSettings()
    service.db_session_factory = mock_session_factory
    service._backend = mock_backend
    return service, mock_config


def _make_backend_with_cpu_sensor():
    """Backend returning one fan and one CPU sensor (hwmon1_temp1)."""
    mock_backend = AsyncMock()
    mock_backend.get_fans.return_value = [
        FanData(
            fan_id="hwmon0_pwm1",
            name="Case Fan",
            rpm=900,
            pwm_percent=40,
            temperature_celsius=None,
            mode=FanMode.AUTO,
            min_pwm_percent=0,
            max_pwm_percent=100,
            emergency_temp_celsius=85.0,
            temp_sensor_id="hwmon0_temp1",
            curve_points=[FanCurvePoint(temp=35, pwm=30), FanCurvePoint(temp=70, pwm=80)],
            is_active=True,
        )
    ]
    mock_backend.get_available_temp_sensors.return_value = [
        TempSensorData(
            sensor_id="hwmon0_temp1",
            device_name="it8688e",
            label="Board",
            is_cpu_sensor=False,
            current_temp=26.0,
        ),
        TempSensorData(
            sensor_id="hwmon1_temp1",
            device_name="k10temp",
            label="Tctl",
            is_cpu_sensor=True,
            current_temp=55.0,
        ),
    ]
    return mock_backend


@pytest.mark.asyncio
async def test_non_cpu_sensor_survives_reload():
    """Non-CPU sensor chosen by user must not be overwritten by CPU sensor on reload."""
    mock_backend = _make_backend_with_cpu_sensor()

    with patch.object(FanControlService, "_instance", None):
        service, mock_config = _make_service(mock_backend, existing_sensor_id="hwmon0_temp1")
        await service._load_fan_configs()

    # Must stay as the user set it — NOT silently replaced with hwmon1_temp1
    assert mock_config.temp_sensor_id == "hwmon0_temp1", (
        "Auto-correction must not overwrite user-chosen non-CPU sensor. "
        "If this assertion fails, the deleted elif branch was re-added."
    )


@pytest.mark.asyncio
async def test_composite_sensor_survives_reload():
    """A composite (mix:) sensor ID must survive service reload even when CPU sensor is available."""
    mock_backend = _make_backend_with_cpu_sensor()

    with patch.object(FanControlService, "_instance", None):
        service, mock_config = _make_service(mock_backend, existing_sensor_id="mix:user-choice")
        await service._load_fan_configs()

    assert mock_config.temp_sensor_id == "mix:user-choice", (
        "Composite sensor must survive reload. "
        "If this assertion fails, the deleted elif branch was re-added."
    )


@pytest.mark.asyncio
async def test_gpu_sensor_survives_reload():
    """A GPU sensor (gpu:edge) must survive service reload unchanged."""
    mock_backend = _make_backend_with_cpu_sensor()

    with patch.object(FanControlService, "_instance", None):
        service, mock_config = _make_service(mock_backend, existing_sensor_id="gpu:edge")
        await service._load_fan_configs()

    assert mock_config.temp_sensor_id == "gpu:edge", (
        "GPU sensor must survive reload. "
        "If this assertion fails, the deleted elif branch was re-added."
    )


@pytest.mark.asyncio
async def test_disk_sensor_survives_reload():
    """A disk sensor (disk:sda) must survive service reload unchanged."""
    mock_backend = _make_backend_with_cpu_sensor()

    with patch.object(FanControlService, "_instance", None):
        service, mock_config = _make_service(mock_backend, existing_sensor_id="disk:sda")
        await service._load_fan_configs()

    assert mock_config.temp_sensor_id == "disk:sda", (
        "Disk sensor must survive reload. "
        "If this assertion fails, the deleted elif branch was re-added."
    )


@pytest.mark.asyncio
async def test_cpu_sensor_assignment_unchanged_on_reload():
    """A fan already using the CPU sensor must continue using it after reload."""
    mock_backend = _make_backend_with_cpu_sensor()

    with patch.object(FanControlService, "_instance", None):
        service, mock_config = _make_service(mock_backend, existing_sensor_id="hwmon1_temp1")
        await service._load_fan_configs()

    assert mock_config.temp_sensor_id == "hwmon1_temp1"
