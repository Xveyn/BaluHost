"""Tests for AMD GPU manual-mode unlock helper."""
from pathlib import Path
import pytest

from app.services.power.fan_gpu_manual import enable_amd_manual, disable_amd_manual, AmdManualState


@pytest.mark.asyncio
async def test_enable_writes_manual_and_pwm_enable(tmp_path):
    # Lay out a fake amdgpu device tree
    drm = tmp_path / "sys" / "class" / "drm" / "card0"
    device = drm / "device"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 1500Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    state = await enable_amd_manual(hwmon_dir=hwmon, drm_root=tmp_path / "sys" / "class" / "drm")

    assert state.previous_level == "auto"
    assert state.previous_pwm_enable == 2
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "manual"
    assert (hwmon / "pwm1_enable").read_text().strip() == "1"


@pytest.mark.asyncio
async def test_disable_restores_previous(tmp_path):
    drm = tmp_path / "sys" / "class" / "drm" / "card0"
    device = drm / "device"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 1500Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("manual\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("1\n")

    state = AmdManualState(previous_level="auto", previous_pwm_enable=2)
    await disable_amd_manual(hwmon_dir=hwmon, drm_root=tmp_path / "sys" / "class" / "drm", state=state)

    assert (device / "power_dpm_force_performance_level").read_text().strip() == "auto"
    assert (hwmon / "pwm1_enable").read_text().strip() == "2"
