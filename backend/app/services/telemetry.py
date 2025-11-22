from __future__ import annotations

import asyncio
import logging
import random
import time
from threading import Lock
from typing import List, Optional, Tuple

import psutil

from app.core.config import settings
from app.schemas.system import (
    CpuTelemetrySample,
    MemoryTelemetrySample,
    NetworkTelemetrySample,
    TelemetryHistoryResponse,
)

logger = logging.getLogger(__name__)

_SAMPLE_INTERVAL_SECONDS = float(getattr(settings, "telemetry_interval_seconds", 3.0))
_MAX_SAMPLES = int(getattr(settings, "telemetry_history_size", 60))

_cpu_history: List[CpuTelemetrySample] = []
_memory_history: List[MemoryTelemetrySample] = []
_network_history: List[NetworkTelemetrySample] = []

_latest_cpu_usage: Optional[float] = None
_latest_memory_sample: Optional[MemoryTelemetrySample] = None
_previous_network_totals: Optional[Tuple[float, int, int]] = None

_monitor_task: Optional[asyncio.Task] = None
_lock = Lock()

try:
    # Prime the internal psutil CPU statistics so the first real sample is meaningful
    psutil.cpu_percent(interval=None)
except Exception as exc:  # pragma: no cover - platform quirks
    logger.debug("Unable to prime CPU stats: %s", exc)


def _push_sample(collection: List, sample) -> None:
    collection.append(sample)
    if len(collection) > _MAX_SAMPLES:
        collection.pop(0)


def _round(value: float) -> float:
    return round(value, 2)


def _generate_mock_network_sample() -> Tuple[float, float]:
    previous = _network_history[-1] if _network_history else None
    base_down = previous.downloadMbps if previous else 1.4
    base_up = previous.uploadMbps if previous else 0.7
    next_down = max(0.0, base_down + random.uniform(-0.6, 0.8))
    next_up = max(0.0, base_up + random.uniform(-0.4, 0.5))
    return _round(next_down), _round(next_up)


def _sample_once() -> None:
    global _latest_cpu_usage, _latest_memory_sample, _previous_network_totals

    timestamp_seconds = time.time()
    timestamp_ms = int(timestamp_seconds * 1000)

    try:
        cpu_usage = _round(float(psutil.cpu_percent(interval=None)))
    except Exception as exc:  # pragma: no cover - psutil edge cases
        logger.debug("CPU percent unavailable: %s", exc)
        cpu_usage = _latest_cpu_usage if _latest_cpu_usage is not None else 0.0

    try:
        virtual_mem = psutil.virtual_memory()
        total_mem = int(virtual_mem.total)
        used_mem = int(virtual_mem.total - virtual_mem.available)
        percent_mem = _round(float(virtual_mem.percent))
    except Exception as exc:  # pragma: no cover - psutil edge cases
        logger.debug("Memory stats unavailable: %s", exc)
        if _latest_memory_sample is not None:
            total_mem = _latest_memory_sample.total
            used_mem = _latest_memory_sample.used
            percent_mem = _latest_memory_sample.percent
        else:
            total_mem = 8 * 1024 ** 3
            used_mem = 3 * 1024 ** 3
            percent_mem = _round((used_mem / total_mem) * 100)

    if settings.is_dev_mode:
        download_mbps, upload_mbps = _generate_mock_network_sample()
        _previous_network_totals = None
    else:
        download_mbps = 0.0
        upload_mbps = 0.0
        try:
            counters = psutil.net_io_counters()
            if counters is not None:
                rx_bytes = int(counters.bytes_recv)
                tx_bytes = int(counters.bytes_sent)
                if _previous_network_totals is None:
                    _previous_network_totals = (timestamp_seconds, rx_bytes, tx_bytes)
                else:
                    last_time, last_rx, last_tx = _previous_network_totals
                    elapsed = max(timestamp_seconds - last_time, 1e-3)
                    rx_diff = rx_bytes - last_rx
                    tx_diff = tx_bytes - last_tx
                    download_mbps = max(0.0, (rx_diff * 8) / (elapsed * 1_000_000))
                    upload_mbps = max(0.0, (tx_diff * 8) / (elapsed * 1_000_000))
                    _previous_network_totals = (timestamp_seconds, rx_bytes, tx_bytes)
        except Exception as exc:  # pragma: no cover - networking edge cases
            logger.debug("Network counters unavailable: %s", exc)
            download_mbps, upload_mbps = _generate_mock_network_sample()
            _previous_network_totals = None

    cpu_sample = CpuTelemetrySample(timestamp=timestamp_ms, usage=_round(cpu_usage))
    memory_sample = MemoryTelemetrySample(
        timestamp=timestamp_ms,
        used=used_mem,
        total=total_mem,
        percent=_round(percent_mem),
    )
    network_sample = NetworkTelemetrySample(
        timestamp=timestamp_ms,
        downloadMbps=_round(download_mbps),
        uploadMbps=_round(upload_mbps),
    )

    with _lock:
        _push_sample(_cpu_history, cpu_sample)
        _push_sample(_memory_history, memory_sample)
        _push_sample(_network_history, network_sample)
        _latest_cpu_usage = cpu_sample.usage
        _latest_memory_sample = memory_sample


async def _monitor_loop(interval_seconds: float) -> None:
    while True:
        try:
            _sample_once()
        except Exception as exc:  # pragma: no cover - diagnostics only
            logger.debug("Telemetry sampling iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def start_telemetry_monitor(interval_seconds: float | None = None) -> None:
    global _monitor_task

    if _monitor_task is not None and not _monitor_task.done():
        return

    effective_interval = interval_seconds or _SAMPLE_INTERVAL_SECONDS
    _sample_once()

    loop = asyncio.get_running_loop()
    _monitor_task = loop.create_task(_monitor_loop(effective_interval))
    logger.info("Telemetry monitor started (interval=%ss, history=%s)", effective_interval, _MAX_SAMPLES)


async def stop_telemetry_monitor() -> None:
    global _monitor_task

    if _monitor_task is None:
        return

    _monitor_task.cancel()
    try:
        await _monitor_task
    except asyncio.CancelledError:  # pragma: no cover - expected on shutdown
        pass
    finally:
        _monitor_task = None
        logger.info("Telemetry monitor stopped")


def get_history() -> TelemetryHistoryResponse:
    with _lock:
        return TelemetryHistoryResponse(
            cpu=[sample.model_copy(deep=True) for sample in _cpu_history],
            memory=[sample.model_copy(deep=True) for sample in _memory_history],
            network=[sample.model_copy(deep=True) for sample in _network_history],
        )


def get_latest_cpu_usage() -> Optional[float]:
    with _lock:
        return _latest_cpu_usage


def get_latest_memory_sample() -> Optional[MemoryTelemetrySample]:
    with _lock:
        return _latest_memory_sample.model_copy(deep=True) if _latest_memory_sample else None
