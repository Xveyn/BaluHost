"""
CPU Power Backend Protocol.

Defines the abstract base class for CPU power control backends
and the default profile configurations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from app.schemas.power import (
    PowerProfile,
    PowerProfileConfig,
)

# Default profile configurations
DEFAULT_PROFILES: Dict[PowerProfile, PowerProfileConfig] = {
    PowerProfile.IDLE: PowerProfileConfig(
        profile=PowerProfile.IDLE,
        governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=400,
        max_freq_mhz=800,
        description="Minimal power consumption for idle NAS"
    ),
    PowerProfile.LOW: PowerProfileConfig(
        profile=PowerProfile.LOW,
        governor="powersave",
        energy_performance_preference="balance_power",
        min_freq_mhz=800,
        max_freq_mhz=1200,
        description="Light workloads: auth, basic CRUD operations"
    ),
    PowerProfile.MEDIUM: PowerProfileConfig(
        profile=PowerProfile.MEDIUM,
        governor="powersave",
        energy_performance_preference="balance_performance",
        min_freq_mhz=1500,
        max_freq_mhz=2500,
        description="File operations, sync, SMART scans"
    ),
    PowerProfile.SURGE: PowerProfileConfig(
        profile=PowerProfile.SURGE,
        governor="performance",
        energy_performance_preference="performance",
        min_freq_mhz=None,  # No limit
        max_freq_mhz=None,  # Full boost
        description="Maximum performance: backup, RAID rebuild"
    ),
}

# Profile priority (higher = more demanding)
PROFILE_PRIORITY: Dict[PowerProfile, int] = {
    PowerProfile.IDLE: 0,
    PowerProfile.LOW: 1,
    PowerProfile.MEDIUM: 2,
    PowerProfile.SURGE: 3,
}


class CpuPowerBackend(ABC):
    """Abstract base class for CPU power control backends."""

    @abstractmethod
    async def apply_profile(self, config: PowerProfileConfig) -> Tuple[bool, Optional[str]]:
        """Apply a power profile to the CPU. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def get_current_frequency_mhz(self) -> Optional[float]:
        """Get the current CPU frequency in MHz."""
        pass

    @abstractmethod
    async def get_available_governors(self) -> List[str]:
        """Get list of available CPU governors."""
        pass

    @abstractmethod
    async def get_current_governor(self) -> Optional[str]:
        """Get the currently active governor."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend can be used on the current system."""
        pass

    async def get_system_freq_range(self) -> Tuple[int, int]:
        """Get system min/max CPU frequency in MHz. Returns (min_mhz, max_mhz)."""
        return (400, 4600)
