"""Rueckgabe von pwm_enable an die Board-Automatik (#534).

Der Rueckgabe-Write umgeht das Backoff aus #533 von selbst: dessen Sperre sitzt
in set_pwm (fan_backend_linux.py:168-174), nicht in _write_hwmon_file. Laege sie
davor, unterbliebe die Rueckgabe ausgerechnet bei den Kanaelen, die zuvor
Schreibfehler hatten -- den kritischsten.
"""
import errno
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_dev import DevFanControlBackend
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _tree(tmp_path: Path) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text("1\n")
    (hwmon / "fan1_input").write_text("900\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


async def _backend(tmp_path, monkeypatch):
    klass = _tree(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()
    return backend, next(iter(backend._fan_cache))


@pytest.mark.asyncio
async def test_release_writes_the_value(tmp_path, monkeypatch):
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    ok = await backend.release_to_board(fan_id, 5)

    assert ok is True
    path = backend._fan_cache[fan_id]["pwm_enable_path"]
    assert path.read_text().strip() == "5"


@pytest.mark.asyncio
async def test_release_verifies_by_reading_back(tmp_path, monkeypatch):
    """Ein still ignorierter Write darf nicht als Erfolg durchgehen."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    async def swallow(path, value):
        return True, None   # tut so, als haette es geschrieben

    monkeypatch.setattr(backend, "_write_hwmon_file", swallow)

    ok = await backend.release_to_board(fan_id, 5)

    assert ok is False


@pytest.mark.asyncio
async def test_release_reports_write_failure(tmp_path, monkeypatch):
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    async def refuse(path, value):
        return False, errno.EINVAL

    monkeypatch.setattr(backend, "_write_hwmon_file", refuse)

    assert await backend.release_to_board(fan_id, 5) is False


@pytest.mark.asyncio
async def test_release_ignores_the_write_backoff(tmp_path, monkeypatch):
    """Genau die Kanaele mit Schreibfehlern brauchen die Rueckgabe."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    backend._write_backoff[fan_id] = (8, backend._monotonic() + 900)

    assert await backend.release_to_board(fan_id, 5) is True


@pytest.mark.asyncio
async def test_release_on_unknown_fan_is_false(tmp_path, monkeypatch):
    backend, _ = await _backend(tmp_path, monkeypatch)
    assert await backend.release_to_board("gibt-es-nicht:pwm9", 5) is False


@pytest.mark.asyncio
async def test_dev_backend_release_is_a_noop():
    backend = DevFanControlBackend(get_settings())
    fans = await backend.get_fans()
    assert await backend.release_to_board(fans[0].fan_id, 5) is True
