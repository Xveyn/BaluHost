import math
import pytest

from app.services import raid
from app.services.raid import DevRaidBackend
from app.core import config
from app.schemas.system import CreateArrayRequest, RaidDevice


def test_parse_mdstat_with_blocks_and_percent():
    mdstat = """
Personalities : [raid1]
md0 : active raid1 sda1[0] sdb1[1]
      2,096,128 blocks super 1.2 [2/2] [UU]
      [>....................]  resync =  3.4% (259212/2096128) finish=1.2min speed=12345K/sec
"""
    parsed = raid._parse_mdstat(mdstat)
    assert "md0" in parsed
    info = parsed["md0"]
    assert info.blocks == 2096128
    assert pytest.approx(info.resync_progress, rel=1e-3) == 3.4


def test_parse_mdstat_fraction_only():
    mdstat = """
md1 : active raid5 sde1 sdf1 sdg1
      2,096,128 blocks super 1.2 [3/3] [UUU]
      [==>..................]  resync = (259212/2096128)
"""
    parsed = raid._parse_mdstat(mdstat)
    assert "md1" in parsed
    info = parsed["md1"]
    assert info.blocks == 2096128
    expected = (259212 / 2096128) * 100.0
    assert pytest.approx(info.resync_progress, rel=1e-3) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("faulty", "failed"),
        ("device has been removed", "removed"),
        ("spare rebuilding", "rebuilding"),
        ("rebuild", "rebuilding"),
        ("spare", "spare"),
        ("blocked", "blocked"),
        ("writemostly", "write-mostly"),
        ("sync", "active"),
        ("active", "active"),
        ("", "unknown"),
    ],
)
def test_map_device_state_variants(text, expected):
    assert raid._map_device_state(text) == expected


def test_derive_array_status_variants():
    # status from state_text
    devices = [RaidDevice(name="sda1", state="active")]
    assert raid._derive_array_status("resyncing now", None, devices) == "rebuilding"
    assert raid._derive_array_status("degraded and faulty", None, devices) == "degraded"
    assert raid._derive_array_status("inactive", None, devices) == "inactive"

    # progress -> rebuilding
    assert raid._derive_array_status(None, 12.3, devices) == "rebuilding"

    # failed device -> degraded
    devices_failed = [RaidDevice(name="sda1", state="failed")]
    assert raid._derive_array_status(None, None, devices_failed) == "degraded"

    # default optimal
    assert raid._derive_array_status(None, None, devices) == "optimal"


def test_devraid_add_mock_and_create_array_and_validation():
    backend = DevRaidBackend()
    before = backend.get_available_disks()
    # ensure base disks present
    names_before = {d.name for d in before.disks}
    assert "sda" in names_before

    # add mock disk
    resp = backend.add_mock_disk("h", 15, "TestDisk", "extra")
    assert "successfully added" in resp.message.lower()

    after = backend.get_available_disks()
    names_after = {d.name for d in after.disks}
    assert "sdh" in names_after or "sdh" in {d.name for d in after.disks}

    # create array with valid devices
    req = CreateArrayRequest(name="md1", level="raid1", devices=["sdc1", "sdd1"])
    create_resp = backend.create_array(req)
    assert "created" in create_resp.message.lower()

    # invalid: raid5 requires at least 3 devices
    with pytest.raises(ValueError):
        req2 = CreateArrayRequest(name="md2", level="raid5", devices=["sda1", "sdb1"])
        backend.create_array(req2)


def test_select_backend_forced_dev(monkeypatch):
    # Ensure forcing dev backend returns DevRaidBackend
    monkeypatch.setattr(config.settings, "raid_force_dev_backend", True)
    backend = raid._select_backend()
    assert isinstance(backend, DevRaidBackend)
    # restore
    monkeypatch.setattr(config.settings, "raid_force_dev_backend", False)


def test_parse_devices_header_variants():
    # English header style
    detail = """
Number   Major   RaidDevice State
   0       8       1        active sync   /dev/sda1
   1       8       1        spare        /dev/sdb1
unused devices: <none>
"""
    devices = raid.MdadmRaidBackend._parse_devices(None, detail)
    names = [d.name for d in devices]
    states = {d.name: d.state for d in devices}
    assert "sda1" in names
    assert "sdb1" in names
    assert states["sda1"] == "active"
    assert states["sdb1"] == "spare"


def test_parse_devices_headerless_indexed():
    # Headerless output where rows start with an index number
    detail = """
 0  8  1  active   /dev/sdc1
 1  8  1  faulty   /dev/sdd1
unused devices: <none>
"""
    devices = raid.MdadmRaidBackend._parse_devices(None, detail)
    assert any(d.name == "sdc1" and d.state == "active" for d in devices)
    assert any(d.name == "sdd1" and d.state == "failed" for d in devices)


def test_parse_devices_non_english_header():
    # German header variant 'Nummer'
    detail = """
Nummer  Major  RaidDevice Zustand
  0      8      1        rebuild  /dev/sde1
  1      8      1        writeMostly  /dev/sdf1
unused devices: <none>
"""
    devices = raid.MdadmRaidBackend._parse_devices(None, detail)
    assert any(d.name == "sde1" and d.state == "rebuilding" for d in devices)
    assert any(d.name == "sdf1" and d.state == "write-mostly" for d in devices)

