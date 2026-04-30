"""NVIDIA GPU backend using the nvidia-smi CLI.

Cross-platform — works wherever the NVIDIA driver provides nvidia-smi
(Linux, Windows, WSL). Used in preference to vendor sysfs/SDK paths
when an NVIDIA GPU is present.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, Dict, Optional

from app.schemas.monitoring import GpuDeviceInfo

logger = logging.getLogger(__name__)

# Order matches the parsing below; keep them in sync.
_QUERY_FIELDS = (
    "name,driver_version,utilization.gpu,memory.used,memory.total,"
    "temperature.gpu,power.draw,clocks.gr,clocks.mem,pci.bus_id"
)


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    s = v.strip()
    if not s or s in ("[N/A]", "N/A", "[Not Supported]"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


class NvidiaSmiBackend:
    """Polls nvidia-smi for the first NVIDIA GPU on the system."""

    def __init__(self) -> None:
        self._info: Optional[GpuDeviceInfo] = None
        self._smi = shutil.which("nvidia-smi")
        if self._smi is None:
            return
        sample = self._query()
        if sample is None:
            return
        self._info = GpuDeviceInfo(
            vendor="nvidia",
            device_name=sample.get("device_name") or "NVIDIA GPU",
            pci_slot=sample.get("pci_slot"),
            vram_total_bytes=sample.get("vram_total_bytes"),
            driver_version=sample.get("driver_version"),
        )
        logger.info(
            "NvidiaSmiBackend detected: %s (driver %s)",
            self._info.device_name,
            self._info.driver_version,
        )

    @property
    def detected(self) -> bool:
        return self._info is not None

    def device_info(self) -> GpuDeviceInfo:
        if self._info is None:
            raise RuntimeError("nvidia-smi backend not detected")
        return self._info

    def read_sample(self) -> Dict[str, Any]:
        sample = self._query()
        if sample is None:
            # Sensor failure — return identity only so the collector still records something
            return {
                "vendor": "nvidia",
                "device_name": self._info.device_name if self._info else "NVIDIA GPU",
                "pci_slot": self._info.pci_slot if self._info else None,
            }
        return sample

    def _query(self) -> Optional[Dict[str, Any]]:
        if self._smi is None:
            return None
        try:
            res = subprocess.run(
                [
                    self._smi,
                    f"--query-gpu={_QUERY_FIELDS}",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except Exception as exc:
            logger.debug("nvidia-smi invocation failed: %s", exc)
            return None
        if res.returncode != 0 or not res.stdout.strip():
            return None
        line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 10:
            return None
        name, driver, util, vmem_used, vmem_total, temp, power, clk_g, clk_m, pci = parts[:10]

        used_mb = _to_float(vmem_used)
        total_mb = _to_float(vmem_total)
        return {
            "vendor": "nvidia",
            "device_name": name,
            "driver_version": driver or None,
            "pci_slot": pci or None,
            "usage_percent": _to_float(util),
            "engine_gfx_percent": _to_float(util),  # nvidia-smi exposes one aggregate value
            "engine_compute_percent": None,
            "engine_decode_percent": None,
            "engine_encode_percent": None,
            "vram_used_bytes": int(used_mb * 1024 * 1024) if used_mb is not None else None,
            "vram_total_bytes": int(total_mb * 1024 * 1024) if total_mb is not None else None,
            "core_clock_mhz": _to_float(clk_g),
            "memory_clock_mhz": _to_float(clk_m),
            "temperature_edge_celsius": _to_float(temp),
            "temperature_junction_celsius": None,
            "temperature_memory_celsius": None,
            "fan_rpm": None,
            "power_watts": _to_float(power),
        }
