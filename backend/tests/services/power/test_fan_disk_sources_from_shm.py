"""Disk temperature sources are derived from SMART summary SHM.

Regression test for disk:* sources missing entirely from the SensorsPanel:
the previous implementation used a per-worker SMART cache that was empty
on every web worker unless that worker had personally hit the SMART API.
Now fan_control reads from smart_summary.json (written by the monitoring
worker), so every web worker sees the same fresh disk list.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.power.fan_control import FanControlService


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset FanControlService singleton between tests."""
    FanControlService._instance = None
    yield
    FanControlService._instance = None


def _make_service():
    """Build a FanControlService with mocked config + db session factory."""
    config = MagicMock(fan_control_enabled=True, is_dev_mode=False)
    db_factory = MagicMock()
    return FanControlService(config, db_factory)


def _shm(devices):
    return {"devices": devices, "timestamp": 1779654000.0}


def test_make_disk_reader_returns_temp_from_shm():
    service = _make_service()
    reader = service._make_disk_reader("sda")

    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([{"name": "sda", "temperature_celsius": 38.0}])):
        temp = asyncio.run(reader())

    assert temp == 38.0


def test_make_disk_reader_returns_none_when_device_missing_from_shm():
    service = _make_service()
    reader = service._make_disk_reader("sda")

    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([{"name": "nvme0n1", "temperature_celsius": 45.0}])):
        temp = asyncio.run(reader())

    assert temp is None


def test_make_disk_reader_returns_none_when_shm_absent():
    service = _make_service()
    reader = service._make_disk_reader("sda")

    with patch("app.services.monitoring.shm.read_shm", return_value=None):
        temp = asyncio.run(reader())

    assert temp is None


def test_list_smart_devices_returns_names_from_shm():
    service = _make_service()
    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([
                   {"name": "sda", "temperature_celsius": 38.0},
                   {"name": "nvme0n1", "temperature_celsius": 45.0},
               ])):
        devices = asyncio.run(service._list_smart_devices())

    assert devices == ["sda", "nvme0n1"]


def test_list_smart_devices_returns_empty_list_when_shm_absent():
    service = _make_service()
    with patch("app.services.monitoring.shm.read_shm", return_value=None):
        devices = asyncio.run(service._list_smart_devices())

    assert devices == []


def test_refresh_disk_sources_registers_disks_present_in_shm():
    service = _make_service()
    # Start with no disk sources registered
    assert all(s.kind != "disk" for s in service._registry.all_sources())

    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([
                   {"name": "sda", "temperature_celsius": 38.0},
                   {"name": "nvme0n1", "temperature_celsius": 45.0},
               ])):
        asyncio.run(service._refresh_disk_sources())

    disk_ids = {s.id for s in service._registry.all_sources() if s.kind == "disk"}
    assert disk_ids == {"disk:sda", "disk:nvme0n1"}


def test_refresh_disk_sources_removes_disks_no_longer_in_shm():
    service = _make_service()

    # First populate with sda + nvme0n1
    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([
                   {"name": "sda", "temperature_celsius": 38.0},
                   {"name": "nvme0n1", "temperature_celsius": 45.0},
               ])):
        asyncio.run(service._refresh_disk_sources())

    # Now SHM only has sda — nvme0n1 must be removed
    with patch("app.services.monitoring.shm.read_shm",
               return_value=_shm([
                   {"name": "sda", "temperature_celsius": 38.0},
               ])):
        asyncio.run(service._refresh_disk_sources())

    disk_ids = {s.id for s in service._registry.all_sources() if s.kind == "disk"}
    assert disk_ids == {"disk:sda"}
