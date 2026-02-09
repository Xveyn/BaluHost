"""
Disk I/O metrics collector.

Collects disk read/write throughput and IOPS per physical disk.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Type

import psutil

from app.models.base import Base
from app.models.monitoring import DiskIoSample
from app.schemas.monitoring import DiskIoSampleSchema
from app.services.monitoring.base import MetricCollector

logger = logging.getLogger(__name__)


class DiskIoMetricCollector(MetricCollector[DiskIoSampleSchema]):
    """
    Collector for disk I/O metrics.

    Collects per-disk:
    - Read/write throughput (MB/s)
    - Read/write IOPS
    - Average response time (ms)
    - Active time percentage
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        super().__init__(
            metric_name="DiskIO",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        # Previous disk counters for rate calculation
        self._previous_counters: Optional[Dict] = None
        # Separate buffers per disk (disk_name -> List[sample])
        self._disk_buffers: Dict[str, List[DiskIoSampleSchema]] = {}

    def collect_sample(self) -> Optional[DiskIoSampleSchema]:
        """
        Collect disk I/O metrics sample.

        Note: This returns the first disk's sample for the base class interface.
        For all disks, use collect_all_samples().
        """
        samples = self.collect_all_samples()
        return samples[0] if samples else None

    def collect_all_samples(self) -> List[DiskIoSampleSchema]:
        """Collect disk I/O samples for all physical disks."""
        samples = []
        timestamp = datetime.utcnow()
        timestamp_seconds = time.time()

        try:
            current_counters = psutil.disk_io_counters(perdisk=True)
            if current_counters is None:
                logger.debug("Disk I/O counters not available")
                return samples

            if self._previous_counters is not None:
                time_delta = timestamp_seconds - self._previous_counters["timestamp"]

                if time_delta > 0:
                    for disk_name, counters in current_counters.items():
                        if not self._is_physical_disk(disk_name):
                            continue

                        prev_counters = self._previous_counters["counters"].get(disk_name)
                        if prev_counters is None:
                            continue

                        # Calculate throughput (MB/s)
                        read_bytes_delta = counters.read_bytes - prev_counters.read_bytes
                        write_bytes_delta = counters.write_bytes - prev_counters.write_bytes

                        read_mbps = round((read_bytes_delta / time_delta) / (1024 * 1024), 2)
                        write_mbps = round((write_bytes_delta / time_delta) / (1024 * 1024), 2)

                        # Calculate IOPS
                        read_ops_delta = counters.read_count - prev_counters.read_count
                        write_ops_delta = counters.write_count - prev_counters.write_count

                        read_iops = round(read_ops_delta / time_delta, 2)
                        write_iops = round(write_ops_delta / time_delta, 2)

                        # Calculate latency and active time
                        avg_response_ms = None
                        active_time_percent = None

                        try:
                            read_time_delta = max(
                                0, getattr(counters, "read_time", 0) - getattr(prev_counters, "read_time", 0)
                            )
                            write_time_delta = max(
                                0, getattr(counters, "write_time", 0) - getattr(prev_counters, "write_time", 0)
                            )
                            total_ops_delta = read_ops_delta + write_ops_delta
                            total_time_delta_ms = time_delta * 1000.0
                            cumulative_time_ms = read_time_delta + write_time_delta

                            if total_ops_delta > 0 and cumulative_time_ms > 0:
                                avg_response_ms = round(cumulative_time_ms / total_ops_delta, 2)

                            if total_time_delta_ms > 0:
                                active_time_percent = round(
                                    min(100.0, (cumulative_time_ms / total_time_delta_ms) * 100.0), 2
                                )
                        except Exception:
                            pass

                        sample = DiskIoSampleSchema(
                            timestamp=timestamp,
                            disk_name=disk_name,
                            read_mbps=max(0.0, read_mbps),
                            write_mbps=max(0.0, write_mbps),
                            read_iops=max(0.0, read_iops),
                            write_iops=max(0.0, write_iops),
                            avg_response_ms=avg_response_ms,
                            active_time_percent=active_time_percent,
                        )
                        samples.append(sample)

                        # Store in per-disk buffer
                        if disk_name not in self._disk_buffers:
                            self._disk_buffers[disk_name] = []
                        self._disk_buffers[disk_name].append(sample)
                        if len(self._disk_buffers[disk_name]) > self.buffer_size:
                            self._disk_buffers[disk_name].pop(0)

            # Update previous counters
            self._previous_counters = {
                "timestamp": timestamp_seconds,
                "counters": current_counters,
            }

        except Exception as e:
            logger.error(f"Error collecting disk I/O samples: {e}")

        return samples

    def _is_physical_disk(self, disk_name: str) -> bool:
        """
        Check if a disk is a physical disk (not a partition).

        On Windows: PhysicalDrive0, PhysicalDrive1, etc.
        On Linux: sda, sdb, nvme0n1, etc. (without partition numbers)
        Also includes software RAID (md0, md127) and LVM/Device-Mapper (dm-0, dm-1).
        """
        disk_lower = disk_name.lower()

        # Windows physical disks
        if "physicaldrive" in disk_lower:
            return True

        # Software RAID (md0, md127)
        if disk_lower.startswith("md") and disk_lower[2:].isdigit():
            return True

        # Device-Mapper / LVM (dm-0, dm-1)
        if disk_lower.startswith("dm-") and disk_lower[3:].isdigit():
            return True

        # Linux physical disks
        if disk_lower.startswith(("sd", "hd", "nvme", "vd")):
            # nvme drives: nvme0n1 is physical, nvme0n1p1 is partition
            if "nvme" in disk_lower:
                return "p" not in disk_lower or disk_lower.endswith("n1")
            # sda, sdb are physical; sda1, sdb2 are partitions
            return not re.search(r"\d+$", disk_name)

        return False

    def get_disk_history(self, disk_name: str) -> List[DiskIoSampleSchema]:
        """Get history for a specific disk."""
        return list(self._disk_buffers.get(disk_name, []))

    def get_all_disk_histories(self) -> Dict[str, List[DiskIoSampleSchema]]:
        """Get history for all disks."""
        return {name: list(samples) for name, samples in self._disk_buffers.items()}

    def get_available_disks(self) -> List[str]:
        """Get list of disks being monitored."""
        return list(self._disk_buffers.keys())

    def get_db_model(self) -> Type[Base]:
        """Get the DiskIoSample model class."""
        return DiskIoSample

    def sample_to_db_dict(self, sample: DiskIoSampleSchema) -> dict:
        """Convert schema to database dict."""
        return {
            "timestamp": sample.timestamp,
            "disk_name": sample.disk_name,
            "read_mbps": sample.read_mbps,
            "write_mbps": sample.write_mbps,
            "read_iops": sample.read_iops,
            "write_iops": sample.write_iops,
            "avg_response_ms": sample.avg_response_ms,
            "active_time_percent": sample.active_time_percent,
        }

    def db_to_sample(self, db_record: DiskIoSample) -> DiskIoSampleSchema:
        """Convert database record to schema."""
        return DiskIoSampleSchema(
            timestamp=db_record.timestamp,
            disk_name=db_record.disk_name,
            read_mbps=db_record.read_mbps,
            write_mbps=db_record.write_mbps,
            read_iops=db_record.read_iops,
            write_iops=db_record.write_iops,
            avg_response_ms=db_record.avg_response_ms,
            active_time_percent=db_record.active_time_percent,
        )

    def save_all_to_db(self, db, samples: List[DiskIoSampleSchema]) -> None:
        """Save multiple disk samples to database."""
        for sample in samples:
            self.save_to_db(db, sample)
