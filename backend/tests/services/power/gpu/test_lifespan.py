"""Lifespan integration: start/stop and clean shutdown."""
import pytest

from app.schemas.gpu_power import GpuPowerState
from app.services.power.gpu.manager import (
    GpuPowerManagerService,
    get_gpu_power_manager,
    start_gpu_power_manager,
    stop_gpu_power_manager,
)


@pytest.fixture(autouse=True)
def _reset():
    GpuPowerManagerService._instance = None
    yield
    GpuPowerManagerService._instance = None


@pytest.mark.asyncio
async def test_start_then_stop():
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    assert mgr._is_running is True
    await stop_gpu_power_manager()
    assert mgr._is_running is False


@pytest.mark.asyncio
async def test_stop_returns_to_active():
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    mgr._state = GpuPowerState.DEEP_IDLE
    await stop_gpu_power_manager()
    # Backend should have been asked to apply ACTIVE on shutdown
    # Only DevGpuPowerBackend records last applied state via current_state();
    # real hardware backends (NVIDIA, AMD) do not expose a readable state.
    if mgr._backend is not None and mgr._backend.detected:
        from app.services.power.gpu.dev_backend import DevGpuPowerBackend
        if isinstance(mgr._backend, DevGpuPowerBackend):
            assert await mgr._backend.current_state() == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_double_start_is_idempotent():
    await start_gpu_power_manager()
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    assert mgr._is_running is True
    await stop_gpu_power_manager()
