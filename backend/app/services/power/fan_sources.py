"""Unified temperature source layer.

Resolves namespaced sensor IDs (hwmon:, gpu:, disk:, mix:) into temperatures.
Used by FanControlService to look up any temperature regardless of origin.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


SourceKind = Literal["hwmon", "gpu", "disk", "mix"]


@runtime_checkable
class TempSource(Protocol):
    """Resolves a sensor ID to a current temperature in °C."""

    id: str
    kind: SourceKind
    device_name: str
    backend_label: Optional[str]
    is_cpu_sensor: bool

    async def current_temp(self) -> Optional[float]: ...


class HwmonTempSource:
    """Wraps a single hwmon temp_input file."""

    kind: SourceKind = "hwmon"

    def __init__(
        self,
        sensor_id: str,                                # legacy: "hwmon0_temp1"
        device_name: str,
        backend_label: Optional[str],
        is_cpu_sensor: bool,
        read_fn: Callable[[], Awaitable[Optional[float]]],
    ) -> None:
        self.id = f"hwmon:{sensor_id}"
        self.legacy_id = sensor_id
        self.device_name = device_name
        self.backend_label = backend_label
        self.is_cpu_sensor = is_cpu_sensor
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class TempSourceRegistry:
    """Registry of temperature sources keyed by namespaced ID."""

    def __init__(self) -> None:
        self._sources: Dict[str, TempSource] = {}
        self._labels: Dict[str, str] = {}  # sensor_id -> custom_label

    def register(self, source: TempSource) -> None:
        self._sources[source.id] = source

    def clear(self) -> None:
        self._sources.clear()

    def all_sources(self) -> List[TempSource]:
        return list(self._sources.values())

    def set_label(self, sensor_id: str, label: str) -> None:
        self._labels[self._normalize_id(sensor_id)] = label

    def clear_label(self, sensor_id: str) -> None:
        self._labels.pop(self._normalize_id(sensor_id), None)

    def display_label(self, sensor_id: str) -> str:
        nid = self._normalize_id(sensor_id)
        if nid in self._labels:
            return self._labels[nid]
        src = self._sources.get(nid)
        if src and src.backend_label:
            return src.backend_label
        if src:
            return src.device_name
        return sensor_id

    async def get_temp(self, sensor_id: str) -> Optional[float]:
        nid = self._normalize_id(sensor_id)
        src = self._sources.get(nid)
        if src is None:
            return None
        try:
            return await src.current_temp()
        except Exception as exc:
            logger.debug("Source %s temp read failed: %s", nid, exc)
            return None

    @staticmethod
    def _normalize_id(sensor_id: str) -> str:
        """Accept both namespaced (hwmon:foo) and legacy (foo) IDs."""
        if ":" in sensor_id:
            return sensor_id
        return f"hwmon:{sensor_id}"
