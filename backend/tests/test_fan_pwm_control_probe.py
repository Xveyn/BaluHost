"""probe_amd_pwm_control: firmware-verwaltete Luefterkurven erkennen (RDNA3+, #480)."""
from pathlib import Path

from app.schemas.fans import PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control


def _hardware_shaped_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Bildet die ECHTE sysfs-Struktur nach.

    Auf der Hardware liegt hwmon unter /sys/class/hwmon/hwmonN und traegt einen
    'device'-Symlink auf das PCI-Geraet. KEIN Elternverzeichnis heisst 'device'
    — genau daran ist der erste Entwurf gescheitert.
    """
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon2"
    device = hwmon / "device"
    device.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    (device / "vendor").write_text("0x1002\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
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
