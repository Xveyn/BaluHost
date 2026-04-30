"""GpuMetricCollector tests."""
from datetime import datetime, timezone

import pytest

from app.models.monitoring import GpuSample
from app.schemas.monitoring import GpuSampleSchema
from app.services.monitoring.gpu_collector import GpuMetricCollector


class _FakeBackend:
    def __init__(self, detected: bool = True, raises: Exception | None = None):
        self._detected = detected
        self._raises = raises

    @property
    def detected(self) -> bool:
        return self._detected

    def device_info(self):
        from app.schemas.monitoring import GpuDeviceInfo
        return GpuDeviceInfo(vendor="amd", device_name="Test GPU")

    def read_sample(self):
        if self._raises:
            raise self._raises
        return {
            "vendor": "amd", "device_name": "Test GPU",
            "usage_percent": 50.0, "power_watts": 150.0,
        }


def test_db_model_is_gpu_sample():
    c = GpuMetricCollector()
    c.backend = _FakeBackend()
    assert c.get_db_model() is GpuSample


def test_collect_sample_when_detected():
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=True)
    s = c.collect_sample()
    assert isinstance(s, GpuSampleSchema)
    assert s.usage_percent == 50.0
    assert s.vendor == "amd"


def test_collect_sample_returns_none_when_not_detected():
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=False)
    assert c.collect_sample() is None


def test_collect_sample_swallows_backend_exceptions(caplog):
    import logging
    caplog.set_level(logging.ERROR)
    c = GpuMetricCollector()
    c.backend = _FakeBackend(raises=RuntimeError("boom"))
    assert c.collect_sample() is None
    assert any("GPU sample" in r.message for r in caplog.records)


def test_round_trip_sample_db_dict():
    c = GpuMetricCollector()
    c.backend = _FakeBackend()
    sample = GpuSampleSchema(
        timestamp=datetime.now(timezone.utc),
        vendor="amd", device_name="RX 7900 XT",
        usage_percent=65.0, vram_used_bytes=8_000_000_000,
        vram_total_bytes=20_000_000_000, power_watts=200.0,
    )
    d = c.sample_to_db_dict(sample)
    assert d["vendor"] == "amd"
    assert d["power_watts"] == 200.0
    record = GpuSample(**d)
    back = c.db_to_sample(record)
    assert back.usage_percent == 65.0
    assert back.device_name == "RX 7900 XT"


def test_detected_property_mirrors_backend():
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=False)
    assert c.detected is False
    c.backend = _FakeBackend(detected=True)
    assert c.detected is True
