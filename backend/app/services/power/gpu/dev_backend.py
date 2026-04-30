"""In-memory mock backend for Windows / dev mode."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)


class DevGpuPowerBackend(GpuPowerBackend):
    """Records applied state in memory; never touches hardware."""

    def __init__(self) -> None:
        self._state: GpuPowerState = GpuPowerState.ACTIVE
        self._has_permission: bool = True

    @property
    def detected(self) -> bool:
        return True

    @property
    def vendor(self) -> str:
        return "dev"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        logger.debug("DevGpuPowerBackend: apply_state %s -> %s", self._state, state)
        self._state = state
        return True, None

    async def current_state(self) -> Optional[GpuPowerState]:
        return self._state

    async def has_write_permission(self) -> bool:
        return self._has_permission

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="dev",
            amd_performance_levels=["auto", "low", "high"],
            amd_profile_modes=["BOOTUP_DEFAULT", "POWER_SAVING", "VIDEO"],
            nvidia_min_clock_mhz=210,
            nvidia_max_clock_mhz=2400,
            nvidia_min_power_watts=50,
            nvidia_max_power_watts=355,
            nvidia_default_power_watts=315,
        )
