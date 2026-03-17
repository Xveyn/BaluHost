"""
Benchmark lifecycle management: recovery, orphan cleanup, shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import signal
import subprocess
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkStatus, DiskBenchmark

from .state import _active_benchmarks, _cancellation_flags

logger = logging.getLogger(__name__)


def recover_stale_benchmarks(db: Session) -> int:
    """Mark any RUNNING/PENDING benchmarks as FAILED after a server restart.

    Returns the number of recovered benchmarks.
    """
    stale = (
        db.query(DiskBenchmark)
        .filter(DiskBenchmark.status.in_([BenchmarkStatus.RUNNING, BenchmarkStatus.PENDING]))
        .all()
    )
    if not stale:
        return 0

    now = datetime.now(timezone.utc)
    for bench in stale:
        bench.status = BenchmarkStatus.FAILED
        bench.error_message = "Server restarted while benchmark was in progress"
        bench.completed_at = now
        if bench.started_at:
            started = bench.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            bench.duration_seconds = (now - started).total_seconds()
    db.commit()
    logger.info("Recovered %d stale benchmark(s) after server restart", len(stale))
    return len(stale)


def kill_orphan_fio_processes() -> None:
    """Kill any orphaned fio processes left from previous benchmark runs.

    Only runs on Linux. Errors are silently ignored.
    """
    if platform.system().lower() != "linux":
        return

    try:
        result = subprocess.run(
            ["pgrep", "-x", "fio"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return  # No fio processes found

        pids = [int(pid.strip()) for pid in result.stdout.strip().split("\n") if pid.strip()]
        for pid in pids:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", 9))
                logger.info("Killed orphan fio process (PID %d)", pid)
            except (ProcessLookupError, PermissionError) as e:
                logger.debug("Could not kill fio PID %d: %s", pid, e)
    except FileNotFoundError:
        logger.debug("pgrep not found, skipping orphan fio cleanup")
    except Exception as e:
        logger.debug("Error during orphan fio cleanup: %s", e)


async def shutdown_benchmarks(db: Session) -> None:
    """Gracefully stop all active benchmarks during server shutdown."""
    # Set cancellation flags for all active benchmarks
    for bench_id in list(_active_benchmarks.keys()):
        _cancellation_flags[bench_id] = True

    # Cancel and wait for active tasks
    for bench_id, task in list(_active_benchmarks.items()):
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass

    # DB cleanup for any still-running benchmarks
    recover_stale_benchmarks(db)

    # Kill orphan fio processes
    kill_orphan_fio_processes()

    # Clear tracking dicts
    _active_benchmarks.clear()
    _cancellation_flags.clear()
    logger.info("Benchmark shutdown complete")
