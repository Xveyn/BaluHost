"""Sync API endpoints for local network file synchronization."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from sqlalchemy.sql import func
import logging

from app import api
from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.models.sync_state import SyncFileVersion
from app.models.mobile import MobileRegistrationToken
from app.models.file_metadata import FileMetadata
from app.models.desktop_sync_folder import DesktopSyncFolder
from app.services.file_sync import FileSyncService
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
)
from app.schemas.user import UserPublic

Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(db: Session = Depends(get_db)) -> FileSyncService:
    """Dependency injection for sync service."""
    return FileSyncService(db)


@router.post("/register")
@user_limiter.limit(get_limit("sync_operations"))
async def register_device(
    request: Request,
    response: Response,
    payload: RegisterDeviceRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
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
    token_record = db.query(MobileRegistrationToken).filter(MobileRegistrationToken.token == token).first()
    if not token_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid registration token")
    if token_record.used:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Registration token already used")
    from datetime import datetime, timezone
    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Registration token expired")
    if str(token_record.user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration token does not belong to the current user")

    # Mark token as used
    token_record.used = True
    db.commit()

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
    db: Session = Depends(deps.get_db),
    sync_service: FileSyncService = Depends(get_sync_service)
):
    """
    Register a desktop device for synchronization.

    Desktop-only registration endpoint that does not require a registration token,
    as the user is already authenticated via JWT. This simplifies the desktop client
    registration flow compared to the mobile QR-code-based registration.
    """
    # Check if device already registered
    from app.models.sync_state import SyncState
    existing_device = db.query(SyncState).filter(
        SyncState.device_id == payload.device_id,
        SyncState.user_id == current_user.id
    ).first()

    if existing_device:
        # Device already registered, return existing info
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
@user_limiter.limit(get_limit("sync_operations"))
async def get_sync_state(
    request: Request,
    response: Response,
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


@router.post("/report-folders", response_model=ReportSyncFoldersResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def report_sync_folders(
    request: Request,
    response: Response,
    payload: ReportSyncFoldersRequest,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """BaluDesk client reports its currently active sync folders.

    Upsert logic:
    - For each reported folder: INSERT or UPDATE (device_id + remote_path as key)
    - All NOT-reported folders of this device are marked is_active=False
    """
    now = func.now()
    reported_paths: set[str] = set()
    accepted = 0

    for folder in payload.folders:
        reported_paths.add(folder.remote_path)

        existing = db.query(DesktopSyncFolder).filter(
            DesktopSyncFolder.device_id == payload.device_id,
            DesktopSyncFolder.remote_path == folder.remote_path,
        ).first()

        if existing:
            existing.device_name = payload.device_name
            existing.platform = payload.platform
            existing.sync_direction = folder.sync_direction
            existing.is_active = True
            existing.last_reported_at = now
            existing.user_id = current_user.id
        else:
            db.add(DesktopSyncFolder(
                user_id=current_user.id,
                device_id=payload.device_id,
                device_name=payload.device_name,
                platform=payload.platform,
                remote_path=folder.remote_path,
                sync_direction=folder.sync_direction,
                is_active=True,
                last_reported_at=now,
            ))
        accepted += 1

    # Deactivate folders no longer reported by this device
    deactivate_query = db.query(DesktopSyncFolder).filter(
        DesktopSyncFolder.device_id == payload.device_id,
        DesktopSyncFolder.user_id == current_user.id,
        DesktopSyncFolder.is_active.is_(True),
    )
    if reported_paths:
        deactivate_query = deactivate_query.filter(
            DesktopSyncFolder.remote_path.notin_(reported_paths),
        )
    deactivated = 0
    for row in deactivate_query.all():
        row.is_active = False
        deactivated += 1

    db.commit()

    return ReportSyncFoldersResponse(accepted=accepted, deactivated=deactivated)


@router.get("/synced-folders", response_model=SyncedFoldersResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def get_synced_folders(
    request: Request,
    response: Response,
    active_only: bool = True,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """List all synced folders.

    Normal users see only their own folders.
    Admins see all folders (with username).
    """
    query = db.query(DesktopSyncFolder)

    if active_only:
        query = query.filter(DesktopSyncFolder.is_active.is_(True))

    if not is_privileged(current_user):
        query = query.filter(DesktopSyncFolder.user_id == current_user.id)

    folders = query.all()

    # Resolve usernames for admins
    user_names: dict[int, str] = {}
    if is_privileged(current_user):
        user_ids = {f.user_id for f in folders}
        if user_ids:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            user_names = {u.id: u.username for u in users}

    return SyncedFoldersResponse(
        folders=[
            SyncedFolderInfo(
                remote_path=f.remote_path,
                device_id=f.device_id,
                device_name=f.device_name,
                platform=f.platform,
                sync_direction=f.sync_direction,
                is_active=f.is_active,
                last_reported_at=f.last_reported_at.isoformat(),
                username=user_names.get(f.user_id) if is_privileged(current_user) else None,
            )
            for f in folders
        ]
    )
