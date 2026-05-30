"""Tests for CPU cap enforcement (re-assert + drift detection)."""
import pytest

from app.schemas.power import PowerProfile, PowerProfileConfig
from app.services.power.cpu_dev_backend import DevCpuPowerBackend


@pytest.fixture(autouse=True)
def _reset_override():
    from app.services.power.manager import PowerManagerService
    mgr = PowerManagerService()
    mgr._boost_max_override = None
    yield
    mgr._boost_max_override = None


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


from app.schemas.power import ServicePowerProperty
from app.services.power.manager import PowerManagerService


@pytest.mark.asyncio
async def test_desired_config_floors_hold_cap_at_400(monkeypatch):
    mgr = PowerManagerService()

    async def fake_preset_config(prop):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=200, max_freq_mhz=300, description="low preset",
        )

    monkeypatch.setattr(mgr, "_get_profile_config_from_preset", fake_preset_config)

    config = await mgr._desired_config_for(PowerProfile.IDLE)

    assert config.max_freq_mhz == 400
    assert config.min_freq_mhz == int(400 * 0.85)


@pytest.mark.asyncio
async def test_desired_config_applies_boost_override_on_surge(monkeypatch):
    mgr = PowerManagerService()
    mgr._boost_max_override = 3000

    async def fake_preset_config(prop):
        return PowerProfileConfig(
            profile=PowerProfile.SURGE, governor="performance",
            energy_performance_preference="performance",
            min_freq_mhz=3600, max_freq_mhz=None, description="surge",
        )

    monkeypatch.setattr(mgr, "_get_profile_config_from_preset", fake_preset_config)

    config = await mgr._desired_config_for(PowerProfile.SURGE)

    assert config.max_freq_mhz == 3000
