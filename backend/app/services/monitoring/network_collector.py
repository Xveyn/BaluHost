"""
Network metrics collector.

Collects network throughput data (download/upload speeds).
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Optional, Tuple, Type

import psutil

from app.core.config import settings
from app.models.base import Base
from app.models.monitoring import NetworkSample
from app.schemas.monitoring import NetworkSampleSchema
from app.services.monitoring.base import MetricCollector

logger = logging.getLogger(__name__)


class NetworkMetricCollector(MetricCollector[NetworkSampleSchema]):
    """
    Collector for network metrics.

    Collects:
    - Download speed (Mbps)
    - Upload speed (Mbps)
    - Bytes sent/received (optional)
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        super().__init__(
            metric_name="Network",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        # Previous network counters for rate calculation
        self._previous_counters: Optional[Tuple[float, int, int]] = None

    def collect_sample(self) -> Optional[NetworkSampleSchema]:
        """Collect network metrics sample."""
        try:
            timestamp = datetime.utcnow()
            timestamp_seconds = time.time()

            # Always try to collect real network data
            download_mbps, upload_mbps, bytes_received, bytes_sent = self._calculate_speeds(
                timestamp_seconds
            )

            return NetworkSampleSchema(
                timestamp=timestamp,
                download_mbps=round(download_mbps, 2),
                upload_mbps=round(upload_mbps, 2),
                bytes_sent=bytes_sent,
                bytes_received=bytes_received,
            )
        except Exception as e:
            logger.error(f"Failed to collect network sample: {e}")
            return None

    def _calculate_speeds(
        self, timestamp_seconds: float
    ) -> Tuple[float, float, Optional[int], Optional[int]]:
        """Calculate network speeds from counters."""
        download_mbps = 0.0
        upload_mbps = 0.0
        bytes_received = None
        bytes_sent = None

        try:
            counters = psutil.net_io_counters()
            if counters is not None:
                rx_bytes = int(counters.bytes_recv)
                tx_bytes = int(counters.bytes_sent)
                bytes_received = rx_bytes
                bytes_sent = tx_bytes

                if self._previous_counters is None:
                    self._previous_counters = (timestamp_seconds, rx_bytes, tx_bytes)
                else:
                    last_time, last_rx, last_tx = self._previous_counters
                    elapsed = max(timestamp_seconds - last_time, 1e-3)
                    rx_diff = rx_bytes - last_rx
                    tx_diff = tx_bytes - last_tx

                    # Convert bytes/sec to Mbps (Megabits per second)
                    download_mbps = max(0.0, (rx_diff * 8) / (elapsed * 1_000_000))
                    upload_mbps = max(0.0, (tx_diff * 8) / (elapsed * 1_000_000))

                    self._previous_counters = (timestamp_seconds, rx_bytes, tx_bytes)
            else:
                # No network counters available, fall back to mock data in dev mode
                if settings.is_dev_mode:
                    download_mbps, upload_mbps = self._generate_mock_data()
                self._previous_counters = None
        except Exception as e:
            logger.debug(f"Network counters unavailable: {e}")
            # Only use mock data in dev mode when real data fails
            if settings.is_dev_mode:
                download_mbps, upload_mbps = self._generate_mock_data()
            self._previous_counters = None

        return download_mbps, upload_mbps, bytes_received, bytes_sent

    def _generate_mock_data(self) -> Tuple[float, float]:
        """Generate mock network data for dev mode."""
        # Get previous values for smooth transitions
        with self._buffer_lock:
            previous = self._memory_buffer[-1] if self._memory_buffer else None

        base_down = previous.download_mbps if previous else 1.4
        base_up = previous.upload_mbps if previous else 0.7

        next_down = max(0.0, base_down + random.uniform(-0.6, 0.8))
        next_up = max(0.0, base_up + random.uniform(-0.4, 0.5))

        return round(next_down, 2), round(next_up, 2)

    def get_db_model(self) -> Type[Base]:
        """Get the NetworkSample model class."""
        return NetworkSample

    def sample_to_db_dict(self, sample: NetworkSampleSchema) -> dict:
        """Convert schema to database dict."""
        return {
            "timestamp": sample.timestamp,
            "download_mbps": sample.download_mbps,
            "upload_mbps": sample.upload_mbps,
            "bytes_sent": sample.bytes_sent,
            "bytes_received": sample.bytes_received,
        }

    def db_to_sample(self, db_record: NetworkSample) -> NetworkSampleSchema:
        """Convert database record to schema."""
        return NetworkSampleSchema(
            timestamp=db_record.timestamp,
            download_mbps=db_record.download_mbps,
            upload_mbps=db_record.upload_mbps,
            bytes_sent=db_record.bytes_sent,
            bytes_received=db_record.bytes_received,
        )
