"""Tests for CPU cap enforcement (re-assert + drift detection)."""
import pytest

from app.schemas.power import PowerProfile, PowerProfileConfig
from app.services.power.cpu_dev_backend import DevCpuPowerBackend


@pytest.mark.asyncio
async def test_dev_backend_reports_enforcement_state_after_apply():
    backend = DevCpuPowerBackend()
    config = PowerProfileConfig(
        profile=PowerProfile.IDLE,
        governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=340,
        max_freq_mhz=400,
        description="test",
    )
    await backend.apply_profile(config)

    governor, max_mhz = await backend.read_enforcement_state()

    assert governor == "powersave"
    assert max_mhz == 400
