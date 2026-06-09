"""AMD GPU power backend.

Writes to amdgpu sysfs files:
- power_dpm_force_performance_level: auto/low/high/...
- pp_power_profile_mode: index of named mode (parsed at startup)

Detection mirrors `services/monitoring/gpu/amd_backend.py`: first dGPU with pp_dpm_sclk.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.schemas.gpu_power import (
    AmdStateConfig,
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"

# Conservative list of valid performance_level values; the kernel exposes more
# but these are the broadly-supported ones across kernels.
AMD_PERFORMANCE_LEVELS = [
    "auto",
    "low",
    "high",
    "manual",
    "profile_standard",
    "profile_min_sclk",
    "profile_min_mclk",
    "profile_peak",
]


class AmdGpuPowerBackend(GpuPowerBackend):
    def __init__(self, sysfs_root: Path | str = Path("/")) -> None:
        self._root = Path(sysfs_root)
        self._device_path: Optional[Path] = None
        self._profile_modes: Dict[str, int] = {}  # name -> index
        self._detect()

    # ---- detection ----

    def _detect(self) -> None:
        drm = self._root / "sys" / "class" / "drm"
        if not drm.exists():
            return
        for card in sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name)):
            device = card / "device"
            if not device.exists():
                continue
            try:
                vendor = (device / "vendor").read_text().strip()
            except OSError:
                continue
            if vendor != AMD_VENDOR_ID:
                continue
            if not (device / "pp_dpm_sclk").exists():
                continue
            self._device_path = device
            self._profile_modes = self._parse_profile_modes(device / "pp_power_profile_mode")
            return

    @staticmethod
    def _parse_profile_modes(path: Path) -> Dict[str, int]:
        """Parse `pp_power_profile_mode` into {NAME: index}.

        Format example:
            PROFILE_INDEX(NAME)
              0 BOOTUP_DEFAULT*
              1 3D_FULL_SCREEN
              2 POWER_SAVING
        """
        if not path.exists():
            return {}
        modes: Dict[str, int] = {}
        try:
            text = path.read_text()
        except OSError:
            return {}
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)\s+(\S+?)\*?\s*$", line)
            if m:
                idx, name = int(m.group(1)), m.group(2).rstrip("*").strip()
                modes[name] = idx
        return modes

    # ---- public API ----

    @property
    def detected(self) -> bool:
        return self._device_path is not None

    @property
    def vendor(self) -> str:
        return "amd"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        if self._device_path is None:
            return False, "AMD GPU not detected"
        if config is None:
            config = GpuPowerConfig()

        state_config = self._config_for_state(config, state)
        try:
            await asyncio.to_thread(self._apply_sync, state_config)
        except OSError as exc:
            logger.warning("AMD apply_state failed: %s", exc)
            return False, str(exc)
        return True, None

    def _config_for_state(self, config: GpuPowerConfig, state: GpuPowerState) -> AmdStateConfig:
        return {
            GpuPowerState.ACTIVE: config.amd_active,
            GpuPowerState.STANDBY: config.amd_standby,
            GpuPowerState.DEEP_IDLE: config.amd_deep_idle,
        }[state]

    def _apply_sync(self, state_config: AmdStateConfig) -> None:
        assert self._device_path is not None
        if state_config.performance_level is not None:
            (self._device_path / "power_dpm_force_performance_level").write_text(
                state_config.performance_level
            )
        if state_config.profile_mode is not None:
            idx = self._profile_modes.get(state_config.profile_mode.value)
            if idx is None:
                idx = self._profile_modes.get("BOOTUP_DEFAULT", 0)
                logger.warning(
                    "AMD profile mode %s not exposed by driver; using fallback index %d",
                    state_config.profile_mode.value, idx,
                )
            (self._device_path / "pp_power_profile_mode").write_text(str(idx))

    async def current_state(self) -> Optional[GpuPowerState]:
        if self._device_path is None:
            return None
        try:
            level = await asyncio.to_thread(
                lambda: (self._device_path / "power_dpm_force_performance_level").read_text().strip()
            )
        except OSError:
            return None
        if level == "low":
            return GpuPowerState.DEEP_IDLE
        if level == "auto":
            return GpuPowerState.ACTIVE
        return None  # ambiguous (manual/high/profile_*)

    async def has_write_permission(self) -> bool:
        if self._device_path is None:
            return False
        target = self._device_path / "power_dpm_force_performance_level"
        return await asyncio.to_thread(os.access, str(target), os.W_OK)

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="amd" if self.detected else None,
            amd_performance_levels=list(AMD_PERFORMANCE_LEVELS),
            amd_profile_modes=list(self._profile_modes.keys()),
        )
