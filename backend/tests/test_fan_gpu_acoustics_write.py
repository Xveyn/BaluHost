"""Schreiben der Akustik-Knoten (#516).

Der Ablauf ist Bereichspruefung, Wert, dann 'c' zum Uebernehmen, dann
Ruecklesen. Der letzte Schritt ist nicht Zierde: derselbe Treiber verschluckt
laut #480 pwm_enable-Writes wortlos, ein Rueckgabewert von True beweist hier
also nichts.
"""
import os
from pathlib import Path

import pytest

from app.services.power.fan_gpu_acoustics import find_fan_ctrl_dir, resolve_restores, write_acoustic

TARGET_TEMPERATURE = (
    "FAN_TARGET_TEMPERATURE:\n95\nOD_RANGE:\nTARGET_TEMPERATURE: 25 105\n"
)


def _card_tree(tmp_path: Path) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    fan_ctrl.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (fan_ctrl / "fan_target_temperature").write_text(TARGET_TEMPERATURE)
    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    os.symlink(device, hwmon / "device", target_is_directory=True)
    return hwmon


def _recording_write(calls, *, applied: str | None = None, fan_ctrl=None):
    """Schreibfunktion in der Form von _write_hwmon_file.

    `applied` simuliert, was der Treiber danach zurueckliest -- damit die
    Ruecklese-Kontrolle pruefbar wird.
    """
    async def write(path: Path, value: str):
        calls.append((path.name, value))
        if applied is not None and value != "c":
            (fan_ctrl / path.name).write_text(
                f"FAN_TARGET_TEMPERATURE:\n{applied}\nOD_RANGE:\n"
                f"TARGET_TEMPERATURE: 25 105\n"
            )
        return True, None
    return write


@pytest.mark.asyncio
async def test_writes_the_value_then_commits(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 75,
        _recording_write(calls, applied="75", fan_ctrl=fan_ctrl),
    )

    assert ok is True
    assert calls == [
        ("fan_target_temperature", "75"),
        ("fan_target_temperature", "c"),
    ]


@pytest.mark.asyncio
async def test_a_value_outside_the_reported_range_is_refused(tmp_path):
    """Der Kernel lehnt selbst ab (EINVAL bei 200, gemessen). Die Pruefung
    bleibt, damit die Fehlermeldung aus der UI kommt statt aus dmesg."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 200, _recording_write(calls),
    )

    assert ok is False
    assert calls == [], "trotz ungueltigem Wert geschrieben"


@pytest.mark.asyncio
async def test_a_write_without_effect_is_a_failure(tmp_path):
    """Der Kern: der Treiber nimmt an und aendert nichts."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 75,
        _recording_write(calls, applied="95", fan_ctrl=fan_ctrl),
    )

    assert ok is False


@pytest.mark.asyncio
async def test_an_unknown_node_is_refused(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(fan_ctrl, "fan_curve", 1, _recording_write(calls))

    assert ok is False
    assert calls == []


# --- Die Ruecksetz-Entscheidung, rein und ohne sysfs ---------------------
#
# Sie steckte im Entwurf als dreifach bedingte Comprehension im Route-Handler.
# Genau diese Form versteckt Fehler; #534 hat dafuer fan_restore.py gebaut.

def test_unmanaging_a_value_restores_its_baseline():
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": None},
        baseline={"fan_target_temperature": 95},
    )
    assert restores == {"fan_target_temperature": 95}


def test_a_value_that_was_never_managed_is_not_touched():
    """Sonst schriebe ein Speichern-Klick eine Baseline auf einen Knoten, den
    BaluHost nie angefasst hat."""
    restores = resolve_restores(
        previous_desired={"fan_minimum_pwm": None},
        incoming={"fan_minimum_pwm": None},
        baseline={"fan_minimum_pwm": 23},
    )
    assert restores == {}


def test_without_a_baseline_nothing_is_restored():
    """Kein Rueckfall auf einen geratenen Herstellerstandard (#534)."""
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": None},
        baseline={"fan_target_temperature": None},
    )
    assert restores == {}


def test_a_changed_value_is_not_a_restore():
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": 80},
        baseline={"fan_target_temperature": 95},
    )
    assert restores == {}
