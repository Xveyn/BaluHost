import pytest
from app.services.power.gpu.dev_backend import DevGpuPowerBackend
from app.services.power.gpu.protocol import GpuPowerBackend
from app.schemas.gpu_power import GpuPowerState, GpuPowerCapabilities


def test_dev_backend_implements_protocol():
    backend = DevGpuPowerBackend()
    assert isinstance(backend, GpuPowerBackend)


def test_dev_backend_detected():
    backend = DevGpuPowerBackend()
    assert backend.detected is True
    assert backend.vendor == "dev"


def test_dev_backend_default_state():
    backend = DevGpuPowerBackend()
    assert backend._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_dev_backend_apply_state():
    backend = DevGpuPowerBackend()
    success, error = await backend.apply_state(GpuPowerState.STANDBY, config=None)
    assert success is True
    assert error is None
    assert await backend.current_state() == GpuPowerState.STANDBY


@pytest.mark.asyncio
async def test_dev_backend_has_write_permission():
    backend = DevGpuPowerBackend()
    assert await backend.has_write_permission() is True


def test_dev_backend_capabilities():
    backend = DevGpuPowerBackend()
    caps = backend.capabilities()
    assert isinstance(caps, GpuPowerCapabilities)
    assert caps.vendor == "dev"
