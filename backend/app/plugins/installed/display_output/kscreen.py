"""Der einzige Ort, der weiss, dass es kscreen-doctor gibt.

Kapselt Aufruf, Auswertung und Argumentbau. Ein spaeterer Wechsel auf die
KScreen-D-Bus-Schnittstelle beruehrt nur diese Datei.

**Modi werden ueber ihre ID adressiert, niemals ueber den Namen.** libkscreen
bildet den Namen in ``findMode()`` mit ``qRound(refreshRate)``, weshalb 119,88
und 120,000 beide ``3840x2160@120`` heissen; die Funktion nimmt den ersten
Treffer und bricht ab. Eine Adressierung ueber den Namen setzt also je nach
Listenreihenfolge einen anderen Modus — ohne Fehlermeldung.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.plugins.installed.display_output.models import DisplayMode, DisplayOutput

logger = logging.getLogger(__name__)

# Auf wie viele Nachkommastellen zwei Bildwiederholraten als gleich gelten.
# Feiner zu unterscheiden hiesse, Gleitkomma-Rauschen zu Modi zu erklaeren.
_RATE_PRECISION = 3


def parse_modes(raw_modes: object) -> List[DisplayMode]:
    """Wandelt die Modenliste eines Ausgangs in eine anzeigbare Liste.

    Drei Schritte, alle drei aus gemessenen Daten begruendet:

    1. **Exakte Dubletten zusammenfassen** (gleiche Breite, Hoehe und
       Bildwiederholrate). Auf BaluNode traegt HDMI-A-1 fuenf solcher Paare;
       sie unterscheiden sich nur in DRM-Timing-Flags (CEA gegen DMT), was
       sich einem Menschen nicht sinnvoll anzeigen laesst. Die kleinere ID
       gewinnt.
    2. **Absteigend nach Flaeche, dann nach Rate sortieren.** kscreen-doctor
       liefert lexikografisch nach ID-String ("1", "10", "11", ..., "2", "20").
    3. Die Rate bleibt **ungerundet** — ``119.88`` und ``120.00`` sind der
       einzige Unterschied, an dem ein Mensch die beiden 4K-Modi von DP-3
       auseinanderhaelt.

    Args:
        raw_modes: Die ``modes``-Liste eines Ausgangs aus ``kscreen-doctor -j``.

    Returns:
        Sortierte, entdoppelte Modi. Unbrauchbare Eintraege werden
        uebersprungen, nicht als Fehler gemeldet — ein defekter Modus darf
        die Enumeration nicht scheitern lassen.
    """
    if not isinstance(raw_modes, list):
        return []

    seen: dict[tuple, DisplayMode] = {}
    for raw in raw_modes:
        if not isinstance(raw, dict):
            continue
        size = raw.get("size")
        mode_id = raw.get("id")
        if not isinstance(size, dict) or mode_id is None:
            logger.debug("Modus ohne Groesse oder ID uebersprungen: %r", raw)
            continue
        width = size.get("width")
        height = size.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            continue
        try:
            rate = float(raw.get("refreshRate", 0.0))
        except (TypeError, ValueError):
            continue

        mode = DisplayMode(
            id=str(mode_id),
            name=str(raw.get("name", "")),
            width=width,
            height=height,
            refresh_rate=rate,
        )
        key = (width, height, round(rate, _RATE_PRECISION))
        existing = seen.get(key)
        # Kleinere ID gewinnt. IDs sind Zeichenketten, deshalb numerisch
        # vergleichen, wo moeglich - sonst waere "10" kleiner als "9".
        if existing is None or _id_sort_key(mode.id) < _id_sort_key(existing.id):
            seen[key] = mode

    return sorted(seen.values(), key=lambda m: (-(m.width * m.height), -m.refresh_rate, m.id))


def _id_sort_key(mode_id: str) -> tuple:
    """Sortierschluessel, der numerische IDs numerisch ordnet."""
    return (0, int(mode_id)) if mode_id.isdigit() else (1, mode_id)


def parse_outputs(payload: object) -> List[DisplayOutput]:
    """Liest die Ausgangsliste aus der JSON-Struktur von ``kscreen-doctor -j``.

    ``lit`` bleibt hier ``None``: dieses Modul kennt sysfs nicht. Die
    DRM-Ebene ergaenzt das Backend (Task 4).

    Jeder Feldzugriff laeuft ueber ``.get()``. Die Felder sind nicht bei jedem
    Ausgang vorhanden — auf BaluNode traegt HDMI-A-1 ein ``vrrPolicy``, DP-3
    nicht.
    """
    if not isinstance(payload, dict):
        return []
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        return []

    outputs: List[DisplayOutput] = []
    for raw in raw_outputs:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            continue
        preferred = raw.get("preferredModes")
        preferred_id: Optional[str] = None
        if isinstance(preferred, list) and preferred:
            preferred_id = str(preferred[0])
        current = raw.get("currentModeId")

        outputs.append(
            DisplayOutput(
                name=name,
                connected=bool(raw.get("connected", False)),
                selected=bool(raw.get("enabled", False)),
                lit=None,
                current_mode_id=str(current) if current is not None else None,
                preferred_mode_id=preferred_id,
                scale=float(raw.get("scale", 1.0) or 1.0),
                priority=int(raw.get("priority", 0) or 0),
                modes=parse_modes(raw.get("modes")),
            )
        )
    return outputs
