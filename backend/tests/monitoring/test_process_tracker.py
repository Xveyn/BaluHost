"""Tests for ProcessTracker pattern matching and BALUHOST_PROCESS_PATTERNS."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring import process_tracker
from app.services.monitoring.process_tracker import (
    BALUHOST_PROCESS_PATTERNS,
    ProcessTracker,
)


def _fake_proc(pid: int, name: str, cmdline_str: str, rss_bytes: int = 1024 * 1024):
    """Build a MagicMock that behaves like a psutil.Process .info dict source."""
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cmdline": cmdline_str.split(),
        "cpu_percent": 0.0,
        "memory_info": MagicMock(rss=rss_bytes),
        "status": "running",
    }
    return proc


def test_patterns_include_all_five_systemd_units():
    """All five production systemd units are present in BALUHOST_PROCESS_PATTERNS.

    (TUI and frontend-dev are optional/dev-only and not asserted here.)
    """
    names = {entry["name"] for entry in BALUHOST_PROCESS_PATTERNS}
    assert "baluhost-backend" in names
    assert "baluhost-backend-local" in names
    assert "baluhost-scheduler" in names
    assert "baluhost-webdav" in names
    assert "baluhost-monitoring" in names


def test_patterns_order_puts_backend_local_before_backend():
    """First-match-wins requires backend-local to precede backend in the list."""
    order = [entry["name"] for entry in BALUHOST_PROCESS_PATTERNS]
    assert order.index("baluhost-backend-local") < order.index("baluhost-backend")


def test_find_processes_requires_all_patterns_to_match():
    """Multi-token pattern: all tokens must be in cmdline."""
    tracker = ProcessTracker()
    procs = [
        # Has "uvicorn app.main" but not "--fd 3" → should NOT match a two-token pattern
        _fake_proc(101, "python", "python -m uvicorn app.main --port 8000"),
        # Has both tokens → should match
        _fake_proc(102, "python", "python -m uvicorn app.main --fd 3 --workers 2"),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        matched = tracker._find_processes(["uvicorn app.main", "--fd 3"])
    pids = [m["pid"] for m in matched]
    assert pids == [102]


def test_find_processes_single_pattern_still_matches():
    """Single-token pattern behaves like before (no regression)."""
    tracker = ProcessTracker()
    procs = [
        _fake_proc(201, "python", "python scripts/scheduler_worker.py"),
        _fake_proc(202, "python", "python scripts/webdav_worker.py"),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        matched = tracker._find_processes(["scheduler_worker.py"])
    pids = [m["pid"] for m in matched]
    assert pids == [201]


def test_collect_samples_routes_backend_local_to_its_own_bucket():
    """A uvicorn process with --fd 3 is sampled as baluhost-backend-local, NOT baluhost-backend."""
    tracker = ProcessTracker()
    procs = [
        # Backend (HTTP): uvicorn app.main without --fd
        _fake_proc(301, "python", "python -m uvicorn app.main --port 8000", rss_bytes=200 * 1024 * 1024),
        # Backend (Local): uvicorn app.main with --fd 3
        _fake_proc(302, "python", "python -m uvicorn app.main --fd 3 --workers 2", rss_bytes=100 * 1024 * 1024),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        samples = tracker.collect_samples()

    by_pid = {s.pid: s for s in samples}
    assert by_pid[301].process_name == "baluhost-backend"
    assert by_pid[302].process_name == "baluhost-backend-local"
    # The same PID is NOT duplicated under two names
    assert sum(1 for s in samples if s.pid == 302) == 1


def test_collect_samples_emits_stopped_sample_for_vanished_unit():
    """When a previously-seen unit disappears, emit a synthetic is_alive=False sample."""
    tracker = ProcessTracker()
    proc = _fake_proc(501, "python", "python scripts/scheduler_worker.py")

    # Prime _known_pids with one alive sample
    with patch.object(process_tracker.psutil, "process_iter", return_value=[proc]):
        tracker.collect_samples()

    # Next tick: process gone
    with patch.object(process_tracker.psutil, "process_iter", return_value=[]):
        samples = tracker.collect_samples()

    stopped = [s for s in samples if not s.is_alive]
    assert len(stopped) == 1
    assert stopped[0].process_name == "baluhost-scheduler"
    assert stopped[0].pid == 501
    assert stopped[0].status == "stopped"
    assert stopped[0].cpu_percent == 0.0
    assert stopped[0].memory_mb == 0.0
