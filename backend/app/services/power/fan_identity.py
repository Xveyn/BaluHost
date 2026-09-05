"""Stabile Chip-Identitaet fuer hwmon-Knoten (#532).

Bildet die libsensors-Kennung <prefix>-<bus>-<adresse>, damit Luefter- und
Sensor-IDs ein hwmon-Renumbering ueberleben. Normativ ist lm-sensors 3.6.2
(lib/sysfs.c, lib/data.c); Regeln aus master gelten fuer diese Zielhardware
nicht.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

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

    Erste bewusste Abweichung von libsensors 3.6.2: libsensors' zweiter
    sscanf ("%x.%*s") liefert bereits 1, wenn %x etwas konsumiert hat --
    auch wenn der Punkt danach nie matcht. Daraus werden asus-nb-wmi -> 0x0a
    und eeepc-wmi -> 0xeee: stabil, aber bedeutungslos. _PLATFORM_HEX
    verlangt den Punkt tatsaechlich und bildet damit den gemeinten
    Device-Tree-Fall ab statt des Parser-Unfalls. Betroffen sind nur Chips,
    die `sensors` ohnehin nicht listet.

    Technische Anmerkung zu _PLATFORM_DECIMAL: sscanf ("%d") liest den
    fuehrenden Ziffernlauf und ignoriert den Rest. Das Muster verzichtet
    bewusst auf einen Stringende-Anker ($), um dieses Verhalten nachzubilden.
    Ein Anker waere eine Abweichung -- "nct6775.656.1" wuerde dann None
    liefern statt 656. Keinen Anker zu setzen ist die Paritaet.

    Zweite bewusste Abweichung: Zeichenklasse enthaelt Bindestrich,
    normatives Scanset %*[a-zA-Z0-9_] nicht. Ohne Bindestrich fiele
    "abc-def.5" in den Hex-Parser-Unfall (sscanf "%x" liest "abc" -> 0xabc).
    Stattdessen lesen wir den Suffix.
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


logger = logging.getLogger(__name__)

# Bustypen, deren Adressformat wir bilden koennen.
_SUPPORTED_BUSES = {"pci": "pci", "platform": "isa", "of_platform": "isa"}
# Bustypen, die libsensors kennt und wir NICHT bilden. Wird einer davon
# getroffen, brechen wir sofort ab statt weiterzuklettern: bei drivetemp
# (scsi) landete man sonst auf dem AHCI-Controller und gaebe allen Platten
# desselben Controllers dieselbe Kennung.
_FALLBACK_BUSES = {"i2c", "spi", "scsi", "hid", "acpi", "mdio_bus", "sdio"}
_MAX_CLIMB = 12


@dataclass(frozen=True)
class ChipIdentity:
    key: str
    prefix: str
    stable: bool
    hwmon_name: str
    reason: Optional[str]


def _read_name(hwmon_dir: Path) -> Optional[str]:
    try:
        value = (hwmon_dir / "name").read_text().strip()
    except OSError:
        return None
    return value or None


def _subsystem_of(device: Path) -> Optional[str]:
    link = device / "subsystem"
    try:
        if not link.exists():
            return None
        return os.path.basename(os.path.realpath(link))
    except OSError:
        return None


def _unstable(hwmon_name: str, prefix: Optional[str], reason: str) -> ChipIdentity:
    # M-2: DEBUG statt WARNING. derive_all() laeuft nicht nur beim Start,
    # sondern bei jedem Sensor-Listing-Request (get_available_temp_sensors(),
    # _find_cpu_temp_sensor()) -- eine WARNING pro instabilem Chip UND
    # Request waere die Log-Flut aus #533 im Kleinen. Ein Chip, der instabil
    # ist, bleibt es fuer die Laufzeit des Prozesses; ein modulweiter Merker
    # gegen wiederholtes Loggen waere komplexer als der Nutzen hier
    # rechtfertigt -- DEBUG ist die einfachere Variante mit demselben Effekt
    # (bei Bedarf im Log sichtbar, aber ohne Dauerrauschen auf WARNING).
    logger.debug("hwmon %s: keine stabile Kennung (%s)", hwmon_name, reason)
    return ChipIdentity(key=hwmon_name, prefix=prefix or "Unknown",
                        stable=False, hwmon_name=hwmon_name, reason=reason)


def derive_chip_identity(hwmon_link: Path) -> ChipIdentity:
    """Leitet die stabile Kennung eines hwmon-Knotens ab.

    hwmon_link ist der Eintrag unter /sys/class/hwmon -- ein Symlink. Der
    Aufstieg laeuft ueber den AUFGELOESTEN Pfad; ein lexikalisches
    Path.parent landete bei /sys/class und faende nie ein subsystem
    (dieselbe Falle wie in fan_gpu_manual.py:101-127).
    """
    hwmon_name = hwmon_link.name
    hwmon_dir = Path(os.path.realpath(hwmon_link))
    prefix = _read_name(hwmon_dir)
    if prefix is None:
        return _unstable(hwmon_name, None, "hwmon/name fehlt oder ist unlesbar")

    device_link = hwmon_dir / "device"
    if not device_link.exists():
        return _unstable(hwmon_name, prefix, "kein device-Symlink (virtueller Chip)")

    current = Path(os.path.realpath(device_link))
    for _ in range(_MAX_CLIMB):
        subsystem = _subsystem_of(current)
        if subsystem in _SUPPORTED_BUSES:
            bus = _SUPPORTED_BUSES[subsystem]
            addr = (encode_pci_address(current.name) if subsystem == "pci"
                    else encode_platform_address(current.name))
            if addr is None:
                # Kein extrahierbarer Suffix: Geraetename ist innerhalb
                # seines Busses eindeutig und damit selbst ein tauglicher Anker.
                key = f"{prefix}@{current.name}"
            else:
                key = format_chip_name(prefix, bus, addr)
            return ChipIdentity(key=key, prefix=prefix, stable=True,
                                hwmon_name=hwmon_name, reason=None)
        if subsystem in _FALLBACK_BUSES:
            return _unstable(hwmon_name, prefix, f"Bustyp {subsystem} nicht unterstuetzt")
        parent = current.parent
        if parent == current or current.name == "devices":
            break
        current = parent

    return _unstable(hwmon_name, prefix, "kein pci/platform-Elter gefunden")


def derive_all(hwmon_base: Path) -> Dict[str, ChipIdentity]:
    """Kennungen aller hwmon-Knoten, mit Duplikaterkennung."""
    identities: Dict[str, ChipIdentity] = {}
    try:
        entries = sorted(hwmon_base.iterdir())
    except OSError:
        return identities

    for entry in entries:
        if not entry.name.startswith("hwmon"):
            continue
        identities[entry.name] = derive_chip_identity(entry)

    by_key: Dict[str, list] = {}
    for name, identity in identities.items():
        if identity.stable:
            by_key.setdefault(identity.key, []).append(name)
    for key, names in by_key.items():
        if len(names) > 1:
            for name in names:
                identities[name] = _unstable(
                    name, identities[name].prefix,
                    f"Kennung {key} nicht eindeutig ({len(names)} hwmon-Knoten)",
                )
    return identities


def build_fan_id(identity: ChipIdentity, pwm_num: int) -> str:
    if identity.stable:
        return f"{identity.key}:pwm{pwm_num}"
    return f"{identity.hwmon_name}_pwm{pwm_num}"


def build_sensor_id(identity: ChipIdentity, temp_num: int) -> str:
    if identity.stable:
        return f"{identity.key}:temp{temp_num}"
    return f"{identity.hwmon_name}_temp{temp_num}"
