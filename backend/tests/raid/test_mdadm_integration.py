import json
import subprocess
from types import SimpleNamespace

from app.services.raid import MdadmRaidBackend, MdstatInfo
from app.schemas.system import RaidSpeedLimits, RaidStatusResponse, RaidArray, RaidDevice


def _mk_backend():
    backend = object.__new__(MdadmRaidBackend)
    return backend


def test_get_status_with_mocked_mdadm_and_detail():
    backend = _mk_backend()
    backend._read_mdstat = lambda: {"md0": MdstatInfo(blocks=2096128, resync_progress=12.3)}
    backend._scan_arrays = lambda: ["md0"]

    detail_output = """
Raid Level : raid1
Array Size : 2,096,128 blocks
Number   Major   Minor   RaidDevice State
   0       8        1        0      active sync   /dev/sda1
   1       8       17        1      spare         /dev/sdb1
"""

    def fake_run(command, *, check: bool = True, capture_output: bool = True, text: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        cmd_key = " ".join(command)
        if "mdadm --detail --scan" in cmd_key:
            return subprocess.CompletedProcess(command, 0, stdout="ARRAY /dev/md0\n", stderr="")
        if "mdadm /dev/md0 --detail" in cmd_key:
            return subprocess.CompletedProcess(command, 0, stdout=detail_output, stderr="")
        raise RuntimeError(f"Unexpected command in test fake: {cmd_key}")

    backend._run = fake_run
    backend._read_speed_limits = lambda: RaidSpeedLimits(minimum=1000, maximum=2000)

    status = MdadmRaidBackend.get_status(backend)
    assert len(status.arrays) == 1
    arr = status.arrays[0]
    assert arr.name == "md0"
    assert arr.size_bytes == 2096128 * 1024
    assert abs((arr.resync_progress or 0.0) - 12.3) < 1e-6


def test_get_available_disks_with_mocked_lsblk_and_raid():
    backend = _mk_backend()
    backend._lsblk_available = True
    backend.get_status = lambda: RaidStatusResponse(
        arrays=[
            RaidArray(
                name="md0",
                level="raid1",
                size_bytes=0,
                status="optimal",
                devices=[RaidDevice(name="sda1", state="active")],
            )
        ],
        speed_limits=None,
    )

    lsblk_json = {
        "blockdevices": [
            {
                "name": "sda",
                "size": 5368709120,
                "model": "TestDisk 5GB",
                "type": "disk",
                "children": [
                    {"name": "sda1", "size": 5368709120, "type": "part", "fstype": None}
                ],
            },
            {
                "name": "sdb",
                "size": 5368709120,
                "model": "TestDisk 5GB",
                "type": "disk",
            },
        ]
    }

    def fake_run(command, *, check: bool = True, capture_output: bool = True, text: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        if command[0] == "lsblk":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(lsblk_json), stderr="")
        raise RuntimeError(f"Unexpected command in test fake: {' '.join(command)}")

    backend._run = fake_run

    disks_resp = MdadmRaidBackend.get_available_disks(backend)
    names = [d.name for d in disks_resp.disks]
    assert "sda" in names and "sdb" in names
    sda = next(d for d in disks_resp.disks if d.name == "sda")
    assert sda.is_partitioned is True
    assert sda.in_raid is True
