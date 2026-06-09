"""Real mdadm integration tests against loop-device backed RAID arrays.

These exercise MdadmRaidBackend against an actual mdadm/kernel (create, status,
degrade, rebuild, finalize, delete) on throwaway loop devices — no production
disks involved. They run ONLY in the dedicated `raid-mdadm-loopback.yml` CI job
(ubuntu-latest), gated by the BALUHOST_MDADM_LOOPBACK env var, and are skipped
everywhere else (dev machines, normal CI).
"""
import os
import subprocess
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.hardware.raid import MdadmRaidBackend
from app.schemas.system import (
    CreateArrayRequest,
    DeleteArrayRequest,
    RaidSimulationRequest,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("BALUHOST_MDADM_LOOPBACK"),
    reason="loopback mdadm integration runs only in the dedicated CI job",
)

ARRAY_NAME = "md0"
ARRAY_PATH = f"/dev/{ARRAY_NAME}"


def _sudo(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sudo", "-n", *args], check=check, capture_output=True, text=True
    )


@pytest.fixture
def loop_raid(tmp_path):
    """Provision two loop devices; guarantee teardown of array + loops + files."""
    loops: list[str] = []
    files: list[Path] = []
    # Defensive: the array name must be free on this (ephemeral) host.
    assert not Path(ARRAY_PATH).exists(), f"{ARRAY_PATH} already exists on this host"
    try:
        for i in range(2):
            f = tmp_path / f"disk{i}.img"
            subprocess.run(["truncate", "-s", "128M", str(f)], check=True)
            files.append(f)
            res = _sudo("losetup", "--find", "--show", str(f))
            loops.append(res.stdout.strip())
        yield loops
    finally:
        # Stop array if present, zero superblocks, detach loops, remove files.
        _sudo("mdadm", "--stop", ARRAY_PATH, check=False)
        for lp in loops:
            _sudo("mdadm", "--zero-superblock", lp, check=False)
            _sudo("losetup", "-d", lp, check=False)
        for f in files:
            try:
                f.unlink()
            except OSError:
                pass


def _array_named(status, name):
    return next((a for a in status.arrays if a.name == name), None)


def test_create_status_delete_lifecycle(loop_raid, monkeypatch):
    monkeypatch.setattr(settings, "raid_assume_clean_by_default", True, raising=False)
    backend = MdadmRaidBackend()
    loop_a, loop_b = loop_raid

    backend.create_array(
        CreateArrayRequest(name=ARRAY_NAME, level="raid1", devices=[loop_a, loop_b])
    )

    status = backend.get_status()
    arr = _array_named(status, ARRAY_NAME)
    assert arr is not None, f"{ARRAY_NAME} not found in status after create"
    assert arr.level == "raid1"
    assert arr.status == "optimal"
    assert len(arr.devices) == 2

    backend.delete_array(DeleteArrayRequest(array=ARRAY_NAME, force=True))

    assert _array_named(backend.get_status(), ARRAY_NAME) is None


def test_degrade_rebuild_finalize_cycle(loop_raid, monkeypatch):
    monkeypatch.setattr(settings, "raid_assume_clean_by_default", True, raising=False)
    backend = MdadmRaidBackend()
    loop_a, loop_b = loop_raid

    backend.create_array(
        CreateArrayRequest(name=ARRAY_NAME, level="raid1", devices=[loop_a, loop_b])
    )
    created = _array_named(backend.get_status(), ARRAY_NAME)
    assert created is not None
    assert created.status == "optimal"

    backend.degrade(RaidSimulationRequest(array=ARRAY_NAME, device=loop_a))
    degraded = _array_named(backend.get_status(), ARRAY_NAME)
    assert degraded is not None
    assert degraded.status != "optimal"

    backend.rebuild(RaidSimulationRequest(array=ARRAY_NAME, device=loop_a))
    backend.finalize(RaidSimulationRequest(array=ARRAY_NAME))

    healed = _array_named(backend.get_status(), ARRAY_NAME)
    assert healed is not None
    assert healed.status == "optimal"

    backend.delete_array(DeleteArrayRequest(array=ARRAY_NAME, force=True))
