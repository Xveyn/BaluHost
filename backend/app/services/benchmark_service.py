"""
Disk Benchmark Service.

Provides CrystalDiskMark-style disk performance benchmarks using fio.
Supports both production (real fio) and development (simulated) modes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import secrets
import signal
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.benchmark import (
    BenchmarkProfile,
    BenchmarkStatus,
    BenchmarkTargetType,
    BenchmarkTestResult,
    DiskBenchmark,
)
from app.schemas.benchmark import (
    BENCHMARK_PROFILES,
    BenchmarkProfileConfig,
    BenchmarkTestConfig,
    DiskInfo,
)

logger = logging.getLogger(__name__)

# Active benchmarks tracking (for cancellation)
_active_benchmarks: Dict[int, asyncio.Task] = {}
_cancellation_flags: Dict[int, bool] = {}

# Raw device confirmation tokens (token -> (disk_name, profile, expires_at))
_confirmation_tokens: Dict[str, Tuple[str, str, datetime]] = {}
_TOKEN_EXPIRY_MINUTES = 5

# Timeout for a single fio test (10 minutes)
_FIO_TIMEOUT_SECONDS = 600


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
                os.kill(pid, signal.SIGKILL)
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


class BenchmarkBackend(Protocol):
    """Protocol for benchmark backends."""

    def get_available_disks(self) -> List[DiskInfo]:
        """Get list of available disks for benchmarking."""
        ...

    async def run_benchmark(
        self,
        benchmark: DiskBenchmark,
        profile_config: BenchmarkProfileConfig,
        db: Session,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Run the benchmark and update results in database."""
        ...

    def cancel_benchmark(self, benchmark_id: int) -> bool:
        """Request cancellation of a running benchmark."""
        ...


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


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
            benchmark.completed_at = datetime.now(timezone.utc)
            if benchmark.started_at:
                benchmark.duration_seconds = (
                    benchmark.completed_at - benchmark.started_at
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
            benchmark.completed_at = datetime.now(timezone.utc)
            if benchmark.started_at:
                benchmark.duration_seconds = (
                    benchmark.completed_at - benchmark.started_at
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
            # Run fio asynchronously
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


# Singleton backend instance
_benchmark_backend: Optional[BenchmarkBackend] = None


class FioNotFoundError(RuntimeError):
    """Raised when fio is required but not installed."""


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


def generate_confirmation_token(disk_name: str, profile: str) -> Tuple[str, datetime]:
    """Generate a confirmation token for raw device benchmark."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRY_MINUTES)
    _confirmation_tokens[token] = (disk_name, profile, expires_at)

    # Clean up expired tokens
    now = datetime.now(timezone.utc)
    expired = [t for t, (_, _, exp) in _confirmation_tokens.items() if exp < now]
    for t in expired:
        del _confirmation_tokens[t]

    return token, expires_at


def validate_confirmation_token(token: str, disk_name: str, profile: str) -> bool:
    """Validate a confirmation token for raw device benchmark."""
    if token not in _confirmation_tokens:
        return False

    stored_disk, stored_profile, expires_at = _confirmation_tokens[token]

    if datetime.now(timezone.utc) > expires_at:
        del _confirmation_tokens[token]
        return False

    if stored_disk != disk_name or stored_profile != profile:
        return False

    # Token is valid, remove it (one-time use)
    del _confirmation_tokens[token]
    return True


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
