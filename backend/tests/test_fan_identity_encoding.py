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


def test_platform_address_ignores_trailing_garbage_after_the_number():
    # sscanf' %d liest den fuehrenden Ziffernlauf und stoppt; alles danach
    # ist ihm gleich. Ein Endanker im Muster waere hier falsch.
    assert encode_platform_address("nct6775.656.1") == 656


def test_platform_address_accepts_hyphen_before_the_suffix():
    # Zweite bewusste Abweichung: libsensors' Scanset kennt kein "-" und
    # fiele in den Hex-Unfall (0xabc). Wir lesen den Suffix.
    assert encode_platform_address("abc-def.5") == 5


def test_device_tree_prefix_is_case_insensitive():
    assert encode_platform_address("F0000000.hwmon") == 0xf0000000


@pytest.mark.parametrize("prefix,bus,addr,expected", [
    ("nct6798", "isa", 656, "nct6798-isa-0290"),
    ("amdgpu", "pci", 0x0300, "amdgpu-pci-0300"),
    ("k10temp", "pci", 0x00c3, "k10temp-pci-00c3"),
    ("nvme", "pci", 0x0d00, "nvme-pci-0d00"),
    ("nvme", "pci", 0x10d00, "nvme-pci-10d00"),  # %04x ist Mindestbreite
])
def test_format_chip_name(prefix, bus, addr, expected):
    assert format_chip_name(prefix, bus, addr) == expected
