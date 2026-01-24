"""
Process tracker for BaluHost-related processes.

Tracks backend (uvicorn), frontend (node), and other BaluHost processes
for historical analysis and crash detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional, Type

import psutil

from app.models.base import Base
from app.models.monitoring import ProcessSample
from app.schemas.monitoring import ProcessSampleSchema
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Process patterns to track
BALUHOST_PROCESS_PATTERNS = [
    {"name": "baluhost-backend", "patterns": ["uvicorn", "app.main"]},
    {"name": "baluhost-frontend", "patterns": ["node", "vite"]},
    {"name": "baluhost-tui", "patterns": ["baluhost-tui", "baluhost_tui"]},
]


class ProcessTracker:
    """
    Tracks BaluHost-related processes.

    Features:
    - Identifies and tracks backend, frontend, TUI processes
    - Records CPU and memory usage per process
    - Detects process crashes (process disappears)
    - Stores history in database for analysis
    """

    def __init__(self, buffer_size: int = 60):
        """
        Initialize the process tracker.

        Args:
            buffer_size: Number of samples to keep in memory per process
        """
        self.buffer_size = buffer_size
        self._process_buffers: Dict[str, List[ProcessSampleSchema]] = {}
        self._known_pids: Dict[str, int] = {}  # process_name -> last known PID
        self._lock = Lock()

    def collect_samples(self) -> List[ProcessSampleSchema]:
        """
        Collect samples for all BaluHost processes.

        Returns:
            List of process samples
        """
        samples = []
        timestamp = datetime.utcnow()

        for process_def in BALUHOST_PROCESS_PATTERNS:
            process_name = process_def["name"]
            patterns = process_def["patterns"]

            # Find matching processes
            matching_procs = self._find_processes(patterns)

            if matching_procs:
                for proc_info in matching_procs:
                    sample = ProcessSampleSchema(
                        timestamp=timestamp,
                        process_name=process_name,
                        pid=proc_info["pid"],
                        cpu_percent=round(proc_info["cpu_percent"], 2),
                        memory_mb=round(proc_info["memory_mb"], 2),
                        status=proc_info["status"],
                        is_alive=True,
                    )
                    samples.append(sample)

                    # Store in buffer
                    with self._lock:
                        if process_name not in self._process_buffers:
                            self._process_buffers[process_name] = []
                        self._process_buffers[process_name].append(sample)
                        if len(self._process_buffers[process_name]) > self.buffer_size:
                            self._process_buffers[process_name].pop(0)

                        # Track PID for crash detection
                        self._known_pids[process_name] = proc_info["pid"]
            else:
                # Process not found - check if it crashed
                with self._lock:
                    if process_name in self._known_pids:
                        # Was running before, now gone = crash or stop
                        sample = ProcessSampleSchema(
                            timestamp=timestamp,
                            process_name=process_name,
                            pid=self._known_pids[process_name],
                            cpu_percent=0.0,
                            memory_mb=0.0,
                            status="stopped",
                            is_alive=False,
                        )
                        samples.append(sample)

                        if process_name not in self._process_buffers:
                            self._process_buffers[process_name] = []
                        self._process_buffers[process_name].append(sample)
                        if len(self._process_buffers[process_name]) > self.buffer_size:
                            self._process_buffers[process_name].pop(0)

                        logger.warning(f"Process '{process_name}' (PID {self._known_pids[process_name]}) stopped or crashed")
                        del self._known_pids[process_name]

        return samples

    def _find_processes(self, patterns: List[str]) -> List[Dict]:
        """
        Find processes matching the given patterns.

        Args:
            patterns: List of substrings to match in process name or cmdline

        Returns:
            List of process info dicts
        """
        matching = []

        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info", "status"]):
                try:
                    proc_info = proc.info
                    name = proc_info.get("name", "").lower()
                    cmdline = " ".join(proc_info.get("cmdline") or []).lower()

                    # Check if any pattern matches
                    if any(p.lower() in name or p.lower() in cmdline for p in patterns):
                        memory_mb = 0.0
                        if proc_info.get("memory_info"):
                            memory_mb = proc_info["memory_info"].rss / (1024 * 1024)

                        matching.append({
                            "pid": proc_info["pid"],
                            "cpu_percent": proc_info.get("cpu_percent", 0.0) or 0.0,
                            "memory_mb": memory_mb,
                            "status": proc_info.get("status", "unknown"),
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"Error finding processes: {e}")

        return matching

    def get_process_history(self, process_name: str) -> List[ProcessSampleSchema]:
        """Get history for a specific process."""
        with self._lock:
            return list(self._process_buffers.get(process_name, []))

    def get_all_histories(self) -> Dict[str, List[ProcessSampleSchema]]:
        """Get history for all tracked processes."""
        with self._lock:
            return {name: list(samples) for name, samples in self._process_buffers.items()}

    def get_current_status(self) -> Dict[str, Optional[ProcessSampleSchema]]:
        """Get current status of all tracked processes."""
        with self._lock:
            status = {}
            for name, samples in self._process_buffers.items():
                status[name] = samples[-1] if samples else None
            return status

    def detect_crashes(self, since: timedelta = timedelta(minutes=5)) -> List[ProcessSampleSchema]:
        """
        Detect process crashes in the given time window.

        Args:
            since: How far back to look for crashes

        Returns:
            List of crash samples (is_alive=False)
        """
        crashes = []
        cutoff = datetime.utcnow() - since

        with self._lock:
            for process_name, samples in self._process_buffers.items():
                for sample in samples:
                    if sample.timestamp >= cutoff and not sample.is_alive:
                        crashes.append(sample)

        return crashes

    def save_samples_to_db(self, db: Session, samples: List[ProcessSampleSchema]) -> None:
        """Save process samples to database."""
        try:
            for sample in samples:
                db_record = ProcessSample(
                    timestamp=sample.timestamp,
                    process_name=sample.process_name,
                    pid=sample.pid,
                    cpu_percent=sample.cpu_percent,
                    memory_mb=sample.memory_mb,
                    status=sample.status,
                    is_alive=sample.is_alive,
                )
                db.add(db_record)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to save process samples to DB: {e}")
            db.rollback()

    def get_history_db(
        self,
        db: Session,
        process_name: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[ProcessSampleSchema]:
        """
        Get process history from database.

        Args:
            db: Database session
            process_name: Filter by process name (optional)
            start: Start timestamp (inclusive)
            end: End timestamp (inclusive)
            limit: Maximum number of samples

        Returns:
            List of process samples
        """
        try:
            query = db.query(ProcessSample)

            if process_name:
                query = query.filter(ProcessSample.process_name == process_name)
            if start:
                query = query.filter(ProcessSample.timestamp >= start)
            if end:
                query = query.filter(ProcessSample.timestamp <= end)

            query = query.order_by(ProcessSample.timestamp.asc()).limit(limit)
            records = query.all()

            return [
                ProcessSampleSchema(
                    timestamp=r.timestamp,
                    process_name=r.process_name,
                    pid=r.pid,
                    cpu_percent=r.cpu_percent,
                    memory_mb=r.memory_mb,
                    status=r.status,
                    is_alive=r.is_alive,
                )
                for r in records
            ]
        except Exception as e:
            logger.error(f"Failed to get process history from DB: {e}")
            return []

    def cleanup_old_data(self, db: Session, retention_hours: int) -> int:
        """Delete old process samples from database."""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
            deleted = db.query(ProcessSample).filter(
                ProcessSample.timestamp < cutoff
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Cleaned up {deleted} old process samples")
            return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup old process data: {e}")
            db.rollback()
            return 0
