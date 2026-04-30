import pytest
from pydantic import ValidationError
from app.schemas.gpu_power import (
    GpuPowerState,
    AmdProfileMode,
    AmdStateConfig,
    NvidiaStateConfig,
    GpuPowerConfig,
    GpuPowerDemandInfo,
    GpuPowerStatus,
    GpuPowerCapabilities,
)


def test_gpu_power_state_values():
    assert GpuPowerState.ACTIVE.value == "active"
    assert GpuPowerState.STANDBY.value == "standby"
    assert GpuPowerState.DEEP_IDLE.value == "deep_idle"


def test_gpu_power_config_defaults():
    config = GpuPowerConfig()
    assert config.enabled is False
    assert config.idle_window_seconds == 30
    assert config.deep_idle_extra_seconds == 120
    assert config.deep_idle_grace_seconds == 5
    assert config.usage_threshold_percent == 5.0
    assert config.monitor_interval_seconds == 5
    assert config.amd_active.performance_level == "auto"
    assert config.amd_standby.profile_mode == AmdProfileMode.POWER_SAVING
    assert config.amd_deep_idle.performance_level == "low"


def test_gpu_power_config_idle_window_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(idle_window_seconds=5)  # below ge=10
    with pytest.raises(ValidationError):
        GpuPowerConfig(idle_window_seconds=601)  # above le=600


def test_gpu_power_config_deep_idle_extra_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(deep_idle_extra_seconds=29)
    with pytest.raises(ValidationError):
        GpuPowerConfig(deep_idle_extra_seconds=3601)


def test_gpu_power_config_usage_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(usage_threshold_percent=-1.0)
    with pytest.raises(ValidationError):
        GpuPowerConfig(usage_threshold_percent=51.0)


def test_amd_state_config_optional_fields():
    cfg = AmdStateConfig()
    assert cfg.performance_level is None
    assert cfg.profile_mode is None


def test_nvidia_state_config_clock_validation():
    cfg = NvidiaStateConfig(min_clock_mhz=210, max_clock_mhz=1500, power_limit_watts=100)
    assert cfg.min_clock_mhz == 210
    assert cfg.max_clock_mhz == 1500
    assert cfg.power_limit_watts == 100


def test_gpu_power_demand_info_required_fields():
    from datetime import datetime, timezone
    info = GpuPowerDemandInfo(source="test", registered_at=datetime.now(timezone.utc))
    assert info.source == "test"
    assert info.expires_at is None


def test_gpu_power_capabilities_defaults():
    caps = GpuPowerCapabilities(vendor=None)
    assert caps.amd_performance_levels == []
    assert caps.amd_profile_modes == []
    assert caps.nvidia_min_clock_mhz is None
