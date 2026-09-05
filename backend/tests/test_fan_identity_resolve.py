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

requires_colon_paths = pytest.mark.skipif(
    os.name == "nt",
    reason="NTFS erlaubt keine Doppelpunkte in Verzeichnisnamen; PCI-Pfade "
           "wie pci0000:00/0000:03:00.0 sind unter Windows nicht anlegbar. "
           "Die CI (Linux) fuehrt diesen Test aus.",
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


@requires_colon_paths
def test_pci_chip(tmp_path):
    link = _tree(tmp_path, "hwmon2", "pci0000:00/0000:03:00.0", "amdgpu")
    assert derive_chip_identity(link).key == "amdgpu-pci-0300"


@requires_colon_paths
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
    # drivetemp haengt am scsi-Bus. Die Schleife bricht sofort ab, wenn
    # subsystem=scsi erkannt wird; der PCI-Baum darueber wird nicht betreten.
    link = _tree(tmp_path, "hwmon7", "platform/ahci-sim/ata1/host0",
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
    # Namensprüfung läuft vor dem Gerätelauf. Ein vollständiger Baum
    # mit fehlender name ist trotzdem instabil.
    link = _tree(tmp_path, "hwmon4", "platform/k10temp-sim.1", "k10temp",
                 subsystem="platform")
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
