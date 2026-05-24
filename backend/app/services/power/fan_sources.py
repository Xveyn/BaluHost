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


class GpuTempSource:
    """One temperature channel of the dedicated GPU (edge/junction/mem)."""

    kind: SourceKind = "gpu"

    def __init__(
        self,
        channel: str,                                  # "edge" | "junction" | "mem"
        read_fn: Callable[[], Awaitable[Optional[float]]],
        gpu_vendor: str = "amd",
    ) -> None:
        self.id = f"gpu:{channel}"
        self.channel = channel
        self.device_name = f"{gpu_vendor}gpu"
        self.backend_label = channel
        self.is_cpu_sensor = False
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class DiskTempSource:
    """SMART-reported disk temperature for one block device."""

    kind: SourceKind = "disk"

    def __init__(
        self,
        device: str,                                   # "sda", "nvme0n1"
        read_fn: Callable[[], Awaitable[Optional[float]]],
    ) -> None:
        self.id = f"disk:{device}"
        self.device = device
        self.device_name = device
        self.backend_label = None
        self.is_cpu_sensor = False
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class MixTempSource:
    """Composite source combining N other sources via max/min/avg."""

    kind: SourceKind = "mix"
    _MAX_DEPTH = 5

    def __init__(
        self,
        composite_id: str,                             # "mix:<uuid>"
        name: str,
        function: str,                                 # "max" | "min" | "avg"
        source_ids: List[str],
        registry: "TempSourceRegistry",
    ) -> None:
        if not composite_id.startswith("mix:"):
            composite_id = f"mix:{composite_id}"
        self.id = composite_id
        self.composite_id = composite_id
        self.name = name
        self.function = function
        self.source_ids = source_ids
        self._registry = registry
        self.device_name = "composite"
        self.backend_label = name
        self.is_cpu_sensor = False

    async def current_temp(self, _depth: int = 0, _path: Optional[set] = None) -> Optional[float]:
        if _depth >= self._MAX_DEPTH:
            logger.warning("MixTempSource %s exceeded max depth", self.id)
            return None
        path = _path if _path is not None else set()
        if self.id in path:
            logger.warning("MixTempSource cycle detected at %s", self.id)
            return None
        path = path | {self.id}

        values: List[float] = []
        for sid in self.source_ids:
            sub = self._registry._sources.get(self._registry._normalize_id(sid))
            if isinstance(sub, MixTempSource):
                v = await sub.current_temp(_depth + 1, path)
            elif sub is not None:
                try:
                    v = await sub.current_temp()
                except Exception:
                    v = None
            else:
                v = None
            if v is not None:
                values.append(v)

        if not values:
            return None
        if self.function == "max":
            return max(values)
        if self.function == "min":
            return min(values)
        if self.function == "avg":
            return sum(values) / len(values)
        return None
