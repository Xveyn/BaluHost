"""Die Scan-Reihenfolge darf kein Dateisystem-Zufall sein (#553).

_scan_pwm_fans iterierte hwmon-Verzeichnisse, PWM-Kanaele und Temperatur-
Eingaenge unsortiert. Weder Path.iterdir() noch Path.glob() sortieren -- beide
liefern os.scandir-Reihenfolge. Damit war die Einfuegereihenfolge von
_fan_cache und die Wahl des Fallback-Sensors reine readdir-Reihenfolge.

Beide Tests erzwingen eine numerisch absteigende Eingangsreihenfolge, statt
sich auf die Reihenfolge des jeweiligen Dateisystems zu verlassen: auf NTFS
ist sie alphabetisch, auf ext4 hashbasiert. Ein Test, der die eine Ordnung
voraussetzt, waere auf dem anderen System gruen, ohne etwas zu pruefen.
"""
import os
import re
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _leading_number(name: str) -> int:
    """hwmon10 -> 10, pwm2 -> 2, temp10_input -> 10."""
    digits = re.search(r"\d+", name)
    return int(digits.group()) if digits else 0


@pytest.fixture
def descending_filesystem(monkeypatch):
    """Liefert Verzeichniseintraege numerisch absteigend.

    Das ist die denkbar unguenstigste Reihenfolge: ohne Sortierung im
    Produktivcode landet sie unveraendert im Cache, und die Erwartung
    (aufsteigend) schlaegt fehl. Mit Sortierung ist die Eingangsreihenfolge
    gleichgueltig -- genau die Eigenschaft, um die es geht.
    """
    original_iterdir = Path.iterdir
    original_glob = Path.glob

    def descending_iterdir(self):
        return iter(sorted(original_iterdir(self),
                           key=lambda p: _leading_number(p.name), reverse=True))

    def descending_glob(self, pattern):
        return iter(sorted(original_glob(self, pattern),
                           key=lambda p: _leading_number(p.name), reverse=True))

    monkeypatch.setattr(Path, "iterdir", descending_iterdir)
    monkeypatch.setattr(Path, "glob", descending_glob)


def _chip(sysfs: Path, device_name: str, hwmon_name: str, chip_name: str,
          pwm_channels: list[int], temp_inputs: dict[int, str]) -> None:
    """Ein Platform-Chip. Doppelpunktfrei, damit es auf Windows laeuft."""
    device = sysfs / "devices" / "platform" / device_name
    hwmon = device / "hwmon" / hwmon_name
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text(f"{chip_name}\n")

    for channel in pwm_channels:
        (hwmon / f"pwm{channel}").write_text("128\n")
        (hwmon / f"pwm{channel}_enable").write_text("1\n")
        (hwmon / f"fan{channel}_input").write_text("900\n")
    for number, millicelsius in temp_inputs.items():
        (hwmon / f"temp{number}_input").write_text(millicelsius + "\n")

    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / hwmon_name, target_is_directory=True)


def _two_chip_tree(tmp_path: Path) -> Path:
    """hwmon2 mit drei Kanaelen, hwmon10 mit einem.

    Die Indizes sind so gewaehlt, dass numerische und lexikografische Ordnung
    auseinanderfallen: lexikografisch steht "hwmon10" vor "hwmon2" und "pwm10"
    vor "pwm2". Ein blosses sorted() wuerde diesen Test nicht bestehen.
    """
    sysfs = tmp_path / "sys"
    _chip(sysfs, "chipa.100", "hwmon2", "chipa",
          pwm_channels=[1, 2, 10], temp_inputs={1: "42000", 10: "0"})
    _chip(sysfs, "chipb.200", "hwmon10", "chipb",
          pwm_channels=[1], temp_inputs={1: "38000"})
    return sysfs / "class" / "hwmon"


def _channel_order(cache: dict) -> list[tuple[str, str]]:
    """(hwmon-Verzeichnis, PWM-Datei) je Cache-Eintrag, in Cache-Reihenfolge."""
    return [(info["pwm_path"].parent.name, info["pwm_path"].name)
            for info in cache.values()]


@pytest.mark.asyncio
async def test_scan_order_is_numeric_not_filesystem_order(
        tmp_path, monkeypatch, descending_filesystem):
    """Chips und Kanaele stehen numerisch aufsteigend im Cache."""
    klass = _two_chip_tree(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    assert _channel_order(cache) == [
        ("hwmon2", "pwm1"),
        ("hwmon2", "pwm2"),
        ("hwmon2", "pwm10"),
        ("hwmon10", "pwm1"),
    ]


@pytest.mark.asyncio
async def test_temp_fallback_picks_lowest_numbered_sensor(
        tmp_path, monkeypatch, descending_filesystem):
    """Ohne CPU-Sensor bindet der Fallback an temp1, nicht an temp10.

    Auf BaluNode traegt der nct6798 temp1..temp13; temp10 ist PCH_CHIP_TEMP
    und meldet 0. Genau so ein Eingang darf nicht zur Kurvenquelle werden,
    bloss weil er in irgendeiner Ordnung zuerst kommt.
    """
    klass = _two_chip_tree(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    chip_a = [info for info in cache.values()
              if info["pwm_path"].parent.name == "hwmon2"]
    assert chip_a, "chipa wurde gar nicht gescannt"
    for info in chip_a:
        assert info["temp_path"].name == "temp1_input"
