"""Dev-mode mock of an AMD Radeon RX 7900 XT.

Used when settings.is_dev_mode is True so Windows development does not require
real AMD hardware. Values fluctuate with sin/cos + small jitter for a plausible feel.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict

from app.schemas.monitoring import GpuDeviceInfo


VRAM_TOTAL = 20 * 1024 ** 3  # 20 GB
DEVICE_NAME = "AMD Radeon RX 7900 XT (dev-mock)"
PCI_SLOT = "0000:03:00.0"
DRIVER_VERSION = "amdgpu 6.5.0-dev"


class DevGpuBackend:
    """Always-detected mock GPU backend."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()

    @property
    def detected(self) -> bool:
        return True

    def device_info(self) -> GpuDeviceInfo:
        return GpuDeviceInfo(
            vendor="amd",
            device_name=DEVICE_NAME,
            pci_slot=PCI_SLOT,
            vram_total_bytes=VRAM_TOTAL,
            driver_version=DRIVER_VERSION,
        )

    def read_sample(self) -> Dict[str, Any]:
        t = time.monotonic() - self._t0
        usage = max(0.0, min(100.0, 30 + 25 * math.sin(t / 20) + random.uniform(-5, 5)))
        gfx = max(0.0, min(100.0, usage + random.uniform(-5, 5)))
        compute = max(0.0, min(100.0, max(0.0, usage - 10) + random.uniform(-5, 5)))
        decode = random.uniform(0, 15)
        encode = random.uniform(0, 8)
        vram_used = int(6e9 + 2e9 * math.sin(t / 30))
        vram_used = max(0, min(VRAM_TOTAL, vram_used))

        return {
            "vendor": "amd",
            "device_name": DEVICE_NAME,
            "pci_slot": PCI_SLOT,
            "usage_percent": round(usage, 2),
            "engine_gfx_percent": round(gfx, 2),
            "engine_compute_percent": round(compute, 2),
            "engine_decode_percent": round(decode, 2),
            "engine_encode_percent": round(encode, 2),
            "vram_used_bytes": vram_used,
            "vram_total_bytes": VRAM_TOTAL,
            "core_clock_mhz": round(2500 + random.uniform(-300, 300), 1),
            "memory_clock_mhz": 2500.0,
            "temperature_edge_celsius": round(55 + random.uniform(-3, 8), 1),
            "temperature_junction_celsius": round(65 + random.uniform(-3, 10), 1),
            "temperature_memory_celsius": round(70 + random.uniform(-3, 8), 1),
            "fan_rpm": 1500 + int(random.uniform(-200, 400)),
            "power_watts": round(180 + random.uniform(-30, 60), 1),
        }
