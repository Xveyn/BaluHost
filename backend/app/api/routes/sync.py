"""Sync API endpoints for local network file synchronization."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import api
from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.models.sync_state import FileVersion
from app.models.file_metadata import FileMetadata
from app.services.file_sync import FileSyncService
from app.schemas.sync import (
    RegisterDeviceRequest,
    SyncChangesRequest,
    SyncChangesResponse,
    SyncStatusResponse,
    ResolveConflictRequest,
    ResolveConflictResponse,
    FileHistoryResponse
)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(db: Session = Depends(get_db)) -> FileSyncService:
    """Dependency injection for sync service."""
    return FileSyncService(db)


@router.post("/register")
async def register_device(
    request: RegisterDeviceRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """Register a device for synchronization."""
    sync_state = sync_service.register_device(
        user_id=current_user.id,
        device_id=request.device_id,
        device_name=request.device_name or request.device_id
    )
    
    return {
        "device_id": sync_state.device_id,
        "device_name": sync_state.device_name,
        "status": "registered",
        "change_token": sync_state.last_change_token
    }


@router.get("/status/{device_id}", response_model=SyncStatusResponse)
async def get_sync_status(
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
async def detect_changes(
    request: SyncChangesRequest,
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
        device_id=request.device_id,
        file_list=[f.dict() for f in request.file_list]
    )
    
    if "error" in changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=changes["error"]
        )
    
    return changes


@router.post("/conflicts/{file_path}/resolve", response_model=ResolveConflictResponse)
async def resolve_conflict(
    file_path: str,
    request: ResolveConflictRequest,
    current_user: User = Depends(deps.get_current_user),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """Resolve a file conflict."""
    if request.resolution not in ["keep_local", "keep_server", "create_version"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resolution method"
        )
    
    success = sync_service.resolve_conflict(
        user_id=current_user.id,
        file_path=file_path,
        resolution=request.resolution
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found"
        )
    
    return {
        "file_path": file_path,
        "resolution": request.resolution,
        "resolved": True
    }


@router.get("/history/{file_path}", response_model=FileHistoryResponse)
async def get_file_history(
    file_path: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get version history for a file."""
    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.path == file_path,
        FileMetadata.owner_id == current_user.id
    ).first()
    
    if not file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    versions = db.query(FileVersion).filter(
        FileVersion.file_metadata_id == file_metadata.id
    ).order_by(FileVersion.version_number.desc()).all()
    
    return {
        "file_path": file_path,
        "versions": [
            {
                "version_number": v.version_number,
                "size": v.file_size,
                "hash": v.content_hash,
                "created_at": v.created_at.isoformat(),
                "reason": v.change_reason
            }
            for v in versions
        ]
    }
