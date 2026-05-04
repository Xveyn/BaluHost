"""State machine tests using DevGpuPowerBackend with controlled time and inputs."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.gpu_power import GpuPowerConfig, GpuPowerState
from app.services.power.gpu.dev_backend import DevGpuPowerBackend
from app.services.power.gpu.manager import GpuPowerManagerService


@pytest.fixture
def manager(monkeypatch):
    GpuPowerManagerService._instance = None
    mgr = GpuPowerManagerService()
    mgr._backend = DevGpuPowerBackend()
    mgr._config = GpuPowerConfig(enabled=True)
    # Stub config loaders so _tick doesn't reload
    monkeypatch.setattr(
        "app.services.power.gpu.manager.load_gpu_power_config",
        lambda: mgr._config,
    )
    monkeypatch.setattr(
        "app.services.power.gpu.manager.save_gpu_power_config",
        lambda c: True,
    )
    yield mgr
    GpuPowerManagerService._instance = None


@pytest.mark.asyncio
async def test_active_when_display_connected(manager):
    with patch.object(manager, "_get_displays", AsyncMock(return_value=1)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_active_when_usage_high(manager):
    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=80.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_transition_active_to_standby_after_idle_window(manager):
    manager._config = GpuPowerConfig(enabled=True, idle_window_seconds=10)
    manager._idle_since = datetime.now(timezone.utc) - timedelta(seconds=15)

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.STANDBY


@pytest.mark.asyncio
async def test_transition_standby_to_deep_idle_after_grace(manager):
    manager._config = GpuPowerConfig(
        enabled=True,
        idle_window_seconds=10,
        deep_idle_extra_seconds=30,  # minimum allowed by schema (ge=30)
        deep_idle_grace_seconds=0,
    )
    manager._state = GpuPowerState.STANDBY
    manager._standby_since = datetime.now(timezone.utc) - timedelta(seconds=35)  # > 30s elapsed
    manager._idle_since = datetime.now(timezone.utc) - timedelta(seconds=50)

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)), \
         patch("app.services.power.gpu.manager.emit_deep_idle_entering", AsyncMock()) as mock_emit:
        await manager._tick()
        assert manager._state == GpuPowerState.DEEP_IDLE
        mock_emit.assert_awaited_once()


@pytest.mark.asyncio
async def test_demand_forces_active(manager):
    manager._state = GpuPowerState.DEEP_IDLE

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager.register_demand("test_source")
        # Tick should re-evaluate; demand alone forces ACTIVE
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_disabled_config_does_nothing(manager):
    manager._config = GpuPowerConfig(enabled=False)
    manager._state = GpuPowerState.DEEP_IDLE

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.DEEP_IDLE  # unchanged


@pytest.mark.asyncio
async def test_demand_expiration(manager):
    # Register with already-expired timeout
    await manager.register_demand("expired", timeout_seconds=1)
    # Backdate in both the in-memory cache *and* the shared DB row, since
    # _purge_expired_demands reads from gpu_power_demands.
    backdated = datetime.now(timezone.utc) - timedelta(seconds=10)
    manager._demands["expired"].expires_at = backdated
    from app.services.power.gpu.runtime_state_store import upsert_demand
    upsert_demand(
        source="expired",
        registered_at=manager._demands["expired"].registered_at,
        expires_at=backdated,
        description=None,
    )
    await manager._purge_expired_demands()
    assert "expired" not in manager._demands


@pytest.mark.asyncio
async def test_unregister_demand(manager):
    await manager.register_demand("plugin_x")
    assert "plugin_x" in manager._demands
    removed = await manager.unregister_demand("plugin_x")
    assert removed is True
    assert "plugin_x" not in manager._demands


@pytest.mark.asyncio
async def test_get_status_returns_current_state(manager):
    manager._state = GpuPowerState.STANDBY
    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=2.5)):
        status = await manager.get_status()
        assert status.current_state == GpuPowerState.STANDBY
        assert status.detected is True
        assert status.vendor == "dev"
        assert status.usage_percent == 2.5
