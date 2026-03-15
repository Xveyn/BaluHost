from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from typing import Any
from pydantic import BaseModel

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.core.power_rating import requires_power
from app.schemas.power import ServicePowerProperty
from app.schemas.system import (
    AvailableDisksResponse,
    CreateArrayRequest,
    DeleteArrayRequest,
    DiskIOResponse,
    FormatDiskRequest,
    RaidActionResponse,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidStatusResponse,
    SystemHealthResponse,
)
from app.schemas.user import UserPublic
from app.services import disk_monitor
from app.services import raid as raid_service
from app.services import smart as smart_service
from app.services import system as system_service
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


@router.get("/raid/status", response_model=RaidStatusResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_raid_status(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> RaidStatusResponse:
    return raid_service.get_status()


@router.post("/raid/degrade", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def simulate_raid_failure(
    request: Request,
    response: Response,
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.simulate_failure(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/raid/rebuild", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=86400, description="RAID rebuild")
async def simulate_raid_rebuild(
    request: Request,
    response: Response,
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.simulate_rebuild(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/raid/finalize", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600, description="Finalizing RAID rebuild")
async def finalize_raid_rebuild(
    request: Request,
    response: Response,
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.finalize_rebuild(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/disk-io/history", response_model=DiskIOResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_disk_io_history(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> DiskIOResponse:
    """Get real-time disk I/O history for all physical disks."""
    history = disk_monitor.get_disk_io_history()
    from app.schemas.system import DiskIOHistory, DiskIOSample
    from app.services.smart import get_smart_device_models, get_smart_device_order
    import re
    import platform

    model_map = get_smart_device_models()

    # Erstelle reverse mapping: psutil disk name -> SMART model
    psutil_to_model: dict[str, str] = {}

    is_windows = platform.system().lower() == 'windows'

    if is_windows:
        # Auf Windows: Verwende die Scan-Reihenfolge von smartctl
        # smartctl --scan gibt Geräte in der Reihenfolge zurück, die PhysicalDrive0, 1, 2, ... entspricht
        device_order = get_smart_device_order()

        for index, smart_name in enumerate(device_order):
            model = model_map.get(smart_name)
            if model:
                psutil_name = f'PhysicalDrive{index}'
                psutil_to_model[psutil_name] = model
                psutil_to_model[psutil_name.lower()] = model
    else:
        # Linux: Direktes Mapping (sda, nvme0n1, etc.)
        for smart_name, model in model_map.items():
            clean_name = smart_name.replace('/dev/', '').lower()
            psutil_to_model[clean_name] = model

    disks = []
    for disk_name, samples in history.items():
        disk_lower = disk_name.lower()

        # Versuche direktes Mapping
        model = psutil_to_model.get(disk_name) or psutil_to_model.get(disk_lower)

        disks.append(DiskIOHistory(
            diskName=disk_name,
            model=model,
            samples=[DiskIOSample(**sample) for sample in samples]
        ))

    return DiskIOResponse(disks=disks, interval=1.0)


@router.post("/raid/options", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def configure_raid_options(
    request: Request,
    response: Response,
    payload: RaidOptionsRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.configure_array(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/raid/available-disks", response_model=AvailableDisksResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_available_disks(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_admin)) -> AvailableDisksResponse:
    """Get list of available disks for RAID or formatting."""
    try:
        return raid_service.get_available_disks()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/raid/format-disk", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.MEDIUM, timeout_seconds=1800, description="Formatting disk")
async def format_disk(
    request: Request,
    response: Response,
    payload: FormatDiskRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Format a disk with the specified filesystem."""
    try:
        return raid_service.format_disk(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/raid/create-array", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=7200, description="Creating RAID array")
async def create_array(
    request: Request,
    response: Response,
    payload: CreateArrayRequest,
    current_admin: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Create a new RAID array."""
    audit_logger = get_audit_logger_db()

    try:
        result = raid_service.create_array(payload)

        audit_logger.log_raid_operation(
            action="raid_array_created",
            user=current_admin.username,
            raid_array=payload.name,
            details={
                "raid_level": payload.level,
                "devices": payload.devices,
                "spare_devices": payload.spare_devices,
            },
            success=True
        )

        return result
    except ValueError as exc:
        audit_logger.log_raid_operation(
            action="raid_array_create_failed",
            user=current_admin.username,
            raid_array=payload.name,
            details={"error": str(exc)},
            success=False,
            error_message=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        audit_logger.log_raid_operation(
            action="raid_array_create_failed",
            user=current_admin.username,
            raid_array=payload.name,
            details={"error": str(exc)},
            success=False,
            error_message=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/raid/delete-array", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_array(
    request: Request,
    response: Response,
    payload: DeleteArrayRequest,
    current_admin: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Delete a RAID array."""
    audit_logger = get_audit_logger_db()

    try:
        result = raid_service.delete_array(payload)

        audit_logger.log_raid_operation(
            action="raid_array_deleted",
            user=current_admin.username,
            raid_array=payload.name,
            details={"force": payload.force if hasattr(payload, 'force') else False},
            success=True
        )

        return result
    except ValueError as exc:
        audit_logger.log_raid_operation(
            action="raid_array_delete_failed",
            user=current_admin.username,
            raid_array=payload.name,
            details={"error": str(exc)},
            success=False,
            error_message=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        audit_logger.log_raid_operation(
            action="raid_array_delete_failed",
            user=current_admin.username,
            raid_array=payload.name,
            details={"error": str(exc)},
            success=False,
            error_message=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/health", response_model=SystemHealthResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_system_health(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> SystemHealthResponse:
    """Aggregated health summary combining system, SMART, RAID and disk I/O info."""
    from app.services import disk_monitor

    system_info = system_service.get_system_info()

    # SMART data: best-effort, may fallback to mock
    try:
        smart_info = smart_service.get_smart_status()
    except Exception:
        smart_info = None

    # RAID status: optional
    try:
        raid_info = raid_service.get_status()
    except Exception:
        raid_info = None

    disk_io = disk_monitor.get_latest_disk_io()

    return SystemHealthResponse(
        status="ok",
        system=system_info,
        smart=smart_info,
        raid=raid_info,
        disk_io=disk_io,
    )


# Dev-Mode: Mock Disk Management
class AddMockDiskRequest(BaseModel):
    letter: str
    size_gb: int
    name: str
    purpose: str


@router.post("/raid/dev/add-mock-disk", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def add_mock_disk(
    request: Request,
    response: Response,
    payload: AddMockDiskRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Dev-Mode only: Add a simulated mock disk to the available disks pool."""
    from app.core.config import settings

    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock disk management is only available in dev mode"
        )

    try:
        return raid_service.add_mock_disk(payload.letter, payload.size_gb, payload.name, payload.purpose)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


class SmartTestRequest(BaseModel):
    device: str
    type: str = "short"  # short or long


@router.post("/smart/test")
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.MEDIUM, timeout_seconds=3600, description="Running SMART self-test")
async def trigger_smart_test(
    request: Request,
    response: Response,
    payload: SmartTestRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> dict:
    """Trigger a SMART self-test on a given device (admin only)."""
    try:
        msg = smart_service.run_smart_self_test(payload.device, payload.type)
        return {"message": msg}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


class ScrubRequest(BaseModel):
    array: str | None = None


@router.post("/raid/scrub", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600, description="Running RAID scrub")
async def trigger_raid_scrub(
    request: Request,
    response: Response,
    payload: ScrubRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Trigger an immediate RAID scrub/check for a specific array or all arrays (admin only)."""
    try:
        return raid_service.scrub_now(payload.array)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# Two-step confirmation API for destructive RAID operations
class ConfirmRequest(BaseModel):
    action: str
    payload: dict[str, Any]
    ttl_seconds: int | None = 3600


class ConfirmResponse(BaseModel):
    token: str
    expires_at: int


@router.post("/raid/confirm/request", response_model=ConfirmResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def request_raid_confirmation(
    request: Request,
    response: Response,
    payload: ConfirmRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> ConfirmResponse:
    """Request a one-time confirmation token for a destructive RAID action.

    Supported actions: `delete_array`, `format_disk`, `create_array`.
    """
    allowed = {"delete_array", "format_disk", "create_array"}
    if payload.action not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {payload.action}")
    try:
        res = raid_service.request_confirmation(payload.action, payload.payload, payload.ttl_seconds or 3600)
        return ConfirmResponse(**res)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


class ExecuteConfirmRequest(BaseModel):
    token: str


@router.post("/raid/confirm/execute", response_model=RaidActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def execute_raid_confirmation(
    request: Request,
    response: Response,
    payload: ExecuteConfirmRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Execute a previously requested confirmation token (one-time).
    """
    try:
        resp = raid_service.execute_confirmation(payload.token)
        return resp
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
