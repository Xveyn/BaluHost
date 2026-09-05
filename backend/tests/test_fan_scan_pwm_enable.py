"""Der Scan liest pwm_enable, bevor der erste Write ihn ueberschreibt (#534).

_scan_pwm_fans laeuft aus is_available() beim Backend-Init -- einmal pro Start
und vor dem ersten set_pwm. Das ist der einzige Moment, in dem der Board-Wert
ueberhaupt sichtbar sein kann.
"""
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _tree(tmp_path: Path, enable_value: str | None) -> Path:
    """nct6798 an platform/nct6775.656, doppelpunktfrei (Windows)."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "fan1_input").write_text("900\n")
    (hwmon / "temp1_input").write_text("42000\n")
    if enable_value is not None:
        (hwmon / "pwm1_enable").write_text(enable_value + "\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_scan_captures_automatic_mode(tmp_path, monkeypatch):
    klass = _tree(tmp_path, "5")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] == 5


@pytest.mark.asyncio
async def test_scan_captures_manual_mode_as_is(tmp_path, monkeypatch):
    """Der Scan bewertet nicht -- er liest. Die Regel entscheidet spaeter."""
    klass = _tree(tmp_path, "1")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] == 1


@pytest.mark.asyncio
async def test_missing_enable_file_yields_none(tmp_path, monkeypatch):
    klass = _tree(tmp_path, None)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] is None
    assert cache[fan_id]["pwm_enable_path"] is None
