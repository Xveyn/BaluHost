"""API endpoints for progressive sync, scheduling, and selective sync."""

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status
from sqlalchemy.orm import Session

from app import api
from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.services.progressive_sync import ProgressiveSyncService
from app.services.sync_scheduler import SyncSchedulerService
from app.schemas.sync import (
    RegisterDeviceRequest,
    SyncStatusResponse,
    StartChunkedUploadRequest,
    UploadChunkResponse,
    UploadProgressResponse,
    SetBandwidthLimitRequest,
    BandwidthLimitResponse,
    CreateSyncScheduleRequest,
    UpdateSyncScheduleRequest,
    SyncScheduleResponse,
    SelectiveSyncRequest,
    SelectiveSyncResponse,
)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_progressive_sync_service(db: Session = Depends(get_db)) -> ProgressiveSyncService:
    """Dependency injection for progressive sync service."""
    return ProgressiveSyncService(db)


def get_sync_scheduler_service(db: Session = Depends(get_db)) -> SyncSchedulerService:
    """Dependency injection for sync scheduler service."""
    return SyncSchedulerService(db)


# ============================================================================
# PROGRESSIVE/CHUNKED UPLOADS
# ============================================================================

@router.post("/upload/start")
async def start_chunked_upload(
    request: StartChunkedUploadRequest,
    device_id: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Start a chunked upload session for a large file."""
    result = sync_service.start_chunked_upload(
        user_id=current_user.id,
        device_id=device_id,
        file_path=request.file_path,
        file_name=request.file_name,
        total_size=request.total_size,
        chunk_size=request.chunk_size
    )
    return result


@router.post("/upload/{upload_id}/chunk/{chunk_number}")
async def upload_chunk(
    upload_id: str,
    chunk_number: int,
    chunk_hash: str,
    chunk_file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Upload a single chunk."""
    chunk_data = await chunk_file.read()
    
    result = sync_service.upload_chunk(
        upload_id=upload_id,
        chunk_number=chunk_number,
        chunk_data=chunk_data,
        chunk_hash=chunk_hash
    )
    
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    
    return result


@router.get("/upload/{upload_id}/progress")
async def get_upload_progress(
    upload_id: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Get progress of a chunked upload."""
    progress = sync_service.get_upload_progress(upload_id)
    
    if not progress:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    
    return progress


@router.post("/upload/{upload_id}/resume")
async def resume_upload(
    upload_id: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Resume a paused chunked upload."""
    result = sync_service.resume_upload(upload_id)
    
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    
    return result


@router.delete("/upload/{upload_id}")
async def cancel_upload(
    upload_id: str,
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Cancel a chunked upload."""
    success = sync_service.cancel_upload(upload_id)
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    
    return {"cancelled": True, "upload_id": upload_id}


# ============================================================================
# BANDWIDTH LIMITS
# ============================================================================

@router.post("/bandwidth/limit")
async def set_bandwidth_limit(
    request: SetBandwidthLimitRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Set bandwidth limits for sync."""
    success = sync_service.set_bandwidth_limit(
        user_id=current_user.id,
        upload_speed_limit=request.upload_speed_limit,
        download_speed_limit=request.download_speed_limit
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return {"success": True}


@router.get("/bandwidth/limit")
async def get_bandwidth_limit(
    current_user: User = Depends(deps.get_current_user),
    sync_service: ProgressiveSyncService = Depends(get_progressive_sync_service)
):
    """Get current bandwidth limits."""
    limit = sync_service.get_bandwidth_limit(current_user.id)
    
    if not limit:
        return {"upload_speed_limit": None, "download_speed_limit": None}
    
    return limit


# ============================================================================
# SYNC SCHEDULING
# ============================================================================

@router.post("/schedule/create")
async def create_sync_schedule(
    request: CreateSyncScheduleRequest,
    current_user: User = Depends(deps.get_current_user),
    scheduler: SyncSchedulerService = Depends(get_sync_scheduler_service)
):
    """Create a new sync schedule."""
    result = scheduler.create_schedule(
        user_id=current_user.id,
        device_id=request.device_id,
        schedule_type=request.schedule_type,
        time_of_day=request.time_of_day,
        day_of_week=request.day_of_week,
        day_of_month=request.day_of_month,
        sync_deletions=request.sync_deletions,
        resolve_conflicts=request.resolve_conflicts
    )
    return result


@router.get("/schedule/list")
async def list_sync_schedules(
    current_user: User = Depends(deps.get_current_user),
    scheduler: SyncSchedulerService = Depends(get_sync_scheduler_service)
):
    """List all sync schedules for current user."""
    schedules = scheduler.get_schedules(current_user.id)
    return {"schedules": schedules}


@router.post("/schedule/{schedule_id}/disable")
async def disable_sync_schedule(
    schedule_id: int,
    current_user: User = Depends(deps.get_current_user),
    scheduler: SyncSchedulerService = Depends(get_sync_scheduler_service)
):
    """Disable a sync schedule."""
    success = scheduler.disable_schedule(schedule_id, current_user.id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    return {"disabled": True, "schedule_id": schedule_id}


@router.put("/schedule/{schedule_id}")
async def update_sync_schedule(
    schedule_id: int,
    request: UpdateSyncScheduleRequest,
    current_user: User = Depends(deps.get_current_user),
    scheduler: SyncSchedulerService = Depends(get_sync_scheduler_service)
):
    """Update an existing sync schedule."""
    result = scheduler.update_schedule(
        schedule_id=schedule_id,
        user_id=current_user.id,
        schedule_type=request.schedule_type,
        time_of_day=request.time_of_day,
        day_of_week=request.day_of_week,
        day_of_month=request.day_of_month,
        sync_deletions=request.sync_deletions,
        resolve_conflicts=request.resolve_conflicts,
        is_active=request.is_active,
    )

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    return result


# ============================================================================
# SELECTIVE SYNC
# ============================================================================

@router.post("/selective/configure")
async def configure_selective_sync(
    request: SelectiveSyncRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Configure selective sync for a device."""
    from app.models.sync_progress import SelectiveSync
    
    # Clear existing
    db.query(SelectiveSync).filter(
        SelectiveSync.user_id == current_user.id,
        SelectiveSync.device_id == request.device_id
    ).delete()
    
    # Add new preferences
    for folder in request.folders:
        sync = SelectiveSync(
            user_id=current_user.id,
            device_id=request.device_id,
            folder_path=folder["path"],
            include_subfolders=folder.get("include_subfolders", True),
            is_enabled=folder.get("enabled", True)
        )
        db.add(sync)
    
    db.commit()
    
    return {
        "device_id": request.device_id,
        "folders_configured": len(request.folders)
    }


@router.get("/selective/list/{device_id}")
async def list_selective_sync(
    device_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """List selective sync configuration for a device."""
    from app.models.sync_progress import SelectiveSync
    
    syncs = db.query(SelectiveSync).filter(
        SelectiveSync.user_id == current_user.id,
        SelectiveSync.device_id == device_id
    ).all()
    
    return {
        "device_id": device_id,
        "folders": [
            {
                "folder_path": s.folder_path,
                "enabled": s.is_enabled,
                "include_subfolders": s.include_subfolders
            }
            for s in syncs
        ]
    }
