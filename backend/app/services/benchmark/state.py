"""
Benchmark shared state, constants, protocols, and helpers.

This is a leaf module with no internal dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol

from sqlalchemy.orm import Session

from app.schemas.benchmark import DiskInfo

if TYPE_CHECKING:
    from app.models.benchmark import DiskBenchmark

logger = logging.getLogger(__name__)

# Active benchmarks tracking (for cancellation)
_active_benchmarks: Dict[int, asyncio.Task] = {}
_cancellation_flags: Dict[int, bool] = {}

# Timeout for a single fio test (10 minutes)
_FIO_TIMEOUT_SECONDS = 600


class BenchmarkBackend(Protocol):
    """Protocol for benchmark backends."""

    def get_available_disks(self) -> List[DiskInfo]:
        """Get list of available disks for benchmarking."""
        ...

    async def run_benchmark(
        self,
        benchmark: DiskBenchmark,
        profile_config: Any,
        db: Session,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Run the benchmark and update results in database."""
        ...

    def cancel_benchmark(self, benchmark_id: int) -> bool:
        """Request cancellation of a running benchmark."""
        ...


class FioNotFoundError(RuntimeError):
    """Raised when fio is required but not installed."""


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    value = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def _get_fio_path() -> Optional[str]:
    """Find fio executable path."""
    fio = shutil.which("fio")
    if fio:
        return fio

    # Check common paths on Linux
    common_paths = ["/usr/bin/fio", "/usr/local/bin/fio"]
    for path in common_paths:
        if os.path.exists(path):
            return path

    return None


def _is_system_disk(disk_name: str, mount_point: Optional[str]) -> bool:
    """Check if a disk is the system disk."""
    if mount_point in ["/", "C:\\", "/boot", "/boot/efi"]:
        return True

    # Check for common system disk indicators
    if platform.system().lower() == "linux":
        # Check if root filesystem is on this disk
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        device, mount = parts[0], parts[1]
                        if mount == "/" and disk_name in device:
                            return True
        except Exception:
            pass

    return False
