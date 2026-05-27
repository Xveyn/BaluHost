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
