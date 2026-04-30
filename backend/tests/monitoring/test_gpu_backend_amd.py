"""AMD GPU backend tests with sysfs fixtures."""
import struct
from pathlib import Path

import pytest

from app.services.monitoring.gpu.amd_backend import AmdGpuBackend

FIX_7900XT = Path(__file__).parent.parent / "fixtures" / "amd_gpu" / "7900xt"
FIX_IGPU = Path(__file__).parent.parent / "fixtures" / "amd_gpu" / "with_igpu"


def test_detects_single_dgpu():
    b = AmdGpuBackend(sysfs_root=FIX_7900XT)
    assert b.detected is True
    info = b.device_info()
    assert info.vendor == "amd"
    assert info.pci_slot == "0000:03:00.0"
    assert info.vram_total_bytes == 21474836480


def test_skips_igpu_picks_dgpu():
    """card0 is iGPU (no pp_dpm_sclk), card1 is dGPU — pick card1."""
    b = AmdGpuBackend(sysfs_root=FIX_IGPU)
    assert b.detected is True
    assert b.device_info().pci_slot == "0000:03:00.0"


def test_no_amdgpu_present(tmp_path):
    """Empty sysfs → detected is False."""
    (tmp_path / "sys" / "class" / "drm").mkdir(parents=True)
    b = AmdGpuBackend(sysfs_root=tmp_path)
    assert b.detected is False


def test_read_sample_core_metrics():
    b = AmdGpuBackend(sysfs_root=FIX_7900XT)
    s = b.read_sample()
    assert s["vendor"] == "amd"
    assert s["usage_percent"] == 42.0
    assert s["vram_used_bytes"] == 6442450944
    assert s["vram_total_bytes"] == 21474836480
    assert s["core_clock_mhz"] == 2400.0
    assert s["memory_clock_mhz"] == 2500.0
    assert s["temperature_edge_celsius"] == 55.0
    assert s["temperature_junction_celsius"] == 65.0
    assert s["temperature_memory_celsius"] == 70.0
    assert s["fan_rpm"] == 1500
    assert s["power_watts"] == 180.0


def test_read_sample_missing_sensor_yields_none(tmp_path):
    """Delete one sysfs file — that metric should be absent/None, rest should survive."""
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    (copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_busy_percent").unlink()
    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    assert s.get("usage_percent") is None
    assert s["temperature_edge_celsius"] == 55.0


def _make_gpu_metrics_v1_4(
    gfx: int, mm: int, vcn0: int, vcn1: int, vcn2: int, vcn3: int
) -> bytes:
    """Generate a minimal v1.4 gpu_metrics blob.

    Layout (relevant fields only, little-endian):
      0: size u16
      2: format_revision u8
      3: content_revision u8
      36: average_gfx_activity u16 (0.01% units)
      38: average_mm_activity u16
      152: vcn_activity[4] u16 each
    """
    STRUCT_SIZE = 296
    buf = bytearray(STRUCT_SIZE)
    struct.pack_into("<H", buf, 0, STRUCT_SIZE)
    buf[2] = 1  # format_revision
    buf[3] = 4  # content_revision
    struct.pack_into("<H", buf, 36, gfx)
    struct.pack_into("<H", buf, 38, mm)
    struct.pack_into("<HHHH", buf, 152, vcn0, vcn1, vcn2, vcn3)
    return bytes(buf)


def test_gpu_metrics_v1_4_parses_engines(tmp_path):
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    metrics_file = copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_metrics"
    metrics_file.write_bytes(_make_gpu_metrics_v1_4(gfx=7500, mm=2500, vcn0=3000, vcn1=0, vcn2=0, vcn3=1500))

    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    assert s["engine_gfx_percent"] == pytest.approx(75.0, abs=0.1)
    assert s["engine_compute_percent"] == pytest.approx(75.0, abs=0.1)
    assert s["engine_decode_percent"] == pytest.approx(30.0, abs=0.1)
    assert s["engine_encode_percent"] == pytest.approx(15.0, abs=0.1)


def test_gpu_metrics_unknown_revision_yields_none(tmp_path):
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    metrics = bytearray(32)
    struct.pack_into("<H", metrics, 0, 32)
    metrics[2] = 99  # unknown format_revision
    metrics[3] = 0
    (copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_metrics").write_bytes(bytes(metrics))

    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    assert s["engine_gfx_percent"] is None
    assert s["temperature_edge_celsius"] == 55.0
