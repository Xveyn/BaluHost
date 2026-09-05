# Stabile Lüfter- und Sensor-Identität — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lüfter- und Sensor-IDs vom hwmon-Index lösen, damit eine eingestellte Lüfterkurve ein Renumbering überlebt.

**Architecture:** Eine neue, reine Modul-Einheit `fan_identity.py` leitet aus dem sysfs-Baum die libsensors-Kennung `<prefix>-<bus>-<adresse>` ab. Das Linux-Backend bildet daraus `fan_id`/`temp_sensor_id` und führt eine Rückabbildung Kennung → hwmon-Pfad mit. Ein zweites Modul `fan_reconcile.py` überführt bestehende Datenbankzeilen anhand des Chip-Namens in `fan_configs.name`; es läuft beim Dienststart vor der Anlage-Schleife, im Primary-Worker, in einer Transaktion.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, pytest. Keine neuen Abhängigkeiten.

**Spec:** `docs/superpowers/specs/2026-09-05-stable-fan-identity-design.md`

## Global Constraints

- **Normative libsensors-Version: 3.6.2** (`1:3.6.2-2` auf BaluNode). Regeln aus `master` gelten hier nicht.
- **Keine neuen Abhängigkeiten.**
- **Nichts wird gelöscht.** Verwaiste Zeilen werden ausschließlich auf `is_active=False` gesetzt.
- **Abwesenheit darf niemals schreiben.** Eine Zeile, deren Chip beim Scan nicht auftaucht, bleibt unangetastet und aktiv.
- **`dev_*`-Zeilen bleiben unberührt.** Nur `^hwmon\d+_pwm\d+$` wird angefasst.
- Kommentare und Log-Meldungen auf Deutsch, wie im umgebenden Fan-Code (`fan_backend_linux.py` verwendet Umlaut-freie deutsche Kommentare — dieser Konvention folgen).
- Die volle Backend-Suite läuft in der CI, nicht lokal (hängt auf Windows). Lokal gilt `python -m pytest -k "fan or power"`.
- Alembic-Elternrevision ist `c4b18e9a2f37` (verifizierter einziger Head).

---

### Task 1: `fan_identity.py` — Adressbildung und Namensformat

Reine Funktionen ohne Dateisystemzugriff. Sie sind der Kern, an dem die selbstgebaute Kodierung hängt, und deshalb zuerst und isoliert.

**Files:**
- Create: `backend/app/services/power/fan_identity.py`
- Test: `backend/tests/test_fan_identity_encoding.py`

**Interfaces:**
- Produces: `encode_pci_address(dev_name: str) -> Optional[int]`, `encode_platform_address(dev_name: str) -> Optional[int]`, `format_chip_name(prefix: str, bus: str, addr: int) -> str`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_identity_encoding.py`:

```python
"""Adressbildung der stabilen Chip-Kennung (#532).

Sollwerte sind die Chip-Ueberschriften, die `sensors` auf BaluNode ausgibt --
also eine unabhaengige Implementierung derselben Regeln auf derselben Hardware.
"""
import pytest

from app.services.power.fan_identity import (
    encode_pci_address,
    encode_platform_address,
    format_chip_name,
)


@pytest.mark.parametrize("dev_name,expected", [
    ("0000:03:00.0", 0x0300),   # amdgpu
    ("0000:00:18.3", 0x00c3),   # k10temp: (0x18 << 3) | 3
    ("0000:0d:00.0", 0x0d00),   # nvme
    ("0000:0a:00.0", 0x0a00),   # nvme
    ("0001:0d:00.0", 0x10d00),  # Domain != 0 geht mit <<16 ein
])
def test_pci_address(dev_name, expected):
    assert encode_pci_address(dev_name) == expected


def test_pci_address_rejects_non_bdf():
    assert encode_pci_address("nct6775.656") is None


def test_platform_address_reads_suffix_as_decimal():
    # 656 dezimal == 0x290 -- der Wert, den `sensors` als nct6798-isa-0290 zeigt
    assert encode_platform_address("nct6775.656") == 656


def test_platform_address_accepts_colon_separator():
    assert encode_platform_address("foo:42") == 42


def test_platform_address_reads_device_tree_prefix_as_hex():
    assert encode_platform_address("f0000000.hwmon") == 0xf0000000


def test_platform_address_without_suffix_is_none():
    # Bewusste Abweichung von libsensors 3.6.2: dessen "%x.%*s" liefert hier
    # 0x0a bzw. 0xeee, weil sscanf schon zaehlt, bevor der Punkt scheitert.
    assert encode_platform_address("asus-nb-wmi") is None
    assert encode_platform_address("eeepc-wmi") is None


@pytest.mark.parametrize("prefix,bus,addr,expected", [
    ("nct6798", "isa", 656, "nct6798-isa-0290"),
    ("amdgpu", "pci", 0x0300, "amdgpu-pci-0300"),
    ("k10temp", "pci", 0x00c3, "k10temp-pci-00c3"),
    ("nvme", "pci", 0x0d00, "nvme-pci-0d00"),
    ("nvme", "pci", 0x10d00, "nvme-pci-10d00"),  # %04x ist Mindestbreite
])
def test_format_chip_name(prefix, bus, addr, expected):
    assert format_chip_name(prefix, bus, addr) == expected
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_identity_encoding.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.power.fan_identity'`

- [ ] **Step 3: Modul anlegen**

`backend/app/services/power/fan_identity.py`:

```python
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
_PLATFORM_DECIMAL = re.compile(r"^[A-Za-z0-9_-]+[.:](\d+)$")
# "f0000000.hwmon" -- Device-Tree-Adresse, hexadezimal
_PLATFORM_HEX = re.compile(r"^([0-9a-f]+)\.")


def encode_pci_address(dev_name: str) -> Optional[int]:
    """PCI-Adresse nach lib/sysfs.c: (domain<<16)+(bus<<8)+(slot<<3)+fn."""
    match = _PCI_BDF.match(dev_name)
    if not match:
        return None
    domain, bus, slot, fn = (int(group, 16) for group in match.groups())
    return (domain << 16) + (bus << 8) + (slot << 3) + fn


def encode_platform_address(dev_name: str) -> Optional[int]:
    """Platform-Adresse: dezimaler Suffix, sonst Device-Tree-Hex, sonst None.

    libsensors' zweiter sscanf ("%x.%*s") liefert bereits 1, wenn %x etwas
    konsumiert hat -- auch wenn der Punkt danach nie matcht. Daraus werden
    asus-nb-wmi -> 0x0a und eeepc-wmi -> 0xeee: stabil, aber bedeutungslos.
    _PLATFORM_HEX verlangt den Punkt tatsaechlich und bildet damit den
    gemeinten Device-Tree-Fall ab statt des Parser-Unfalls. Betroffen sind nur
    Chips, die `sensors` ohnehin nicht listet.
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
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_identity_encoding.py -v`
Expected: PASS (alle 14 Fälle)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_identity.py backend/tests/test_fan_identity_encoding.py
git commit -m "feat(fans): Adressbildung der stabilen Chip-Kennung (#532)"
```

---

### Task 2: `fan_identity.py` — Auflösung aus dem sysfs-Baum

**Files:**
- Modify: `backend/app/services/power/fan_identity.py`
- Test: `backend/tests/test_fan_identity_resolve.py`

**Interfaces:**
- Consumes: `encode_pci_address`, `encode_platform_address`, `format_chip_name` aus Task 1
- Produces: `ChipIdentity` (Felder `key: str`, `prefix: str`, `stable: bool`, `hwmon_name: str`, `reason: Optional[str]`), `derive_chip_identity(hwmon_dir: Path) -> ChipIdentity`, `derive_all(hwmon_base: Path) -> Dict[str, ChipIdentity]` (Schlüssel: `hwmon_dir.name`), `build_fan_id(identity, pwm_num: int) -> str`, `build_sensor_id(identity, temp_num: int) -> str`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_identity_resolve.py`:

