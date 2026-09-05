"""probe_amd_pwm_control: firmware-verwaltete Luefterkurven erkennen (RDNA3+, #480)."""
import os
from pathlib import Path

from app.schemas.fans import PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control


def _hardware_shaped_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Bildet die ECHTE sysfs-Struktur nach.

    Auf der Hardware liegt hwmon unter /sys/class/hwmon/hwmonN und traegt einen
    'device'-Symlink auf das PCI-Geraet. KEIN Elternverzeichnis heisst 'device'
    — genau daran ist der erste Entwurf gescheitert.

    Platform-foermig (kein PCI-Doppelpunkt, #532) mit device/subsystem-Symlink,
    damit die stabile Identitaetsableitung greift statt in den Fallback zu
    fallen -- die zwei Scan-Tests unten pruefen genau das.
    """
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)

    hwmon = sysfs / "class" / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    os.symlink(device, hwmon / "device", target_is_directory=True)
    return hwmon


def _drm_shaped_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Die synthetische Struktur, die bestehende Tests verwenden."""
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (hwmon / "name").write_text("amdgpu\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
    return hwmon


def test_hardware_layout_detects_firmware_managed(tmp_path):
    """Der Fall, der in Produktion zaehlt."""
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.FIRMWARE_MANAGED


def test_hardware_layout_without_fan_curve_is_supported(tmp_path):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_drm_layout_still_works(tmp_path):
    """Der Aufwaertslauf bleibt als Fallback erhalten."""
    hwmon = _drm_shaped_tree(tmp_path, with_fan_curve=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.FIRMWARE_MANAGED


def test_gpu_od_without_fan_curve_is_supported(tmp_path):
    """gpu_od/ allein genuegt nicht — nur fan_curve ist der Marker."""
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    (hwmon / "device" / "gpu_od" / "fan_ctrl").mkdir(parents=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_non_amd_vendor_is_supported(tmp_path):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    (hwmon / "device" / "vendor").write_text("0x10de\n")
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_board_sensor_without_device_is_supported(tmp_path):
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.mark.asyncio
async def test_scan_marks_rdna3_fan_firmware_managed(tmp_path, monkeypatch):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    (hwmon / "pwm1").write_text("0\n")
    (hwmon / "fan1_input").write_text("0\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", hwmon.parent)
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))
    # Beweis, dass der Scan den stabilen Zweig trifft, nicht den Fallback
    # ("hwmon2_pwm1"): ohne device/subsystem-Symlink waere die ID instabil.
    assert fan_id == "amdgpu-isa-0001:pwm1"
    assert backend._fan_cache[fan_id]["identity_stable"] is True
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.FIRMWARE_MANAGED

    fans = await backend.get_fans()
    assert fans[0].pwm_control is PwmControl.FIRMWARE_MANAGED


@pytest.mark.asyncio
async def test_scan_marks_normal_fan_supported(tmp_path, monkeypatch):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "fan1_input").write_text("1200\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", hwmon.parent)
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))
    assert fan_id == "amdgpu-isa-0001:pwm1"
    assert backend._fan_cache[fan_id]["identity_stable"] is True
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.SUPPORTED


@pytest.mark.asyncio
async def test_dev_backend_exposes_a_firmware_managed_gpu_fan():
    import asyncio
    from app.services.power.fan_backend_dev import DevFanControlBackend

    backend = DevFanControlBackend(get_settings())
    fans = {f.fan_id: f for f in await backend.get_fans()}

    assert fans["dev_gpu_pwm1"].pwm_control is PwmControl.SUPPORTED
    assert fans["dev_gpu_rdna3_pwm1"].pwm_control is PwmControl.FIRMWARE_MANAGED

    # Verify set_pwm is rejected for firmware-managed fan
    assert await backend.set_pwm("dev_gpu_rdna3_pwm1", 80) is False

    # Verify that pwm_percent and target_rpm remain unchanged after rejected set_pwm
    assert backend._fans["dev_gpu_rdna3_pwm1"]["pwm_percent"] == 0
    assert backend._fans["dev_gpu_rdna3_pwm1"]["target_rpm"] == 0

    # Verify current_rpm stays at 0 across multiple get_fans() calls (no drift via fluctuation)
    for _ in range(5):
        fans = await backend.get_fans()
        fan = next(f for f in fans if f.fan_id == "dev_gpu_rdna3_pwm1")
        assert fan.rpm == 0, f"current_rpm drifted to {fan.rpm}"
        await asyncio.sleep(0.05)  # Small delay between calls to test stability
