"""
API routes for the Smart Device plugin system.

Mounted at /api/smart-devices/.

Read endpoints:  any authenticated user.
Write endpoints: admin only.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.models.smart_device import SmartDeviceSample
from app.models.user import User
from app.plugins.smart_device.manager import get_smart_device_manager
from app.plugins.smart_device.schemas import (
    DeviceCommandRequest,
    DeviceCommandResponse,
    DeviceTypeResponse,
    PowerSummaryResponse,
    SmartDeviceCreate,
    SmartDeviceHistoryResponse,
    SmartDeviceListResponse,
    SmartDeviceResponse,
    SmartDeviceUpdate,
)
from app.services.audit.logger_db import AuditLoggerDB

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _device_to_response(device, state=None) -> SmartDeviceResponse:
    """Convert a SmartDevice ORM instance to SmartDeviceResponse."""
    # capabilities may come back as a JSON string from some DB drivers
    caps = device.capabilities or []
    if isinstance(caps, str):
        caps = json.loads(caps)
    return SmartDeviceResponse(
        id=device.id,
        name=device.name,
        plugin_name=device.plugin_name,
        device_type_id=device.device_type_id,
        address=device.address,
        mac_address=device.mac_address,
        capabilities=caps,
        is_active=device.is_active,
        is_online=device.is_online,
        last_seen=device.last_seen,
        last_error=device.last_error,
        state=state,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /smart-devices/types  — All available device types
# ---------------------------------------------------------------------------

@router.get(
    "/types",
    response_model=List[DeviceTypeResponse],
    summary="List all available device types",
)
@user_limiter.limit(get_limit("admin_operations"))
def list_device_types(
    request: Request,
    response: Response,
    current_user: User = Depends(deps.get_current_user),
) -> List[DeviceTypeResponse]:
    """Return all device types offered by loaded smart_device plugins.

    **Requires authentication.**
    """
    manager = get_smart_device_manager()
    types_raw = manager.get_all_device_types()
    return [
        DeviceTypeResponse(
            type_id=t["type_id"],
            display_name=t["display_name"],
            manufacturer=t["manufacturer"],
            capabilities=t["capabilities"],
            config_schema=t.get("config_schema"),
            icon=t["icon"],
            plugin_name=t["plugin_name"],
        )
        for t in types_raw
    ]


# ---------------------------------------------------------------------------
# GET /smart-devices/power/summary  — Aggregated power data
# ---------------------------------------------------------------------------

@router.get(
    "/power/summary",
    response_model=PowerSummaryResponse,
    summary="Aggregated power consumption",
)
@user_limiter.limit(get_limit("admin_operations"))
def get_power_summary(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PowerSummaryResponse:
    """Return total and per-device power consumption.

    Data sourced from SHM (fresh polling data).
    **Requires authentication.**
    """
    manager = get_smart_device_manager()
    summary = manager.get_power_summary(db)
    return PowerSummaryResponse(**summary)


# ---------------------------------------------------------------------------
# GET /smart-devices/discover/{plugin}  — Trigger discovery
# ---------------------------------------------------------------------------

@router.get(
    "/discover/{plugin_name}",
    summary="Trigger device discovery for a plugin",
)
@user_limiter.limit(get_limit("admin_operations"))
async def discover_devices(
    request: Request,
    response: Response,
    plugin_name: str,
    current_user: User = Depends(deps.get_current_admin),
):
    """Ask a smart device plugin to scan the local network for compatible devices.

    Returns a list of discovered devices that can be added via POST /.
    **Admin only.**
    """
    manager = get_smart_device_manager()
    plugin = manager.get_plugin(plugin_name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{plugin_name}' is not loaded",
        )

    try:
        discovered = await plugin.discover_devices()
    except Exception as exc:
        logger.error("Discovery failed for plugin '%s': %s", plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery failed: {exc}",
        )

    return {
        "plugin_name": plugin_name,
        "discovered": [d.model_dump() for d in discovered],
    }


# ---------------------------------------------------------------------------
# GET /smart-devices/  — List all devices
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=SmartDeviceListResponse,
    summary="List all smart devices",
)
@user_limiter.limit(get_limit("admin_operations"))
def list_devices(
    request: Request,
    response: Response,
    plugin_name: Optional[str] = Query(default=None, description="Filter by plugin name"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SmartDeviceListResponse:
    """Return all registered smart devices with their current state.

    **Requires authentication.**
    """
    manager = get_smart_device_manager()
    devices = manager.list_devices(db, plugin_name=plugin_name)

    device_responses = []
    for device in devices:
        state = manager.get_device_state(device.id, db)
        device_responses.append(_device_to_response(device, state=state))

    return SmartDeviceListResponse(devices=device_responses, total=len(device_responses))


# ---------------------------------------------------------------------------
# POST /smart-devices/  — Create device (Admin)
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=SmartDeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new smart device",
)
@user_limiter.limit(get_limit("admin_operations"))
def create_device(
    request: Request,
    response: Response,
    data: SmartDeviceCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> SmartDeviceResponse:
    """Register a new smart device.

    Credentials in ``config`` are encrypted before storage.
    **Admin only.**
    """
    manager = get_smart_device_manager()
    try:
        device = manager.create_device(db, data, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    AuditLoggerDB().log_event(
        event_type="SMART_DEVICE",
        action="create_device",
        user=current_user.username,
        resource=f"device:{device.id}",
        success=True,
        details={"device_id": device.id, "name": device.name, "plugin": device.plugin_name},
    )

    return _device_to_response(device)


# ---------------------------------------------------------------------------
# GET /smart-devices/{id}  — Device detail + current state
# ---------------------------------------------------------------------------

@router.get(
    "/{device_id}",
    response_model=SmartDeviceResponse,
    summary="Get smart device detail",
)
@user_limiter.limit(get_limit("admin_operations"))
def get_device(
    request: Request,
    response: Response,
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SmartDeviceResponse:
    """Return detail and current state for a single smart device.

    **Requires authentication.**
    """
    manager = get_smart_device_manager()
    device = manager.get_device(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Smart device {device_id} not found",
        )

    state = manager.get_device_state(device_id, db)
    return _device_to_response(device, state=state)


# ---------------------------------------------------------------------------
# PATCH /smart-devices/{id}  — Update device (Admin)
# ---------------------------------------------------------------------------

@router.patch(
    "/{device_id}",
    response_model=SmartDeviceResponse,
    summary="Update smart device configuration",
)
@user_limiter.limit(get_limit("admin_operations"))
def update_device(
    request: Request,
    response: Response,
    device_id: int,
    data: SmartDeviceUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> SmartDeviceResponse:
    """Partially update a smart device.

    If ``config`` is provided it is re-encrypted before storage.
    **Admin only.**
    """
    manager = get_smart_device_manager()
    device = manager.get_device(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Smart device {device_id} not found",
        )

    try:
        updated = manager.update_device(db, device, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    AuditLoggerDB().log_event(
        event_type="SMART_DEVICE",
        action="update_device",
        user=current_user.username,
        resource=f"device:{device_id}",
        success=True,
        details={
            "device_id": device_id,
            "updates": list(data.model_dump(exclude_unset=True).keys()),
        },
    )

    state = manager.get_device_state(device_id, db)
    return _device_to_response(updated, state=state)


# ---------------------------------------------------------------------------
# DELETE /smart-devices/{id}  — Delete device (Admin)
# ---------------------------------------------------------------------------

@router.delete(
    "/{device_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a smart device",
)
@user_limiter.limit(get_limit("admin_operations"))
def delete_device(
    request: Request,
    response: Response,
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> None:
    """Permanently delete a smart device and all its samples.

    **Admin only.**
    """
    manager = get_smart_device_manager()
    device = manager.get_device(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Smart device {device_id} not found",
        )

    device_name = device.name
    manager.delete_device(db, device)

    AuditLoggerDB().log_event(
        event_type="SMART_DEVICE",
        action="delete_device",
        user=current_user.username,
        resource=f"device:{device_id}",
        success=True,
        details={"device_id": device_id, "name": device_name},
    )


# ---------------------------------------------------------------------------
# POST /smart-devices/{id}/command  — Execute command
# ---------------------------------------------------------------------------

@router.post(
    "/{device_id}/command",
    response_model=DeviceCommandResponse,
    summary="Execute a command on a smart device",
)
@user_limiter.limit(get_limit("admin_operations"))
async def execute_command(
    request: Request,
    response: Response,
    device_id: int,
    cmd: DeviceCommandRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> DeviceCommandResponse:
    """Send a control command to a smart device (switch on/off, dim, colour).

    **Admin only.**
    """
    manager = get_smart_device_manager()
    try:
        result = await manager.execute_command(
            device_id=device_id,
            capability=cmd.capability,
            command=cmd.command,
            params=cmd.params,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Command execution failed for device %d: %s", device_id, exc)
        return DeviceCommandResponse(success=False, error=str(exc))

    AuditLoggerDB().log_event(
        event_type="SMART_DEVICE",
        action="execute_command",
        user=current_user.username,
        resource=f"device:{device_id}",
        success=result["success"],
        details={
            "device_id": device_id,
            "capability": cmd.capability,
            "command": cmd.command,
            "params": cmd.params,
        },
    )

    return DeviceCommandResponse(
        success=result["success"],
        state=result.get("state"),
        error=result.get("error"),
    )


# ---------------------------------------------------------------------------
# GET /smart-devices/{id}/history  — State history
# ---------------------------------------------------------------------------

@router.get(
    "/{device_id}/history",
    response_model=SmartDeviceHistoryResponse,
    summary="Get state history for a smart device",
)
@user_limiter.limit(get_limit("admin_operations"))
def get_device_history(
    request: Request,
    response: Response,
    device_id: int,
    capability: str = Query(default="switch", description="Capability to retrieve history for"),
    hours: int = Query(default=24, ge=1, le=720, description="How many hours of history"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SmartDeviceHistoryResponse:
    """Return time-series samples for a given device and capability.

    **Requires authentication.**
    """
    manager = get_smart_device_manager()
    device = manager.get_device(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Smart device {device_id} not found",
        )

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(hours=hours)

    try:
        rows = (
            db.query(SmartDeviceSample)
            .filter(
                SmartDeviceSample.device_id == device_id,
                SmartDeviceSample.capability == capability,
                SmartDeviceSample.timestamp >= period_start,
                SmartDeviceSample.timestamp <= period_end,
            )
            .order_by(SmartDeviceSample.timestamp.asc())
            .all()
        )
    except Exception as exc:
        logger.error("History query failed for device %d: %s", device_id, exc)
        rows = []

    samples = []
    for row in rows:
        try:
            data = json.loads(row.data_json)
        except Exception:
            data = {"raw": row.data_json}
        samples.append({"timestamp": row.timestamp.isoformat(), **data})

    return SmartDeviceHistoryResponse(
        device_id=device_id,
        capability=capability,
        samples=samples,
        period_start=period_start,
        period_end=period_end,
    )
