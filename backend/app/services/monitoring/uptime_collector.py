"""
Uptime metrics collector.

Collects server uptime (BaluHost backend) and system uptime (OS/hardware).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Type

import psutil

from app.models.monitoring import UptimeSample
from app.schemas.monitoring import UptimeSampleSchema
from app.services.monitoring.base import MetricCollector

logger = logging.getLogger(__name__)


class UptimeCollector(MetricCollector[UptimeSampleSchema]):
    """
    Collector for uptime metrics.

    Collects:
    - Server uptime (time since BaluHost backend started)
    - System uptime (time since OS last booted)
    - Server start time
    - System boot time
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        super().__init__(
            metric_name="Uptime",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )

    def collect_sample(self) -> Optional[UptimeSampleSchema]:
        """Collect uptime metrics sample."""
        try:
            from app.services.telemetry import _SERVER_START_TIME
            from app.core.config import settings

            timestamp = datetime.now(timezone.utc)
            now = time.time()

            # Server uptime
            server_uptime = int(now - _SERVER_START_TIME)
            server_start = datetime.fromtimestamp(_SERVER_START_TIME, tz=timezone.utc)

            # System uptime
            if getattr(settings, "is_dev_mode", False):
                # Dev mode: system uptime = server uptime
                system_boot = server_start
                system_uptime = server_uptime
            else:
                try:
                    boot_time = psutil.boot_time()
                    system_boot = datetime.fromtimestamp(boot_time, tz=timezone.utc)
                    system_uptime = int(now - boot_time)
                except Exception:
                    # Fallback to server uptime
                    system_boot = server_start
                    system_uptime = server_uptime

            return UptimeSampleSchema(
                timestamp=timestamp,
                server_uptime_seconds=server_uptime,
                system_uptime_seconds=system_uptime,
                server_start_time=server_start,
                system_boot_time=system_boot,
            )
        except Exception as e:
            logger.error(f"Failed to collect uptime sample: {e}")
            return None

    def get_db_model(self) -> Type[Any]:
        """Get the UptimeSample model class."""
        return UptimeSample

    def sample_to_db_dict(self, sample: UptimeSampleSchema) -> dict:
        """Convert schema to database dict."""
        return {
            "timestamp": sample.timestamp,
            "server_uptime_seconds": sample.server_uptime_seconds,
            "system_uptime_seconds": sample.system_uptime_seconds,
            "server_start_time": sample.server_start_time,
            "system_boot_time": sample.system_boot_time,
        }

    def db_to_sample(self, db_record: UptimeSample) -> UptimeSampleSchema:
        """Convert database record to schema."""
        return UptimeSampleSchema(
            timestamp=db_record.timestamp,
            server_uptime_seconds=db_record.server_uptime_seconds,
            system_uptime_seconds=db_record.system_uptime_seconds,
            server_start_time=db_record.server_start_time,
            system_boot_time=db_record.system_boot_time,
        )