```python
"""Aufloesung der Chip-Kennung aus dem sysfs-Baum (#532).

Die Baeume bilden die auf BaluNode gemessenen Pfade nach, inklusive echter
device- und subsystem-Symlinks -- ohne die laeuft die Ableitung in den
Fallback und der Test prueft das Falsche.
"""
import os
from pathlib import Path

import pytest

from app.services.power.fan_identity import (
    ChipIdentity,
    build_fan_id,
    build_sensor_id,
    derive_all,
    derive_chip_identity,
)


def _tree(tmp_path: Path, hwmon_name: str, device_rel: str, chip: str,
          subsystem: str = "pci") -> Path:
    """Legt /sys/devices/<device_rel> an und haengt <hwmon_name> daran.

    device_rel ist relativ zu sys/devices, z. B. "platform/nct6775.656".
    subsystem wird an das TIEFSTE Verzeichnis von device_rel gehaengt.
    """
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / device_rel
    hwmon = device / "hwmon" / hwmon_name
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text(chip + "\n")

    bus_dir = sysfs / "bus" / subsystem
    bus_dir.mkdir(parents=True, exist_ok=True)
    os.symlink(bus_dir, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)

    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    link = klass / hwmon_name
    os.symlink(hwmon, link, target_is_directory=True)
    return link


def test_platform_chip_uses_decimal_suffix(tmp_path):
    link = _tree(tmp_path, "hwmon3", "platform/nct6775.656", "nct6798",
                 subsystem="platform")
    identity = derive_chip_identity(link)
    assert identity.stable is True
    assert identity.key == "nct6798-isa-0290"


def test_pci_chip(tmp_path):
    link = _tree(tmp_path, "hwmon2", "pci0000:00/0000:03:00.0", "amdgpu")
    assert derive_chip_identity(link).key == "amdgpu-pci-0300"


def test_climbs_past_intermediate_class_to_pci_parent(tmp_path):
    # NVMe: der device-Link zeigt auf nvme1, dessen subsystem die Klasse
    # "nvme" ist -- weder pci noch platform, also weiterklettern.
    sysfs = tmp_path / "sys"
    pci = sysfs / "devices" / "pci0000:00" / "0000:0d:00.0"
    nvme = pci / "nvme" / "nvme1"
    hwmon = nvme / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nvme\n")
    for bus, target in (("pci", pci), ("nvme", nvme)):
        bus_dir = sysfs / "bus" / bus
        bus_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(bus_dir, target / "subsystem", target_is_directory=True)
    os.symlink(nvme, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True)
    link = klass / "hwmon0"
    os.symlink(hwmon, link, target_is_directory=True)

    identity = derive_chip_identity(link)
    assert identity.stable is True
    assert identity.key == "nvme-pci-0d00"   # ohne den instabilen nvme1


def test_platform_without_numeric_suffix_uses_device_name(tmp_path):
    link = _tree(tmp_path, "hwmon5", "platform/asus-nb-wmi", "asus",
                 subsystem="platform")
    identity = derive_chip_identity(link)
    assert identity.stable is True
    assert identity.key == "asus@asus-nb-wmi"


def test_unsupported_bus_falls_back(tmp_path):
    # drivetemp haengt am scsi-Bus. Weiterklettern landete auf dem
    # AHCI-Controller und gaebe allen Platten dieselbe Kennung.
    link = _tree(tmp_path, "hwmon7", "pci0000:00/0000:00:17.0/ata1/host0",
                 "drivetemp", subsystem="scsi")
    identity = derive_chip_identity(link)
    assert identity.stable is False
    assert "scsi" in (identity.reason or "")


def test_missing_device_link_falls_back(tmp_path):
    sysfs = tmp_path / "sys"
    hwmon = sysfs / "devices" / "virtual" / "hwmon" / "hwmon9"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("acpitz\n")
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True)
    link = klass / "hwmon9"
    os.symlink(hwmon, link, target_is_directory=True)

    assert derive_chip_identity(link).stable is False


def test_missing_name_falls_back(tmp_path):
    link = _tree(tmp_path, "hwmon4", "pci0000:00/0000:00:18.3", "k10temp")
    (link.resolve() / "name").unlink()
    assert derive_chip_identity(link).stable is False


def test_duplicate_keys_both_fall_back(tmp_path):
    # Zwei hwmon-Knoten am selben Geraet erzeugen dieselbe Kennung. Ohne
    # Erkennung ueberschriebe der zweite den ersten still im Scan-Cache.
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "twin.1"
    bus_dir = sysfs / "bus" / "platform"
    bus_dir.mkdir(parents=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True)
    device.mkdir(parents=True)
    os.symlink(bus_dir, device / "subsystem", target_is_directory=True)
    for name in ("hwmon0", "hwmon1"):
        hwmon = device / "hwmon" / name
        hwmon.mkdir(parents=True)
        (hwmon / "name").write_text("twin\n")
        os.symlink(device, hwmon / "device", target_is_directory=True)
        os.symlink(hwmon, klass / name, target_is_directory=True)

    identities = derive_all(klass)
    assert identities["hwmon0"].stable is False
    assert identities["hwmon1"].stable is False


def test_id_builders_use_legacy_form_when_unstable():
    stable = ChipIdentity(key="nct6798-isa-0290", prefix="nct6798",
                          stable=True, hwmon_name="hwmon3", reason=None)
    unstable = ChipIdentity(key="hwmon3", prefix="Unknown",
                            stable=False, hwmon_name="hwmon3", reason="x")
    assert build_fan_id(stable, 1) == "nct6798-isa-0290:pwm1"
    assert build_sensor_id(stable, 6) == "nct6798-isa-0290:temp6"
    # Fallback behaelt exakt die Altform -- sonst waere die Zeile bei jedem
    # Start erneut ein Migrationskandidat.
    assert build_fan_id(unstable, 1) == "hwmon3_pwm1"
    assert build_sensor_id(unstable, 6) == "hwmon3_temp6"
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_identity_resolve.py -v`
Expected: FAIL mit `ImportError: cannot import name 'ChipIdentity'`

- [ ] **Step 3: Auflösung implementieren**

An `backend/app/services/power/fan_identity.py` anhängen (Importblock oben um `os`, `logging`, `dataclass`, `Path`, `Dict` ergänzen):

```python
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
    logger.warning("hwmon %s: keine stabile Kennung (%s)", hwmon_name, reason)
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
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_identity_resolve.py -v`
Expected: PASS (9 Tests)

Hinweis: `os.symlink` auf Verzeichnisse braucht unter Windows entweder Entwicklermodus oder Adminrechte. Schlägt der Test lokal mit `OSError: symbolic link privilege not held` fehl, ist das eine Umgebungs-, keine Codefrage — die CI läuft unter Linux. In dem Fall Task 3 fortsetzen und diesen Test der CI überlassen.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_identity.py backend/tests/test_fan_identity_resolve.py
git commit -m "feat(fans): Chip-Kennung aus dem sysfs-Baum ableiten (#532)"
```

---

### Task 3: Scan auf stabile IDs umstellen, Rückabbildung mitführen

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py:361-466` (`_scan_pwm_fans`), `:48` (Konstruktor)
- Test: `backend/tests/test_fan_scan_stable_ids.py`

