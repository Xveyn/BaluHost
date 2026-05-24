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
