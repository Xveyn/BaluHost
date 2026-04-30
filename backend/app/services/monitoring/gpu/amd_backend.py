"""AMD GPU backend.

Reads sensors from the `amdgpu` driver's sysfs interface under
/sys/class/drm/card*/device/ (and hwmon child directory).

Detection: iterate card* entries, filter vendor 0x1002, pick first with
pp_dpm_sclk (skips iGPUs which typically lack it on modern kernels).

Per-sensor failures return None rather than raising so a single bad file
does not invalidate the entire sample.
"""
from __future__ import annotations

import logging
import re
import struct
from pathlib import Path
from typing import Any, Dict, Optional

from app.schemas.monitoring import GpuDeviceInfo

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"


class AmdGpuBackend:
    """Real-hardware AMD GPU backend."""

    def __init__(self, sysfs_root: Path | str = Path("/")) -> None:
        self._root = Path(sysfs_root)
        self._device_path: Optional[Path] = None
        self._hwmon_path: Optional[Path] = None
        self._pci_slot: Optional[str] = None
        self._device_name: str = "AMD GPU"
        self._detect()

    # ---- Detection ----

    def _detect(self) -> None:
        drm = self._root / "sys" / "class" / "drm"
        if not drm.exists():
            return
        candidates = sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name))
        for card in candidates:
            device = card / "device"
            if not device.exists():
                continue
            vendor = self._read_text(device / "vendor")
            if vendor != AMD_VENDOR_ID:
                continue
            # Skip iGPUs: dGPUs expose pp_dpm_sclk
            if not (device / "pp_dpm_sclk").exists():
                continue
            self._device_path = device
            self._pci_slot = self._parse_pci_slot(device / "uevent")
            self._hwmon_path = self._find_hwmon(device)
            self._device_name = self._guess_device_name(device)
            return

    @staticmethod
    def _parse_pci_slot(uevent: Path) -> Optional[str]:
        try:
            for line in uevent.read_text().splitlines():
                if line.startswith("PCI_SLOT_NAME="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    @staticmethod
    def _find_hwmon(device: Path) -> Optional[Path]:
        hwmon = device / "hwmon"
        if not hwmon.exists():
            return None
        for child in hwmon.iterdir():
            if child.is_dir() and AmdGpuBackend._read_text(child / "name") == "amdgpu":
                return child
        return None

    def _guess_device_name(self, device: Path) -> str:
        device_id = self._read_text(device / "device") or ""
        return {
            "0x744c": "AMD Radeon RX 7900 XTX",
            "0x7448": "AMD Radeon RX 7900 XT",
        }.get(device_id, f"AMD GPU ({device_id})")

    # ---- Public API ----

    @property
    def detected(self) -> bool:
        return self._device_path is not None

    def device_info(self) -> GpuDeviceInfo:
        if not self.detected:
            raise RuntimeError("No AMD GPU detected")
        return GpuDeviceInfo(
            vendor="amd",
            device_name=self._device_name,
            pci_slot=self._pci_slot,
            vram_total_bytes=self._read_int(self._device_path / "mem_info_vram_total"),
            driver_version=None,
        )

    def read_sample(self) -> Dict[str, Any]:
        if not self.detected:
            raise RuntimeError("No AMD GPU detected")
        dev = self._device_path
        hw = self._hwmon_path

        sample: Dict[str, Any] = {
            "vendor": "amd",
            "device_name": self._device_name,
            "pci_slot": self._pci_slot,
        }

        # Usage
        sample["usage_percent"] = self._read_float(dev / "gpu_busy_percent")

        # VRAM
        sample["vram_used_bytes"] = self._read_int(dev / "mem_info_vram_used")
        sample["vram_total_bytes"] = self._read_int(dev / "mem_info_vram_total")

        # Core clock (Hz → MHz)
        if hw:
            freq_hz = self._read_int(hw / "freq1_input")
            sample["core_clock_mhz"] = round(freq_hz / 1_000_000, 1) if freq_hz else None
        else:
            sample["core_clock_mhz"] = None

        # Memory clock — parse the "*"-marked line of pp_dpm_mclk
        sample["memory_clock_mhz"] = self._parse_dpm_active_mhz(dev / "pp_dpm_mclk")

        # Temperatures (labels: edge / junction / mem)
        sample["temperature_edge_celsius"] = None
        sample["temperature_junction_celsius"] = None
        sample["temperature_memory_celsius"] = None
        if hw:
            for i in range(1, 5):
                label = self._read_text(hw / f"temp{i}_label")
                val = self._read_int(hw / f"temp{i}_input")
                if val is None:
                    continue
                celsius = val / 1000.0
                if label == "edge":
                    sample["temperature_edge_celsius"] = celsius
                elif label == "junction":
                    sample["temperature_junction_celsius"] = celsius
                elif label == "mem":
                    sample["temperature_memory_celsius"] = celsius

        # Fan / Power
        sample["fan_rpm"] = self._read_int(hw / "fan1_input") if hw else None
        power_uw = self._read_int(hw / "power1_average") if hw else None
        sample["power_watts"] = round(power_uw / 1_000_000, 1) if power_uw else None

        # Engine activity — from binary gpu_metrics
        sample["engine_gfx_percent"] = None
        sample["engine_compute_percent"] = None
        sample["engine_decode_percent"] = None
        sample["engine_encode_percent"] = None
        try:
            engines = self._read_gpu_metrics(dev / "gpu_metrics")
            sample.update(engines)
        except Exception as exc:
            logger.debug("gpu_metrics parse failed: %s", exc)

        return sample

    # ---- Sensor helpers ----

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text().strip()
        except OSError:
            return None

    @staticmethod
    def _read_int(path: Path) -> Optional[int]:
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _read_float(path: Path) -> Optional[float]:
        try:
            return float(path.read_text().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _parse_dpm_active_mhz(path: Path) -> Optional[float]:
        try:
            for line in path.read_text().splitlines():
                if "*" in line:
                    m = re.search(r"(\d+)\s*Mhz", line, re.IGNORECASE)
                    if m:
                        return float(m.group(1))
        except OSError:
            pass
        return None

    def _read_gpu_metrics(self, path: Path) -> Dict[str, Optional[float]]:
        """Parse amdgpu gpu_metrics binary.

        Header: size u16, format_revision u8, content_revision u8.
        Dispatch on (format_revision, content_revision). Unknown combinations
        return {} so engine fields stay None.
        """
        try:
            raw = path.read_bytes()
        except OSError:
            return {}
        if len(raw) < 4:
            return {}
        size = int.from_bytes(raw[0:2], "little")
        fmt_rev = raw[2]
        cnt_rev = raw[3]

        parsers = {
            (1, 4): self._parse_v1_4,
            (1, 3): self._parse_v1_4,  # v1.3 and v1.4 share the fields we read
        }
        parser = parsers.get((fmt_rev, cnt_rev))
        if parser is None:
            return {}
        return parser(raw, size)

    @staticmethod
    def _parse_v1_4(buf: bytes, size: int) -> Dict[str, Optional[float]]:
        def u16(off: int) -> Optional[int]:
            if off + 2 > size:
                return None
            return struct.unpack_from("<H", buf, off)[0]

        gfx_raw = u16(36)
        mm_raw = u16(38)
        vcn = [u16(152 + i * 2) for i in range(4)]

        def pct(x: Optional[int]) -> Optional[float]:
            return round(x / 100.0, 2) if x is not None else None

        def vcn_pct(a: Optional[int], b: Optional[int]) -> Optional[float]:
            vals = [x for x in (a, b) if x is not None]
            return round(max(vals) / 100.0, 2) if vals else None

        return {
            "engine_gfx_percent": pct(gfx_raw),
            "engine_compute_percent": pct(gfx_raw),
            "engine_decode_percent": vcn_pct(vcn[0], vcn[1]),
            "engine_encode_percent": vcn_pct(vcn[2], vcn[3]),
        }
