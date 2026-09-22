"""Die sudoers-Vorlage deckt genau die Units ab, die der Code neu startet.

Ohne diese Prüfung fällt eine neue Unit erst in Produktion auf — als
`sudo: no entry`, gemeldet als fehlgeschlagener Neustart, den niemand erklärt.
Und eine übrig gebliebene Zeile erweitert den Radius, ohne dass sie jemand
benutzt.
"""
import re
from pathlib import Path

from app.services.system_restart import BALUHOST_UNITS

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-deploy-sudoers"
)


def _restart_units() -> set[str]:
    lines = [
        line
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    return set(re.findall(r"/usr/bin/systemctl restart (\S+)", "\n".join(lines)))


def test_sudoers_covers_exactly_the_units_we_restart():
    assert _restart_units() == set(BALUHOST_UNITS)


def test_no_wildcard_in_the_restart_entries():
    """Ein Platzhalter im Unit-Namen wäre ein viel längerer Hebel."""
    assert not [unit for unit in _restart_units() if "*" in unit or "?" in unit]
