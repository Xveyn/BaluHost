"""Der Scan bildet stabile IDs und ueberlebt ein Renumbering (#532)."""
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _nct_tree(tmp_path: Path, hwmon_name: str) -> Path:
    """nct6798 an platform/nct6775.656, mit pwm1 + fan1_input + temp1_input."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / hwmon_name
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text("1\n")
    (hwmon / "fan1_input").write_text("900\n")
    (hwmon / "temp1_input").write_text("42000\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    if not (device / "subsystem").exists():
        os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / hwmon_name, target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_scan_builds_stable_fan_id(tmp_path, monkeypatch):
    klass = _nct_tree(tmp_path, "hwmon3")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    assert "nct6798-isa-0290:pwm1" in cache
    assert cache["nct6798-isa-0290:pwm1"]["identity_stable"] is True


@pytest.mark.asyncio
async def test_same_device_under_other_hwmon_index_keeps_id(tmp_path, monkeypatch):
    """Das Akzeptanzkriterium des Issues: Renumbering aendert die ID nicht."""
    first = _nct_tree(tmp_path / "boot_a", "hwmon3")
    second = _nct_tree(tmp_path / "boot_b", "hwmon5")

    backend_a = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend_a, "_hwmon_base", first)
    cache_a = await backend_a._scan_pwm_fans()

    backend_b = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend_b, "_hwmon_base", second)
    cache_b = await backend_b._scan_pwm_fans()

    assert set(cache_a) == set(cache_b) == {"nct6798-isa-0290:pwm1"}


@pytest.mark.asyncio
async def test_scan_registers_reverse_path_for_sensor(tmp_path, monkeypatch):
    klass = _nct_tree(tmp_path, "hwmon3")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()

    sensor_id = "nct6798-isa-0290:temp1"
    assert sensor_id in backend._temp_paths
    assert backend._temp_paths[sensor_id].name == "temp1_input"
