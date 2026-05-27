"""
Memory metrics collector.

Collects RAM usage data including BaluHost process memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Type

import psutil

from app.models.monitoring import MemorySample
from app.schemas.monitoring import MemorySampleSchema
from app.services.monitoring.base import MetricCollector
from app.services.monitoring.process_tracker import BALUHOST_PROCESS_PATTERNS

logger = logging.getLogger(__name__)


def get_baluhost_memory_breakdown() -> dict[str, int]:
    """
    Get RSS memory per BaluHost systemd unit.

    Returns a dict keyed by ``process_name`` from ``BALUHOST_PROCESS_PATTERNS``.
    All defined unit names appear as keys; missing units have value 0 so the
    UI can distinguish "unit not defined" (key absent) from "unit not running"
    (key present, value 0).

    Routing is first-match-wins (same order as BALUHOST_PROCESS_PATTERNS) so
    a process matching multiple patterns is counted under the first.
    """
    breakdown: dict[str, int] = {entry["name"]: 0 for entry in BALUHOST_PROCESS_PATTERNS}

    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                cmdline = " ".join(info.get("cmdline") or []).lower()

                for entry in BALUHOST_PROCESS_PATTERNS:
                    if all(p.lower() in name or p.lower() in cmdline for p in entry["patterns"]):
                        if info.get("memory_info"):
                            breakdown[entry["name"]] += info["memory_info"].rss
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Error getting BaluHost memory breakdown: {e}")

    return breakdown


def get_baluhost_memory_bytes() -> int:
    """Backward-compat: total memory across all BaluHost processes."""
    return sum(get_baluhost_memory_breakdown().values())


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
            timestamp = datetime.now(timezone.utc)

            mem = psutil.virtual_memory()
            breakdown = get_baluhost_memory_breakdown()
            total_baluhost = sum(breakdown.values())

            return MemorySampleSchema(
                timestamp=timestamp,
                used_bytes=mem.total - mem.available,
                total_bytes=mem.total,
                percent=round(mem.percent, 2),
                available_bytes=mem.available,
                baluhost_memory_bytes=total_baluhost,
                baluhost_memory_breakdown=breakdown,
            )
        except Exception as e:
            logger.error(f"Failed to collect memory sample: {e}")
            return None

    def get_db_model(self) -> Type[Any]:
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
        # baluhost_memory_breakdown is live-only (no DB column); defaults to None.
        # Frontend consumers must handle null for history endpoints.
        return MemorySampleSchema(
            timestamp=db_record.timestamp,
            used_bytes=db_record.used_bytes,
            total_bytes=db_record.total_bytes,
            percent=db_record.percent,
            available_bytes=db_record.available_bytes,
            baluhost_memory_bytes=db_record.baluhost_memory_bytes,
        )
