"""Disk I/O monitoring service with real-time tracking and logging."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional

import psutil

from app.core.config import settings
from app.services.audit_logger_db import get_audit_logger_db


def get_audit_logger():
    """Compatibility wrapper used by tests to patch audit logger retrieval."""
    return get_audit_logger_db()

logger = logging.getLogger(__name__)

# Configuration
_SAMPLE_INTERVAL_SECONDS = 1.0  # Sample every second for real-time monitoring
_MAX_SAMPLES = 120  # Keep 2 minutes of history
_LOG_INTERVAL_SECONDS = 60.0  # Log summary every minute

# Storage for disk I/O history
_disk_io_history: Dict[str, List[Dict]] = defaultdict(list)
_previous_disk_io: Optional[Dict] = None
_monitor_task: Optional[asyncio.Task] = None
_lock = Lock()


class DiskIOSample:
    """Represents a single disk I/O sample."""
    
    def __init__(self, disk_name: str, timestamp_ms: int, read_mbps: float, write_mbps: float,
                 read_iops: float, write_iops: float):
        self.disk_name = disk_name
        self.timestamp_ms = timestamp_ms
        self.read_mbps = read_mbps
        self.write_mbps = write_mbps
        self.read_iops = read_iops
        self.write_iops = write_iops


def _push_sample(disk_name: str, sample: Dict) -> None:
    """Add a sample to the history and maintain max size."""
    _disk_io_history[disk_name].append(sample)
    if len(_disk_io_history[disk_name]) > _MAX_SAMPLES:
        _disk_io_history[disk_name].pop(0)


def _round(value: float) -> float:
    """Round to 2 decimal places."""
    return round(value, 2)


def _sample_disk_io() -> None:
    """Sample disk I/O statistics for all physical disks."""
    global _previous_disk_io
    
    timestamp_seconds = time.time()
    timestamp_ms = int(timestamp_seconds * 1000)
    
    try:
        # Get current disk I/O counters
        current_disk_io = psutil.disk_io_counters(perdisk=True)
        
        if current_disk_io is None:
            logger.debug("Disk I/O counters not available")
            return
        
        # Calculate rates if we have previous data
        if _previous_disk_io is not None:
            time_delta = timestamp_seconds - _previous_disk_io['timestamp']
            
            if time_delta > 0:
                for disk_name, counters in current_disk_io.items():
                    # Skip if not a physical disk (filter out partitions on Windows)
                    if not _is_physical_disk(disk_name):
                        continue
                    
                    prev_counters = _previous_disk_io['counters'].get(disk_name)
                    
                    if prev_counters:
                        # Calculate bytes per second
                        read_bytes_delta = counters.read_bytes - prev_counters.read_bytes
                        write_bytes_delta = counters.write_bytes - prev_counters.write_bytes
                        
                        read_mbps = _round((read_bytes_delta / time_delta) / (1024 * 1024))
                        write_mbps = _round((write_bytes_delta / time_delta) / (1024 * 1024))
                        
                        # Calculate IOPS (operations per second)
                        read_ops_delta = counters.read_count - prev_counters.read_count
                        write_ops_delta = counters.write_count - prev_counters.write_count
                        
                        read_iops = _round(read_ops_delta / time_delta)
                        write_iops = _round(write_ops_delta / time_delta)

                        # Average response time (latency) approximation
                        # psutil.disk_io_counters provides cumulative read_time/write_time (ms spent doing I/O)
                        avg_response_ms = 0.0
                        active_time_percent = None
                        try:
                            read_time_delta = max(0, getattr(counters, 'read_time', 0) - getattr(prev_counters, 'read_time', 0))
                            write_time_delta = max(0, getattr(counters, 'write_time', 0) - getattr(prev_counters, 'write_time', 0))
                            total_ops_delta = read_ops_delta + write_ops_delta
                            total_time_delta_ms = time_delta * 1000.0
                            cumulative_time_ms = read_time_delta + write_time_delta
                            if total_ops_delta > 0 and cumulative_time_ms > 0:
                                avg_response_ms = _round(cumulative_time_ms / total_ops_delta)
                            # Active Time (%) ~ fraction of interval the disk was busy
                            if total_time_delta_ms > 0:
                                active_time_percent = _round(min(100.0, (cumulative_time_ms / total_time_delta_ms) * 100.0))
                        except Exception:
                            avg_response_ms = 0.0
                            active_time_percent = None
                        
                        sample = {
                            'timestamp': timestamp_ms,
                            'readMbps': max(0.0, read_mbps),
                            'writeMbps': max(0.0, write_mbps),
                            'readIops': max(0.0, read_iops),
                            'writeIops': max(0.0, write_iops),
                            'avgResponseMs': avg_response_ms,
                            'activeTimePercent': active_time_percent,
                        }
                        
                        with _lock:
                            _push_sample(disk_name, sample)
        
        # Store current counters for next iteration
        _previous_disk_io = {
            'timestamp': timestamp_seconds,
            'counters': current_disk_io
        }
        
    except Exception as exc:
        logger.error(f"Error sampling disk I/O: {exc}")
        audit = get_audit_logger()
        audit.log_disk_monitor(
            action="sampling_error",
            success=False,
            error_message=str(exc)
        )


def _is_physical_disk(disk_name: str) -> bool:
    """
    Determine if a disk is a physical disk (not a partition).
    On Windows: PhysicalDrive0, PhysicalDrive1, etc.
    On Linux: sda, sdb, nvme0n1, etc. (without partition numbers)
    """
    disk_lower = disk_name.lower()
    
    # Windows physical disks
    if 'physicaldrive' in disk_lower:
        return True
    
    # Linux physical disks (exclude partitions like sda1, nvme0n1p1)
    if disk_lower.startswith(('sd', 'hd', 'nvme', 'vd')):
        # Exclude if it ends with a digit (partition)
        import re
        # nvme drives: nvme0n1 is physical, nvme0n1p1 is partition
        if 'nvme' in disk_lower:
            return 'p' not in disk_lower or disk_lower.endswith('n1')
        # sda, sdb are physical; sda1, sdb2 are partitions
        return not re.search(r'\d+$', disk_name)
    
    return False


def _log_disk_activity() -> None:
    """Log a summary of disk activity."""
    audit = get_audit_logger()
    
    with _lock:
        if not _disk_io_history:
            logger.info("Disk Activity Log: No data available")
            return
        
        log_entries = []
        disk_stats = {}
        
        for disk_name, samples in _disk_io_history.items():
            if not samples:
                continue
            
            # Calculate averages for the last minute
            recent_samples = samples[-60:]  # Last 60 seconds
            
            avg_read = sum(s['readMbps'] for s in recent_samples) / len(recent_samples)
            avg_write = sum(s['writeMbps'] for s in recent_samples) / len(recent_samples)
            avg_read_iops = sum(s['readIops'] for s in recent_samples) / len(recent_samples)
            avg_write_iops = sum(s['writeIops'] for s in recent_samples) / len(recent_samples)
            
            max_read = max(s['readMbps'] for s in recent_samples)
            max_write = max(s['writeMbps'] for s in recent_samples)
            
            log_entries.append(
                f"{disk_name}: Read={avg_read:.2f}MB/s (max {max_read:.2f}), "
                f"Write={avg_write:.2f}MB/s (max {max_write:.2f}), "
                f"IOPS R={avg_read_iops:.0f}/W={avg_write_iops:.0f}"
            )
            
            disk_stats[disk_name] = {
                "avg_read_mbps": round(avg_read, 2),
                "avg_write_mbps": round(avg_write, 2),
                "max_read_mbps": round(max_read, 2),
                "max_write_mbps": round(max_write, 2),
                "avg_read_iops": round(avg_read_iops, 0),
                "avg_write_iops": round(avg_write_iops, 0)
            }
        
        logger.info("Disk Activity Log (last 60s):\n  " + "\n  ".join(log_entries))
        
        # Log to audit system
        audit.log_disk_monitor(
            action="periodic_summary",
            details={"disks": disk_stats, "interval_seconds": 60}
        )


async def _monitor_loop() -> None:
    """Main monitoring loop for disk I/O."""
    audit = get_audit_logger()
    
    logger.info("Starting disk I/O monitor...")
    audit.log_disk_monitor(action="monitor_started")
    
    last_log_time = time.time()
    
    while True:
        try:
            _sample_disk_io()
            
            # Log summary periodically
            current_time = time.time()
            if current_time - last_log_time >= _LOG_INTERVAL_SECONDS:
                _log_disk_activity()
                last_log_time = current_time
            
            await asyncio.sleep(_SAMPLE_INTERVAL_SECONDS)
            
        except asyncio.CancelledError:
            logger.info("Disk I/O monitor stopped")
            audit.log_disk_monitor(action="monitor_stopped")
            break
        except Exception as exc:
            logger.error(f"Error in disk I/O monitor loop: {exc}")
            audit.log_disk_monitor(
                action="monitor_error",
                success=False,
                error_message=str(exc)
            )
            await asyncio.sleep(_SAMPLE_INTERVAL_SECONDS)


def start_monitoring() -> None:
    """Start the disk I/O monitoring background task."""
    global _monitor_task
    audit = get_audit_logger()
    
    if _monitor_task is not None:
        logger.warning("Disk I/O monitor already running")
        return
    
    try:
        loop = asyncio.get_event_loop()
        _monitor_task = loop.create_task(_monitor_loop())
        logger.info("Disk I/O monitoring task started")
    except Exception as exc:
        logger.error(f"Failed to start disk I/O monitor: {exc}")
        audit.log_disk_monitor(
            action="start_failed",
            success=False,
            error_message=str(exc)
        )


def stop_monitoring() -> None:
    """Stop the disk I/O monitoring background task."""
    global _monitor_task
    audit = get_audit_logger()
    
    if _monitor_task is None:
        return
    
    _monitor_task.cancel()
    _monitor_task = None
    logger.info("Disk I/O monitoring task cancelled")
    audit.log_disk_monitor(action="monitor_stopped_manually")


def get_disk_io_history() -> Dict[str, List[Dict]]:
    """Get the complete disk I/O history for all disks."""
    with _lock:
        return {disk: list(samples) for disk, samples in _disk_io_history.items()}


def get_available_disks() -> List[str]:
    """Get list of all physical disks being monitored."""
    with _lock:
        return list(_disk_io_history.keys())


def get_latest_disk_io() -> Dict[str, Optional[Dict]]:
    """Get the latest I/O sample for each disk."""
    with _lock:
        return {
            disk: samples[-1] if samples else None
            for disk, samples in _disk_io_history.items()
        }
