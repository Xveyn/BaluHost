"""
Production benchmark backend using fio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.benchmark import (
    BenchmarkStatus,
    BenchmarkTargetType,
    BenchmarkTestResult,
    DiskBenchmark,
)
from app.schemas.benchmark import (
    BenchmarkProfileConfig,
    BenchmarkTestConfig,
    DiskInfo,
)

from .state import (
    _FIO_TIMEOUT_SECONDS,
    _cancellation_flags,
    _format_size,
    _get_fio_path,
    _is_system_disk,
)

logger = logging.getLogger(__name__)


class FioBenchmarkBackend:
    """Production benchmark backend using fio."""

    def __init__(self):
        self.fio_path = _get_fio_path()

    def get_available_disks(self) -> List[DiskInfo]:
        """Get list of available disks from the system."""
        disks: List[DiskInfo] = []

        try:
            import psutil

            # Get disk partitions
            partitions = psutil.disk_partitions(all=False)
            seen_devices = set()

            for partition in partitions:
                device = partition.device

                # Extract base device name (e.g., /dev/sda1 -> sda)
                if platform.system().lower() == "linux":
                    base_device = os.path.basename(device).rstrip("0123456789")
                    device_path = f"/dev/{base_device}"
                else:
                    base_device = device
                    device_path = device

                if base_device in seen_devices:
                    continue
                seen_devices.add(base_device)

                # Get disk size
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    size_bytes = usage.total
                except Exception:
                    size_bytes = 0

                # Check if system disk
                is_system = _is_system_disk(base_device, partition.mountpoint)

                # Check if RAID member
                is_raid = self._is_raid_member(device_path)

                disks.append(
                    DiskInfo(
                        name=base_device,
                        model=self._get_disk_model(device_path),
                        size_bytes=size_bytes,
                        size_display=_format_size(size_bytes),
                        mount_point=partition.mountpoint,
                        filesystem=partition.fstype,
                        is_system_disk=is_system,
                        is_raid_member=is_raid,
                        can_benchmark=not is_system,
                        warning="System disk - benchmarking not recommended" if is_system else None,
                    )
                )

        except ImportError:
            logger.warning("psutil not available, returning empty disk list")
        except Exception as e:
            logger.error(f"Error getting available disks: {e}")

        return disks

    def _get_disk_model(self, device_path: str) -> Optional[str]:
        """Get disk model from system."""
        try:
            # Try to get from /sys on Linux
            if platform.system().lower() == "linux":
                base_name = os.path.basename(device_path)
                model_path = f"/sys/block/{base_name}/device/model"
                if os.path.exists(model_path):
                    with open(model_path, "r") as f:
                        return f.read().strip()
        except Exception:
            pass
        return None

    def _is_raid_member(self, device_path: str) -> bool:
        """Check if device is part of a RAID array."""
        try:
            if platform.system().lower() == "linux":
                # Check /proc/mdstat
                if os.path.exists("/proc/mdstat"):
                    with open("/proc/mdstat", "r") as f:
                        content = f.read()
                        base_name = os.path.basename(device_path)
                        if base_name in content:
                            return True
        except Exception:
            pass
        return False

    async def run_benchmark(
        self,
        benchmark: DiskBenchmark,
        profile_config: BenchmarkProfileConfig,
        db: Session,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Run benchmark using fio."""
        if not self.fio_path:
            raise RuntimeError("fio is not installed or not found in PATH")

        logger.info(
            f"FIO benchmark started: disk={benchmark.disk_name}, profile={benchmark.profile.value}"
        )

        # Determine test file path
        if benchmark.target_type == BenchmarkTargetType.TEST_FILE:
            test_file = self._get_test_file_path(benchmark)
            benchmark.test_file_path = test_file
        else:
            test_file = f"/dev/{benchmark.disk_name}"

        benchmark.test_file_size_bytes = profile_config.test_file_size_bytes
        db.commit()

        total_tests = sum(len(test.operations) for test in profile_config.tests)
        completed_tests = 0

        try:
            for test_config in profile_config.tests:
                for operation in test_config.operations:
                    # Check for cancellation
                    if _cancellation_flags.get(benchmark.id, False):
                        benchmark.status = BenchmarkStatus.CANCELLED
                        db.commit()
                        self._cleanup_test_file(benchmark)
                        logger.info(f"Benchmark {benchmark.id} cancelled")
                        return

                    test_name = f"{test_config.name}_{operation}"
                    benchmark.current_test = test_name

                    if progress_callback:
                        progress = (completed_tests / total_tests) * 100
                        progress_callback(progress, test_name)

                    benchmark.progress_percent = (completed_tests / total_tests) * 100
                    db.commit()

                    # Run fio test
                    result = await self._run_fio_test(
                        benchmark.id,
                        test_file,
                        test_config,
                        operation,
                        profile_config.test_file_size_bytes,
                    )

                    if result:
                        db.add(result)
                        db.commit()

                        # Update summary fields
                        self._update_summary_from_result(
                            benchmark, test_config.name, operation, result
                        )

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

            logger.info(f"FIO benchmark {benchmark.id} completed successfully")

        except Exception as e:
            logger.exception(f"FIO benchmark {benchmark.id} failed: {e}")
            benchmark.status = BenchmarkStatus.FAILED
            benchmark.error_message = str(e)
            db.commit()
            raise
        finally:
            # Cleanup test file
            self._cleanup_test_file(benchmark)

    def _get_test_file_path(self, benchmark: DiskBenchmark) -> str:
        """Get path for test file."""
        # Use temp directory on the target disk's mount point
        # For now, use system temp with benchmark ID
        temp_dir = tempfile.gettempdir()
        return os.path.join(temp_dir, f"baluhost_benchmark_{benchmark.id}.bin")

    def _cleanup_test_file(self, benchmark: DiskBenchmark) -> None:
        """Remove test file after benchmark."""
        if benchmark.test_file_path and os.path.exists(benchmark.test_file_path):
            try:
                os.remove(benchmark.test_file_path)
                logger.debug(f"Cleaned up test file: {benchmark.test_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup test file: {e}")

    async def _run_fio_test(
        self,
        benchmark_id: int,
        test_file: str,
        test_config: BenchmarkTestConfig,
        operation: str,
        file_size: int,
    ) -> Optional[BenchmarkTestResult]:
        """Run a single fio test and parse results."""
        # Build fio command
        rw_mode = "read" if operation == "read" else "write"
        if "RND" in test_config.name:
            rw_mode = f"rand{rw_mode}"

        cmd = [
            self.fio_path,
            f"--filename={test_file}",
            f"--size={file_size}",
            "--direct=1",
            f"--rw={rw_mode}",
            f"--bs={test_config.block_size}",
            "--ioengine=libaio",
            f"--iodepth={test_config.queue_depth}",
            f"--runtime={test_config.runtime_seconds}",
            f"--numjobs={test_config.num_jobs}",
            "--time_based",
            "--group_reporting",
            f"--name={test_config.name}_{operation}",
            "--output-format=json",
        ]

        logger.debug(f"Running fio command: {' '.join(cmd)}")

        try:
            # Run fio asynchronously using create_subprocess_exec (safe, no shell)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=_FIO_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"fio test timed out after {_FIO_TIMEOUT_SECONDS}s "
                    f"(benchmark={benchmark_id}, test={test_config.name}_{operation})"
                )
                process.kill()
                await process.wait()
                return None

            if process.returncode != 0:
                logger.error(f"fio failed: {stderr.decode()}")
                return None

            # Parse JSON output
            fio_output = json.loads(stdout.decode())
            return self._parse_fio_result(
                benchmark_id, test_config, operation, fio_output
            )

        except asyncio.TimeoutError:
            raise  # Already handled above
        except Exception as e:
            logger.error(f"Error running fio test: {e}")
            return None

    def _parse_fio_result(
        self,
        benchmark_id: int,
        test_config: BenchmarkTestConfig,
        operation: str,
        fio_output: Dict[str, Any],
    ) -> BenchmarkTestResult:
        """Parse fio JSON output into BenchmarkTestResult."""
        jobs = fio_output.get("jobs", [])
        if not jobs:
            raise ValueError("No job results in fio output")

        job = jobs[0]
        op_data = job.get(operation, {})

        # Extract metrics
        bw_bytes = op_data.get("bw_bytes", 0)
        throughput_mbps = bw_bytes / (1024 * 1024)
        iops = op_data.get("iops", 0)

        # Latency (in nanoseconds, convert to microseconds)
        lat_ns = op_data.get("lat_ns", {})
        latency_avg = lat_ns.get("mean", 0) / 1000
        latency_min = lat_ns.get("min", 0) / 1000
        latency_max = lat_ns.get("max", 0) / 1000

        # Percentiles
        percentile = lat_ns.get("percentile", {})
        latency_p99 = percentile.get("99.000000", 0) / 1000
        latency_p95 = percentile.get("95.000000", 0) / 1000
        latency_p50 = percentile.get("50.000000", 0) / 1000

        return BenchmarkTestResult(
            benchmark_id=benchmark_id,
            test_name=test_config.name,
            operation=operation,
            block_size=test_config.block_size,
            queue_depth=test_config.queue_depth,
            num_jobs=test_config.num_jobs,
            throughput_mbps=round(throughput_mbps, 2),
            iops=round(iops, 2),
            latency_avg_us=round(latency_avg, 2),
            latency_min_us=round(latency_min, 2),
            latency_max_us=round(latency_max, 2),
            latency_p99_us=round(latency_p99, 2),
            latency_p95_us=round(latency_p95, 2),
            latency_p50_us=round(latency_p50, 2),
            bandwidth_bytes=int(op_data.get("io_bytes", 0)),
            runtime_ms=int(op_data.get("runtime", 0)),
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
