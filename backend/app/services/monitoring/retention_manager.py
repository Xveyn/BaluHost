"""
Retention manager for monitoring data.

Manages data retention policies and cleanup for all metric types.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.monitoring import (
    MetricType,
    MonitoringConfig,
    CpuSample,
    MemorySample,
    NetworkSample,
    DiskIoSample,
    ProcessSample,
)

logger = logging.getLogger(__name__)

# Default retention periods (hours)
DEFAULT_RETENTION = {
    MetricType.CPU: 168,       # 7 days
    MetricType.MEMORY: 168,    # 7 days
    MetricType.NETWORK: 168,   # 7 days
    MetricType.DISK_IO: 168,   # 7 days
    MetricType.PROCESS: 72,    # 3 days
}

# Mapping of metric types to their database models
METRIC_MODELS = {
    MetricType.CPU: CpuSample,
    MetricType.MEMORY: MemorySample,
    MetricType.NETWORK: NetworkSample,
    MetricType.DISK_IO: DiskIoSample,
    MetricType.PROCESS: ProcessSample,
}


class RetentionManager:
    """
    Manages data retention policies for monitoring metrics.

    Features:
    - Configurable retention per metric type
    - Periodic cleanup of old data
    - Database size tracking
    """

    def __init__(self):
        """Initialize the retention manager."""
        self._last_cleanup: Dict[MetricType, datetime] = {}

    def get_config(self, db: Session, metric_type: MetricType) -> MonitoringConfig:
        """
        Get or create retention config for a metric type.

        Args:
            db: Database session
            metric_type: Type of metric

        Returns:
            MonitoringConfig record
        """
        config = db.query(MonitoringConfig).filter(
            MonitoringConfig.metric_type == metric_type
        ).first()

        if config is None:
            # Create default config
            config = MonitoringConfig(
                metric_type=metric_type,
                retention_hours=DEFAULT_RETENTION.get(metric_type, 168),
                db_persist_interval=12,
                is_enabled=True,
            )
            db.add(config)
            db.commit()
            logger.info(f"Created default retention config for {metric_type.value}")

        return config

    def set_retention(
        self,
        db: Session,
        metric_type: MetricType,
        retention_hours: int,
    ) -> MonitoringConfig:
        """
        Set retention period for a metric type.

        Args:
            db: Database session
            metric_type: Type of metric
            retention_hours: Hours of data to retain

        Returns:
            Updated MonitoringConfig
        """
        if retention_hours < 1:
            raise ValueError("Retention must be at least 1 hour")
        if retention_hours > 8760:  # 1 year
            raise ValueError("Retention cannot exceed 1 year (8760 hours)")

        config = self.get_config(db, metric_type)
        config.retention_hours = retention_hours
        db.commit()

        logger.info(f"Set {metric_type.value} retention to {retention_hours} hours")
        return config

    def apply_retention_policy(
        self,
        db: Session,
        metric_type: MetricType,
    ) -> int:
        """
        Apply retention policy for a metric type.

        Deletes data older than the configured retention period.

        Args:
            db: Database session
            metric_type: Type of metric to clean up

        Returns:
            Number of records deleted
        """
        config = self.get_config(db, metric_type)
        model = METRIC_MODELS.get(metric_type)

        if model is None:
            logger.error(f"Unknown metric type: {metric_type}")
            return 0

        try:
            cutoff = datetime.utcnow() - timedelta(hours=config.retention_hours)

            deleted = db.query(model).filter(
                model.timestamp < cutoff
            ).delete(synchronize_session=False)

            # Update config
            config.last_cleanup = datetime.utcnow()
            config.samples_cleaned += deleted
            db.commit()

            self._last_cleanup[metric_type] = datetime.utcnow()
            logger.info(f"Cleaned up {deleted} {metric_type.value} samples (retention={config.retention_hours}h)")

            return deleted
        except Exception as e:
            logger.error(f"Failed to apply retention policy for {metric_type.value}: {e}")
            db.rollback()
            return 0

    def run_all_cleanup(self, db: Session) -> Dict[str, int]:
        """
        Run cleanup for all metric types.

        Args:
            db: Database session

        Returns:
            Dict of metric_type -> deleted count
        """
        results = {}

        for metric_type in MetricType:
            deleted = self.apply_retention_policy(db, metric_type)
            results[metric_type.value] = deleted

        total = sum(results.values())
        logger.info(f"Total cleanup: {total} samples deleted")

        return results

    def get_database_stats(self, db: Session) -> Dict[str, Dict]:
        """
        Get database statistics for all metric types.

        Args:
            db: Database session

        Returns:
            Dict with counts, oldest/newest timestamps per metric
        """
        stats = {}

        for metric_type, model in METRIC_MODELS.items():
            try:
                count = db.query(model).count()
                oldest = db.query(model).order_by(model.timestamp.asc()).first()
                newest = db.query(model).order_by(model.timestamp.desc()).first()

                config = self.get_config(db, metric_type)

                stats[metric_type.value] = {
                    "count": count,
                    "oldest": oldest.timestamp.isoformat() if oldest else None,
                    "newest": newest.timestamp.isoformat() if newest else None,
                    "retention_hours": config.retention_hours,
                    "last_cleanup": config.last_cleanup.isoformat() if config.last_cleanup else None,
                    "total_cleaned": config.samples_cleaned,
                }
            except Exception as e:
                logger.error(f"Failed to get stats for {metric_type.value}: {e}")
                stats[metric_type.value] = {"error": str(e)}

        return stats

    def estimate_database_size(self, db: Session) -> Dict[str, int]:
        """
        Estimate database size per metric type.

        Rough estimate based on sample count * average row size.

        Args:
            db: Database session

        Returns:
            Dict of metric_type -> estimated bytes
        """
        # Estimated row sizes (bytes, including indexes)
        ROW_SIZES = {
            MetricType.CPU: 50,
            MetricType.MEMORY: 50,
            MetricType.NETWORK: 60,
            MetricType.DISK_IO: 100,
            MetricType.PROCESS: 120,
        }

        sizes = {}

        for metric_type, model in METRIC_MODELS.items():
            try:
                count = db.query(model).count()
                row_size = ROW_SIZES.get(metric_type, 80)
                sizes[metric_type.value] = count * row_size
            except Exception as e:
                logger.error(f"Failed to estimate size for {metric_type.value}: {e}")
                sizes[metric_type.value] = 0

        sizes["total"] = sum(sizes.values())
        return sizes

    def should_run_cleanup(self, interval_hours: float = 6.0) -> bool:
        """
        Check if cleanup should run based on time since last cleanup.

        Args:
            interval_hours: Minimum hours between cleanups

        Returns:
            True if cleanup should run
        """
        if not self._last_cleanup:
            return True

        oldest_cleanup = min(self._last_cleanup.values())
        elapsed = datetime.utcnow() - oldest_cleanup

        return elapsed >= timedelta(hours=interval_hours)
