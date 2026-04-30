"""GPU metrics collector.

Mirrors CpuMetricCollector in structure but delegates sensor reads to a
vendor backend selected at construction time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Type

from app.core.config import settings
from app.models.monitoring import GpuSample
from app.schemas.monitoring import GpuSampleSchema
from app.services.monitoring.base import MetricCollector
from app.services.monitoring.gpu.backend import GpuBackend, _NoGpuBackend
from app.services.monitoring.gpu.dev_backend import DevGpuBackend

logger = logging.getLogger(__name__)


class GpuMetricCollector(MetricCollector[GpuSampleSchema]):
    """Dedicated-GPU metric collector.

    Selects a backend at init time: DevGpuBackend in dev mode, AmdGpuBackend in
    production, or _NoGpuBackend when nothing is detected. When the backend is
    not detected, collect_sample returns None and no DB write is issued.
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ) -> None:
        super().__init__(
            metric_name="GPU",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.backend: GpuBackend = self._select_backend()
        if self.backend.detected:
            try:
                info = self.backend.device_info()
                logger.info(f"GPU detected: {info.device_name} ({info.pci_slot})")
            except Exception as exc:
                logger.warning(f"GPU device_info failed: {exc}")
        else:
            logger.info("No dedicated GPU detected")

    @staticmethod
    def _select_backend() -> GpuBackend:
        # Try real backends first on every platform; fall back to mock only
        # in dev mode when nothing real is detected.
        try:
            from app.services.monitoring.gpu.nvidia_backend import NvidiaSmiBackend
            nv = NvidiaSmiBackend()
            if nv.detected:
                return nv
        except Exception as exc:
            logger.debug(f"NVIDIA backend detection failed: {exc}")

        try:
            from app.services.monitoring.gpu.amd_backend import AmdGpuBackend
            amd = AmdGpuBackend()
            if amd.detected:
                return amd
        except Exception as exc:
            logger.debug(f"AMD GPU detection failed: {exc}")

        if getattr(settings, "is_dev_mode", False):
            logger.info("No real GPU detected — using DevGpuBackend mock (dev mode)")
            return DevGpuBackend()
        return _NoGpuBackend()

    @property
    def detected(self) -> bool:
        return self.backend.detected

    def collect_sample(self) -> Optional[GpuSampleSchema]:
        if not self.backend.detected:
            return None
        try:
            raw = self.backend.read_sample()
            return GpuSampleSchema(timestamp=datetime.now(timezone.utc), **raw)
        except Exception as exc:
            logger.error(f"GPU sample collection failed: {exc}")
            return None

    def get_db_model(self) -> Type[Any]:
        return GpuSample

    def sample_to_db_dict(self, sample: GpuSampleSchema) -> dict:
        return {
            "timestamp": sample.timestamp,
            "vendor": sample.vendor,
            "device_name": sample.device_name,
            "pci_slot": sample.pci_slot,
            "usage_percent": sample.usage_percent,
            "engine_gfx_percent": sample.engine_gfx_percent,
            "engine_compute_percent": sample.engine_compute_percent,
            "engine_decode_percent": sample.engine_decode_percent,
            "engine_encode_percent": sample.engine_encode_percent,
            "vram_used_bytes": sample.vram_used_bytes,
            "vram_total_bytes": sample.vram_total_bytes,
            "core_clock_mhz": sample.core_clock_mhz,
            "memory_clock_mhz": sample.memory_clock_mhz,
            "temperature_edge_celsius": sample.temperature_edge_celsius,
            "temperature_junction_celsius": sample.temperature_junction_celsius,
            "temperature_memory_celsius": sample.temperature_memory_celsius,
            "fan_rpm": sample.fan_rpm,
            "power_watts": sample.power_watts,
        }

    def db_to_sample(self, db_record: GpuSample) -> GpuSampleSchema:
        return GpuSampleSchema(
            timestamp=db_record.timestamp,
            vendor=db_record.vendor,
            device_name=db_record.device_name,
            pci_slot=db_record.pci_slot,
            usage_percent=db_record.usage_percent,
            engine_gfx_percent=db_record.engine_gfx_percent,
            engine_compute_percent=db_record.engine_compute_percent,
            engine_decode_percent=db_record.engine_decode_percent,
            engine_encode_percent=db_record.engine_encode_percent,
            vram_used_bytes=db_record.vram_used_bytes,
            vram_total_bytes=db_record.vram_total_bytes,
            core_clock_mhz=db_record.core_clock_mhz,
            memory_clock_mhz=db_record.memory_clock_mhz,
            temperature_edge_celsius=db_record.temperature_edge_celsius,
            temperature_junction_celsius=db_record.temperature_junction_celsius,
            temperature_memory_celsius=db_record.temperature_memory_celsius,
            fan_rpm=db_record.fan_rpm,
            power_watts=db_record.power_watts,
        )
