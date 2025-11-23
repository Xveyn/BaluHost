from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.schemas.system import (
    DiskIOResponse,
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
    from app.services.smart import get_smart_device_models

    model_map = get_smart_device_models()

    def _normalize(name: str) -> str:
        return name.lower().replace('\\\\.\\physicaldrive', 'physicaldrive').replace('\\.\\physicaldrive', 'physicaldrive').replace('/dev/', '')

    normalized_map = { _normalize(k): v for k, v in model_map.items() }

    disks = []
    for disk_name, samples in history.items():
        norm = _normalize(disk_name)
        model = normalized_map.get(norm)
        # Fallback heuristics (Index / Teilstring)
        if model is None:
            import re
            m = re.search(r'(physicaldrive)?(\d+)$', norm)
            if m:
                model = normalized_map.get(m.group(2))
        if model is None and len(norm) == 3 and norm.startswith('sd'):
            letter_index = str(ord(norm[2]) - ord('a'))
            model = normalized_map.get(letter_index)
        if model is None:
            for k, v in normalized_map.items():
                if k in norm or norm in k:
                    model = v
                    break
        disks.append(DiskIOHistory(diskName=disk_name, model=model, samples=[DiskIOSample(**sample) for sample in samples]))

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
