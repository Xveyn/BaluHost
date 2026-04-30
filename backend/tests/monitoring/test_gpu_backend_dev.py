"""Dev-mode GPU backend tests."""
from app.services.monitoring.gpu.dev_backend import DevGpuBackend
from app.services.monitoring.gpu.backend import GpuBackend


def test_dev_backend_implements_protocol():
    b = DevGpuBackend()
    # Protocol attributes
    assert b.detected is True
    info = b.device_info()
    assert info.vendor == "amd"
    assert "7900 XT" in info.device_name
    assert info.vram_total_bytes == 20 * 1024 ** 3


def test_dev_backend_read_sample_shape():
    b = DevGpuBackend()
    sample = b.read_sample()
    assert sample["vendor"] == "amd"
    assert "device_name" in sample
    assert "usage_percent" in sample
    for key in (
        "engine_gfx_percent", "engine_compute_percent",
        "engine_decode_percent", "engine_encode_percent",
        "vram_used_bytes", "vram_total_bytes",
        "core_clock_mhz", "memory_clock_mhz",
        "temperature_edge_celsius", "temperature_junction_celsius",
        "temperature_memory_celsius",
        "fan_rpm", "power_watts",
    ):
        assert key in sample, f"missing {key}"


def test_dev_backend_values_in_plausible_range():
    b = DevGpuBackend()
    s = b.read_sample()
    assert 0 <= s["usage_percent"] <= 100
    assert 0 <= s["engine_gfx_percent"] <= 100
    assert 40 <= s["temperature_edge_celsius"] <= 85
    assert 100 <= s["power_watts"] <= 300
    assert s["vram_total_bytes"] == 20 * 1024 ** 3
    assert 0 < s["vram_used_bytes"] <= s["vram_total_bytes"]
