"""Tests for AMD GPU power backend (sysfs-based)."""
from pathlib import Path
from typing import Optional

import pytest

from app.schemas.gpu_power import (
    AmdProfileMode,
    AmdStateConfig,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.amd_backend import AmdGpuPowerBackend


def _make_amd_card(root: Path, *, with_profile_mode: bool = True) -> Path:
    """Create a minimal sysfs tree for an AMD dGPU."""
    device = root / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 2400Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    if with_profile_mode:
        (device / "pp_power_profile_mode").write_text(
            "PROFILE_INDEX(NAME)\n"
            "  0 BOOTUP_DEFAULT*\n"
            "  1 3D_FULL_SCREEN\n"
            "  2 POWER_SAVING\n"
            "  3 VIDEO\n"
        )
    return device


def test_detect_amd_card(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is True
    assert backend.vendor == "amd"


def test_no_amd_card(tmp_path: Path):
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_skip_non_amd_vendor(tmp_path: Path):
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x10de\n")  # NVIDIA
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n")
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_skip_igpu_no_pp_dpm_sclk(tmp_path: Path):
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")  # AMD vendor but no pp_dpm_sclk
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_parse_profile_modes(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    caps = backend.capabilities()
    assert "POWER_SAVING" in caps.amd_profile_modes
    assert "BOOTUP_DEFAULT" in caps.amd_profile_modes


@pytest.mark.asyncio
async def test_apply_active_state(tmp_path: Path):
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig()
    ok, err = await backend.apply_state(GpuPowerState.ACTIVE, config)
    assert ok is True
    assert err is None
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "auto"


@pytest.mark.asyncio
async def test_apply_deep_idle_state(tmp_path: Path):
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig()  # defaults: deep_idle = "low" + POWER_SAVING
    ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
    assert ok is True
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "low"
    # POWER_SAVING is index 2 in our fake mode list
    assert (device / "pp_power_profile_mode").read_text().splitlines()[-1].strip() == "2"


@pytest.mark.asyncio
async def test_apply_unknown_profile_falls_back(tmp_path: Path):
    """If user requests a profile mode not exposed by the driver, fall back to BOOTUP_DEFAULT."""
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig(
        amd_deep_idle=AmdStateConfig(
            performance_level="low",
            profile_mode=AmdProfileMode.VR,  # not exposed in fake setup
        )
    )
    ok, _ = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
    assert ok is True
    # Should write index 0 (BOOTUP_DEFAULT) as fallback
    assert (device / "pp_power_profile_mode").read_text().splitlines()[-1].strip() == "0"


@pytest.mark.asyncio
async def test_has_write_permission(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    # Files in tmp_path are writable for current user
    assert await backend.has_write_permission() is True
