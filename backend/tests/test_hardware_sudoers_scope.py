"""Die tee-Regeln der Hardware-sudoers decken genau die Schreibstellen ab (#570 Punkt 5).

Gemessen auf BaluNode am 2026-09-07: der Dienstnutzer kann die PWM-Knoten NICHT
direkt schreiben (root:root 0644), jeder Luefter-Write laeuft also ueber
`sudo -n tee`. Die Regel ist damit der Hauptpfad der Luefterregelung -- und war
zugleich viel zu breit: Wildcards in sudoers-ARGUMENTEN matchen auch '/', und
sudo normalisiert Argumente nicht. '/sys/class/hwmon/*' deckte deshalb auch
'/sys/class/hwmon/../../etc/shadow' ab.

Dieser Test haelt die Vorlage gegen beide Seiten: die Pfade, die der Code
wirklich schreibt, muessen erlaubt bleiben, und die Ausbruchspfade muessen
abgelehnt werden.

Das Matching wird mit fnmatch nachgebildet -- ohne FNM_PATHNAME, weil genau das
sudos Verhalten bei Argumenten ist (sudoers(5): "When matching the command line
arguments, however, a slash does get matched by wildcards").
"""
import fnmatch
import re
from pathlib import Path

import pytest

from app.services.power.fan_gpu_acoustics import ACOUSTIC_NODES

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-hardware-sudoers"
)

# Die vier cpufreq-Dateien, die cpu_linux_backend._apply_profile_to_cpu schreibt.
CPUFREQ_NODES = (
    "scaling_governor",
    "scaling_min_freq",
    "scaling_max_freq",
    "energy_performance_preference",
)


def _tee_patterns() -> list[str]:
    """Die Argumentmuster aller `/usr/bin/tee`-Eintraege der Vorlage.

    Erfasst Cmnd_Alias-Zeilen wie Direkteintraege, weil beide dieselbe Form
    haben: '/usr/bin/tee <muster>', getrennt durch Komma oder Zeilenende.
    Zeilenfortsetzungen ('\\' am Zeilenende) werden vorher zusammengezogen --
    ohne das findet der Ausdruck in einem Cmnd_Alias-Block keinen einzigen
    Eintrag.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    text = re.sub(r"\\\s*\n\s*", " ", text)
    return re.findall(r"/usr/bin/tee\s+([^\s,]+)", text)


def _erlaubt(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in _tee_patterns())


def test_die_vorlage_ist_ueberhaupt_lesbar_und_traegt_muster():
    """Schutz gegen einen vakuum-gruenen Test: findet der Ausdruck nichts,
    waeren alle Ablehnungs-Zusicherungen unten trivial erfuellt."""
    assert TEMPLATE.is_file()
    assert len(_tee_patterns()) >= 12


@pytest.mark.parametrize("path", [
    "/sys/class/hwmon/hwmon3/pwm1",
    "/sys/class/hwmon/hwmon3/pwm7",
    "/sys/class/hwmon/hwmon12/pwm1",
    "/sys/class/hwmon/hwmon3/pwm1_enable",
    "/sys/class/hwmon/hwmon3/pwm7_enable",
])
def test_die_pwm_knoten_bleiben_erlaubt(path):
    """fan_backend_linux schreibt pwm{n} und pwm{n}_enable -- ohne diese
    Erlaubnis steht die Luefterregelung auf dieser Box still."""
    assert _erlaubt(path)


@pytest.mark.parametrize("node", ACOUSTIC_NODES)
def test_jeder_akustik_knoten_bleibt_erlaubt(node):
    """An ACOUSTIC_NODES gekoppelt statt abgeschrieben: kommt ein fuenfter
    Knoten dazu (ab Kernel 6.13 fan_zero_rpm_enable), schlaegt dieser Test an,
    solange die sudoers-Vorlage nicht nachgezogen wurde."""
    assert _erlaubt(f"/sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl/{node}")


@pytest.mark.parametrize("node", CPUFREQ_NODES)
def test_jede_cpufreq_datei_bleibt_erlaubt(node):
    assert _erlaubt(f"/sys/devices/system/cpu/cpu0/cpufreq/{node}")
    assert _erlaubt(f"/sys/devices/system/cpu/cpu11/cpufreq/{node}")


@pytest.mark.parametrize("path", [
    # Der Ausbruch, der die alte Fassung zur Rechteausweitung machte.
    "/sys/class/hwmon/../../etc/shadow",
    "/sys/class/hwmon/hwmon0/../../../../etc/shadow",
    "/sys/devices/system/cpu/cpu0/cpufreq/../../../../../etc/shadow",
    "/etc/shadow",
    # Geraetesteuerung ueber den device-Symlink: auf dieser Box sind hwmon0
    # und hwmon1 die NVMe-Controller.
    "/sys/class/hwmon/hwmon0/device/driver/unbind",
    "/sys/class/hwmon/hwmon2/device/remove",
    "/sys/class/hwmon/hwmon2/device/reset",
    # Nachbarn im selben Verzeichnis, die niemand schreiben muss.
    "/sys/class/hwmon/hwmon3/temp1_input",
    "/sys/class/hwmon/hwmon3/pwm1_auto_point1_pwm",
    "/sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl/fan_curve",
    "/sys/devices/system/cpu/cpu0/cpufreq/scaling_setspeed",
])
def test_alles_andere_wird_abgelehnt(path):
    assert not _erlaubt(path)
