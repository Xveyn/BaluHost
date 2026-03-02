"""
Service intensity tracking for power management.

Determines the power intensity of running services by combining data from:
1. Active power demands (services with registered power requirements)
2. Registered background services (from service_status registry)
3. Process tracker metrics (BaluHost processes with CPU/RAM usage)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

from app.schemas.power import (
    PowerDemandInfo,
    PowerProfile,
    ServiceIntensityInfo,
    ServiceIntensityResponse,
    ServicePowerProperty,
)

logger = logging.getLogger(__name__)

# Priority order for intensity comparison
INTENSITY_PRIORITY: Dict[ServicePowerProperty, int] = {
    ServicePowerProperty.IDLE: 0,
    ServicePowerProperty.LOW: 1,
    ServicePowerProperty.MEDIUM: 2,
    ServicePowerProperty.SURGE: 3,
}

# Display name mapping for service identifiers
DISPLAY_NAMES: Dict[str, str] = {
    # Power demand sources
    "backup_create": "Backup erstellen",
    "backup_restore": "Backup wiederherstellen",
    "raid_rebuild": "RAID Rebuild",
    "raid_scrub": "RAID Scrub",
    "file_upload": "Datei-Upload",
    "file_download": "Datei-Download",
    "smart_scan": "SMART Scan",
    "sync_operation": "Sync Operation",
    # Process tracker names
    "baluhost-backend": "BaluHost Backend",
    "baluhost-frontend": "BaluHost Frontend",
    "baluhost-tui": "BaluHost TUI",
}


def cpu_to_intensity(cpu_percent: float) -> ServicePowerProperty:
    """
    Convert CPU usage percentage to intensity level.

    Thresholds:
    - >= 60%: SURGE
    - >= 30%: MEDIUM
    - >= 10%: LOW
    - < 10%: IDLE
    """
    if cpu_percent >= 60.0:
        return ServicePowerProperty.SURGE
    elif cpu_percent >= 30.0:
        return ServicePowerProperty.MEDIUM
    elif cpu_percent >= 10.0:
        return ServicePowerProperty.LOW
    return ServicePowerProperty.IDLE


def get_display_name(source: str) -> str:
    """
    Get a human-readable display name for a source identifier.

    Maps internal identifiers to user-friendly names.
    """
    return DISPLAY_NAMES.get(source, source.replace("_", " ").replace("-", " ").title())


def service_state_to_intensity(is_running: bool, has_error: bool = False) -> ServicePowerProperty:
    """
    Convert service state to intensity level.

    Running services are considered LOW intensity (background work).
    Stopped services are IDLE, errored services are also shown as IDLE.
    """
    if has_error:
        return ServicePowerProperty.IDLE
    if is_running:
        return ServicePowerProperty.LOW
    return ServicePowerProperty.IDLE


async def get_service_intensities(
    demands: Dict[str, PowerDemandInfo],
    current_profile: PowerProfile,
) -> ServiceIntensityResponse:
    """
    Get intensity information for all tracked services and processes.

    Combines data from four sources:
    1. Active power demands (services that have registered power requirements)
    2. Registered background services (from service_status registry)
    3. Process tracker metrics (BaluHost processes with CPU/RAM usage)
    4. Inferred intensity from CPU usage (for processes without demands)

    Args:
        demands: Currently active power demands.
        current_profile: The currently active power profile.

    Returns:
        ServiceIntensityResponse with list of all services and their intensity levels
    """
    services: List[ServiceIntensityInfo] = []
    seen_sources: set = set()
    highest_intensity = ServicePowerProperty.IDLE

    # 1. Add services from active power demands
    for source, demand in demands.items():
        seen_sources.add(source)

        intensity = demand.power_property or ServicePowerProperty(demand.level.value)

        if INTENSITY_PRIORITY[intensity] > INTENSITY_PRIORITY[highest_intensity]:
            highest_intensity = intensity

        service_info = ServiceIntensityInfo(
            name=source,
            display_name=get_display_name(source),
            intensity_level=intensity,
            intensity_source="demand",
            has_active_demand=True,
            demand_description=demand.description,
            demand_registered_at=demand.registered_at,
            demand_expires_at=demand.expires_at,
            is_alive=True,
        )
        services.append(service_info)

    # 2. Add registered background services from service_status
    try:
        from app.services.service_status import _service_registry

        for service_name, registry in _service_registry.items():
            # Skip if already added from demands
            if service_name in seen_sources:
                continue
            seen_sources.add(service_name)

            # Get service status
            status_fn = registry.get("get_status")
            display_name = registry.get("display_name", service_name)

            is_running = False
            has_error = False

            if status_fn:
                try:
                    status_data = status_fn()
                    is_running = status_data.get("is_running", False)
                    has_error = status_data.get("has_error", False)
                except Exception:
                    pass

            # Derive intensity from service state
            intensity = service_state_to_intensity(is_running, has_error)

            if INTENSITY_PRIORITY[intensity] > INTENSITY_PRIORITY[highest_intensity]:
                highest_intensity = intensity

            service_info = ServiceIntensityInfo(
                name=service_name,
                display_name=display_name,
                intensity_level=intensity,
                intensity_source="service",
                has_active_demand=False,
                is_alive=is_running,
            )
            services.append(service_info)

    except Exception as e:
        logger.warning(f"Could not get registered services: {e}")

    # 3. Add services from process tracker
    try:
        from app.services.monitoring.orchestrator import MonitoringOrchestrator

        orchestrator = MonitoringOrchestrator.get_instance()
        process_status = orchestrator.process_tracker.get_current_status()

        for process_name, sample in process_status.items():
            if sample is None:
                continue

            # Skip if already added from demands or services
            if process_name in seen_sources:
                continue
            seen_sources.add(process_name)

            # Derive intensity from CPU usage
            intensity = cpu_to_intensity(sample.cpu_percent)

            if INTENSITY_PRIORITY[intensity] > INTENSITY_PRIORITY[highest_intensity]:
                highest_intensity = intensity

            service_info = ServiceIntensityInfo(
                name=process_name,
                display_name=get_display_name(process_name),
                intensity_level=intensity,
                intensity_source="cpu_usage",
                has_active_demand=False,
                cpu_percent=sample.cpu_percent,
                memory_mb=sample.memory_mb,
                pid=sample.pid,
                is_alive=sample.is_alive,
            )
            services.append(service_info)

    except Exception as e:
        logger.warning(f"Could not get process tracker data: {e}")

    # Sort by intensity level (highest first), then by name
    services.sort(
        key=lambda s: (-INTENSITY_PRIORITY[s.intensity_level], s.display_name.lower())
    )

    return ServiceIntensityResponse(
        services=services,
        timestamp=datetime.now(timezone.utc),
        total_services=len(services),
        active_demands_count=sum(1 for s in services if s.has_active_demand),
        highest_intensity=highest_intensity,
    )
