"""Tests for disk_monitor's RAID member detection (mdstat-based).

These tests verify that _refresh_raid_members reads /proc/mdstat directly
without invoking mdadm/sudo, and that the throttle timestamp is advanced
even when reading fails (preventing per-second retry storms).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import disk_monitor


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset the module-level RAID cache around each test."""
    disk_monitor._raid_member_names = set()
    disk_monitor._raid_members_last_refresh = 0.0
    disk_monitor._disk_io_history.clear()
    yield
    disk_monitor._raid_member_names = set()
    disk_monitor._raid_members_last_refresh = 0.0
    disk_monitor._disk_io_history.clear()


_MDSTAT_TWO_ARRAYS = (
    "Personalities : [raid1]\n"
    "md0 : active raid1 sda1[0] sdb1[1]\n"
    "      976630336 blocks super 1.2 [2/2] [UU]\n"
    "\n"
    "md1 : active raid1 nvme0n1p1[0] nvme1n1p1[1]\n"
    "      488378368 blocks super 1.2 [2/2] [UU]\n"
    "\n"
    "unused devices: <none>\n"
)


def test_refresh_extracts_member_base_names(tmp_path):
    """/proc/mdstat content yields stripped base disk names."""
    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text(_MDSTAT_TWO_ARRAYS, encoding="utf-8")

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat):
        disk_monitor._refresh_raid_members()

    assert disk_monitor._raid_member_names == {"sda", "sdb", "nvme0n1", "nvme1n1"}


def test_refresh_does_not_invoke_subprocess(tmp_path):
    """The new implementation must never spawn mdadm/sudo subprocesses."""
    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text(_MDSTAT_TWO_ARRAYS, encoding="utf-8")

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat), \
         patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen") as mock_popen:
        disk_monitor._refresh_raid_members()

    assert mock_run.call_count == 0
    assert mock_popen.call_count == 0


def test_refresh_advances_throttle_on_missing_mdstat(tmp_path):
    """Even when /proc/mdstat is missing, the throttle must advance so the
    next call within 60s short-circuits (no retry storm)."""
    missing = tmp_path / "does_not_exist"
    assert not missing.exists()

    with patch.object(disk_monitor, "_MDSTAT_PATH", missing):
        disk_monitor._refresh_raid_members()

    # Throttle moved past 0 → second call within the window is a no-op.
    assert disk_monitor._raid_members_last_refresh > 0.0
    last = disk_monitor._raid_members_last_refresh

    with patch.object(disk_monitor, "_MDSTAT_PATH", missing):
        disk_monitor._refresh_raid_members()

    # Same timestamp → second call short-circuited (the 60s window guard).
    assert disk_monitor._raid_members_last_refresh == last


def test_refresh_advances_throttle_on_parse_failure(tmp_path):
    """If parsing raises, the throttle must still advance to prevent a
    per-tick error spam loop."""
    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text("garbage", encoding="utf-8")

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat), \
         patch(
             "app.services.hardware.raid.parsing._parse_mdstat",
             side_effect=RuntimeError("boom"),
         ):
        disk_monitor._refresh_raid_members()

    assert disk_monitor._raid_members_last_refresh > 0.0


def test_refresh_clears_stale_history_for_new_members(tmp_path):
    """When a new RAID member appears, its disk_io_history entry is dropped."""
    # Pre-existing history for a disk that's about to be classified as a RAID member.
    disk_monitor._disk_io_history["sda"] = [{"timestamp": 1, "readMbps": 10}]
    disk_monitor._disk_io_history["sdc"] = [{"timestamp": 1, "readMbps": 20}]

    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text(_MDSTAT_TWO_ARRAYS, encoding="utf-8")

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat):
        disk_monitor._refresh_raid_members()

    assert "sda" not in disk_monitor._disk_io_history
    assert "sdc" in disk_monitor._disk_io_history  # untouched (not a member)


def test_throttle_short_circuits_within_window(tmp_path):
    """A second call within 60s must not re-read /proc/mdstat."""
    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text(_MDSTAT_TWO_ARRAYS, encoding="utf-8")

    call_count = {"reads": 0}
    real_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        if self == fake_mdstat:
            call_count["reads"] += 1
        return real_read_text(self, *args, **kwargs)

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat), \
         patch.object(Path, "read_text", counting_read_text):
        disk_monitor._refresh_raid_members()
        disk_monitor._refresh_raid_members()
        disk_monitor._refresh_raid_members()

    assert call_count["reads"] == 1


def test_is_raid_member_uses_refreshed_set(tmp_path):
    """End-to-end: after refresh, _is_raid_member returns True for stripped names."""
    fake_mdstat = tmp_path / "mdstat"
    fake_mdstat.write_text(_MDSTAT_TWO_ARRAYS, encoding="utf-8")

    with patch.object(disk_monitor, "_MDSTAT_PATH", fake_mdstat):
        disk_monitor._refresh_raid_members()

    assert disk_monitor._is_raid_member("sda") is True
    assert disk_monitor._is_raid_member("nvme0n1") is True
    assert disk_monitor._is_raid_member("sdc") is False
