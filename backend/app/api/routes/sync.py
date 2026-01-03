"""Sync API endpoints for local network file synchronization."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import api
from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.models.sync_state import SyncFileVersion
from app.models.mobile import MobileRegistrationToken
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
    sync_service: FileSyncService = Depends(get_sync_service),
    http_request: Request = None
):
    """Register a device for synchronization."""
    # Enforce token-only registration: require a one-time registration token
    token = None
    if hasattr(request, 'registration_token') and request.registration_token:
        token = request.registration_token
    # Also allow token via header for non-JSON clients
    if not token and http_request is not None:
        token = http_request.headers.get('x-registration-token')

    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration token required. Generate a registration token via /api/mobile/token/generate and use it to register the device."
        )

    # Validate token
    token_record = db.query(MobileRegistrationToken).filter(MobileRegistrationToken.token == token).first()
    if not token_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid registration token")
    if token_record.used:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Registration token already used")
    from datetime import datetime
    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Registration token expired")
    if str(token_record.user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration token does not belong to the current user")

    # Mark token as used
    token_record.used = True
    db.commit()

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
    
    versions = db.query(SyncFileVersion).filter(
        SyncFileVersion.file_metadata_id == file_metadata.id
    ).order_by(SyncFileVersion.version_number.desc()).all()
    
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


@router.get("/state")
async def get_sync_state(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
    sync_service: FileSyncService = Depends(get_sync_service),
):
    """Return a simple sync state summary for the current user.

    Provides a list of files with paths and SHA256 hashes for client sync.
    """
    files = db.query(FileMetadata).filter(FileMetadata.owner_id == current_user.id).all()
    result_files = []
    from pathlib import Path
    from app.core.config import settings

    storage_root = Path(settings.nas_storage_path)
    for fm in files:
        # Skip directories for file-hash calculations
        if fm.is_directory:
            continue
        display_path = fm.path if fm.path.startswith("/") else f"/{fm.path}"
        abs_path = storage_root / fm.path.lstrip("/")
        sha = sync_service.calculate_file_hash(abs_path) if abs_path.exists() else ""
        result_files.append({
            "path": display_path,
            "size": fm.size_bytes,
            "sha256": sha,
            "modified_at": fm.updated_at.isoformat() if fm.updated_at else None,
        })

    return {"files": result_files}
