"""MonitoringWorker._write_telemetry_snapshot publishes GPU sample to SHM.

Regression test for the gap that left gpu:edge/junction/mem sources reading
None in the fan_control registry: telemetry.json had no "gpu" key, so the
fan_control._make_gpu_reader returned None for every GPU channel.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.monitoring.worker_service import MonitoringWorker
from app.services.monitoring.shm import TELEMETRY_FILE


_EMPTY_LEGACY_TELEMETRY = SimpleNamespace(cpu=[], memory=[], network=[])


def _make_gpu_sample(**overrides):
    """Build a GpuSampleSchema-like SimpleNamespace with model_dump compat."""
    base = dict(
        timestamp=datetime(2026, 5, 24, tzinfo=timezone.utc),
        vendor="amd",
        device_name="AMD Radeon RX 7900 XT",
        pci_slot="0000:03:00.0",
        usage_percent=12.0,
        engine_gfx_percent=None,
        engine_compute_percent=None,
        engine_decode_percent=None,
        engine_encode_percent=None,
        vram_used_bytes=2_600_000_000,
        vram_total_bytes=20_000_000_000,
        core_clock_mhz=3.0,
        memory_clock_mhz=96.0,
        temperature_edge_celsius=41.0,
        temperature_junction_celsius=45.0,
        temperature_memory_celsius=60.0,
        fan_rpm=0,
        power_watts=17.0,
    )
    base.update(overrides)
    from app.schemas.monitoring import GpuSampleSchema
    return GpuSampleSchema(**base)


def test_snapshot_includes_gpu_when_orchestrator_has_sample():
    """telemetry.json must carry a 'gpu' key with the latest collector sample."""
    worker = MonitoringWorker()
    captured: dict = {}

    def _capture(filename, data):
        if filename == TELEMETRY_FILE:
            captured["data"] = data

    sample = _make_gpu_sample()

    with patch("app.services.monitoring.worker_service.write_shm", side_effect=_capture), \
         patch("app.services.telemetry.get_history", return_value=_EMPTY_LEGACY_TELEMETRY), \
         patch("app.services.telemetry.get_latest_cpu_usage", return_value=None), \
         patch("app.services.telemetry.get_latest_memory_sample", return_value=None), \
         patch("app.services.monitoring.orchestrator.MonitoringOrchestrator.get_gpu_current",
               return_value=sample):
        worker._write_telemetry_snapshot()

    assert "data" in captured, "snapshot did not write to TELEMETRY_FILE"
    gpu = captured["data"].get("gpu")
    assert gpu is not None, "telemetry.json must include a 'gpu' key when collector has a sample"
    assert gpu["temperature_edge_celsius"] == 41.0
    assert gpu["temperature_junction_celsius"] == 45.0
    assert gpu["temperature_memory_celsius"] == 60.0


def test_snapshot_sets_gpu_to_none_when_orchestrator_has_no_sample():
    """If the orchestrator has no GPU sample, the 'gpu' key must be None (not missing)."""
    worker = MonitoringWorker()
    captured: dict = {}

    def _capture(filename, data):
        if filename == TELEMETRY_FILE:
            captured["data"] = data

    with patch("app.services.monitoring.worker_service.write_shm", side_effect=_capture), \
         patch("app.services.telemetry.get_history", return_value=_EMPTY_LEGACY_TELEMETRY), \
         patch("app.services.telemetry.get_latest_cpu_usage", return_value=None), \
         patch("app.services.telemetry.get_latest_memory_sample", return_value=None), \
         patch("app.services.monitoring.orchestrator.MonitoringOrchestrator.get_gpu_current",
               return_value=None):
        worker._write_telemetry_snapshot()

    assert "gpu" in captured["data"], "'gpu' key must always be present"
    assert captured["data"]["gpu"] is None
