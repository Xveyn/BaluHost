"""amdgpu/nouveau hwmon entries are suppressed in favor of gpu:* sources.

The hwmon scanner finds GPU temperatures under amdgpu/nouveau drivers as
hwmon:<dir>_tempN, and the registry separately exposes gpu:edge/junction/mem
from the monitoring SHM. Without dedup, both appear in the SensorsPanel —
the same physical sensor listed twice with different IDs. Keep only the
gpu:* form so users can rename/reference one canonical entry.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.power.fan_control import FanControlService


@pytest.fixture(autouse=True)
def _reset_singleton():
    FanControlService._instance = None
    yield
    FanControlService._instance = None


def _temp_sensor_data(sensor_id, device_name, label=None, is_cpu_sensor=False, current_temp=None):
    from app.services.power.fan_control import TempSensorData
    return TempSensorData(
        sensor_id=sensor_id,
        device_name=device_name,
        label=label,
        is_cpu_sensor=is_cpu_sensor,
        current_temp=current_temp,
    )


def _make_service_with_backend(backend):
    config = MagicMock(fan_control_enabled=True, is_dev_mode=False)
    db_factory = MagicMock()
    # db_factory() returns a context manager that yields a session with empty queries
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=MagicMock(
        execute=MagicMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    ))
    cm.__exit__ = MagicMock(return_value=False)
    db_factory.return_value = cm

    service = FanControlService(config, db_factory)
    service._backend = backend
    return service


def test_rebuild_registry_skips_amdgpu_hwmon_sources():
    backend = MagicMock()
    backend.get_available_temp_sensors = AsyncMock(return_value=[
        _temp_sensor_data("hwmon0_temp1", "nct6798", label="SYSTIN"),
        _temp_sensor_data("hwmon1_temp1", "amdgpu", label="edge"),
        _temp_sensor_data("hwmon1_temp2", "amdgpu", label="junction"),
        _temp_sensor_data("hwmon1_temp3", "amdgpu", label="mem"),
        _temp_sensor_data("hwmon3_temp1", "k10temp", label="Tctl", is_cpu_sensor=True),
    ])

    service = _make_service_with_backend(backend)

    with patch("app.services.monitoring.shm.read_shm", return_value=None):
        asyncio.run(service._rebuild_registry())

    hwmon_device_names = {
        s.device_name for s in service._registry.all_sources() if s.kind == "hwmon"
    }
    assert "amdgpu" not in hwmon_device_names, \
        "amdgpu hwmon entries must be suppressed (gpu:* is the canonical source)"
    # Non-GPU hwmon entries are preserved
    assert "nct6798" in hwmon_device_names
    assert "k10temp" in hwmon_device_names


def test_rebuild_registry_skips_nouveau_hwmon_sources():
    backend = MagicMock()
    backend.get_available_temp_sensors = AsyncMock(return_value=[
        _temp_sensor_data("hwmon0_temp1", "nct6798", label="SYSTIN"),
        _temp_sensor_data("hwmon2_temp1", "nouveau", label="GPU"),
    ])

    service = _make_service_with_backend(backend)

    with patch("app.services.monitoring.shm.read_shm", return_value=None):
        asyncio.run(service._rebuild_registry())

    hwmon_device_names = {
        s.device_name for s in service._registry.all_sources() if s.kind == "hwmon"
    }
    assert "nouveau" not in hwmon_device_names
    assert "nct6798" in hwmon_device_names


def test_rebuild_registry_still_registers_gpu_namespace_sources():
    """Even with amdgpu suppressed, gpu:edge/junction/mem must still exist."""
    backend = MagicMock()
    backend.get_available_temp_sensors = AsyncMock(return_value=[
        _temp_sensor_data("hwmon1_temp1", "amdgpu", label="edge"),
    ])

    service = _make_service_with_backend(backend)

    with patch("app.services.monitoring.shm.read_shm", return_value=None):
        asyncio.run(service._rebuild_registry())

    gpu_ids = {s.id for s in service._registry.all_sources() if s.kind == "gpu"}
    assert gpu_ids == {"gpu:edge", "gpu:junction", "gpu:mem"}
