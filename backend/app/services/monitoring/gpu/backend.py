"""GPU backend protocol and null-object."""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from app.schemas.monitoring import GpuDeviceInfo


@runtime_checkable
class GpuBackend(Protocol):
    """Vendor-agnostic GPU sensor backend.

    Implementations populate as many sample fields as the hardware supports;
    missing fields default to None in the Pydantic schema.
    """

    @property
    def detected(self) -> bool: ...

    def device_info(self) -> GpuDeviceInfo: ...

    def read_sample(self) -> Dict[str, Any]:
        """Return dict of sensor readings matching GpuSampleSchema fields.

        Required keys: vendor, device_name. All others optional.
        Implementations should catch per-sensor failures and omit the key
        rather than raising — one broken sensor must not poison the sample.
        """


class _NoGpuBackend:
    """Null-object backend used when no dGPU is detected."""

    @property
    def detected(self) -> bool:
        return False

    def device_info(self) -> GpuDeviceInfo:
        raise RuntimeError("No GPU detected — device_info is not available")

    def read_sample(self) -> Dict[str, Any]:
        raise RuntimeError("No GPU detected — read_sample must not be called")
