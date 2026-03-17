"""
Development mode benchmark backend with simulated results.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.models.benchmark import (
    BenchmarkStatus,
    BenchmarkTestResult,
    DiskBenchmark,
)
from app.schemas.benchmark import (
    BenchmarkProfileConfig,
    BenchmarkTestConfig,
    DiskInfo,
)

from .state import _cancellation_flags

logger = logging.getLogger(__name__)


class DevBenchmarkBackend:
    """Development mode benchmark backend with simulated results."""

    def get_available_disks(self) -> List[DiskInfo]:
        """Return mock disks for development mode."""
        return [
            DiskInfo(
                name="sda",
                model="BaluHost Dev Disk 5GB (Mirror A)",
                size_bytes=5 * 1024 * 1024 * 1024,
                size_display="5.0 GB",
                mount_point="/mnt/pool1",
                filesystem="ext4",
                is_system_disk=False,
                is_raid_member=True,
                can_benchmark=True,
                warning=None,
            ),
            DiskInfo(
                name="sdb",
                model="BaluHost Dev Disk 5GB (Mirror B)",
                size_bytes=5 * 1024 * 1024 * 1024,
                size_display="5.0 GB",
                mount_point="/mnt/pool1",
                filesystem="ext4",
                is_system_disk=False,
                is_raid_member=True,
                can_benchmark=True,
                warning=None,
            ),
            DiskInfo(
                name="sdc",
                model="BaluHost Dev Disk 10GB (Backup)",
                size_bytes=10 * 1024 * 1024 * 1024,
                size_display="10.0 GB",
                mount_point="/mnt/backup",
                filesystem="ext4",
                is_system_disk=False,
                is_raid_member=False,
                can_benchmark=True,
                warning=None,
            ),
            DiskInfo(
                name="nvme0n1",
                model="BaluHost Dev NVMe 256GB",
                size_bytes=256 * 1024 * 1024 * 1024,
                size_display="256.0 GB",
                mount_point="/",
                filesystem="ext4",
                is_system_disk=True,
                is_raid_member=False,
                can_benchmark=False,
                warning="System disk - benchmarking not recommended",
            ),
        ]

    async def run_benchmark(
        self,
        benchmark: DiskBenchmark,
        profile_config: BenchmarkProfileConfig,
        db: Session,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Simulate a benchmark run with realistic delays and fake results."""
        logger.info(
            f"Dev benchmark started: disk={benchmark.disk_name}, profile={benchmark.profile.value}"
        )

        # Simulated performance characteristics based on disk type
        is_nvme = "nvme" in benchmark.disk_name.lower()
        base_seq_read = 3500 if is_nvme else 550
        base_seq_write = 3000 if is_nvme else 520
        base_rand_iops = 500000 if is_nvme else 95000

        total_tests = sum(
            len(test.operations) for test in profile_config.tests
        )
        completed_tests = 0

        try:
            for test_config in profile_config.tests:
                for operation in test_config.operations:
                    # Check for cancellation
                    if _cancellation_flags.get(benchmark.id, False):
                        benchmark.status = BenchmarkStatus.CANCELLED
                        db.commit()
                        logger.info(f"Benchmark {benchmark.id} cancelled")
                        return

                    test_name = f"{test_config.name}_{operation}"
                    benchmark.current_test = test_name

                    if progress_callback:
                        progress = (completed_tests / total_tests) * 100
                        progress_callback(progress, test_name)

                    benchmark.progress_percent = (completed_tests / total_tests) * 100
                    db.commit()

                    # Simulate test duration (shorter in dev mode)
                    await asyncio.sleep(min(test_config.runtime_seconds / 10, 2))

                    # Generate simulated results
                    result = self._generate_mock_result(
                        benchmark.id,
                        test_config,
                        operation,
                        base_seq_read,
                        base_seq_write,
                        base_rand_iops,
                    )
                    db.add(result)
                    db.commit()

                    # Update summary fields
                    self._update_summary_from_result(benchmark, test_config.name, operation, result)

                    completed_tests += 1

            # Finalize benchmark
            benchmark.status = BenchmarkStatus.COMPLETED
            benchmark.progress_percent = 100.0
            benchmark.current_test = None
            now = datetime.now(timezone.utc)
            benchmark.completed_at = now
            if benchmark.started_at:
                benchmark.duration_seconds = (
                    now - benchmark.started_at
                ).total_seconds()
            db.commit()

            logger.info(f"Dev benchmark {benchmark.id} completed successfully")

        except Exception as e:
            logger.exception(f"Dev benchmark {benchmark.id} failed: {e}")
            benchmark.status = BenchmarkStatus.FAILED
            benchmark.error_message = str(e)
            db.commit()
            raise

    def _generate_mock_result(
        self,
        benchmark_id: int,
        test_config: BenchmarkTestConfig,
        operation: str,
        base_seq_read: float,
        base_seq_write: float,
        base_rand_iops: float,
    ) -> BenchmarkTestResult:
        """Generate realistic mock benchmark results."""
        import random

        # Add some variance
        variance = random.uniform(0.9, 1.1)

        is_read = operation == "read"
        is_sequential = test_config.block_size in ["1m", "128k"]

        if is_sequential:
            base_mbps = base_seq_read if is_read else base_seq_write
            # Queue depth affects throughput
            qd_factor = min(1.0, 0.6 + (test_config.queue_depth / 16) * 0.4)
            throughput = base_mbps * variance * qd_factor
            iops = throughput * 1024 / int(test_config.block_size.rstrip("mk")) if "k" in test_config.block_size else throughput
        else:
            # Random 4K
            base_iops = base_rand_iops if is_read else base_rand_iops * 0.8
            qd_factor = min(1.0, 0.2 + (test_config.queue_depth / 64) * 0.8)
            iops = base_iops * variance * qd_factor
            throughput = (iops * 4) / 1024  # 4KB blocks to MB/s

        # Latency calculations (inverse relationship with queue depth for single operations)
        base_latency = 80 if "nvme" in str(benchmark_id) else 5000  # microseconds
        if test_config.queue_depth == 1:
            latency_avg = base_latency * variance
        else:
            latency_avg = base_latency * test_config.queue_depth * variance * 0.5

        return BenchmarkTestResult(
            benchmark_id=benchmark_id,
            test_name=test_config.name,
            operation=operation,
            block_size=test_config.block_size,
            queue_depth=test_config.queue_depth,
            num_jobs=test_config.num_jobs,
            throughput_mbps=round(throughput, 2),
            iops=round(iops, 2),
            latency_avg_us=round(latency_avg, 2),
            latency_min_us=round(latency_avg * 0.5, 2),
            latency_max_us=round(latency_avg * 3.0, 2),
            latency_p99_us=round(latency_avg * 2.5, 2),
            latency_p95_us=round(latency_avg * 2.0, 2),
            latency_p50_us=round(latency_avg * 0.8, 2),
            bandwidth_bytes=int(throughput * 1024 * 1024 * test_config.runtime_seconds),
            runtime_ms=test_config.runtime_seconds * 1000,
            completed_at=datetime.now(timezone.utc),
        )

    def _update_summary_from_result(
        self,
        benchmark: DiskBenchmark,
        test_name: str,
        operation: str,
        result: BenchmarkTestResult,
    ) -> None:
        """Update benchmark summary fields based on test result."""
        if test_name == "SEQ1M_Q8T1":
            if operation == "read":
                benchmark.seq_read_mbps = result.throughput_mbps
            else:
                benchmark.seq_write_mbps = result.throughput_mbps
        elif test_name == "SEQ1M_Q1T1":
            if operation == "read":
                benchmark.seq_read_q1_mbps = result.throughput_mbps
            else:
                benchmark.seq_write_q1_mbps = result.throughput_mbps
        elif test_name == "RND4K_Q32T1":
            if operation == "read":
                benchmark.rand_read_iops = result.iops
            else:
                benchmark.rand_write_iops = result.iops
        elif test_name == "RND4K_Q1T1":
            if operation == "read":
                benchmark.rand_read_q1_iops = result.iops
            else:
                benchmark.rand_write_q1_iops = result.iops

    def cancel_benchmark(self, benchmark_id: int) -> bool:
        """Request cancellation of a running benchmark."""
        _cancellation_flags[benchmark_id] = True
        return True
