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

from app.schemas.fans import PwmControl

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
        try:
            await asyncio.to_thread(pwm_enable_path.write_text, "1")
        except OSError:
            # Nichts halb angewendet zuruecklassen.
            try:
                await asyncio.to_thread(level_path.write_text, prev_level or "auto")
            except OSError:
                logger.error("Rollback of performance_level failed for %s", device)
            raise

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


def probe_amd_pwm_control(hwmon_dir: Path) -> PwmControl:
    """Stellt fest, ob Live-PWM fuer diesen AMD-GPU-Luefter moeglich ist.

    Ab RDNA3 (SMU13) liegt die Luefterkurve in der Firmware und wird ueber
    <device>/gpu_od/fan_ctrl/ exponiert; pwm{n}-Writes lehnt der Treiber mit
    EINVAL ab. Die Existenz von fan_curve ist der Marker.

    WICHTIG: Aus einem fehlenden gpu_od/ darf NICHT auf ein fehlendes
    Overdrive-Bit geschlossen werden. Auf der Referenzkarte (RX 7900 XT) war
    amdgpu.ppfeaturemask=0xffffffff gesetzt und PWM trotzdem tot — die
    gegenteilige Annahme war der urspruengliche Fehler in #480.
    """
    device = _device_from_hwmon(hwmon_dir)
    if device is None:
        return PwmControl.SUPPORTED
    if (device / "gpu_od" / "fan_ctrl" / "fan_curve").exists():
        return PwmControl.FIRMWARE_MANAGED
    return PwmControl.SUPPORTED


def _device_from_hwmon(hwmon_dir: Path, drm_root: Optional[Path] = None) -> Optional[Path]:
    """Finde das amdgpu-PCI-Device zu einer hwmon-Directory.

    Primaerweg: jede hwmon-Directory traegt einen 'device'-Symlink auf ihr
    PCI-Geraet. An der Hardware verifiziert:
        ls -d /sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl  -> existiert

    Fallback: Aufwaertslauf ueber den aufgeloesten Pfad. Der funktioniert NUR
    in synthetischen Baeumen — real enthaelt readlink -f keine Komponente
    namens 'device'. Bleibt erhalten, damit bestehende Tests gueltig bleiben.
    """
    direct = hwmon_dir / "device"
    try:
        if (direct / "vendor").read_text().strip() == AMD_VENDOR_ID:
            return direct
    except OSError:
        pass

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
