"""Vorlage und Installationsskript fuehren dieselbe Dateiliste (#516).

Die udev-Regel existiert zweimal: als Vorlage unter deploy/install/templates
und als Here-Doc im Installationsskript. Laufen sie auseinander, traegt die
installierte Regel andere Pfade als die im Repo -- und die Diagnose beginnt
an der falschen Datei.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "deploy" / "install" / "templates" / "70-baluhost-amd-gpu.rules"
SCRIPT = REPO / "deploy" / "scripts" / "install-amd-gpu-permissions.sh"

ACOUSTIC_NODES = (
    "fan_target_temperature",
    "acoustic_limit_rpm_threshold",
    "acoustic_target_rpm_threshold",
    "fan_minimum_pwm",
)

_SYSFS = re.compile(r"/sys/class/drm/%k/device/[A-Za-z0-9_/]+")


def _sysfs_paths(text: str) -> set:
    return set(_SYSFS.findall(text))


def test_template_and_script_carry_the_same_paths():
    assert _sysfs_paths(TEMPLATE.read_text()) == _sysfs_paths(SCRIPT.read_text())


def test_the_acoustic_nodes_are_covered():
    paths = _sysfs_paths(TEMPLATE.read_text())
    for node in ACOUSTIC_NODES:
        assert any(p.endswith("gpu_od/fan_ctrl/" + node) for p in paths), node
