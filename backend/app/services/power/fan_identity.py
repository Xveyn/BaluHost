"""Stabile Chip-Identitaet fuer hwmon-Knoten (#532).

Bildet die libsensors-Kennung <prefix>-<bus>-<adresse>, damit Luefter- und
Sensor-IDs ein hwmon-Renumbering ueberleben. Normativ ist lm-sensors 3.6.2
(lib/sysfs.c, lib/data.c); Regeln aus master gelten fuer diese Zielhardware
nicht.
"""
from __future__ import annotations

import re
from typing import Optional

# "0000:03:00.0" -- Domain, Bus, Slot, Funktion
_PCI_BDF = re.compile(
    r"^([0-9a-fA-F]{4}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-9a-fA-F])$"
)
# "nct6775.656" / "foo:42" -- Suffix wird DEZIMAL gelesen
_PLATFORM_DECIMAL = re.compile(r"^[A-Za-z0-9_-]+[.:](\d+)")
# "f0000000.hwmon" -- Device-Tree-Adresse, hexadezimal
_PLATFORM_HEX = re.compile(r"^([0-9a-fA-F]+)\.")


def encode_pci_address(dev_name: str) -> Optional[int]:
    """PCI-Adresse nach lib/sysfs.c: (domain<<16)+(bus<<8)+(slot<<3)+fn."""
    match = _PCI_BDF.match(dev_name)
    if not match:
        return None
    domain, bus, slot, fn = (int(group, 16) for group in match.groups())
    return (domain << 16) + (bus << 8) + (slot << 3) + fn


def encode_platform_address(dev_name: str) -> Optional[int]:
    """Platform-Adresse: dezimaler Suffix, sonst Device-Tree-Hex, sonst None.

    Erste bewusste Abweichung von libsensors 3.6.2: sscanf ("%d") traegt dem
    Eintritt ohne Stringende-Anker Rechnung -- "nct6775.656.1" liefert 656.
    Libsensors' "%*[a-zA-Z0-9_]%*1[.:]%d" haette das gleiche Ergebnis.

    Zweite bewusste Abweichung: Zeichenklasse enthaelt Bindestrich, normatives
    Scanset %*[a-zA-Z0-9_] nicht. Ohne Bindestrich fiele "abc-def.5" in den
    Hex-Parser-Unfall (sscanf "%x" liest "abc" -> 0xabc). Stattdessen lesen
    wir den Suffix. Betroffen sind nur Chips, die `sensors` ohnehin nicht listet.
    """
    match = _PLATFORM_DECIMAL.match(dev_name)
    if match:
        return int(match.group(1), 10)
    match = _PLATFORM_HEX.match(dev_name)
    if match:
        return int(match.group(1), 16)
    return None


def format_chip_name(prefix: str, bus: str, addr: int) -> str:
    """lib/data.c: "%s-isa-%04x" bzw. "%s-pci-%04x" -- Mindestbreite, nicht fix."""
    return f"{prefix}-{bus}-{addr:04x}"
