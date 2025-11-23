from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.schemas.system import (
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
from app.services import system as system_service
from app.services import telemetry as telemetry_service

router = APIRouter()


@router.get("/info", response_model=SystemInfo)
async def get_system_info(_: UserPublic = Depends(deps.get_current_user)) -> SystemInfo:
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
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Create a new RAID array."""
    try:
        return raid_service.create_array(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/raid/delete-array", response_model=RaidActionResponse)
async def delete_array(
    payload: DeleteArrayRequest,
    _: UserPublic = Depends(deps.get_current_admin),
) -> RaidActionResponse:
    """Delete a RAID array."""
    try:
        return raid_service.delete_array(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


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
