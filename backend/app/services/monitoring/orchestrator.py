"""
Monitoring orchestrator.

Coordinates all metric collectors, manages background sampling,
and handles database persistence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.monitoring.cpu_collector import CpuMetricCollector
from app.services.monitoring.memory_collector import MemoryMetricCollector
from app.services.monitoring.network_collector import NetworkMetricCollector
from app.services.monitoring.disk_io_collector import DiskIoMetricCollector
from app.services.monitoring.process_tracker import ProcessTracker
from app.services.monitoring.retention_manager import RetentionManager

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_SAMPLE_INTERVAL = 5.0  # seconds
DEFAULT_BUFFER_SIZE = 120  # 10 minutes at 5s interval
DEFAULT_PERSIST_INTERVAL = 12  # Every 12th sample (1 minute at 5s)
DEFAULT_CLEANUP_INTERVAL = 6  # hours


class MonitoringOrchestrator:
    """
    Orchestrates all monitoring collectors.

    Manages:
    - Background sampling task
    - Database persistence timing
    - Retention policy enforcement
    - Collector lifecycle
    """

    _instance: Optional["MonitoringOrchestrator"] = None

    def __init__(
        self,
        sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        persist_interval: int = DEFAULT_PERSIST_INTERVAL,
    ):
        """
        Initialize the orchestrator.

        Args:
            sample_interval: Seconds between samples
            buffer_size: In-memory buffer size per collector
            persist_interval: Persist to DB every N samples
        """
        self.sample_interval = sample_interval
        self.buffer_size = buffer_size
        self.persist_interval = persist_interval

        # Initialize collectors
        self.cpu_collector = CpuMetricCollector(
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.memory_collector = MemoryMetricCollector(
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.network_collector = NetworkMetricCollector(
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.disk_io_collector = DiskIoMetricCollector(
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.process_tracker = ProcessTracker(buffer_size=60)
        self.retention_manager = RetentionManager()

        # State
        self._monitor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._db_session_factory: Optional[Callable] = None
        self._is_running = False
        self._sample_count = 0
        self._last_cleanup: Optional[datetime] = None

    @classmethod
    def get_instance(cls) -> "MonitoringOrchestrator":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(
        self,
        db_session_factory: Callable,
        sample_interval: Optional[float] = None,
    ) -> None:
        """
        Start the monitoring background tasks.

        Args:
            db_session_factory: Factory function that returns DB sessions
            sample_interval: Override default sampling interval
        """
        if self._is_running:
            logger.warning("Monitoring orchestrator already running")
            return

        self._db_session_factory = db_session_factory
        if sample_interval:
            self.sample_interval = sample_interval

        self._is_running = True

        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Monitoring started (interval={self.sample_interval}s, "
            f"buffer={self.buffer_size}, persist_every={self.persist_interval})"
        )

    async def stop(self) -> None:
        """Stop the monitoring background tasks."""
        if not self._is_running:
            return

        logger.info("Stopping monitoring orchestrator...")
        self._is_running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        logger.info("Monitoring orchestrator stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        # Fast start: collect a few samples quickly
        for _ in range(3):
            await self._sample_once()
            await asyncio.sleep(0.5)

        # Regular sampling loop
        while self._is_running:
            try:
                await self._sample_once()

                # Check if cleanup is needed (every 6 hours)
                if self._should_run_cleanup():
                    await self._run_cleanup()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Monitoring iteration failed: {e}", exc_info=True)

            await asyncio.sleep(self.sample_interval)

    async def _sample_once(self) -> None:
        """Collect one sample from all collectors."""
        self._sample_count += 1

        # Get DB session if needed for persistence
        db: Optional[Session] = None
        should_persist = self._sample_count % self.persist_interval == 0

        if should_persist and self._db_session_factory:
            try:
                db = next(self._db_session_factory())
            except Exception as e:
                logger.error(f"Failed to get DB session: {e}")

        try:
            # Collect from all metric collectors
            self.cpu_collector.process_sample(db)
            self.memory_collector.process_sample(db)
            self.network_collector.process_sample(db)

            # Disk I/O collects multiple samples (one per disk)
            disk_samples = self.disk_io_collector.collect_all_samples()
            if should_persist and db and disk_samples:
                self.disk_io_collector.save_all_to_db(db, disk_samples)

            # Process tracking
            process_samples = self.process_tracker.collect_samples()
            if should_persist and db and process_samples:
                self.process_tracker.save_samples_to_db(db, process_samples)

        finally:
            if db:
                db.close()

    def _should_run_cleanup(self) -> bool:
        """Check if retention cleanup should run."""
        if self._last_cleanup is None:
            # Run cleanup after 1 hour of operation
            return self._sample_count > (3600 / self.sample_interval)

        from datetime import timedelta
        elapsed = datetime.utcnow() - self._last_cleanup
        return elapsed >= timedelta(hours=DEFAULT_CLEANUP_INTERVAL)

    async def _run_cleanup(self) -> None:
        """Run retention cleanup in background."""
        if not self._db_session_factory:
            return

        try:
            db = next(self._db_session_factory())
            try:
                results = self.retention_manager.run_all_cleanup(db)
                self._last_cleanup = datetime.utcnow()
                total = sum(results.values())
                if total > 0:
                    logger.info(f"Retention cleanup completed: {total} total samples removed")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Retention cleanup failed: {e}")

    # ===== Public API for current values =====

    def get_cpu_current(self):
        """Get current CPU sample."""
        return self.cpu_collector.get_current()

    def get_memory_current(self):
        """Get current memory sample."""
        return self.memory_collector.get_current()

    def get_network_current(self):
        """Get current network sample."""
        return self.network_collector.get_current()

    def get_disk_io_current(self) -> Dict:
        """Get current disk I/O samples for all disks."""
        return {
            disk: samples[-1] if samples else None
            for disk, samples in self.disk_io_collector.get_all_disk_histories().items()
        }

    def get_process_current(self):
        """Get current process status."""
        return self.process_tracker.get_current_status()

    # ===== Public API for history =====

    def get_cpu_history(self, limit: Optional[int] = None):
        """Get CPU history from memory."""
        return self.cpu_collector.get_history_memory(limit)

    def get_memory_history(self, limit: Optional[int] = None):
        """Get memory history from memory."""
        return self.memory_collector.get_history_memory(limit)

    def get_network_history(self, limit: Optional[int] = None):
        """Get network history from memory."""
        return self.network_collector.get_history_memory(limit)

    def get_disk_io_history(self, disk_name: Optional[str] = None):
        """Get disk I/O history from memory."""
        if disk_name:
            return self.disk_io_collector.get_disk_history(disk_name)
        return self.disk_io_collector.get_all_disk_histories()

    def get_process_history(self, process_name: Optional[str] = None):
        """Get process history from memory."""
        if process_name:
            return self.process_tracker.get_process_history(process_name)
        return self.process_tracker.get_all_histories()

    # ===== Status and info =====

    def is_running(self) -> bool:
        """Check if monitoring is running."""
        return self._is_running

    def get_stats(self) -> Dict:
        """Get orchestrator statistics."""
        return {
            "is_running": self._is_running,
            "sample_count": self._sample_count,
            "sample_interval": self.sample_interval,
            "buffer_size": self.buffer_size,
            "persist_interval": self.persist_interval,
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "collectors": {
                "cpu": self.cpu_collector.is_enabled(),
                "memory": self.memory_collector.is_enabled(),
                "network": self.network_collector.is_enabled(),
                "disk_io": self.disk_io_collector.is_enabled(),
                "process": True,
            },
        }


# Module-level functions for easy access
_orchestrator: Optional[MonitoringOrchestrator] = None


def get_monitoring_orchestrator() -> MonitoringOrchestrator:
    """Get the global monitoring orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MonitoringOrchestrator()
    return _orchestrator


async def start_monitoring(db_session_factory: Callable) -> None:
    """Start the global monitoring orchestrator."""
    orchestrator = get_monitoring_orchestrator()
    await orchestrator.start(db_session_factory)


async def stop_monitoring() -> None:
    """Stop the global monitoring orchestrator."""
    orchestrator = get_monitoring_orchestrator()
    await orchestrator.stop()


def get_status() -> dict:
    """
    Get monitoring orchestrator service status.

    Returns:
        Dict with service status information for admin dashboard
    """
    orchestrator = get_monitoring_orchestrator()

    return {
        "is_running": orchestrator._is_running,
        "started_at": None,  # Not tracked separately
        "uptime_seconds": None,
        "sample_count": orchestrator._sample_count,
        "error_count": 0,  # Not tracked separately
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": orchestrator.sample_interval,
        "buffer_size": orchestrator.buffer_size,
        "persist_interval": orchestrator.persist_interval,
        "last_cleanup": orchestrator._last_cleanup.isoformat() if orchestrator._last_cleanup else None,
    }
