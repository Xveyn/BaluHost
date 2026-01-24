"""
Memory metrics collector.

Collects RAM usage data including BaluHost process memory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Type

import psutil

from app.models.base import Base
from app.models.monitoring import MemorySample
from app.schemas.monitoring import MemorySampleSchema
from app.services.monitoring.base import MetricCollector

logger = logging.getLogger(__name__)

# Process patterns to track (same as process_tracker)
BALUHOST_PROCESS_PATTERNS = [
    ["uvicorn", "app.main"],  # Backend
    ["node", "vite"],  # Frontend
    ["baluhost-tui", "baluhost_tui"],  # TUI
]


def get_baluhost_memory_bytes() -> int:
    """
    Get total memory used by BaluHost processes.

    Returns:
        Total memory in bytes used by all BaluHost processes.
    """
    total_memory = 0

    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
            try:
                proc_info = proc.info
                name = proc_info.get("name", "").lower()
                cmdline = " ".join(proc_info.get("cmdline") or []).lower()

                # Check if any pattern matches
                for patterns in BALUHOST_PROCESS_PATTERNS:
                    if any(p.lower() in name or p.lower() in cmdline for p in patterns):
                        if proc_info.get("memory_info"):
                            total_memory += proc_info["memory_info"].rss
                        break  # Don't count same process twice
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Error getting BaluHost memory: {e}")

    return total_memory


class MemoryMetricCollector(MetricCollector[MemorySampleSchema]):
    """
    Collector for memory metrics.

    Collects:
    - Used memory (bytes)
    - Total memory (bytes)
    - Memory usage percentage
    - Available memory (bytes)
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        super().__init__(
            metric_name="Memory",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )

    def collect_sample(self) -> Optional[MemorySampleSchema]:
        """Collect memory metrics sample."""
        try:
            timestamp = datetime.utcnow()

            # Get memory info
            mem = psutil.virtual_memory()

            # Get BaluHost process memory
            baluhost_memory = get_baluhost_memory_bytes()

            return MemorySampleSchema(
                timestamp=timestamp,
                used_bytes=mem.total - mem.available,
                total_bytes=mem.total,
                percent=round(mem.percent, 2),
                available_bytes=mem.available,
                baluhost_memory_bytes=baluhost_memory,
            )
        except Exception as e:
            logger.error(f"Failed to collect memory sample: {e}")
            return None

    def get_db_model(self) -> Type[Base]:
        """Get the MemorySample model class."""
        return MemorySample

    def sample_to_db_dict(self, sample: MemorySampleSchema) -> dict:
        """Convert schema to database dict."""
        return {
            "timestamp": sample.timestamp,
            "used_bytes": sample.used_bytes,
            "total_bytes": sample.total_bytes,
            "percent": sample.percent,
            "available_bytes": sample.available_bytes,
            "baluhost_memory_bytes": sample.baluhost_memory_bytes,
        }

    def db_to_sample(self, db_record: MemorySample) -> MemorySampleSchema:
        """Convert database record to schema."""
        return MemorySampleSchema(
            timestamp=db_record.timestamp,
            used_bytes=db_record.used_bytes,
            total_bytes=db_record.total_bytes,
            percent=db_record.percent,
            available_bytes=db_record.available_bytes,
            baluhost_memory_bytes=db_record.baluhost_memory_bytes,
        )
