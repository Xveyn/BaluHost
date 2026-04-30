"""GPU power backend protocol."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

from app.schemas.gpu_power import GpuPowerCapabilities, GpuPowerConfig, GpuPowerState


class GpuPowerBackend(ABC):
    """Vendor-agnostic GPU power backend.

    Concrete implementations: AmdGpuPowerBackend, NvidiaGpuPowerBackend, DevGpuPowerBackend.
    """

    @property
    @abstractmethod
    def detected(self) -> bool:
        """True if this backend's hardware is present."""

    @property
    @abstractmethod
    def vendor(self) -> str:
        """One of 'amd', 'nvidia', 'dev'."""

    @abstractmethod
    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        """Apply target state. Returns (success, error_message)."""

    @abstractmethod
    async def current_state(self) -> Optional[GpuPowerState]:
        """Best-effort read of the currently-applied state. None if unknown."""

    @abstractmethod
    async def has_write_permission(self) -> bool:
        """True if this process can apply state to the hardware."""

    @abstractmethod
    def capabilities(self) -> GpuPowerCapabilities:
        """Hardware-reported ranges/options for UI bounds and selects."""
