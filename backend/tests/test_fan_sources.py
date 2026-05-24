"""Tests for fan source registry."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.power.fan_sources import (
    TempSourceRegistry,
    HwmonTempSource,
)


@pytest.mark.asyncio
async def test_hwmon_source_resolves_temp():
    src = HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=42.5),
    )
    assert src.id == "hwmon:hwmon0_temp1"
    assert src.kind == "hwmon"
    assert await src.current_temp() == 42.5


@pytest.mark.asyncio
async def test_registry_accepts_legacy_unprefixed_id():
    src = HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=40.0),
    )
    registry = TempSourceRegistry()
    registry.register(src)

    # Legacy ID (no namespace) must resolve as if "hwmon:" was prepended
    assert await registry.get_temp("hwmon0_temp1") == 40.0
    assert await registry.get_temp("hwmon:hwmon0_temp1") == 40.0


@pytest.mark.asyncio
async def test_registry_returns_none_for_unknown_id():
    registry = TempSourceRegistry()
    assert await registry.get_temp("hwmon:does_not_exist") is None


from app.services.power.fan_sources import GpuTempSource, DiskTempSource, MixTempSource


@pytest.mark.asyncio
async def test_gpu_source_reads_channel():
    src = GpuTempSource(channel="edge", read_fn=AsyncMock(return_value=55.3))
    assert src.id == "gpu:edge"
    assert src.kind == "gpu"
    assert await src.current_temp() == 55.3


@pytest.mark.asyncio
async def test_disk_source():
    src = DiskTempSource(device="sda", read_fn=AsyncMock(return_value=38.0))
    assert src.id == "disk:sda"
    assert src.kind == "disk"
    assert await src.current_temp() == 38.0


@pytest.mark.asyncio
async def test_mix_source_max():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", "Tctl", True, AsyncMock(return_value=50.0)))
    registry.register(HwmonTempSource("h1_t1", "amdgpu", "edge", False, AsyncMock(return_value=70.0)))

    mix = MixTempSource(
        composite_id="mix:abc",
        name="hottest",
        function="max",
        source_ids=["hwmon:h0_t1", "hwmon:h1_t1"],
        registry=registry,
    )
    registry.register(mix)
    assert await mix.current_temp() == 70.0


@pytest.mark.asyncio
async def test_mix_source_avg():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", None, True, AsyncMock(return_value=40.0)))
    registry.register(HwmonTempSource("h1_t1", "k10temp", None, True, AsyncMock(return_value=60.0)))

    mix = MixTempSource("mix:x", "avg", "avg", ["hwmon:h0_t1", "hwmon:h1_t1"], registry)
    assert await mix.current_temp() == 50.0


@pytest.mark.asyncio
async def test_mix_source_ignores_unavailable_subsource():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", None, True, AsyncMock(return_value=50.0)))
    registry.register(HwmonTempSource("h1_t1", "k10temp", None, True, AsyncMock(return_value=None)))

    mix = MixTempSource("mix:x", "max", "max", ["hwmon:h0_t1", "hwmon:h1_t1"], registry)
    assert await mix.current_temp() == 50.0  # None ignored, max of remaining


@pytest.mark.asyncio
async def test_mix_source_detects_cycle():
    registry = TempSourceRegistry()
    mix_a = MixTempSource("mix:a", "a", "max", ["mix:b"], registry)
    mix_b = MixTempSource("mix:b", "b", "max", ["mix:a"], registry)
    registry.register(mix_a)
    registry.register(mix_b)

    # Cycle detection should return None rather than recurse forever
    assert await mix_a.current_temp() is None
