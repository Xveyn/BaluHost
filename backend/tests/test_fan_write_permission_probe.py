"""Der Rechte-Probe muss den echten Schreibpfad treffen (#552).

Zwei Messungen auf BaluNode (2026-09-06) geben den Rahmen vor:

1. Ein pwm-Write scheitert mit EBUSY, solange pwm_enable >= 2 steht:

       $ sudo -n tee /sys/class/hwmon/hwmon3/pwm1 < /sys/class/hwmon/hwmon3/pwm1
       tee: /sys/class/hwmon/hwmon3/pwm1: Das Geraet oder die Ressource ist belegt
       exit=1

   Seit #556 steht nach jedem Dienst-Ende genau dieser Auto-Modus an. Ein
   Probe, der pwm schreibt, meldet also bei jedem Start "readonly".

2. Ein Write auf pwm_enable mit dem gerade gelesenen Wert geht durch und
   laesst den Modus unveraendert:

       $ sudo -n tee /sys/class/hwmon/hwmon3/pwm1_enable < .../pwm1_enable
       5
       exit=0
       $ cat /sys/class/hwmon/hwmon3/pwm1_enable
       5

Daraus folgt der Entwurf: geprueft wird auf dem Modus-Register, mit seinem
eigenen Wert. Dieselbe Datei, dieselben Rechte, dieselbe sudoers-Regel wie im
Regelbetrieb -- aber ohne Eingriff.

os.access wird in diesen Tests auf False gezwungen und subprocess.run zum
Scheitern gebracht. Beides bildet die Produktionslage nach: die pwm-Dateien
gehoeren root:root 0644, der Dienst laeuft als unprivilegierter Nutzer, und
kein Test darf `sudo` tatsaechlich aufrufen.
"""
import errno
import os
import subprocess
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.schemas.fans import PwmControl
from app.services.power.fan_backend_linux import LinuxFanControlBackend


class _FailedProcess:
    returncode = 1
    stdout = b""
    stderr = b"tee: Permission denied\n"


@pytest.fixture
def unprivileged(monkeypatch):
    """Kein direktes Schreibrecht, kein nutzbares sudo."""
    monkeypatch.setattr(os, "access", lambda *args, **kwargs: False)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _FailedProcess())


def _gpu_chip(sysfs: Path) -> None:
    """amdgpu mit gpu_od/fan_ctrl/fan_curve -- also FIRMWARE_MANAGED."""
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    fan_ctrl.mkdir(parents=True)
    (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
    (device / "vendor").write_text("0x1002\n")

    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1").write_text("0\n")
    (hwmon / "pwm1_enable").write_text("2\n")
    (hwmon / "fan1_input").write_text("0\n")
    (hwmon / "temp1_input").write_text("35000\n")

    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon2", target_is_directory=True)


def _super_io_chip(sysfs: Path) -> None:
    """nct6798 im Auto-Modus, wie nach einem Dienst-Ende seit #556."""
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("163\n")
    (hwmon / "pwm1_enable").write_text("5\n")
    (hwmon / "fan1_input").write_text("463\n")
    (hwmon / "temp1_input").write_text("32000\n")

    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)


def _both_chips(tmp_path: Path) -> Path:
    """Die Lage auf BaluNode: der GPU-Chip steht vor dem Super-I/O.

    hwmon2 < hwmon3, der firmware-verwaltete Luefter kommt also zuerst --
    seit #553 nicht mehr zufaellig, sondern verlaesslich.
    """
    sysfs = tmp_path / "sys"
    _gpu_chip(sysfs)
    _super_io_chip(sysfs)
    return sysfs / "class" / "hwmon"


async def _scanned_backend(klass: Path, monkeypatch) -> LinuxFanControlBackend:
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()
    return backend


@pytest.mark.asyncio
async def test_probe_skips_firmware_managed_fan(tmp_path, monkeypatch, unprivileged):
    """Der erste Luefter ist der GPU-Luefter -- und der sagt nichts aus.

    set_pwm fasst einen FIRMWARE_MANAGED-Kanal gar nicht erst an. Ein Probe,
    der ihn trotzdem beschreibt, misst eine Faehigkeit, die im Regelbetrieb
    nie gebraucht wird, und meldet deshalb readonly, obwohl die Steuerung
    arbeitet.
    """
    backend = await _scanned_backend(_both_chips(tmp_path), monkeypatch)
    gpu_fans = [f for f in backend._fan_cache.values()
                if f.get("pwm_control") is PwmControl.FIRMWARE_MANAGED]
    assert gpu_fans, "der GPU-Luefter wurde nicht als firmware-verwaltet erkannt"

    await backend._check_write_permission()

    assert backend._has_write_permission is True


@pytest.mark.asyncio
async def test_probe_writes_the_mode_register_with_its_own_value(
        tmp_path, monkeypatch, unprivileged):
    """Geschrieben wird pwm_enable=5 auf den nct6798 -- der Wert, der dort steht.

    pwm taugt nicht: im Auto-Modus lehnt der Treiber den Write mit EBUSY ab
    (Messung im Modul-Docstring). Und ein pwm_enable=1, wie set_pwm es setzt,
    waere ein echter Eingriff als Nebenwirkung einer Frage -- er schaltete
    die Board-Automatik ab, die #556 gerade erst zurueckgegeben hat.
    """
    backend = await _scanned_backend(_both_chips(tmp_path), monkeypatch)

    written: list[tuple[Path, str]] = []

    async def recording_write(path, value):
        written.append((path, value))
        return True, None

    monkeypatch.setattr(backend, "_write_hwmon_file", recording_write)

    await backend._check_write_permission()

    assert len(written) == 1, f"erwartet genau ein Write, war: {written}"
    path, value = written[0]
    assert path.parent.name == "hwmon3", "der GPU-Luefter wurde angefasst"
    assert path.name == "pwm1_enable"
    assert value == "5"


@pytest.mark.asyncio
async def test_probe_reports_readonly_when_every_write_fails(
        tmp_path, monkeypatch, unprivileged):
    """Regressionsschutz: der Fix darf nicht pauschal True melden.

    Dieser Test schlaegt vor dem Fix nicht fehl -- die alte Fassung meldet
    hier ebenfalls readonly, nur aus dem falschen Grund. Er haelt fest, dass
    der neue Probe weiterhin ein Nein kennt.
    """
    backend = await _scanned_backend(_both_chips(tmp_path), monkeypatch)

    async def failing_write(path, value):
        return False, errno.EACCES

    monkeypatch.setattr(backend, "_write_hwmon_file", failing_write)

    await backend._check_write_permission()

    assert backend._has_write_permission is False
