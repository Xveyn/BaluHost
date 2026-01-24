"""
Base metric collector abstract class.

Provides the common interface and functionality for all metric collectors
with dual storage (in-memory circular buffer + database persistence).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from threading import Lock
from typing import Generic, TypeVar, List, Optional, Type

from sqlalchemy.orm import Session

from app.models.base import Base

logger = logging.getLogger(__name__)

# Type variable for the sample type
T = TypeVar("T")


class MetricCollector(ABC, Generic[T]):
    """
    Abstract base class for metric collectors.

    Provides:
    - In-memory circular buffer for fast dashboard access
    - Periodic database persistence for historical data
    - Configurable retention and persistence intervals

    Type Parameters:
        T: The Pydantic schema type for samples (e.g., CpuSampleSchema)
    """

    def __init__(
        self,
        metric_name: str,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        """
        Initialize the metric collector.

        Args:
            metric_name: Human-readable name for logging
            buffer_size: Maximum samples to keep in memory (circular buffer)
            persist_interval: Persist to DB every N samples
        """
        self.metric_name = metric_name
        self.buffer_size = buffer_size
        self.persist_interval = persist_interval

        self._memory_buffer: List[T] = []
        self._buffer_lock = Lock()
        self._persist_counter = 0
        self._is_enabled = True

    @abstractmethod
    def collect_sample(self) -> Optional[T]:
        """
        Collect a single metric sample.

        Returns:
            Sample object or None if collection failed
        """
        pass

    @abstractmethod
    def get_db_model(self) -> Type[Base]:
        """
        Get the SQLAlchemy model class for this metric.

        Returns:
            Model class (e.g., CpuSample)
        """
        pass

    @abstractmethod
    def sample_to_db_dict(self, sample: T) -> dict:
        """
        Convert a sample schema to database model kwargs.

        Args:
            sample: Sample schema object

        Returns:
            Dict of column values for the database model
        """
        pass

    @abstractmethod
    def db_to_sample(self, db_record) -> T:
        """
        Convert a database record to a sample schema.

        Args:
            db_record: SQLAlchemy model instance

        Returns:
            Sample schema object
        """
        pass

    def process_sample(self, db: Optional[Session] = None) -> Optional[T]:
        """
        Collect and process a sample.

        Stores in memory buffer and optionally persists to database.

        Args:
            db: Optional database session for persistence

        Returns:
            The collected sample or None
        """
        if not self._is_enabled:
            return None

        sample = self.collect_sample()
        if sample is None:
            return None

        # Store in memory buffer
        with self._buffer_lock:
            self._memory_buffer.append(sample)
            if len(self._memory_buffer) > self.buffer_size:
                self._memory_buffer.pop(0)

        # Check if we should persist to database
        self._persist_counter += 1
        if db is not None and self._should_persist():
            self._persist_counter = 0
            self.save_to_db(db, sample)

        return sample

    def _should_persist(self) -> bool:
        """Check if it's time to persist to database."""
        return self._persist_counter >= self.persist_interval

    def save_to_db(self, db: Session, sample: T) -> None:
        """
        Save a sample to the database.

        Args:
            db: Database session
            sample: Sample to save
        """
        try:
            model_class = self.get_db_model()
            db_dict = self.sample_to_db_dict(sample)
            db_record = model_class(**db_dict)
            db.add(db_record)
            db.commit()
            logger.debug(f"{self.metric_name}: Saved sample to database")
        except Exception as e:
            logger.error(f"{self.metric_name}: Failed to save sample to DB: {e}")
            db.rollback()

    def get_current(self) -> Optional[T]:
        """
        Get the latest sample from memory.

        Returns:
            Latest sample or None if no samples yet
        """
        with self._buffer_lock:
            if self._memory_buffer:
                return self._memory_buffer[-1]
            return None

    def get_history_memory(self, limit: Optional[int] = None) -> List[T]:
        """
        Get historical samples from memory buffer.

        Args:
            limit: Optional limit on number of samples to return

        Returns:
            List of samples (oldest first)
        """
        with self._buffer_lock:
            if limit:
                return list(self._memory_buffer[-limit:])
            return list(self._memory_buffer)

    def get_history_db(
        self,
        db: Session,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[T]:
        """
        Get historical samples from database.

        Args:
            db: Database session
            start: Start timestamp (inclusive)
            end: End timestamp (inclusive)
            limit: Maximum number of samples

        Returns:
            List of samples (oldest first)
        """
        try:
            model_class = self.get_db_model()
            query = db.query(model_class)

            if start:
                query = query.filter(model_class.timestamp >= start)
            if end:
                query = query.filter(model_class.timestamp <= end)

            query = query.order_by(model_class.timestamp.asc()).limit(limit)
            records = query.all()

            return [self.db_to_sample(record) for record in records]
        except Exception as e:
            logger.error(f"{self.metric_name}: Failed to get history from DB: {e}")
            return []

    def get_history_auto(
        self,
        db: Session,
        duration: timedelta,
    ) -> List[T]:
        """
        Get history from the appropriate source based on duration.

        For short durations (< memory buffer time), uses memory.
        For longer durations, uses database.

        Args:
            db: Database session
            duration: How far back to look

        Returns:
            List of samples
        """
        # Estimate memory buffer duration (assuming 5s sampling)
        memory_duration = timedelta(seconds=self.buffer_size * 5)

        if duration <= memory_duration:
            # Use memory buffer
            return self.get_history_memory()
        else:
            # Use database
            start = datetime.utcnow() - duration
            return self.get_history_db(db, start=start)

    def cleanup_old_data(self, db: Session, retention_hours: int) -> int:
        """
        Delete samples older than retention period.

        Args:
            db: Database session
            retention_hours: How many hours of data to keep

        Returns:
            Number of samples deleted
        """
        try:
            model_class = self.get_db_model()
            cutoff = datetime.utcnow() - timedelta(hours=retention_hours)

            deleted = db.query(model_class).filter(
                model_class.timestamp < cutoff
            ).delete(synchronize_session=False)

            db.commit()
            logger.info(f"{self.metric_name}: Cleaned up {deleted} old samples")
            return deleted
        except Exception as e:
            logger.error(f"{self.metric_name}: Failed to cleanup old data: {e}")
            db.rollback()
            return 0

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable this collector."""
        self._is_enabled = enabled

    def is_enabled(self) -> bool:
        """Check if this collector is enabled."""
        return self._is_enabled

    def clear_memory_buffer(self) -> None:
        """Clear the in-memory buffer."""
        with self._buffer_lock:
            self._memory_buffer.clear()
