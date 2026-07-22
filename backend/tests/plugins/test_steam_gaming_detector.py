"""Detecting the running Steam game from /proc (see spec 2026-07-22)."""

from pathlib import Path

from app.plugins.installed.steam_gaming import detector


def _fake_proc(tmp_path: Path, procs: dict[int, str]) -> Path:
    """Build a /proc-shaped tree: <pid>/cmdline with NUL-separated argv."""
    root = tmp_path / "proc"
    root.mkdir()
    for pid, cmdline in procs.items():
        entry = root / str(pid)
        entry.mkdir()
        (entry / "cmdline").write_bytes(cmdline.replace(" ", "\x00").encode())
    (root / "meminfo").write_text("not a pid dir")
    return root


REAPER = "/home/sven/.local/share/Steam/ubuntu12_32/reaper SteamLaunch AppId=1449560 -- /proton"
WRAPPER = "/bin/sh -c mangohud steam-launch-wrapper -- reaper SteamLaunch AppId=1449560 -- /proton"


def test_no_game_running_returns_none(tmp_path):
    root = _fake_proc(tmp_path, {1: "/sbin/init", 4367: "/usr/bin/steam"})

    assert detector.detect_running_app_id(root) is None


def test_finds_the_app_id_of_a_running_game(tmp_path):
    root = _fake_proc(tmp_path, {1: "/sbin/init", 591762: REAPER})

    assert detector.detect_running_app_id(root) == "1449560"


def test_mangohud_duplicate_yields_one_app_id(tmp_path):
    """The wrapper and the reaper both carry AppId= for the same game."""
    root = _fake_proc(tmp_path, {591737: WRAPPER, 591762: REAPER})

    assert detector.detect_running_app_id(root) == "1449560"


def test_lowest_pid_wins_when_two_app_ids_are_present(tmp_path):
    """Deterministic answer instead of /proc directory order.

    PIDs differ in digit count (9 vs 800) so numeric and lexicographic
    ordering disagree — a regression to string comparison ("9" < "800")
    would pick the wrong winner and this test would catch it.
    """
    root = _fake_proc(tmp_path, {
        9: "reaper SteamLaunch AppId=222 -- /x",
        800: "reaper SteamLaunch AppId=111 -- /x",
    })

    assert detector.detect_running_app_id(root) == "222"


def test_unreadable_and_vanished_entries_are_skipped(tmp_path):
    """A process can die between listdir() and read()."""
    root = _fake_proc(tmp_path, {591762: REAPER})
    (root / "999").mkdir()  # pid dir without cmdline — vanished mid-scan

    assert detector.detect_running_app_id(root) == "1449560"


def test_missing_proc_returns_none(tmp_path):
    """Windows dev boxes have no /proc at all."""
    assert detector.detect_running_app_id(tmp_path / "nope") is None
