from fastapi import APIRouter, Depends, HTTPException, status, Request
import threading
import os
import logging
import signal

from app.api import deps
from app.schemas.system import (
    AuditLoggingStatus,
    AuditLoggingToggle,
    AvailableDisksResponse,
    CreateArrayRequest,
    DeleteArrayRequest,
    DiskIOResponse,
    FormatDiskRequest,
    ProcessListResponse,
    QuotaStatus,
    RaidActionResponse,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidStatusResponse,
    SystemHealthResponse,
    SmartStatusResponse,
    StorageInfo,
    SystemInfo,
    TelemetryHistoryResponse,
)
from pydantic import BaseModel
from app.schemas.user import UserPublic
from app.services import disk_monitor
from app.services import raid as raid_service
from app.services import smart as smart_service
from app.services.audit_logger_db import get_audit_logger_db
from app.services import system as system_service
from app.services import telemetry as telemetry_service
from app.services.audit_logger import get_audit_logger

router = APIRouter()


@router.get("/info", response_model=SystemInfo)
async def get_system_info(_: UserPublic = Depends(deps.get_current_user)) -> SystemInfo:
    return system_service.get_system_info()


@router.get("/info/local", response_model=SystemInfo)
def get_system_info_local(request: Request) -> SystemInfo:
    """Local-only unauthenticated access for trusted localhost clients.

    This endpoint is intended for desktop integrations running on the same
    host (e.g. the Baludesk C++ backend). It rejects requests that do not
    originate from localhost to avoid exposing system telemetry over the
    network without authentication.
    """
    client_host = request.client.host if request.client else None
    allowed = {"127.0.0.1", "::1", "localhost"}
    if client_host not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
    return system_service.get_system_info()


@router.get("/storage", response_model=StorageInfo)
async def get_storage_info(_: UserPublic = Depends(deps.get_current_user)) -> StorageInfo:
    return system_service.get_storage_info()


@router.get("/storage/aggregated", response_model=StorageInfo)
async def get_aggregated_storage_info(_: UserPublic = Depends(deps.get_current_user)) -> StorageInfo:
    """Gibt aggregierte Speicherinformationen über alle Festplatten zurück.
    
    Berücksichtigt SMART-Daten aller Festplatten und RAID-Arrays.
    Bei RAID wird die effektive Kapazität berechnet.
    """
    return system_service.get_aggregated_storage_info()


@router.get("/quota", response_model=QuotaStatus)
async def get_quota(_: UserPublic = Depends(deps.get_current_user)) -> QuotaStatus:
    return system_service.get_quota_status()


@router.get("/processes", response_model=ProcessListResponse)
async def get_process_list(
    limit: int = 20,
    _: UserPublic = Depends(deps.get_current_user),
) -> ProcessListResponse:
    return system_service.get_process_list(limit=limit)


@router.get("/telemetry/history", response_model=TelemetryHistoryResponse)
async def get_telemetry_history(
    _: UserPublic = Depends(deps.get_current_user),
) -> TelemetryHistoryResponse:
    return telemetry_service.get_history()


@router.post("/shutdown")
async def shutdown_system(
    user: UserPublic = Depends(deps.get_current_admin),
) -> dict:
    """Schedule a graceful application shutdown (admin only).

    This endpoint returns immediately and schedules a short-timer that
    will exit the process, allowing the response to be delivered to the
    caller. An audit log entry is written.
    """
    audit = get_audit_logger()
    audit.log_system_event(action="shutdown_initiated", user=user.username, details={"method": "api"}, success=True)
    logging.getLogger(__name__).info("Shutdown requested via API by user %s", user.username)

    def _perform_exit() -> None:
        logging.getLogger(__name__).info("Performing graceful shutdown (sending SIGINT to process)")
        try:
            current_pid = os.getpid()
            parent_pid = os.getppid()

            # Try to send SIGTERM to parent process (start_dev.py) first
            # This ensures both backend and frontend are shut down
            try:
                import psutil
                parent = psutil.Process(parent_pid)
                parent_name = parent.name().lower()

                # Check if parent is Python (start_dev.py)
                if 'python' in parent_name:
                    logging.getLogger(__name__).info(f"Sending SIGTERM to parent process {parent_pid} ({parent_name})")
                    os.kill(parent_pid, signal.SIGTERM)
                    return
            except Exception as e:
                logging.getLogger(__name__).debug(f"Could not terminate parent: {e}")

            # Fallback: terminate current process
            os.kill(current_pid, signal.SIGINT)
        except Exception as e:
            # Fallback to hard exit if signal fails
            logging.getLogger(__name__).warning(f"Signal failed: {e}, falling back to os._exit")
            os._exit(0)

    # Give 1 second for the HTTP response to be delivered and for proxies
    # to flush. Then trigger shutdown.
    eta = 1
    timer = threading.Timer(float(eta), _perform_exit)
    timer.daemon = True
    timer.start()

    return {"message": "Shutdown scheduled", "initiated_by": user.username, "eta_seconds": eta}


