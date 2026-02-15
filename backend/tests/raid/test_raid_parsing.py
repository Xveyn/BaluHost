from app.schemas.system import RaidDevice
from app.services.raid import MdstatInfo, _derive_array_status, _map_device_state, _parse_mdstat


def test_parse_mdstat_with_progress() -> None:
    sample = """Personalities : [raid1]\nmd0 : active raid1 sda1[0] sdb1[1]\n      976630336 blocks super 1.2 [2/2] [UU]\n      [>....................]  resync = 8.4% (82048/976630336) finish=10.3min speed=153600K/sec\n\nunused devices: <none>\n"""
    info = _parse_mdstat(sample)

    assert "md0" in info
    entry = info["md0"]
    assert entry.blocks == 976630336
    assert entry.resync_progress == 8.4


def test_parse_mdstat_without_progress() -> None:
    sample = """md1 : active raid1 sdc1[0] sdd1[1]\n      488378368 blocks super 1.2 [2/2] [U_]\n"""
    info = _parse_mdstat(sample)

    entry = info["md1"]
    assert entry.blocks == 488378368
    assert entry.resync_progress is None


def test_map_device_state() -> None:
    assert _map_device_state("active sync") == "active"
    assert _map_device_state("spare rebuilding") == "rebuilding"
    assert _map_device_state("faulty removed") == "failed"
    assert _map_device_state("write-mostly") == "write-mostly"


def test_derive_array_status() -> None:
    devices = [RaidDevice(name="sda1", state="active"), RaidDevice(name="sdb1", state="active")]
    assert _derive_array_status("clean", None, devices) == "optimal"

    degraded = [RaidDevice(name="sda1", state="active"), RaidDevice(name="sdb1", state="failed")]
    assert _derive_array_status("clean, degraded", None, degraded) == "degraded"

    rebuilding = [RaidDevice(name="sda1", state="active"), RaidDevice(name="sdb1", state="rebuilding")]
    assert _derive_array_status("clean", 32.5, rebuilding) == "rebuilding"
