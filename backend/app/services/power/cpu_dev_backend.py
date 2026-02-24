"""
Development/simulation backend for CPU power management.

Simulates CPU frequency changes without actual hardware control.
Used for development on Windows/macOS or when running without root.
"""

from __future__ import annotations

import logging
import random
from typing import List, Optional, Tuple

from app.schemas.power import PowerProfile, PowerProfileConfig
from app.services.power.cpu_protocol import CpuPowerBackend

logger = logging.getLogger(__name__)


class DevCpuPowerBackend(CpuPowerBackend):
    """
    Development/simulation backend for CPU power management.

    Simulates CPU frequency changes without actual hardware control.
    Used for development on Windows/macOS or when running without root.
    """

    def __init__(self):
        self._current_profile: PowerProfile = PowerProfile.IDLE
        self._simulated_freq_mhz: float = 800.0
        self._current_governor: str = "powersave"
        logger.info("DevCpuPowerBackend initialized (simulation mode)")

    async def apply_profile(self, config: PowerProfileConfig) -> Tuple[bool, Optional[str]]:
        """Simulate applying a power profile."""
        self._current_governor = config.governor
        self._current_profile = config.profile

        # Simulate realistic frequency based on profile
        if config.profile == PowerProfile.IDLE:
            self._simulated_freq_mhz = random.uniform(400, 800)
        elif config.profile == PowerProfile.LOW:
            self._simulated_freq_mhz = random.uniform(800, 1200)
        elif config.profile == PowerProfile.MEDIUM:
            self._simulated_freq_mhz = random.uniform(1500, 2500)
        elif config.profile == PowerProfile.SURGE:
            self._simulated_freq_mhz = random.uniform(4200, 4600)  # AMD Ryzen 5600GT boost

        logger.info(
            f"[DEV] Applied profile '{config.profile.value}': "
            f"governor={config.governor}, freq={self._simulated_freq_mhz:.0f}MHz"
        )
        return True, None

    async def get_current_frequency_mhz(self) -> Optional[float]:
        """Return simulated frequency with small variations."""
        variation = random.uniform(-50, 50)
        return round(self._simulated_freq_mhz + variation, 1)

    async def get_available_governors(self) -> List[str]:
        """Return typical Linux governors for simulation."""
        return ["powersave", "performance", "schedutil", "conservative", "ondemand"]

    async def get_current_governor(self) -> Optional[str]:
        """Return the simulated current governor."""
        return self._current_governor

    def is_available(self) -> bool:
        """Dev backend is always available."""
        return True
