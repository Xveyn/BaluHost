"""Tests for CPU cap enforcement (re-assert + drift detection)."""
import pytest

from app.schemas.power import PowerProfile, PowerProfileConfig, ServicePowerProperty
from app.services.power.cpu_dev_backend import DevCpuPowerBackend
from app.services.power.manager import PowerManagerService


@pytest.fixture(autouse=True)
def _reset_override():
    mgr = PowerManagerService()
    mgr._boost_max_override = None
    mgr._last_drift = None
    mgr._cap_unenforceable = False
    yield
    mgr._boost_max_override = None
    mgr._last_drift = None
    mgr._cap_unenforceable = False


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


class _DriftBackend(DevCpuPowerBackend):
    """Dev backend whose read-back can be forced to differ from desired."""
    def __init__(self, drift_governor=None, drift_max=None):
        super().__init__()
        self._drift_governor = drift_governor
        self._drift_max = drift_max
        self.apply_calls = []

    async def apply_profile(self, config):
        self.apply_calls.append(config)
        return await super().apply_profile(config)

    async def read_enforcement_state(self):
        if self._drift_governor is not None or self._drift_max is not None:
            return self._drift_governor, self._drift_max
        return await super().read_enforcement_state()


@pytest.mark.asyncio
async def test_enforce_rewrites_on_drift(monkeypatch):
    mgr = PowerManagerService()
    mgr._current_profile = PowerProfile.IDLE
    backend = _DriftBackend(drift_governor="performance", drift_max=4668)
    mgr._backend = backend

    async def desired(profile):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=340, max_freq_mhz=400, description="hold",
        )
    monkeypatch.setattr(mgr, "_desired_config_for", desired)

    await mgr._enforce_current_profile()

    assert len(backend.apply_calls) == 1
    assert mgr._last_drift is not None
    assert mgr._last_drift["found"] == "performance/4668"


@pytest.mark.asyncio
async def test_enforce_noop_when_in_sync(monkeypatch):
    mgr = PowerManagerService()
    mgr._current_profile = PowerProfile.IDLE
    backend = _DriftBackend()
    mgr._backend = backend
    await backend.apply_profile(PowerProfileConfig(
        profile=PowerProfile.IDLE, governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=340, max_freq_mhz=400, description="hold"))
    backend.apply_calls.clear()

    async def desired(profile):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=340, max_freq_mhz=400, description="hold")
    monkeypatch.setattr(mgr, "_desired_config_for", desired)

    await mgr._enforce_current_profile()

    assert backend.apply_calls == []
