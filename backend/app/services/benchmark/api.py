"""
Benchmark public API: start, cancel, get, history, get_backend.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.benchmark import (
    BenchmarkProfile,
    BenchmarkStatus,
    BenchmarkTargetType,
    DiskBenchmark,
)
from app.schemas.benchmark import (
    BENCHMARK_PROFILES,
    BenchmarkProfileConfig,
    DiskInfo,
)

from .dev_backend import DevBenchmarkBackend
from .fio_backend import FioBenchmarkBackend
from .state import (
    BenchmarkBackend,
    FioNotFoundError,
    _active_benchmarks,
    _cancellation_flags,
    _get_fio_path,
)

logger = logging.getLogger(__name__)

# Singleton backend instance
_benchmark_backend: Optional[BenchmarkBackend] = None


def get_benchmark_backend() -> BenchmarkBackend:
    """Get the appropriate benchmark backend based on settings.

    In dev mode: Uses simulated DevBenchmarkBackend
    In prod mode: Uses FioBenchmarkBackend (requires fio to be installed)

    Raises:
        FioNotFoundError: In production mode when fio is not installed
    """
    global _benchmark_backend

    if _benchmark_backend is None:
        if settings.is_dev_mode:
            logger.info("Using development benchmark backend (simulated)")
            _benchmark_backend = DevBenchmarkBackend()
        else:
            fio_path = _get_fio_path()
            if fio_path:
                logger.info(f"Using FIO benchmark backend (fio at {fio_path})")
                _benchmark_backend = FioBenchmarkBackend()
            else:
                raise FioNotFoundError(
                    "fio is not installed. Install with: apt install fio"
                )

    return _benchmark_backend


def get_available_disks() -> List[DiskInfo]:
    """Get list of available disks for benchmarking."""
    return get_benchmark_backend().get_available_disks()


def get_profile_configs() -> List[BenchmarkProfileConfig]:
    """Get list of available benchmark profiles."""
    return list(BENCHMARK_PROFILES.values())


async def start_benchmark(
    db: Session,
    disk_name: str,
    profile: BenchmarkProfile,
    target_type: BenchmarkTargetType,
    user_id: Optional[int] = None,
    test_directory: Optional[str] = None,
) -> DiskBenchmark:
    """Start a new benchmark."""
    # Get disk info
    disks = get_available_disks()
    disk_info = next((d for d in disks if d.name == disk_name), None)

    if disk_info is None:
        raise ValueError(f"Disk '{disk_name}' not found")

    if not disk_info.can_benchmark and target_type == BenchmarkTargetType.TEST_FILE:
        raise ValueError(f"Disk '{disk_name}' cannot be benchmarked: {disk_info.warning}")

    # Create benchmark record
    benchmark = DiskBenchmark(
        disk_name=disk_name,
        disk_model=disk_info.model,
        disk_size_bytes=disk_info.size_bytes,
        profile=profile,
        target_type=target_type,
        status=BenchmarkStatus.PENDING,
        progress_percent=0.0,
        user_id=user_id,
    )
    db.add(benchmark)
    db.commit()
    db.refresh(benchmark)

    # Get profile config
    profile_config = BENCHMARK_PROFILES[profile.value]

    # Start benchmark in background
    async def run_benchmark_task():
        try:
            benchmark.status = BenchmarkStatus.RUNNING
            benchmark.started_at = datetime.now(timezone.utc)
            db.commit()

            backend = get_benchmark_backend()
            await backend.run_benchmark(benchmark, profile_config, db)
        except Exception as e:
            logger.exception(f"Benchmark {benchmark.id} failed: {e}")
            benchmark.status = BenchmarkStatus.FAILED
            benchmark.error_message = str(e)
            db.commit()
        finally:
            # Cleanup
            if benchmark.id in _active_benchmarks:
                del _active_benchmarks[benchmark.id]
            if benchmark.id in _cancellation_flags:
                del _cancellation_flags[benchmark.id]

    task = asyncio.create_task(run_benchmark_task())
    _active_benchmarks[benchmark.id] = task
    _cancellation_flags[benchmark.id] = False

    return benchmark


def cancel_benchmark(benchmark_id: int, db: Session) -> bool:
    """Cancel a running benchmark."""
    benchmark = db.query(DiskBenchmark).filter(DiskBenchmark.id == benchmark_id).first()
    if not benchmark:
        return False

    if benchmark.status != BenchmarkStatus.RUNNING:
        return False

    backend = get_benchmark_backend()
    return backend.cancel_benchmark(benchmark_id)


def get_benchmark(benchmark_id: int, db: Session) -> Optional[DiskBenchmark]:
    """Get a benchmark by ID."""
    return db.query(DiskBenchmark).filter(DiskBenchmark.id == benchmark_id).first()


def get_benchmark_history(
    db: Session,
    page: int = 1,
    page_size: int = 10,
    disk_name: Optional[str] = None,
) -> Tuple[List[DiskBenchmark], int]:
    """Get paginated benchmark history."""
    query = db.query(DiskBenchmark)

    if disk_name:
        query = query.filter(DiskBenchmark.disk_name == disk_name)

    total = query.count()
    benchmarks = (
        query.order_by(DiskBenchmark.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return benchmarks, total
