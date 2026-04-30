"""Verify GpuSample model and MetricType.GPU enum value."""
from app.models.monitoring import GpuSample, MetricType


def test_metric_type_has_gpu():
    assert MetricType.GPU.value == "gpu"


def test_gpu_sample_columns():
    expected = {
        "id", "timestamp", "vendor", "device_name", "pci_slot",
        "usage_percent", "engine_gfx_percent", "engine_compute_percent",
        "engine_decode_percent", "engine_encode_percent",
        "vram_used_bytes", "vram_total_bytes",
        "core_clock_mhz", "memory_clock_mhz",
        "temperature_edge_celsius", "temperature_junction_celsius",
        "temperature_memory_celsius",
        "fan_rpm", "power_watts",
    }
    actual = {c.name for c in GpuSample.__table__.columns}
    assert actual == expected


def test_gpu_sample_tablename():
    assert GpuSample.__tablename__ == "gpu_samples"
