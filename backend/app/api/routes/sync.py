"""Sync API endpoints for local network file synchronization."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
import logging

from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.services.sync import FileSyncService
from app.services.permissions import is_privileged
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.sync import (
    RegisterDeviceRequest,
    SyncChangesRequest,
    SyncChangesResponse,
    SyncStatusResponse,
    ResolveConflictRequest,
    ResolveConflictResponse,
    FileHistoryResponse,
    ReportSyncFoldersRequest,
    ReportSyncFoldersResponse,
    SyncedFoldersResponse,
    SyncedFolderInfo,
    SyncPreflightResponse,
    SleepScheduleInfo,
)
from app.services.power.sleep import get_sleep_manager
from app.schemas.user import UserPublic

Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(db: Session = Depends(get_db)) -> FileSyncService:
    """Dependency injection for sync service."""
    return FileSyncService(db)


@router.get("/preflight", response_model=SyncPreflightResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def sync_preflight(
    request: Request,
    response: Response,
    current_user: User = Depends(deps.get_current_user),
) -> SyncPreflightResponse:
    """Check if automatic sync is currently allowed and return sleep schedule.

    Lightweight endpoint for sync clients to call before starting automatic sync.
    Does NOT wake the NAS from sleep (whitelisted in auto-wake middleware).
    """
    manager = get_sleep_manager()

    if manager is None:
        return SyncPreflightResponse(
            sync_allowed=True,
            current_sleep_state="awake",
        )

    from app.schemas.sleep import SleepState
    current_state = manager._current_state
    is_awake = current_state == SleepState.AWAKE

    schedule_info = None
    next_sleep_at = None
    next_wake_at = None
    config = manager._load_config()

    if config and config.schedule_enabled:
        schedule_info = SleepScheduleInfo(
            enabled=True,
            sleep_time=config.schedule_sleep_time,
            wake_time=config.schedule_wake_time,
            mode=config.schedule_mode,
        )
        from datetime import datetime, timedelta
        now = datetime.now()
        for time_str, attr in [
            (config.schedule_sleep_time, "next_sleep_at"),
            (config.schedule_wake_time, "next_wake_at"),
        ]:
            h, m = map(int, time_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            if attr == "next_sleep_at":
                next_sleep_at = target.isoformat()
            else:
                next_wake_at = target.isoformat()

    return SyncPreflightResponse(
        sync_allowed=is_awake,
        current_sleep_state=current_state.value,
        sleep_schedule=schedule_info,
        next_sleep_at=next_sleep_at,
        next_wake_at=next_wake_at,
        block_reason="sleep_active" if not is_awake else None,
    )


@router.post("/register")
@user_limiter.limit(get_limit("sync_operations"))
async def register_device(
    request: Request,
    response: Response,
    payload: RegisterDeviceRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """Register a device for synchronization."""
    # Enforce token-only registration: require a one-time registration token
    token = None
    if hasattr(payload, 'registration_token') and payload.registration_token:
        token = payload.registration_token
    # Also allow token via header for non-JSON clients
    if not token:
        token = request.headers.get('x-registration-token')

    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration token required. Generate a registration token via /api/mobile/token/generate and use it to register the device."
        )

    # Validate token
    try:
        token_record = sync_service.validate_registration_token(token, current_user.id)
    except ValueError as e:
        code = status.HTTP_401_UNAUTHORIZED
        if "does not belong" in str(e):
            code = status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=code, detail=str(e))

    # Mark token as used
    sync_service.consume_registration_token(token_record)

    sync_state = sync_service.register_device(
        user_id=current_user.id,
        device_id=payload.device_id,
        device_name=payload.device_name or payload.device_id
    )

    return {
        "device_id": sync_state.device_id,
        "device_name": sync_state.device_name,
        "status": "registered",
        "change_token": sync_state.last_change_token
    }


@router.post("/register-desktop")
@user_limiter.limit(get_limit("sync_operations"))
async def register_desktop_device(
    request: Request,
    response: Response,
    payload: RegisterDeviceRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """
    Register a desktop device for synchronization.

    Desktop-only registration endpoint that does not require a registration token,
    as the user is already authenticated via JWT. This simplifies the desktop client
    registration flow compared to the mobile QR-code-based registration.
    """
    existing_device = sync_service.get_existing_device(payload.device_id, current_user.id)

    if existing_device:
        Logger.info(f"Desktop device {payload.device_id} already registered for user {current_user.username}")
        return {
            "device_id": existing_device.device_id,
            "device_name": existing_device.device_name,
            "status": "already_registered",
            "change_token": existing_device.last_change_token
        }

    # Register new device
    sync_state = sync_service.register_device(
        user_id=current_user.id,
        device_id=payload.device_id,
        device_name=payload.device_name or payload.device_id
    )

    Logger.info(f"Registered desktop device {payload.device_id} for user {current_user.username}")

    return {
        "device_id": sync_state.device_id,
        "device_name": sync_state.device_name,
        "status": "registered",
        "change_token": sync_state.last_change_token
    }


@router.get("/status/{device_id}", response_model=SyncStatusResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def get_sync_status(
    request: Request,
    response: Response,
    device_id: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """Get sync status for a device."""
    sync_status = sync_service.get_sync_status(current_user.id, device_id)

    if sync_status.get("status") == "not_registered":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not registered"
        )

    return sync_status


@router.post("/changes", response_model=SyncChangesResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def detect_changes(
    request: Request,
    response: Response,
    payload: SyncChangesRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """
    Detect changes and return delta sync data.

    The client sends its current file list, and the server returns:
    - Files to download (new/updated on server)
    - Files to delete (removed on server)
    - Conflicts (modified on both sides)
    """
    changes = sync_service.detect_changes(
        user_id=current_user.id,
        device_id=payload.device_id,
        file_list=[f.dict() for f in payload.file_list]
    )

    if "error" in changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=changes["error"]
        )

    return changes


@router.post("/conflicts/{file_path}/resolve", response_model=ResolveConflictResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def resolve_conflict(
    request: Request,
    response: Response,
    file_path: str,
    payload: ResolveConflictRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """Resolve a file conflict."""
    if payload.resolution not in ["keep_local", "keep_server", "create_version"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resolution method"
        )

    success = sync_service.resolve_conflict(
        user_id=current_user.id,
        file_path=file_path,
        resolution=payload.resolution
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found"
        )

    return {
        "file_path": file_path,
        "resolution": payload.resolution,
        "resolved": True
    }


@router.get("/history/{file_path}", response_model=FileHistoryResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def get_file_history(
    request: Request,
    response: Response,
    file_path: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """Get version history for a file."""
    result = sync_service.get_file_version_history(file_path, current_user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    return result


@router.get("/state")
@user_limiter.limit(get_limit("sync_operations"))
async def get_sync_state(
    request: Request,
    response: Response,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """Return a simple sync state summary for the current user.

    Provides a list of files with paths and SHA256 hashes for client sync.
    """
    import asyncio
    from pathlib import Path
    from app.core.config import settings

    files = sync_service.get_user_files(current_user.id)
    storage_root = Path(settings.nas_storage_path)

    # Build file list — use stored checksum when available, otherwise compute in thread.
    files_needing_hash: list[tuple[int, Path]] = []
    result_files: list[dict] = []
    for fm in files:
        if fm.is_directory:
            continue
        display_path = fm.path if fm.path.startswith("/") else f"/{fm.path}"
        abs_path = storage_root / fm.path.lstrip("/")

        # Prefer stored checksum from DB (set during upload) to avoid disk I/O
        if fm.checksum:
            sha = fm.checksum
        else:
            sha = ""
            if abs_path.exists():
                files_needing_hash.append((len(result_files), abs_path))

        result_files.append({
            "path": display_path,
            "size": fm.size_bytes,
            "sha256": sha,
            "modified_at": fm.updated_at.isoformat() if fm.updated_at else None,
        })

    # Compute missing hashes in a worker thread to avoid blocking the event loop
    if files_needing_hash:
        def _compute_hashes() -> list[tuple[int, str]]:
            results = []
            for result_idx, path in files_needing_hash:
                results.append((result_idx, sync_service.calculate_file_hash(path)))
            return results

        hashes = await asyncio.to_thread(_compute_hashes)
        for result_idx, sha in hashes:
            result_files[result_idx]["sha256"] = sha

    return {"files": result_files}


@router.post("/report-folders", response_model=ReportSyncFoldersResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def report_sync_folders(
    request: Request,
    response: Response,
    payload: ReportSyncFoldersRequest,
    current_user: UserPublic = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """BaluDesk client reports its currently active sync folders.

    Upsert logic:
    - For each reported folder: INSERT or UPDATE (device_id + remote_path as key)
    - All NOT-reported folders of this device are marked is_active=False
    """
    accepted, deactivated = sync_service.report_sync_folders(
        user_id=current_user.id,
        device_id=payload.device_id,
        device_name=payload.device_name,
        platform=payload.platform,
        folders=payload.folders,
    )
    return ReportSyncFoldersResponse(accepted=accepted, deactivated=deactivated)


@router.get("/synced-folders", response_model=SyncedFoldersResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def get_synced_folders(
    request: Request,
    response: Response,
    active_only: bool = True,
    current_user: UserPublic = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """List all synced folders.

    Normal users see only their own folders.
    Admins see all folders (with username).
    """
    folders_data = sync_service.get_synced_folders(
        user_id=current_user.id,
        is_admin=is_privileged(current_user),
        active_only=active_only,
    )
    return SyncedFoldersResponse(
        folders=[SyncedFolderInfo(**f) for f in folders_data]
    )
