"""
Power management services package.

Provides power management with:
- CPU frequency/power profile management
- Power monitoring and statistics
- Power presets
- Energy statistics
- Fan control with temperature curves
"""

from app.services.power.manager import (
    CpuPowerBackend,
    DevCpuPowerBackend,
    LinuxCpuPowerBackend,
    PowerManagerService,
    get_power_manager,
    start_power_manager,
    stop_power_manager,
    get_status as get_power_status,
)
from app.services.power.monitor import (
    start_power_monitor,
    stop_power_monitor,
    get_power_history,
    get_current_power,
    get_status as get_monitor_status,
)
from app.services.power.presets import (
    PowerPresetService,
    get_preset_service,
)
from app.services.power.energy import (
    EnergyPeriod,
    save_power_sample,
    get_period_stats,
    get_today_stats,
    get_week_stats,
    get_month_stats,
    get_hourly_samples,
    cleanup_old_samples,
    get_energy_price_config,
    update_energy_price_config,
    get_cumulative_energy_data,
)
from app.services.power.fan_control import (
    FanData,
    HysteresisState,
    FanControlBackend,
    DevFanControlBackend,
    LinuxFanControlBackend,
    FanControlService,
    get_fan_control_service,
    start_fan_control,
    stop_fan_control,
    get_service_status as get_fan_service_status,
)

__all__ = [
    # Manager
    "CpuPowerBackend",
    "DevCpuPowerBackend",
    "LinuxCpuPowerBackend",
    "PowerManagerService",
    "get_power_manager",
    "start_power_manager",
    "stop_power_manager",
    "get_power_status",
    # Monitor
    "start_power_monitor",
    "stop_power_monitor",
    "get_power_history",
    "get_current_power",
    "get_monitor_status",
    # Presets
    "PowerPresetService",
    "get_preset_service",
    # Energy
    "EnergyPeriod",
    "save_power_sample",
    "get_period_stats",
    "get_today_stats",
    "get_week_stats",
    "get_month_stats",
    "get_hourly_samples",
    "cleanup_old_samples",
    "get_energy_price_config",
    "update_energy_price_config",
    "get_cumulative_energy_data",
    # Fan Control
    "FanData",
    "HysteresisState",
    "FanControlBackend",
    "DevFanControlBackend",
    "LinuxFanControlBackend",
    "FanControlService",
    "get_fan_control_service",
    "start_fan_control",
    "stop_fan_control",
    "get_fan_service_status",
]
