"""
Hardware services package.

Provides hardware management with:
- RAID array management (mdadm, dev-mode simulation)
- SMART disk health monitoring
- SSD cache management (bcache, dev-mode simulation)
- CPU/system sensor data (temperature, frequency)
"""

from app.services.hardware.raid import (
    RaidBackend,
    DevRaidBackend,
    MdadmRaidBackend,
    MdstatInfo,
    get_status,
    simulate_failure,
    simulate_rebuild,
    finalize_rebuild,
    configure_array,
    get_available_disks,
    format_disk,
    create_array,
    delete_array,
    add_mock_disk,
    request_confirmation,
    execute_confirmation,
    scrub_now,
    start_scrub_scheduler,
    stop_scrub_scheduler,
    get_scrub_scheduler_status,
)
from app.services.hardware.smart import (
    SmartUnavailableError,
    get_smart_status,
    get_cached_smart_status,
    invalidate_smart_cache,
    run_smart_self_test,
    start_smart_scheduler,
    stop_smart_scheduler,
    get_smart_scheduler_status,
    get_dev_mode_state,
    toggle_dev_mode,
    get_smart_device_models,
    get_smart_device_order,
)
from app.services.hardware.ssd_cache import (
    SsdCacheBackend,
    DevSsdCacheBackend,
    BcacheSsdCacheBackend,
    get_all_cache_statuses,
    get_cache_status,
    attach_cache,
    detach_cache,
    configure_cache,
    set_external_bitmap,
    get_cache_devices,
    get_cached_arrays,
    request_cache_confirmation,
    execute_cache_confirmation,
)
from app.services.hardware.sensors import (
    CPUSensorData,
    get_cpu_frequency,
    get_cpu_temperatures,
    get_cpu_sensor_data,
    check_sensor_availability,
)

__all__ = [
    # RAID
    "RaidBackend",
    "DevRaidBackend",
    "MdadmRaidBackend",
    "MdstatInfo",
    "get_status",
    "simulate_failure",
    "simulate_rebuild",
    "finalize_rebuild",
    "configure_array",
    "get_available_disks",
    "format_disk",
    "create_array",
    "delete_array",
    "add_mock_disk",
    "request_confirmation",
    "execute_confirmation",
    "scrub_now",
    "start_scrub_scheduler",
    "stop_scrub_scheduler",
    "get_scrub_scheduler_status",
    # SMART
    "SmartUnavailableError",
    "get_smart_status",
    "get_cached_smart_status",
    "invalidate_smart_cache",
    "run_smart_self_test",
    "start_smart_scheduler",
    "stop_smart_scheduler",
    "get_smart_scheduler_status",
    "get_dev_mode_state",
    "toggle_dev_mode",
    "get_smart_device_models",
    "get_smart_device_order",
    # SSD Cache
    "SsdCacheBackend",
    "DevSsdCacheBackend",
    "BcacheSsdCacheBackend",
    "get_all_cache_statuses",
    "get_cache_status",
    "attach_cache",
    "detach_cache",
    "configure_cache",
    "set_external_bitmap",
    "get_cache_devices",
    "get_cached_arrays",
    "request_cache_confirmation",
    "execute_cache_confirmation",
    # Sensors
    "CPUSensorData",
    "get_cpu_frequency",
    "get_cpu_temperatures",
    "get_cpu_sensor_data",
    "check_sensor_availability",
]