**Interfaces:**
- Consumes: `derive_all`, `build_fan_id`, `build_sensor_id`, `ChipIdentity` aus Task 2
- Produces: `LinuxFanControlBackend._temp_paths: Dict[str, Path]` (Sensor-ID → `tempN_input`-Pfad), `_fan_cache[fan_id]["identity_stable"]: bool`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_scan_stable_ids.py`:

```python
"""Der Scan bildet stabile IDs und ueberlebt ein Renumbering (#532)."""
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _nct_tree(tmp_path: Path, hwmon_name: str) -> Path:
    """nct6798 an platform/nct6775.656, mit pwm1 + fan1_input + temp1_input."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / hwmon_name
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text("1\n")
    (hwmon / "fan1_input").write_text("900\n")
    (hwmon / "temp1_input").write_text("42000\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    if not (device / "subsystem").exists():
        os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / hwmon_name, target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_scan_builds_stable_fan_id(tmp_path, monkeypatch):
    klass = _nct_tree(tmp_path, "hwmon3")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    assert "nct6798-isa-0290:pwm1" in cache
    assert cache["nct6798-isa-0290:pwm1"]["identity_stable"] is True


@pytest.mark.asyncio
async def test_same_device_under_other_hwmon_index_keeps_id(tmp_path, monkeypatch):
    """Das Akzeptanzkriterium des Issues: Renumbering aendert die ID nicht."""
    first = _nct_tree(tmp_path / "boot_a", "hwmon3")
    second = _nct_tree(tmp_path / "boot_b", "hwmon5")

    backend_a = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend_a, "_hwmon_base", first)
    cache_a = await backend_a._scan_pwm_fans()

    backend_b = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend_b, "_hwmon_base", second)
    cache_b = await backend_b._scan_pwm_fans()

    assert set(cache_a) == set(cache_b) == {"nct6798-isa-0290:pwm1"}


@pytest.mark.asyncio
async def test_scan_registers_reverse_path_for_sensor(tmp_path, monkeypatch):
    klass = _nct_tree(tmp_path, "hwmon3")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()

    sensor_id = "nct6798-isa-0290:temp1"
    assert sensor_id in backend._temp_paths
    assert backend._temp_paths[sensor_id].name == "temp1_input"
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_scan_stable_ids.py -v`
Expected: FAIL — der Cache enthält `hwmon3_pwm1`, `_temp_paths` existiert nicht.

- [ ] **Step 3: Konstruktor und Scan umbauen**

In `fan_backend_linux.py` den Importblock ergänzen:

```python
from app.services.power.fan_identity import (
    build_fan_id,
    build_sensor_id,
    derive_all,
)
```

Im Konstruktor nach `self._write_backoff: Dict[str, Tuple[int, float]] = {}`:

```python
        # Rueckabbildung stabile Sensor-Kennung -> tempN_input-Pfad. Ohne sie
        # kann get_temperature() die ID nicht mehr aufloesen, weil sie nicht
        # mehr aus dem hwmon-Verzeichnisnamen besteht (#532).
        self._temp_paths: Dict[str, Path] = {}
```

In `_scan_pwm_fans` direkt nach `new_cache: Dict[str, Dict] = {}`:

```python
        new_temp_paths: Dict[str, Path] = {}
        identities = derive_all(self._hwmon_base)
```

Die Zeile `fan_id = f"{hwmon_dir.name}_pwm{pwm_num}"` ersetzen durch:

```python
                identity = identities.get(hwmon_dir.name)
                if identity is None:
                    continue
                fan_id = build_fan_id(identity, int(pwm_num))
```

Den Fallback-Zweig für den lokalen Temperatursensor (`temp_sensor_id = f"{hwmon_dir.name}_temp{temp_num}"`) ersetzen durch:

```python
                        temp_sensor_id = build_sensor_id(identity, int(temp_num))
```

Im Dict-Literal `new_cache[fan_id] = {...}` nach `"pwm_control": pwm_control,` ergänzen:

```python
                    "identity_stable": identity.stable,
```

Und direkt vor `new_cache[fan_id] = {...}` alle Temperaturkanäle des Chips in die Rückabbildung eintragen:

```python
                for temp_file in hwmon_dir.glob("temp[0-9]*_input"):
                    num = temp_file.name[len("temp"):-len("_input")]
                    new_temp_paths[build_sensor_id(identity, int(num))] = temp_file
```

Im Block, der den Cache ersetzt (`if new_cache or not self._fan_cache:`), nach der Zuweisung `self._fan_cache = new_cache`:

```python
            self._temp_paths = new_temp_paths
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_scan_stable_ids.py -v`
Expected: PASS (3 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/tests/test_fan_scan_stable_ids.py
git commit -m "feat(fans): Scan bildet stabile IDs und fuehrt die Rueckabbildung mit (#532)"
```

---

### Task 4: `get_temperature()` und `_find_cpu_temp_sensor()` über die Rückabbildung

Ohne diesen Schritt liefert nach Task 3 **jeder** hwmon-Sensor `None`, weil `get_temperature` die ID mit `split("_")` zerlegt.

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py:253-309`
- Test: `backend/tests/test_fan_temp_resolution.py`

**Interfaces:**
- Consumes: `_temp_paths` aus Task 3
- Produces: `get_temperature(sensor_id)` akzeptiert stabile IDs, `hwmon:`-präfixierte IDs und Alt-IDs

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_temp_resolution.py`:

```python
"""get_temperature loest stabile, praefixierte und Alt-IDs auf (#532)."""
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.fixture
def backend(tmp_path):
    hwmon = tmp_path / "hwmon3"
    hwmon.mkdir()
    (hwmon / "temp1_input").write_text("42000\n")
    be = LinuxFanControlBackend(get_settings())
    be._hwmon_base = tmp_path
    be._temp_paths = {"nct6798-isa-0290:temp1": hwmon / "temp1_input"}
    return be


@pytest.mark.asyncio
async def test_resolves_stable_id(backend):
    assert await backend.get_temperature("nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_strips_hwmon_namespace_prefix(backend):
    assert await backend.get_temperature("hwmon:nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_still_resolves_legacy_id(backend):
    # Waehrend der Umstellung stehen Alt-IDs noch in der Datenbank.
    assert await backend.get_temperature("hwmon3_temp1") == 42.0


@pytest.mark.asyncio
async def test_unknown_id_is_none(backend):
    assert await backend.get_temperature("nope-isa-0000:temp9") is None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_temp_resolution.py -v`
Expected: FAIL — die ersten beiden geben `None` zurück.

- [ ] **Step 3: `get_temperature` umbauen**

`fan_backend_linux.py`, die Methode ab Zeile 253 ersetzen:

```python
    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get temperature from hwmon sensor.

        Loest zuerst ueber die Rueckabbildung aus dem Scan auf (stabile
        Kennungen, #532) und faellt danach auf die Altform hwmon<N>_temp<M>
        zurueck, die waehrend der Umstellung noch in der Datenbank steht.
        """
        if not sensor_id:
            return None

        if sensor_id.startswith("hwmon:"):
            sensor_id = sensor_id[len("hwmon:"):]

        temp_path = self._temp_paths.get(sensor_id)
        if temp_path is None:
            temp_path = self._legacy_temp_path(sensor_id)
        if temp_path is None:
            return None

        temp_value = await self._read_hwmon_file(temp_path)
        if temp_value is not None:
            return float(temp_value) / 1000.0
        return None

    def _legacy_temp_path(self, sensor_id: str) -> Optional[Path]:
        """Altform "hwmon0_temp1" -> Pfad. Nur fuer noch nicht migrierte IDs."""
        parts = sensor_id.split("_")
        if len(parts) != 2:
            return None
        hwmon_name, temp_name = parts
        return self._hwmon_base / hwmon_name / f"{temp_name}_input"
```

- [ ] **Step 4: `_find_cpu_temp_sensor` und `get_available_temp_sensors` auf die Kennung umstellen**

Beide bilden Sensor-IDs heute aus dem hwmon-Verzeichnisnamen. Sie müssen dieselbe Ableitung benutzen wie der Scan, sonst weichen die IDs voneinander ab. Dafür in beiden Methoden einmal `identities = derive_all(self._hwmon_base)` holen und pro Temperaturkanal so bilden:

```python
                identity = identities.get(hwmon_dir.name)
                if identity is None:
                    continue
                sensor_id = build_sensor_id(identity, int(temp_num))
                # Auch Sensoren ohne zugehoerigen PWM-Kanal muessen aufloesbar
                # sein -- der Scan traegt nur Chips mit Luefter ein.
                self._temp_paths[sensor_id] = temp_file
```

Die bisherige Bildung `f"{hwmon_dir.name}_temp{temp_num}"` entfällt an beiden Stellen. `_find_cpu_temp_sensor` gibt weiterhin `(sensor_id, path)` zurück, nur mit der neuen ID-Form.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_temp_resolution.py tests/test_fan_scan_stable_ids.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/tests/test_fan_temp_resolution.py
git commit -m "fix(fans): Temperaturaufloesung ueber die Rueckabbildung statt String-Zerlegung (#532)"
```

---

### Task 5: `_normalize_id` auf eine Namespace-Whitelist, `get_status` über die Registry

**Files:**
- Modify: `backend/app/services/power/fan_sources.py:101-106`
- Modify: `backend/app/services/power/fan_control.py:670-680` (`get_status`)
- Test: `backend/tests/test_fan_sources_normalize.py`

**Interfaces:**
- Produces: `TempSourceRegistry._normalize_id` erkennt Namespaces am Präfix statt am Doppelpunkt

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_sources_normalize.py`:

```python
"""Namespace-Erkennung darf nicht am blossen Doppelpunkt haengen (#532)."""
from app.services.power.fan_sources import TempSourceRegistry


def test_legacy_bare_id_gets_hwmon_namespace():
    assert TempSourceRegistry._normalize_id("hwmon3_temp1") == "hwmon:hwmon3_temp1"


def test_stable_bare_id_gets_hwmon_namespace():
    # Enthaelt selbst einen Doppelpunkt -- die alte Heuristik "":" in id"
    # haette die ID unveraendert durchgereicht und die Quelle nicht gefunden.
    assert (TempSourceRegistry._normalize_id("k10temp-pci-00c3:temp1")
            == "hwmon:k10temp-pci-00c3:temp1")


def test_already_namespaced_ids_pass_through():
    for sid in ("hwmon:k10temp-pci-00c3:temp1", "gpu:edge",
                "disk:sda", "mix:abc123"):
        assert TempSourceRegistry._normalize_id(sid) == sid
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_sources_normalize.py -v`
Expected: FAIL bei `test_stable_bare_id_gets_hwmon_namespace`

- [ ] **Step 3: `_normalize_id` ersetzen**

`fan_sources.py`, oberhalb der Klasse:

```python
_NAMESPACES = ("hwmon:", "gpu:", "disk:", "mix:")
```

Die Methode ersetzen:

```python
    @staticmethod
    def _normalize_id(sensor_id: str) -> str:
        """Accept both namespaced (hwmon:foo) and legacy (foo) IDs.

        Geprueft wird der Namespace-Praefix, nicht das blosse Vorkommen eines
        Doppelpunkts: stabile Kennungen (#532) tragen selbst einen.
        """
        if sensor_id.startswith(_NAMESPACES):
            return sensor_id
        return f"hwmon:{sensor_id}"
```

- [ ] **Step 4: `get_status` auf die Registry umstellen**

`fan_control.py:676` liest die Anzeigetemperatur am Registry vorbei über `self._backend.get_temperature(...)` und verschluckt jeden Fehler. Die Zeile ersetzen:

```python
                            sensor_temp = await self._registry.get_temp(config.temp_sensor_id)
```

Damit gilt für die Anzeige dieselbe Auflösung wie für die Regelung (`fan_control.py:482`); sonst zeigt die UI für jeden Lüfter mit abweichend gewähltem Sensor eine andere Temperatur als die, nach der geregelt wird.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_sources_normalize.py tests/test_fan_sources.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_sources.py backend/app/services/power/fan_control.py backend/tests/test_fan_sources_normalize.py
git commit -m "fix(fans): Namespace-Erkennung am Praefix, Anzeigetemperatur ueber die Registry (#532)"
```

---

### Task 6: Alembic-Migration für die Herkunftsspalten

**Files:**
- Create: `backend/alembic/versions/<rev>_fan_identity_legacy_columns.py`
- Modify: `backend/app/models/fans.py` (`FanConfig`, `TempSensorLabel`)

**Interfaces:**
- Produces: `FanConfig.legacy_fan_id: Optional[str]`, `TempSensorLabel.legacy_sensor_id: Optional[str]`

- [ ] **Step 1: Aktuellen Head bestätigen**

Run: `cd backend ; python -m alembic heads`
Expected: genau eine Zeile, `c4b18e9a2f37 (head)`. Weicht das ab, **hier stoppen** und melden — das Projekt hatte bereits einen Multi-Head-Deployfehler.

- [ ] **Step 2: Modelle erweitern**

`backend/app/models/fans.py`, in `FanConfig` nach `is_active`:

```python
    # Herkunft der Zeile vor der Umstellung auf stabile Kennungen (#532).
    # Reiner Nachweis: erlaubt, eine Fehlzuordnung nachtraeglich zu erkennen.
    legacy_fan_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
```

In `TempSensorLabel` nach `custom_label`:

```python
    legacy_sensor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
```

- [ ] **Step 3: Migration erzeugen**

Run: `cd backend ; python -m alembic revision --autogenerate -m "fan identity legacy columns"`

In der erzeugten Datei prüfen, dass `down_revision = "c4b18e9a2f37"` steht und **nur** die beiden `add_column`-Aufrufe enthalten sind. Autogenerate nimmt gern Unbeteiligtes mit — alles andere entfernen.

- [ ] **Step 4: Migration anwenden und zurückrollen**

```bash
cd backend
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```
Expected: alle drei Läufe ohne Fehler; `python -m alembic heads` zeigt wieder genau einen Head.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/fans.py backend/alembic/versions/
git commit -m "feat(fans): Herkunftsspalten fuer die Identitaets-Umstellung (#532)"
```

---

### Task 7: `fan_reconcile.py` — die Zuordnungsregeln

Reines Modul ohne sysfs-Zugriff: es bekommt die Scan-Fakten als Datenstruktur. Dadurch ist die gesamte Regelmenge gegen die echte Datenlage testbar.

**Files:**
- Create: `backend/app/services/power/fan_reconcile.py`
- Test: `backend/tests/test_fan_reconcile.py`

**Interfaces:**
- Produces: `ChipFacts(key: str, pwm_channels: frozenset[int], ambiguous: bool)`, `ReconcileReport(renamed: list[tuple[str, str]], deactivated: list[str], skipped_absent: list[str], unresolved_sensors: list[str])`, `reconcile_fan_identities(db, chips: Dict[str, ChipFacts], sensor_map: Dict[str, str], cpu_sensor_id: Optional[str]) -> ReconcileReport`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_reconcile.py`:

```python
"""Zuordnung der Altzeilen auf stabile Kennungen (#532).

Das Fixture ist die auf BaluNode gemessene Datenlage: 16 Zeilen, davon 13
hwmon-indiziert in vier Generationen fuer 5 physische Luefter, plus 3 dev_*.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power.fan_reconcile import (
    ChipFacts,
    reconcile_fan_identities,
)

NCT = ChipFacts(key="nct6798-isa-0290",
                pwm_channels=frozenset({1, 2, 3, 7}), ambiguous=False)
AMD = ChipFacts(key="amdgpu-pci-0300",
                pwm_channels=frozenset({1}), ambiguous=False)
CHIPS = {"nct6798": NCT, "amdgpu": AMD}

SENSOR_MAP = {
    "hwmon4_temp1": "hwmon:k10temp-pci-00c3:temp1",
    "hwmon3_temp1": "hwmon:nct6798-isa-0290:temp1",
}
CPU_DEFAULT = "hwmon:k10temp-pci-00c3:temp1"


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


ROWS = [
    # (fan_id, name, temp_sensor_id, updated_at)
    ("hwmon5_pwm1", "nct6798 PWM1", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm2", "nct6798 PWM2", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm3", "nct6798 PWM3", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm7", "nct6798 PWM7", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("dev_case_fan_1", "Case Fan 1 (Simulated)", "dev_package_temp", "2026-01-27T22:48:27"),
    ("dev_cpu_fan", "CPU Fan (Simulated)", "dev_cpu_temp", "2026-02-17T21:48:42"),
    ("dev_case_fan_2", "Case Fan 2 (Simulated)", "dev_cpu_temp", "2026-02-25T19:57:42"),
    ("hwmon1_pwm1", "amdgpu PWM1", "hwmon3_temp1", "2026-07-06T23:38:15"),
    ("hwmon2_pwm1", "nct6798 PWM1", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm2", "nct6798 PWM2", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm3", "nct6798 PWM3", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm7", "nct6798 PWM7", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon3_pwm1", "nct6798 PWM1", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm2", "nct6798 PWM2", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm3", "nct6798 PWM3", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm7", "nct6798 PWM7", "hwmon4_temp1", "2026-08-07T00:32:04"),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for fan_id, name, sensor, updated in ROWS:
        session.add(FanConfig(fan_id=fan_id, name=name, mode="auto",
                              temp_sensor_id=sensor, is_active=True,
                              updated_at=_dt(updated)))
    session.commit()
    yield session
    session.close()


def _active(db):
    return {r.fan_id for r in db.execute(
        select(FanConfig).where(FanConfig.is_active.is_(True))).scalars()}


def test_newest_generation_wins_and_nothing_is_deleted(db):
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert _active(db) == {
        "nct6798-isa-0290:pwm1", "nct6798-isa-0290:pwm2",
        "nct6798-isa-0290:pwm3", "nct6798-isa-0290:pwm7",
        "amdgpu-pci-0300:pwm1",
        "dev_case_fan_1", "dev_cpu_fan", "dev_case_fan_2",
    }
    assert db.query(FanConfig).count() == 16   # nichts geloescht


def test_july_row_named_nct6798_does_not_become_the_gpu(db):
    """Die Falle: hwmon2 ist heute die GPU, war im Juli aber der nct6798."""
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    gpu = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "amdgpu-pci-0300:pwm1")).scalar_one()
    assert gpu.legacy_fan_id == "hwmon1_pwm1"
    assert gpu.name == "amdgpu PWM1"


def test_absent_chip_is_never_deactivated(db):
    """Treiber beim Start noch nicht geladen -- Kurven muessen bleiben."""
    reconcile_fan_identities(db, chips={"amdgpu": AMD}, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    for fan_id in ("hwmon3_pwm1", "hwmon2_pwm1", "hwmon5_pwm1"):
        row = db.execute(select(FanConfig).where(
            FanConfig.fan_id == fan_id)).scalar_one()
        assert row.is_active is True


def test_second_run_is_a_noop(db):
    first = reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                                     cpu_sensor_id=CPU_DEFAULT)
    db.commit()
    second = reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                                      cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert len(first.renamed) == 5
    assert second.renamed == []
    assert second.deactivated == []


def test_resumes_after_abort_between_rename_and_deactivate(db):
    """Gewinner schon umbenannt, Verlierer noch aktiv -- kein Unique-Fehler."""
    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon3_pwm1")).scalar_one()
    row.fan_id = "nct6798-isa-0290:pwm1"
    row.legacy_fan_id = "hwmon3_pwm1"
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert "hwmon2_pwm1" not in _active(db)
    assert "nct6798-isa-0290:pwm1" in _active(db)


def test_unknown_name_is_neither_candidate_nor_deactivated(db):
    db.add(FanConfig(fan_id="hwmon9_pwm1", name="Unknown PWM1", mode="auto",
                     temp_sensor_id=None, is_active=True,
                     updated_at=_dt("2026-08-08T00:00:00")))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon9_pwm1")).scalar_one()
    assert row.is_active is True


def test_ambiguous_chip_name_is_no_candidate(db):
    chips = {"nct6798": ChipFacts(key="nct6798-isa-0290",
                                  pwm_channels=frozenset({1, 2, 3, 7}),
                                  ambiguous=True),
             "amdgpu": AMD}
    reconcile_fan_identities(db, chips=chips, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert "hwmon3_pwm1" in _active(db)


def test_winner_sensor_is_rewritten_prefixed(db):
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert row.temp_sensor_id == "hwmon:k10temp-pci-00c3:temp1"


def test_unresolvable_sensor_falls_back_to_cpu_default(db):
    report = reconcile_fan_identities(db, chips=CHIPS, sensor_map={},
                                      cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert row.temp_sensor_id == CPU_DEFAULT
    assert "hwmon4_temp1" in report.unresolved_sensors
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_reconcile.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.power.fan_reconcile'`

- [ ] **Step 3: Modul implementieren**

`backend/app/services/power/fan_reconcile.py`:

```python
"""Ueberfuehrt hwmon-indizierte fan_configs auf stabile Kennungen (#532).

Reines Modul: es bekommt die Scan-Fakten uebergeben und fasst kein sysfs an.
Der Aufrufer haelt die Transaktion.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fans import (
    CompositeTempSensor,
    FanConfig,
    FanScheduleEntry,
    TempSensorLabel,
)

logger = logging.getLogger(__name__)

_LEGACY_FAN_ID = re.compile(r"^hwmon(\d+)_pwm(\d+)$")
_LEGACY_SENSOR_ID = re.compile(r"^hwmon(\d+)_temp(\d+)$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ChipFacts:
    """Was der Scan ueber einen heute vorhandenen Chip weiss."""
    key: str
    pwm_channels: frozenset
    ambiguous: bool


@dataclass
class ReconcileReport:
    renamed: List[Tuple[str, str]] = field(default_factory=list)
    deactivated: List[str] = field(default_factory=list)
    skipped_absent: List[str] = field(default_factory=list)
    unresolved_sensors: List[str] = field(default_factory=list)


def _chip_from_name(name: Optional[str]) -> Optional[str]:
    """"nct6798 PWM1" -> "nct6798". Ohne " PWM" kein Kandidat.

    Der Dev-Backend erzeugt Namen wie "CPU Fan (Simulated)"; ein naives
    rsplit gaebe dort den ganzen Namen als Chip-Namen zurueck.
    """
    if not name:
        return None
    index = name.rfind(" PWM")
    if index <= 0:
        return None
    return name[:index]


def _map_sensor(sensor_id: Optional[str], sensor_map: Dict[str, str],
                cpu_sensor_id: Optional[str],
                report: ReconcileReport) -> Optional[str]:
    if not sensor_id:
        return cpu_sensor_id
    bare = sensor_id[len("hwmon:"):] if sensor_id.startswith("hwmon:") else sensor_id
    mapped = sensor_map.get(bare)
    if mapped:
        return mapped
    report.unresolved_sensors.append(bare)
    logger.warning(
        "Sensor %s nicht aufloesbar, Rueckfall auf den CPU-Default %s",
        sensor_id, cpu_sensor_id,
    )
    return cpu_sensor_id


def reconcile_fan_identities(
    db: Session,
    *,
    chips: Dict[str, ChipFacts],
    sensor_map: Dict[str, str],
    cpu_sensor_id: Optional[str],
) -> ReconcileReport:
    """Ordnet Altzeilen stabilen Kennungen zu. Committet NICHT."""
    report = ReconcileReport()
    rows = list(db.execute(select(FanConfig)).scalars())

    # Rangfolge VOR dem ersten Schreibzugriff festhalten: updated_at traegt
    # ein onupdate=func.now() und aendert sich sonst waehrend des Laufs.
    order = {row.id: row.updated_at for row in rows}

    candidates: Dict[str, List[FanConfig]] = {}
    for row in rows:
        match = _LEGACY_FAN_ID.match(row.fan_id or "")
        if not match:
            continue                                   # Regel 1
        chip = _chip_from_name(row.name)
        if chip is None:
            continue                                   # kein " PWM" im Namen
        facts = chips.get(chip)
        if facts is None:                              # Regel 4: Chip abwesend
            report.skipped_absent.append(row.fan_id)
            continue
        if facts.ambiguous:
            continue                                   # Regel 2
        channel = int(match.group(2))
        if channel not in facts.pwm_channels:
            row.is_active = False                      # Chip da, Kanal weg
            report.deactivated.append(row.fan_id)
            continue
        candidates.setdefault(f"{facts.key}:pwm{channel}", []).append(row)

    # Bereits in Neuform vorliegende Zeilen treten mit an, sonst laeuft ein
    # nach einem Abbruch wiederholter Lauf in den Unique-Index.
    existing = {row.fan_id: row for row in rows}
    for new_id, group in candidates.items():
        incumbent = existing.get(new_id)
        if incumbent is not None and incumbent not in group:
            group.append(incumbent)

        # Kein None in den Sortierschluessel: zwei Zeilen ohne updated_at
        # liefen sonst in einen TypeError beim Vergleich None < None.
        winner = max(group, key=lambda r: order.get(r.id) or _EPOCH)
        for row in group:
            if row is winner:
                continue
            row.is_active = False
            report.deactivated.append(row.fan_id)

        if winner.fan_id != new_id:
            old_id = winner.fan_id
            winner.legacy_fan_id = old_id
            winner.fan_id = new_id
            report.renamed.append((old_id, new_id))
            logger.info("Fan-Identitaet: %s -> %s", old_id, new_id)
            _rewrite_references(db, old_id, new_id)

        winner.temp_sensor_id = _map_sensor(
            winner.temp_sensor_id, sensor_map, cpu_sensor_id, report
        )

    _reconcile_sensor_labels(db, sensor_map, report)
    _reconcile_composites(db, sensor_map)

    logger.info(
        "Identitaets-Abgleich: %d uebernommen, %d deaktiviert, %d ohne Chip",
        len(report.renamed), len(report.deactivated), len(report.skipped_absent),
    )
    return report


def _rewrite_references(db: Session, old_id: str, new_id: str) -> None:
    """sync_fan_id und Zeitplaneintraege ziehen mit."""
    for row in db.execute(
        select(FanConfig).where(FanConfig.sync_fan_id == old_id)
    ).scalars():
        row.sync_fan_id = new_id
    for entry in db.execute(
        select(FanScheduleEntry).where(FanScheduleEntry.fan_id == old_id)
    ).scalars():
        entry.fan_id = new_id


def _reconcile_sensor_labels(db: Session, sensor_map: Dict[str, str],
                             report: ReconcileReport) -> None:
    """Nutzer-Labels auf die neuen Sensor-Kennungen umschluesseln.

    sensor_id ist Primaerschluessel und die Tabelle hat kein is_active. Bei
    einer Kollision gewinnt die juengste Zeile; die verworfene BLEIBT unter
    ihrem alten Schluessel liegen und wird ignoriert. Kein Loeschen -- das
    ist ein ausdrueckliches Nicht-Ziel der Spec.
    """
    rows = list(db.execute(select(TempSensorLabel)).scalars())
    existing = {row.sensor_id for row in rows}
    claimed: Dict[str, TempSensorLabel] = {}

    for row in rows:
        if not _LEGACY_SENSOR_ID.match(row.sensor_id or ""):
            continue
        new_id = sensor_map.get(row.sensor_id)
        if not new_id:
            report.unresolved_sensors.append(row.sensor_id)
            continue
        bare_new = new_id[len("hwmon:"):] if new_id.startswith("hwmon:") else new_id
        if bare_new in existing:
            continue
        rival = claimed.get(bare_new)
        if rival is not None:
            loser = min((rival, row), key=lambda r: r.updated_at or _EPOCH)
            logger.warning(
                "Sensor-Label %s verworfen: %s ist bereits vergeben",
                loser.sensor_id, bare_new,
            )
            if loser is row:
                continue
        claimed[bare_new] = row

    for bare_new, row in claimed.items():
        row.legacy_sensor_id = row.sensor_id
        row.sensor_id = bare_new
        logger.info("Sensor-Label: %s -> %s", row.legacy_sensor_id, bare_new)


def _reconcile_composites(db: Session, sensor_map: Dict[str, str]) -> None:
    """Quell-IDs in composite_temp_sensors mit derselben Abbildung umschreiben."""
    for composite in db.execute(select(CompositeTempSensor)).scalars():
        try:
            sources = json.loads(composite.source_ids_json)
        except (TypeError, ValueError):
            logger.warning("Composite %s: source_ids_json unlesbar", composite.id)
            continue
        if not isinstance(sources, list):
            continue

        changed = False
        rewritten = []
        for source in sources:
            bare = source[len("hwmon:"):] if isinstance(source, str) and source.startswith("hwmon:") else source
            mapped = sensor_map.get(bare) if isinstance(bare, str) else None
            if mapped:
                rewritten.append(mapped)
                changed = True
            else:
                rewritten.append(source)
        if changed:
            composite.source_ids_json = json.dumps(rewritten)
            logger.info("Composite %s: Quell-IDs umgeschrieben", composite.id)
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_reconcile.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 5: Test für Labels und Composite-Sensoren schreiben**

An `backend/tests/test_fan_reconcile.py` anhängen:

```python
from app.models.fans import CompositeTempSensor, TempSensorLabel


def test_sensor_label_is_rekeyed_and_keeps_provenance(db):
    db.add(TempSensorLabel(sensor_id="hwmon4_temp1", custom_label="RAID-Platten"))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    labels = {row.sensor_id: row for row in db.query(TempSensorLabel).all()}
    assert "k10temp-pci-00c3:temp1" in labels
    assert labels["k10temp-pci-00c3:temp1"].custom_label == "RAID-Platten"
    assert labels["k10temp-pci-00c3:temp1"].legacy_sensor_id == "hwmon4_temp1"


def test_composite_sources_are_rewritten(db):
    db.add(CompositeTempSensor(
        id="mix:abc", name="CPU und Board", function="max",
        source_ids_json='["hwmon:hwmon4_temp1", "hwmon3_temp1"]',
    ))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    composite = db.query(CompositeTempSensor).one()
    assert json.loads(composite.source_ids_json) == [
        "hwmon:k10temp-pci-00c3:temp1",
        "hwmon:nct6798-isa-0290:temp1",
    ]


def test_unmappable_composite_source_is_left_alone(db):
    db.add(CompositeTempSensor(
        id="mix:def", name="Mit Luecke", function="max",
        source_ids_json='["gpu:junction", "hwmon9_temp1"]',
    ))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    composite = db.query(CompositeTempSensor).one()
    assert json.loads(composite.source_ids_json) == ["gpu:junction", "hwmon9_temp1"]
```

`import json` oben in der Testdatei ergänzen.

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_reconcile.py -v`
Expected: PASS (13 Tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/fan_reconcile.py backend/tests/test_fan_reconcile.py
git commit -m "feat(fans): Zuordnungsregeln fuer die Identitaets-Umstellung (#532)"
```

---

### Task 8: Verdrahtung in `_load_fan_configs` — Vorbedingungen, Reihenfolge, Primary-Gate

Der gefährlichste Task des Plans: hier entscheidet sich, ob der Abgleich in einer der beiden Fehlkonstellationen produktive Kurven zerstört.

**Files:**
- Modify: `backend/app/services/power/fan_control.py:240-284` (`_load_fan_configs`)
- Test: `backend/tests/test_fan_reconcile_wiring.py`

**Interfaces:**
- Consumes: `reconcile_fan_identities`, `ChipFacts` aus Task 7; `_fan_cache`, `_temp_paths` aus Task 3
- Produces: `FanControlService._collect_chip_facts() -> Dict[str, ChipFacts]`, `_collect_sensor_map() -> Dict[str, str]`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_reconcile_wiring.py`:

```python
"""Vorbedingungen und Gate des Identitaets-Abgleichs (#532)."""
from unittest.mock import MagicMock

import pytest

from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


def _service(monkeypatch, *, primary: bool, linux: bool):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, MagicMock())
    service._use_linux_backend = linux
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_skips_when_not_primary_worker(monkeypatch):
    service = _service(monkeypatch, primary=False, linux=True)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_on_dev_backend(monkeypatch):
    # is_available() faellt bei 0 gefundenen Lueftern auch in Produktion auf
    # das Dev-Backend zurueck. Liefe der Abgleich dann, deaktivierte er in
    # einem Rutsch alle hwmon-Zeilen.
    service = _service(monkeypatch, primary=True, linux=False)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_when_scan_found_no_chip(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=0) is False


def test_runs_when_all_preconditions_hold(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=3) is True
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_reconcile_wiring.py -v`
Expected: FAIL mit `AttributeError: 'FanControlService' object has no attribute '_should_reconcile'`

- [ ] **Step 3: Gate und Fakten-Sammler implementieren**

In `fan_control.py` im Importblock:

```python
from app.core import lifespan
from app.services.power.fan_reconcile import ChipFacts, reconcile_fan_identities
```

`lifespan` wird als **Modul** importiert. Ein `from app.core.lifespan import IS_PRIMARY_WORKER` friert den Importwert `False` ein, weil das Flag erst in `_lifespan()` gesetzt wird — der Abgleich liefe dann nie. Einziges funktionierendes Muster im Repo: `plugin_enablement.py:191`.

Methoden auf `FanControlService`:

```python
    def _should_reconcile(self, chip_count: int) -> bool:
        """Beide Vorbedingungen sind hart -- ihr Fehlen bedeutet Totalverlust.

        Ohne Linux-Backend liefe der Abgleich gegen eine Chip-Menge ohne
        einen einzigen hwmon-Chip; ohne gefundenen Chip gegen eine leere.
        In beiden Faellen faende keine Altzeile ihren Chip wieder.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return False
        if not self._use_linux_backend:
            return False
        return chip_count > 0

    def _collect_chip_facts(self) -> Dict[str, ChipFacts]:
        """Chipname -> Kennung, vorhandene PWM-Kanaele, Mehrdeutigkeit."""
        by_prefix: Dict[str, Dict] = {}
        for fan_id, info in (self._backend._fan_cache or {}).items():
            if not info.get("identity_stable"):
                continue
            prefix = info.get("device_driver") or "Unknown"
            key, _, channel = fan_id.rpartition(":pwm")
            if not channel.isdigit():
                continue
            entry = by_prefix.setdefault(prefix, {"keys": set(), "channels": set()})
            entry["keys"].add(key)
            entry["channels"].add(int(channel))

        facts: Dict[str, ChipFacts] = {}
        for prefix, entry in by_prefix.items():
            keys = entry["keys"]
            facts[prefix] = ChipFacts(
                key=next(iter(sorted(keys))),
                pwm_channels=frozenset(entry["channels"]),
                ambiguous=len(keys) > 1,
            )
        return facts

    def _collect_sensor_map(self) -> Dict[str, str]:
        """Alt-Sensor-ID (hwmon<N>_temp<M>) -> neue, praefixierte Kennung."""
        mapping: Dict[str, str] = {}
        paths = getattr(self._backend, "_temp_paths", {}) or {}
        for stable_id, path in paths.items():
            hwmon_name = path.parent.name
            temp_num = path.name[len("temp"):-len("_input")]
            mapping[f"{hwmon_name}_temp{temp_num}"] = f"hwmon:{stable_id}"
        return mapping
```

- [ ] **Step 4: Abgleich vor die Anlage-Schleife hängen**

In `_load_fan_configs`, innerhalb des bestehenden `with self.db_session_factory() as db:`-Blocks, **vor** der `for fan in fans:`-Schleife:

```python
            chip_facts = self._collect_chip_facts()
            if self._should_reconcile(len(chip_facts)):
                report = reconcile_fan_identities(
                    db,
                    chips=chip_facts,
                    sensor_map=self._collect_sensor_map(),
                    cpu_sensor_id=cpu_sensor_id,
                )
                if report.renamed or report.deactivated:
                    try:
                        from app.services.audit import get_audit_logger_db
                        get_audit_logger_db().log_system_event(
                            action="fan_identity_reconcile",
                            details={
                                "renamed": report.renamed,
                                "deactivated": report.deactivated,
                                "skipped_absent": report.skipped_absent,
                            },
                            db=db,
                        )
                    except Exception:
                        logger.debug("Audit-Eintrag zum Identitaets-Abgleich fehlgeschlagen")
```

Reihenfolge und Transaktion sind wesentlich: der Abgleich läuft **vor** der Anlage-Schleife und im selben `db`-Kontext, sodass ein einziges `db.commit()` am Ende beides trägt. Liefe er danach, wären die Ziel-IDs bereits durch frische Default-Zeilen belegt und jede Altzeile verlöre.

Der Aufruf der Audit-Fassade muss an die im Repo vorhandene Signatur angepasst werden — die exakte Form ist `backend/app/services/audit/` zu entnehmen. Fällt der Audit-Eintrag aus, darf das den Abgleich **nicht** abbrechen; deshalb der `try`.

- [ ] **Step 5: Neuanlage gegen das Worker-Rennen absichern**

In derselben Methode die Anlage-Schleife (`if not existing:`) so umbauen, dass ein paralleler Worker keinen Unique-Fehler auslöst:

```python
                if not existing:
                    config = FanConfig(...)     # bestehender Aufbau, unveraendert
                    db.add(config)
                    try:
                        db.flush()
                    except IntegrityError:
                        # Ein anderer Worker war schneller. Die Zeile existiert,
                        # das ist der gewuenschte Endzustand.
                        db.rollback()
                        logger.debug("Fan-Config %s wurde parallel angelegt", fan.fan_id)
```

`from sqlalchemy.exc import IntegrityError` im Importblock ergänzen. Der `db.rollback()` verwirft auch den Abgleich — deshalb steht dieser Zweig **nach** einem eigenen `db.commit()` des Abgleichs. Diesen Commit direkt nach dem Reconcile-Block einfügen:

```python
                db.commit()
```

- [ ] **Step 6: Den Default-Sensor präfixiert speichern**

In der Anlage-Schleife `temp_sensor_id=cpu_sensor_id or fan.temp_sensor_id` ersetzen durch:

```python
                        temp_sensor_id=TempSourceRegistry._normalize_id(
                            cpu_sensor_id or fan.temp_sensor_id
                        ) if (cpu_sensor_id or fan.temp_sensor_id) else None,
```

Damit steht in der Spalte durchgehend die präfixierte Form — dieselbe, die die API ausgibt und unter der die Registry registriert.

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_reconcile_wiring.py tests/test_fan_reconcile.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_reconcile_wiring.py
git commit -m "feat(fans): Identitaets-Abgleich beim Start, primary-only und fail-safe (#532)"
```

---

### Task 9: Bestand mitziehen — Swagger-Beispiele, Testliterale, Frontend

**Files:**
- Modify: `backend/app/schemas/fans.py` (Zeilen 88, 122, 132, 172, 194, 233, 346, 392, 394, 413)
- Modify: `backend/tests/services/test_fan_control.py`, `tests/test_fan_composite_api.py`, `tests/test_fan_sensor_assignment.py`, `tests/services/power/test_fan_gpu_hwmon_dedup.py`, `tests/test_fan_sensor_label_api.py`, `tests/test_fan_sources.py`, `tests/test_fan_curve_eval.py`, `tests/test_fan_pwm_backoff.py`
- Modify: `backend/tests/test_fan_pwm_control_probe.py`, `tests/test_fan_gpu_manual_mode.py`, `tests/test_fan_einval_diagnostic.py`
- Modify: `client/src/components/fan-control/FanCard.tsx:9`
- Modify: `client/src/__tests__/pages/FanControl.test.tsx`, `__tests__/components/fan-control/FanCard.test.tsx`, `FanDetails.test.tsx`, `fan-details/FanStatsGrid.test.tsx`

- [ ] **Step 1: Die drei Testdateien mit synthetischen Bäumen reparieren**

`test_fan_pwm_control_probe.py`, `test_fan_gpu_manual_mode.py` und `test_fan_einval_diagnostic.py` bauen hwmon-Bäume **ohne** `device`- und `subsystem`-Symlinks. Nach Task 3 laufen sie stillschweigend in den Fallback und bleiben grün, ohne die neue Ableitung abzudecken.

In jeder der drei Dateien die Baum-Hilfsfunktion um den Elternbaum ergänzen — dasselbe Muster wie `_nct_tree` aus Task 3: Gerät unter `sys/devices/<bus>/<name>` anlegen, `subsystem`-Symlink auf `sys/bus/<bus>` setzen, `device`-Symlink vom hwmon-Verzeichnis dorthin, und `_hwmon_base` auf `sys/class/hwmon` zeigen lassen.

- [ ] **Step 2: Tests laufen lassen, echte Fehlschläge sichtbar machen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_gpu_manual_mode.py tests/test_fan_einval_diagnostic.py -v`
Expected: Fehlschläge dort, wo Tests die alte ID-Form behaupten. Diese Behauptungen auf die neue Form umstellen — nicht die Bäume wieder vereinfachen.

- [ ] **Step 3: Die übrigen Testliterale nachziehen**

74 Vorkommen von `hwmon<N>_pwm<M>` / `hwmon<N>_temp<M>` in den acht oben genannten Backend-Dateien. Die meisten sind reine Fixture-Strings und laufen unverändert weiter; anzupassen sind nur die Stellen, die die **gebildete** ID behaupten.

Run: `cd backend ; python -m pytest -k "fan or power" -v`
Expected: 559 passed plus die neuen Tests.

- [ ] **Step 4: Swagger-Beispiele aktualisieren**

In `backend/app/schemas/fans.py` an den zehn genannten Zeilen `"hwmon0_pwm1"` durch `"nct6798-isa-0290:pwm1"` ersetzen und `"hwmon0_temp1"` durch `"hwmon:k10temp-pci-00c3:temp1"`. Bleiben sie stehen, bringt die API-Doku Nutzern die tote Form bei.

- [ ] **Step 5: Frontend-Formatannahme entschärfen**

`client/src/components/fan-control/FanCard.tsx:9` baut `` `hwmon:${sensorId}` ``. Nach der Umstellung liegt die präfixierte Form bereits vor; ein zweites Präfix ergäbe `hwmon:hwmon:…`. Die Stelle so ändern, dass sie nur präfixiert, wenn noch kein Namespace vorhanden ist:

```tsx
const NAMESPACES = ['hwmon:', 'gpu:', 'disk:', 'mix:'];
const namespacedSensorId = NAMESPACES.some((n) => sensorId.startsWith(n))
  ? sensorId
  : `hwmon:${sensorId}`;
```

- [ ] **Step 6: Frontend-Gates**

```bash
cd client
npx eslint .
npm run build
npx vitest run
```
Expected: 0 eslint-Fehler, Build grün, Vitest grün.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/fans.py backend/tests/ client/src/components/fan-control/FanCard.tsx client/src/__tests__/
git commit -m "chore(fans): Beispiele, Testliterale und Sensor-Praefix auf stabile IDs (#532)"
```

---

### Task 10: Dokumentation und Abschluss-Gates

**Files:**
- Modify: `docs/TECHNICAL_DOCUMENTATION.md` (Abschnitt Lüftersteuerung)
- Modify: `backend/app/services/CLAUDE.md` (Hinweis auf `fan_identity.py` / `fan_reconcile.py`)

- [ ] **Step 1: Die ehrliche Einschränkung dokumentieren**

In `docs/TECHNICAL_DOCUMENTATION.md` im Lüfter-Abschnitt festhalten:

- Lüfter- und Sensor-IDs haben die Form `<chip>-<bus>-<adresse>:pwm<N>` bzw. `hwmon:<chip>-<bus>-<adresse>:temp<M>` und überleben ein hwmon-Renumbering.
- **Nicht uneingeschränkt:** Chips ohne `pci`/`platform`-Elter (u. a. i2c-, spi-, scsi-, hid-Busse) behalten die hwmon-indizierte Form und verhalten sich wie bisher. Das betrifft insbesondere `drivetemp` (SATA-Plattentemperaturen).
- Nach einem Restore eines Vor-Umstellungs-Backups ist ein Neustart des Backends erforderlich, weil der Abgleich nur beim Dienststart läuft.
- Der Lüfter-Verlaufsgraph ist nach der Umstellung für alle Lüfter leer; alte `fan_sample`-Zeilen behalten ihre alte ID und laufen über die Retention aus.

- [ ] **Step 2: Modulhinweise ergänzen**

In `backend/app/services/CLAUDE.md` bei den `power/`-Modulen `fan_identity.py` (Ableitung der stabilen Chip-Kennung) und `fan_reconcile.py` (einmaliger Abgleich beim Start) aufnehmen.

- [ ] **Step 3: Alle Gates**

```bash
cd backend
python -m pytest -k "fan or power" -v
python -m ruff check app/services/power/ tests/
cd ../client
npx eslint .
npm run build
npx vitest run
```
Expected: alles grün. Die volle Backend-Suite bleibt der CI überlassen.

- [ ] **Step 4: Commit**

```bash
git add docs/TECHNICAL_DOCUMENTATION.md backend/app/services/CLAUDE.md
git commit -m "docs(fans): Stabile Luefter-Identitaet und ihre Grenzen dokumentieren (#532)"
```

---

## Feldverifikation nach dem Deploy

Kein Task — der Nachweis am lebenden Objekt, den nur die Zielhardware liefern kann.

1. **Kennungen gegen `sensors` prüfen.** Die abgeleiteten Chip-Kennungen müssen für die fünf dort gelisteten Chips zeichengleich sein: `nct6798-isa-0290`, `amdgpu-pci-0300`, `k10temp-pci-00c3`, `nvme-pci-0d00`, `nvme-pci-0a00`.
2. **Zeilenbilanz.** `SELECT count(*) FROM fan_configs WHERE is_active` vor und nach dem ersten Start: **16 → 8** (5 neue plus 3 `dev_*`). Gesamtzahl bleibt 16.
3. **Fehlzuordnung aufgelöst.** `SELECT fan_id, name, legacy_fan_id FROM fan_configs WHERE is_active` — `amdgpu-pci-0300:pwm1` muss `name = "amdgpu PWM1"` und `legacy_fan_id = "hwmon1_pwm1"` tragen. Heute läuft der GPU-Lüfter auf der Config eines Gehäuselüfters.
4. **Renumbering ohne Reboot.** `modprobe -r nct6775 ; modprobe nct6775`, danach Backend neu starten: `fan_configs` muss gleich viele Zeilen haben wie davor. Beim Entladen verliert BaluHost kurzzeitig die Lüfter und `pwm_enable` fällt auf den Board-Default zurück — bei Leerlauftemperaturen ungefährlich, aber ein Eingriff. Ein regulärer Reboot leistet dasselbe.
