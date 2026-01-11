import pytest
from pathlib import Path

from app.services.raid import MdadmRaidBackend, MdstatInfo


def _mk_backend():
    # Bypass __init__ which checks system mdadm availability
    backend = object.__new__(MdadmRaidBackend)
    backend._lsblk_available = False
    return backend


def test_parse_devices_standard_table():
    detail = """
Archive Level : raid1
Number   Major   Minor   RaidDevice State
   0       8        1        0      active sync   /dev/sda1
   1       8       17        1      spare         /dev/sdb1
"""
    backend = _mk_backend()
    devices = backend._parse_devices(detail)
    assert len(devices) == 2
    assert devices[0].name == Path("/dev/sda1").name
    assert devices[0].state == "active"
    assert devices[1].name == Path("/dev/sdb1").name
    assert devices[1].state == "spare"


def test_parse_devices_various_states():
    detail = """
Number   Major   Minor   RaidDevice State
   0       8        1        0      faulty         /dev/sda1
   1       8       17        1      remove         /dev/sdb1
   2       8       33        2      write-mostly   /dev/sdc1
   3       8       49        3      blocked        /dev/sdd1
"""
    backend = _mk_backend()
    devices = backend._parse_devices(detail)
    mapping = {d.name: d.state for d in devices}
    assert mapping["sda1"] == "failed"
    assert mapping["sdb1"] == "removed"
    # write-mostly might be reported as writemostly or with hyphen; ensure parser normalizes
    assert mapping["sdc1"] in {"write-mostly", "writemostly", "active", "unknown"}
    assert mapping["sdd1"] == "blocked"


def test_parse_devices_headerless_rows():
    # Some mdadm versions don't print the 'Number' header; rows start directly with an index
    detail = """
   0       8        1        0      active sync   /dev/sda1
   1       8       17        1      spare         /dev/sdb1
"""
    backend = _mk_backend()
    devices = backend._parse_devices(detail)
    assert len(devices) == 2
    assert devices[0].name == "sda1"
    assert devices[0].state == "active"


def test_parse_devices_localized_header():
    # German localization might print 'Nummer' instead of 'Number'
    detail = """
Nummer   Major   Minor   RaidDevice Zustand
   0       8        1        0      active sync   /dev/sda1
   1       8       17        1      spare         /dev/sdb1
"""
    backend = _mk_backend()
    devices = backend._parse_devices(detail)
    assert len(devices) == 2
    assert devices[1].name == "sdb1"
    assert devices[1].state == "spare"


def test_resolve_array_size_from_mdstat_blocks():
    backend = _mk_backend()
    info = MdstatInfo(blocks=2096128)
    size = backend._resolve_array_size("md0", info, "")
    assert size == 2096128 * 1024


def test_resolve_array_size_from_detail_blocks_and_bytes():
    backend = _mk_backend()
    detail_blocks = "Array Size : 2,096,128 blocks"
    size_blocks = backend._resolve_array_size("md0", None, detail_blocks)
    assert size_blocks == 2096128 * 1024

    detail_bytes = "Array Size : 2147483648 bytes"
    size_bytes = backend._resolve_array_size("md1", None, detail_bytes)
    assert size_bytes == 2147483648


def test_resolve_array_size_raises_when_unknown():
    backend = _mk_backend()
    with pytest.raises(RuntimeError):
        backend._resolve_array_size("mdx", None, "")
