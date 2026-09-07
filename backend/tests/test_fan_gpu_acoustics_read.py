"""Lesen der gpu_od/fan_ctrl-Knoten (#516).

Die Formate stammen von BaluNode, RX 7900 XT, Kernel 6.12.74 — nicht aus der
Kernel-Doku. Die Schluesselnamen sind uneinheitlich (FAN_TARGET_TEMPERATURE
gegen TARGET_TEMPERATURE, OD_ACOUSTIC_LIMIT gegen ACOUSTIC_LIMIT), deshalb
liest der Parser positionell.
"""
import os
from pathlib import Path

import pytest

from app.services.power.fan_gpu_acoustics import (
    find_fan_ctrl_dir,
    parse_node,
    read_acoustics,
)

TARGET_TEMPERATURE = (
    "FAN_TARGET_TEMPERATURE:\n"
    "95\n"
    "OD_RANGE:\n"
    "TARGET_TEMPERATURE: 25 105\n"
)

ACOUSTIC_LIMIT = (
    "OD_ACOUSTIC_LIMIT:\n"
    "3000\n"
    "OD_RANGE:\n"
    "ACOUSTIC_LIMIT: 500 3000\n"
)

MINIMUM_PWM = (
    "FAN_MINIMUM_PWM:\n"
    "23\n"
    "OD_RANGE:\n"
    "MINIMUM_PWM: 23 100\n"
)


def test_parses_value_and_range():
    node = parse_node(TARGET_TEMPERATURE)
    assert (node.value, node.minimum, node.maximum) == (95, 25, 105)


def test_ignores_the_inconsistent_key_names():
    """OD_ACOUSTIC_LIMIT oben, ACOUSTIC_LIMIT unten -- der Parser liest
    positionell, sonst uebernaehme er eine Inkonsistenz des Treibers."""
    node = parse_node(ACOUSTIC_LIMIT)
    assert (node.value, node.minimum, node.maximum) == (3000, 500, 3000)


def test_parses_a_range_whose_minimum_is_not_zero():
    node = parse_node(MINIMUM_PWM)
    assert (node.value, node.minimum, node.maximum) == (23, 23, 100)


def test_unparseable_text_returns_none():
    """Ein leerer oder fremd formatierter Knoten darf nicht werfen -- er wird
    einfach nicht angeboten."""
    assert parse_node("") is None
    assert parse_node("OD_FAN_CURVE:\n0: 0C 0%\n") is None


def _card_tree(tmp_path: Path) -> Path:
    """Bildet die echte Struktur nach: hwmon traegt einen device-Symlink auf
    das PCI-Geraet, darunter liegt gpu_od/fan_ctrl. Doppelpunktfrei, damit es
    auf Windows laeuft (#532)."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    fan_ctrl.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (fan_ctrl / "fan_target_temperature").write_text(TARGET_TEMPERATURE)
    (fan_ctrl / "acoustic_limit_rpm_threshold").write_text(ACOUSTIC_LIMIT)
    (fan_ctrl / "fan_minimum_pwm").write_text(MINIMUM_PWM)
    (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")

    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    os.symlink(device, hwmon / "device", target_is_directory=True)
    return hwmon


def test_finds_the_fan_ctrl_directory(tmp_path):
    hwmon = _card_tree(tmp_path)
    found = find_fan_ctrl_dir(hwmon)
    assert found is not None
    assert found.name == "fan_ctrl"


def test_a_card_without_the_interface_yields_none(tmp_path):
    """Aeltere Kernel haben gpu_od/fan_ctrl nicht -- das ist kein Fehler."""
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    assert find_fan_ctrl_dir(hwmon) is None


@pytest.mark.asyncio
async def test_fan_curve_falls_out_by_parsing_not_by_a_name_list(tmp_path):
    """fan_curve liegt im selben Verzeichnis und fuehrt fuenf Stuetzstellen.

    Es wird nicht ueber eine Namensliste ausgeschlossen, sondern faellt durch
    parse_node heraus -- deshalb kann read_acoustics aufzaehlen und nimmt
    kuenftige Skalare mit."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    nodes = await read_acoustics(fan_ctrl)
    assert set(nodes) == {
        "fan_target_temperature",
        "acoustic_limit_rpm_threshold",
        "fan_minimum_pwm",
    }
    assert nodes["fan_target_temperature"].value == 95


@pytest.mark.asyncio
async def test_an_unreadable_node_is_skipped_not_fatal(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    (fan_ctrl / "acoustic_target_rpm_threshold").write_text("Unsinn\n")
    nodes = await read_acoustics(fan_ctrl)
    assert "acoustic_target_rpm_threshold" not in nodes
    assert "fan_target_temperature" in nodes
