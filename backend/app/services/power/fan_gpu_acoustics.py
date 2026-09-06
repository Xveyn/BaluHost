"""Akustik-Knoten der AMD-GPU unter gpu_od/fan_ctrl lesen und schreiben (#516).

Zustandslos: kein Datenbankzugriff, keine Konfiguration. Die aufrufende
Dienstschicht entscheidet, was gesetzt wird und was die Baseline ist.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_RANGE_LINE = re.compile(r"^\s*[A-Z_]+:\s*(-?\d+)\s+(-?\d+)\s*$")


@dataclass(frozen=True)
class ParsedNode:
    value: int
    minimum: int
    maximum: int


def parse_node(text: str) -> Optional[ParsedNode]:
    """Wert und Bereich aus dem Knoteninhalt.

    Positionell gelesen, nicht ueber Schluesselnamen: der Treiber schreibt
    sie uneinheitlich (FAN_TARGET_TEMPERATURE gegen TARGET_TEMPERATURE).
    Der Wert ist die Zeile nach der ersten Kopfzeile, der Bereich sind die
    zwei Zahlen nach OD_RANGE:.

    Returns:
        None, wenn der Inhalt nicht dieser Form folgt -- etwa fan_curve, das
        fuenf Stuetzstellen statt eines Skalars fuehrt.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return None

    try:
        value = int(lines[1])
    except ValueError:
        return None

    try:
        range_index = lines.index("OD_RANGE:")
    except ValueError:
        return None
    if range_index + 1 >= len(lines):
        return None

    match = _RANGE_LINE.match(lines[range_index + 1])
    if match is None:
        return None

    return ParsedNode(value=value, minimum=int(match.group(1)),
                      maximum=int(match.group(2)))


def find_fan_ctrl_dir(hwmon_dir: Path) -> Optional[Path]:
    """Vom hwmon-Verzeichnis zum gpu_od/fan_ctrl-Verzeichnis der Karte.

    Nutzt die vorhandene Geraeteaufloesung aus fan_gpu_manual, damit die in
    #480 gelernten Fallstricke nicht ein zweites Mal geloest werden: der
    device-Symlink ist der Primaerweg, der Aufwaertslauf funktioniert nur in
    synthetischen Baeumen.
    """
    from app.services.power.fan_gpu_manual import _device_from_hwmon

    device = _device_from_hwmon(hwmon_dir)
    if device is None:
        return None
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    return fan_ctrl if fan_ctrl.is_dir() else None


async def read_acoustics(fan_ctrl_dir: Path) -> Dict[str, ParsedNode]:
    """Die angebotenen Skalare mit Wert und vom Treiber gemeldetem Bereich.

    Aufgezaehlt statt fest verdrahtet: gelesen wird, was im Verzeichnis liegt,
    und behalten wird, was sich als Skalar parsen laesst. Damit faellt
    fan_curve von selbst heraus -- es fuehrt fuenf Stuetzstellen und kein
    parse_node-Ergebnis -- und ein kuenftiger Knoten (ab Kernel 6.13
    fan_zero_rpm_enable) kommt ohne Codeaenderung mit.

    Was BaluHost davon zu SETZEN anbietet, entscheidet die Erlaubnisliste in
    Task 2. Lesen ist offen, Schreiben ist auf bekannte Namen beschraenkt.
    """
    nodes: Dict[str, ParsedNode] = {}
    for path in sorted(fan_ctrl_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            parsed = parse_node(path.read_text())
        except OSError as exc:
            logger.debug("Akustik-Knoten %s nicht lesbar: %s", path.name, exc)
            continue
        if parsed is not None:
            nodes[path.name] = parsed
    return nodes


