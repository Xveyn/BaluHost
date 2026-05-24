"""Tests that the hwmon scanner labels amdgpu/nouveau PWM fans as GPU fans."""
from pathlib import Path

import pytest

from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.core.config import get_settings


def _make_hwmon(tmp_path: Path, hwmon_name: str, driver: str) -> Path:
    d = tmp_path / "sys" / "class" / "hwmon" / hwmon_name
    d.mkdir(parents=True)
    (d / "name").write_text(driver + "\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    return d


@pytest.mark.asyncio
async def test_amdgpu_fan_tagged_as_gpu(tmp_path, monkeypatch):
    _make_hwmon(tmp_path, "hwmon3", "amdgpu")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fans = await backend.get_fans()
    assert any(f.is_gpu_fan and f.gpu_vendor == "amd" for f in fans)


@pytest.mark.asyncio
async def test_chipset_fan_not_tagged(tmp_path, monkeypatch):
    _make_hwmon(tmp_path, "hwmon1", "nct6798")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fans = await backend.get_fans()
    assert all(not f.is_gpu_fan for f in fans)
    assert all(f.device_driver == "nct6798" for f in fans)
