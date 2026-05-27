"""Tests for memory_collector breakdown logic."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring import memory_collector
from app.services.monitoring.memory_collector import (
    MemoryMetricCollector,
    get_baluhost_memory_breakdown,
)
from app.services.monitoring.process_tracker import BALUHOST_PROCESS_PATTERNS


def _fake_proc(pid: int, cmdline_str: str, rss_bytes: int):
    """Build a MagicMock matching the .info dict shape requested by get_baluhost_memory_breakdown (pid/name/cmdline/memory_info)."""
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": "python",
        "cmdline": cmdline_str.split(),
        "memory_info": MagicMock(rss=rss_bytes),
    }
    return proc


def test_breakdown_contains_all_defined_units():
    """All names from BALUHOST_PROCESS_PATTERNS appear as keys (zero-filled)."""
    with patch.object(memory_collector.psutil, "process_iter", return_value=[]):
        result = get_baluhost_memory_breakdown()
    for entry in BALUHOST_PROCESS_PATTERNS:
        assert entry["name"] in result
        assert result[entry["name"]] == 0


def test_breakdown_routes_processes_to_their_unit():
    """Each matched process contributes RSS to its unit bucket."""
    procs = [
        _fake_proc(401, "python -m uvicorn app.main --port 8000", rss_bytes=200_000_000),
        _fake_proc(402, "python -m uvicorn app.main --port 8000", rss_bytes=150_000_000),  # worker 2
        _fake_proc(403, "python -m uvicorn app.main --fd 3 --workers 2", rss_bytes=100_000_000),
        _fake_proc(404, "python scripts/scheduler_worker.py", rss_bytes=50_000_000),
        _fake_proc(405, "python scripts/webdav_worker.py", rss_bytes=40_000_000),
        _fake_proc(406, "python scripts/monitoring_worker.py", rss_bytes=30_000_000),
    ]
    with patch.object(memory_collector.psutil, "process_iter", return_value=procs):
        result = get_baluhost_memory_breakdown()

    assert result["baluhost-backend"] == 350_000_000
    assert result["baluhost-backend-local"] == 100_000_000
    assert result["baluhost-scheduler"] == 50_000_000
    assert result["baluhost-webdav"] == 40_000_000
    assert result["baluhost-monitoring"] == 30_000_000


def test_collect_sample_populates_breakdown_and_total():
    """MemoryMetricCollector.collect_sample fills both breakdown and total."""
    procs = [
        _fake_proc(501, "python -m uvicorn app.main --port 8000", rss_bytes=200_000_000),
        _fake_proc(502, "python scripts/scheduler_worker.py", rss_bytes=50_000_000),
    ]
    fake_vmem = MagicMock(
        total=16 * 1024**3,
        available=8 * 1024**3,
        percent=50.0,
    )
    with patch.object(memory_collector.psutil, "process_iter", return_value=procs), \
         patch.object(memory_collector.psutil, "virtual_memory", return_value=fake_vmem):
        collector = MemoryMetricCollector()
        sample = collector.collect_sample()

    assert sample is not None
    assert sample.baluhost_memory_bytes == 250_000_000  # total backward-compat
    assert sample.baluhost_memory_breakdown is not None
    assert sample.baluhost_memory_breakdown["baluhost-backend"] == 200_000_000
    assert sample.baluhost_memory_breakdown["baluhost-scheduler"] == 50_000_000