@router.get("/smart/status", response_model=SmartStatusResponse)
async def get_smart_status(_: UserPublic = Depends(deps.get_current_user)) -> SmartStatusResponse:
    return smart_service.get_smart_status()


@router.get("/smart/mode")
async def get_smart_mode(_: UserPublic = Depends(deps.get_current_user)) -> dict[str, str]:
    """Get current SMART data mode in Dev-Mode (mock or real)."""
    from app.core.config import settings
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMART mode toggle is only available in dev mode"
        )
    mode = smart_service.get_dev_mode_state()
    return {"mode": mode}


@router.post("/smart/toggle-mode")
async def toggle_smart_mode(_: UserPublic = Depends(deps.get_current_user)) -> dict[str, str]:
    """Toggle between mock and real SMART data in Dev-Mode."""
    from app.core.config import settings
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMART mode toggle is only available in dev mode"
        )
    new_mode = smart_service.toggle_dev_mode()
    return {"mode": new_mode, "message": f"SMART mode switched to {new_mode}"}


@router.get("/raid/status", response_model=RaidStatusResponse)
async def get_raid_status(_: UserPublic = Depends(deps.get_current_user)) -> RaidStatusResponse:
    return raid_service.get_status()


@router.post("/raid/degrade", response_model=RaidActionResponse)
async def simulate_raid_failure(
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.simulate_failure(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/raid/rebuild", response_model=RaidActionResponse)
async def simulate_raid_rebuild(
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.simulate_rebuild(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/raid/finalize", response_model=RaidActionResponse)
async def finalize_raid_rebuild(
    payload: RaidSimulationRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    try:
        return raid_service.finalize_rebuild(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/disk-io/history", response_model=DiskIOResponse)
async def get_disk_io_history(_: UserPublic = Depends(deps.get_current_user)) -> DiskIOResponse:
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
async def configure_raid_options(
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
async def get_available_disks(_: UserPublic = Depends(deps.get_current_admin)) -> AvailableDisksResponse:
    """Get list of available disks for RAID or formatting."""
    try:
        return raid_service.get_available_disks()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/raid/format-disk", response_model=RaidActionResponse)
async def format_disk(
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
async def create_array(
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
                "raid_level": payload.raid_level,
                "devices": payload.devices,
                "mount_point": payload.mount_point
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
async def delete_array(
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
async def get_system_health(_: UserPublic = Depends(deps.get_current_user)) -> SystemHealthResponse:
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
async def add_mock_disk(
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
async def trigger_smart_test(
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
async def trigger_raid_scrub(
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
    payload: dict
    ttl_seconds: int | None = 3600


class ConfirmResponse(BaseModel):
    token: str
    expires_at: int


@router.post("/raid/confirm/request", response_model=ConfirmResponse)
async def request_raid_confirmation(
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
async def execute_raid_confirmation(
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


@router.get("/audit-logging", response_model=AuditLoggingStatus)
async def get_audit_logging_status(
    _: UserPublic = Depends(deps.get_current_admin),
) -> AuditLoggingStatus:
    """Get audit logging status (admin only)."""
    from app.core.config import settings
    audit_logger = get_audit_logger_db()

    return AuditLoggingStatus(
        enabled=audit_logger.is_enabled(),
        can_toggle=settings.is_dev_mode,
        dev_mode=settings.is_dev_mode
    )


@router.post("/audit-logging", response_model=AuditLoggingStatus)
async def toggle_audit_logging(
    payload: AuditLoggingToggle,
    current_admin: UserPublic = Depends(deps.get_current_admin),
) -> AuditLoggingStatus:
    """Toggle audit logging (admin only, dev mode only)."""
    from app.core.config import settings
    audit_logger = get_audit_logger_db()

    # Only allow toggling in dev mode
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit logging can only be toggled in development mode"
        )

    # Toggle the audit logger
    if payload.enabled:
        audit_logger.enable()
        audit_logger.log_system_config_change(
            action="audit_logging_enabled",
            user=current_admin.username,
            config_key="audit_logging",
            old_value=False,
            new_value=True,
            success=True
        )
    else:
        audit_logger.log_system_config_change(
            action="audit_logging_disabled",
            user=current_admin.username,
            config_key="audit_logging",
            old_value=True,
            new_value=False,
            success=True
        )
        audit_logger.disable()

    return AuditLoggingStatus(
        enabled=audit_logger.is_enabled(),
        can_toggle=settings.is_dev_mode,
        dev_mode=settings.is_dev_mode
    )
