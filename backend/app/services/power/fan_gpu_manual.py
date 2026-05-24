"""AMD GPU manual fan-control unlock.

Required so PWM writes to amdgpu hwmon are accepted by the kernel:
- power_dpm_force_performance_level=manual
- pwm{n}_enable=1

State of the prior values is captured so disable_amd_manual can revert.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"


@dataclass
class AmdManualState:
    """Captured original values prior to enabling manual mode."""
    previous_level: str
    previous_pwm_enable: int


async def enable_amd_manual(hwmon_dir: Path, drm_root: Optional[Path] = None) -> AmdManualState:
    """Enable manual fan control on the AMD GPU whose hwmon_dir is given."""
    device = _device_from_hwmon(hwmon_dir, drm_root)
    if device is None:
        raise RuntimeError(f"Could not locate amdgpu device for {hwmon_dir}")

    level_path = device / "power_dpm_force_performance_level"
    prev_level = await asyncio.to_thread(lambda: level_path.read_text().strip())

    pwm_enable_path = _find_pwm_enable(hwmon_dir)
    prev_enable = 2
    if pwm_enable_path is not None:
        try:
            prev_enable = int(await asyncio.to_thread(lambda: pwm_enable_path.read_text().strip()))
        except (OSError, ValueError):
            prev_enable = 2

    await asyncio.to_thread(level_path.write_text, "manual")
    if pwm_enable_path is not None:
        await asyncio.to_thread(pwm_enable_path.write_text, "1")

    logger.info("AMD GPU manual mode enabled (prev_level=%s, prev_enable=%s)", prev_level, prev_enable)
    return AmdManualState(previous_level=prev_level, previous_pwm_enable=prev_enable)


async def disable_amd_manual(hwmon_dir: Path, drm_root: Optional[Path], state: AmdManualState) -> None:
    device = _device_from_hwmon(hwmon_dir, drm_root)
    if device is None:
        raise RuntimeError(f"Could not locate amdgpu device for {hwmon_dir}")

    level_path = device / "power_dpm_force_performance_level"
    await asyncio.to_thread(level_path.write_text, state.previous_level or "auto")

    pwm_enable_path = _find_pwm_enable(hwmon_dir)
    if pwm_enable_path is not None:
        await asyncio.to_thread(pwm_enable_path.write_text, str(state.previous_pwm_enable))

    logger.info("AMD GPU manual mode disabled (restored level=%s, enable=%s)",
                state.previous_level, state.previous_pwm_enable)


def _device_from_hwmon(hwmon_dir: Path, drm_root: Optional[Path]) -> Optional[Path]:
    """Walk up from hwmon dir to find the amdgpu PCI device directory."""
    # hwmon_dir typically looks like: <drm>/card0/device/hwmon/hwmonN
    p = hwmon_dir.resolve()
    for parent in p.parents:
        if parent.name == "device" and (parent / "vendor").exists():
            try:
                if (parent / "vendor").read_text().strip() == AMD_VENDOR_ID:
                    return parent
            except OSError:
                pass
    return None


def _find_pwm_enable(hwmon_dir: Path) -> Optional[Path]:
    """First pwmN_enable file in the hwmon dir."""
    for p in sorted(hwmon_dir.glob("pwm*_enable")):
        if re.fullmatch(r"pwm\d+_enable", p.name):
            return p
    return None
