from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, Request, Response, UploadFile, status
from fastapi import Body
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.power_rating import requires_power
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.schemas.power import ServicePowerProperty
from app.schemas.files import (
    FileListResponse,
    FileOperationResponse,
    FileUploadResponse,
    FolderCreateRequest,
    MoveRequest,
    RenameRequest,
    FilePermissions,
    FilePermissionsRequest,
)
from app.schemas.user import UserPublic
from app.services import files as file_service
from app.services.permissions import PermissionDeniedError
from app.services.audit_logger_db import get_audit_logger_db
from app.services.shares import ShareService
from app.models.file_metadata import FileMetadata
from app.plugins.emit import emit_hook


router = APIRouter()
# ...existing code...

# --- Permissions Endpoints ---
@router.get("/permissions", response_model=FilePermissions)
@user_limiter.limit(get_limit("file_list"))
async def get_permissions(
    request: Request,
    response: Response,
    path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FilePermissions:
    from app.services import file_metadata_db
    from app.models.file_share import FileShare
    metadata = file_metadata_db.get_metadata(path, db=db)
    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")
    # Alle Berechtigungsregeln für diese Datei auslesen
    shares = db.query(FileShare).filter(FileShare.file_id == metadata.id).all()
    rules = [
        {
            "user_id": share.shared_with_user_id,
            "can_view": share.can_read,
            "can_edit": share.can_write,
            "can_delete": share.can_delete
        }
        for share in shares
    ]
    from app.schemas.files import FilePermissions, FilePermissionRule
    return FilePermissions(
        path=metadata.path,
        owner_id=metadata.owner_id,
        rules=[FilePermissionRule(**rule) for rule in rules]
    )

@router.put("/permissions", response_model=FilePermissions)
@user_limiter.limit(get_limit("file_delete"))
async def set_permissions(
    request: Request,
    response: Response,
    payload: FilePermissionsRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FilePermissions:
    from app.services import file_metadata_db
    from app.models.file_share import FileShare
    # Nur Owner/Admin darf setzen
    metadata = file_metadata_db.get_metadata(payload.path, db=db)
    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")
    from app.services.permissions import ensure_owner_or_privileged
    ensure_owner_or_privileged(user, str(metadata.owner_id))
    # Owner setzen
    file_metadata_db.set_owner_id(payload.path, payload.owner_id, db=db)
    # Bestehende Regeln löschen
    db.query(FileShare).filter(FileShare.file_id == metadata.id).delete()
    # Neue Regeln speichern
    for rule in payload.rules:
        share = FileShare(
            file_id=metadata.id,
            owner_id=payload.owner_id,
            shared_with_user_id=rule.user_id,
            can_read=rule.can_view,
            can_write=rule.can_edit,
            can_delete=rule.can_delete,
            can_share=False
        )
        db.add(share)
    db.commit()
    # Rückgabe: aktuelle Regeln
    shares = db.query(FileShare).filter(FileShare.file_id == metadata.id).all()
    rules = [
        {
            "user_id": share.shared_with_user_id,
            "can_view": share.can_read,
            "can_edit": share.can_write,
            "can_delete": share.can_delete
        }
        for share in shares
    ]
    from app.schemas.files import FilePermissions, FilePermissionRule
    return FilePermissions(
        path=payload.path,
        owner_id=payload.owner_id,
        rules=[FilePermissionRule(**rule) for rule in rules]
    )


@router.get("/mountpoints")
async def get_mountpoints(
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of available storage mountpoints (RAID arrays, disks, etc.)."""
    from app.schemas.storage import MountpointsResponse, StorageMountpoint
    from app.services import raid as raid_service
    from app.core.config import settings
    
    raid_status = raid_service.get_status()
    
    mountpoints = []
    
    if settings.is_dev_mode:
        # Dev Mode: Show dev-storage as default + all RAID arrays
        # Dev storage mountpoint
        used_bytes = file_service.calculate_used_bytes()
        quota_bytes = settings.nas_quota_bytes or 0
        available_bytes = file_service.calculate_available_bytes() or 0
        
        mountpoints.append(StorageMountpoint(
            id="dev-storage",
            name="Dev Storage",
            type="dev-storage",
            path="",
            size_bytes=quota_bytes,
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            status="optimal",
            is_default=True
        ))
        
        # Add mock RAID arrays
        for array in raid_status.arrays:
            mountpoints.append(StorageMountpoint(
                id=array.name,
                name=f"{array.level.upper()} Setup - {array.name}",
                type="raid",
                path=f"/{array.name}",
                size_bytes=array.size_bytes,
                used_bytes=0,  # Mock: not tracking usage per array in dev mode
                available_bytes=array.size_bytes,
                raid_level=array.level,
                status=array.status,
                is_default=False
            ))
    else:
        # Production Mode: Show actual RAID arrays
        for array in raid_status.arrays:
            # Try to get actual storage usage for this array
            try:
                # This would need to be implemented to check actual mount point usage
                size_bytes = array.size_bytes
                used_bytes = 0  # TODO: Implement actual usage tracking
                available_bytes = size_bytes - used_bytes
            except Exception:
                size_bytes = array.size_bytes
                used_bytes = 0
                available_bytes = size_bytes
            
            mountpoints.append(StorageMountpoint(
                id=array.name,
                name=f"{array.level.upper()} Array - {array.name}",
                type="raid",
                path=f"/{array.name}",
                size_bytes=size_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                raid_level=array.level,
                status=array.status,
                is_default=(array.name == "md0")  # md0 is typically the default
            ))
    
    default_id = next((m.id for m in mountpoints if m.is_default), mountpoints[0].id if mountpoints else "dev-storage")
    
    return MountpointsResponse(
        mountpoints=mountpoints,
        default_mountpoint=default_id
    )


@router.get("/list", response_model=FileListResponse)
@user_limiter.limit(get_limit("file_list"))
async def list_files(
    request: Request,
    response: Response,
    path: str = "",
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileListResponse:
    audit_logger = get_audit_logger_db()
    try:
        entries = list(file_service.list_directory(path, user=user, db=db))
    except PermissionDeniedError as exc:
        # Log unauthorized directory access
        audit_logger.log_authorization_failure(
            user=user.username,
            action="list_directory",
            resource=path,
            required_permission="read",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileListResponse(files=entries)


@router.get("/download/{resource_path:path}")
@user_limiter.limit(get_limit("file_download"))
async def download_file(
    request: Request,
    response: Response,
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Legacy download endpoint using file path."""
    audit_logger = get_audit_logger_db()
    try:
        file_service.ensure_can_view(resource_path, user, db=db)
        file_path = file_service.get_absolute_path(resource_path)
    except PermissionDeniedError as exc:
        # Log unauthorized file download attempt
        audit_logger.log_authorization_failure(
            user=user.username,
            action="download_file",
            resource=resource_path,
            required_permission="read",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=file_path.name)


@router.get("/download/{file_id}")
async def download_file_by_id(
    file_id: int,
    request: Request,
    x_share_token: Optional[str] = Header(None),
    x_share_password: Optional[str] = Header(None),
    user: Optional[UserPublic] = Depends(deps.get_current_user_optional),
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Download a file by ID. Supports both authenticated and public share link access.
    """
    audit_logger = get_audit_logger_db()
    
    # Get file metadata
    file_metadata = db.get(FileMetadata, file_id)
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check if accessing via share link
    if x_share_token:
        # Public share link access
        share_link = ShareService.get_share_link_by_token(db, x_share_token)
        
        if not share_link:
            raise HTTPException(status_code=404, detail="Share link not found")
        
        if not share_link.is_accessible():
            raise HTTPException(status_code=410, detail="Share link has expired or reached download limit")
        
        if share_link.file_id != file_id:
            raise HTTPException(status_code=403, detail="Share link does not match file")
        
        # Verify password if required
        if not ShareService.verify_share_link_password(share_link, x_share_password):
            raise HTTPException(status_code=403, detail="Invalid password")
        
        if not share_link.allow_download:
            raise HTTPException(status_code=403, detail="Download not allowed for this share")
        
        # Increment download count
        ShareService.increment_download_count(db, share_link)
        
        # Log public share download (use owner's ID for tracking)
        audit_logger.log_file_action(
            action="file_download_via_share",
            user_id=share_link.owner_id,
            username=f"shared_link:{x_share_token[:8]}",
            file_path=file_metadata.path,
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )
    else:
        # Authenticated user access
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        try:
            file_service.ensure_can_view(file_metadata.path, user, db=db)
        except PermissionDeniedError as exc:
            audit_logger.log_authorization_failure(
                user=user.username,
                action="download_file",
                resource=file_metadata.path,
                required_permission="read",
                db=db
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except file_service.FileAccessError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    
    # Get absolute file path
    file_path = file_service.get_absolute_path(file_metadata.path)
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(path=file_path, filename=file_metadata.name)


@router.post("/upload", response_model=FileUploadResponse)
@user_limiter.limit(get_limit("file_upload"))
@requires_power(ServicePowerProperty.MEDIUM, timeout_seconds=600, description="File upload")
async def upload_files(
    request: Request,
    response: Response,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    path: str = Form(""),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileUploadResponse:
    from app.services.upload_progress import get_upload_progress_manager
    
    # Create upload sessions for progress tracking
    progress_manager = get_upload_progress_manager()
    upload_ids = []
    
    # Normalize incoming file parameters: accept either `files` (list) or `file` (single)
    incoming = files if files is not None else ([file] if file is not None else [])

    for upload_file in incoming:
        # Get file size from the upload
        upload_file.file.seek(0, 2)  # Seek to end
        file_size = upload_file.file.tell()
        upload_file.file.seek(0)  # Reset to start
        
        upload_id = progress_manager.create_upload_session(
            filename=upload_file.filename or "upload.bin",
            total_bytes=file_size
        )
        upload_ids.append(upload_id)
    
    # folder_paths is optional and sent as individual form fields
    # FastAPI will collect them automatically if present
    try:
        saved = await file_service.save_uploads(
            path, incoming, user=user, folder_paths=None, db=db, upload_ids=upload_ids
        )
    except file_service.QuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Emit plugin hooks for uploaded files
    for saved_file in saved:
        emit_hook(
            "on_file_uploaded",
            path=saved_file,
            user_id=user.id,
            size=0,  # Size would need to be tracked separately
            content_type=None,
        )

    return FileUploadResponse(message="Files uploaded", uploaded=saved, upload_ids=upload_ids)


@router.get("/storage/available")
async def get_available_storage(
    user: UserPublic = Depends(deps.get_current_user),
) -> dict[str, int | None]:
    """Get remaining storage capacity in bytes. Returns None if no quota is set."""
    available = file_service.calculate_available_bytes()
    used = file_service.calculate_used_bytes()
    quota = file_service.settings.nas_quota_bytes
    return {
        "available_bytes": available,
        "used_bytes": used,
        "quota_bytes": quota,
    }


@router.delete("/raw/{resource_path:path}", response_model=FileOperationResponse)
@user_limiter.limit(get_limit("file_delete"))
async def delete_path_raw(
    request: Request,
    response: Response,
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    """Internal/raw delete handler kept for compatibility; not used by tests.
    Use the parameterized delete handler defined later which is registered after
    the `/delete` static route so that `DELETE /delete` can accept a JSON body.
    """
    audit_logger = get_audit_logger_db()
    try:
        file_service.delete_path(resource_path, user=user, db=db)
    except PermissionDeniedError as exc:
        audit_logger.log_authorization_failure(
            user=user.username,
            action="delete_file",
            resource=resource_path,
            required_permission="delete",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Emit plugin hook for file deletion
    emit_hook("on_file_deleted", path=resource_path, user_id=user.id)

    return FileOperationResponse(message="Deleted")


@router.delete("/delete", response_model=FileOperationResponse)
async def delete_path_body(
    payload: dict = Body(...),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path required")
    audit_logger = get_audit_logger_db()
    try:
        file_service.delete_path(path, user=user, db=db)
    except PermissionDeniedError as exc:
        audit_logger.log_authorization_failure(
            user=user.username,
            action="delete_file",
            resource=path,
            required_permission="delete",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Emit plugin hook for file deletion
    emit_hook("on_file_deleted", path=path, user_id=user.id)

    return FileOperationResponse(message="Deleted")


@router.post("/delete", response_model=FileOperationResponse)
async def delete_path_post(
    payload: dict = Body(...),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    # Delegate to delete_by_body logic
    return await delete_path_body(payload=payload, user=user, db=db)


@router.post("/folder", response_model=FileOperationResponse)
async def create_folder(
    payload: FolderCreateRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    if not payload.name:
        raise HTTPException(status_code=400, detail="Folder name required")

    try:
        file_service.create_folder(payload.path or "", payload.name, owner=user, db=db)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileOperationResponse(message="Folder created")


@router.post("/mkdir", response_model=FileOperationResponse)
async def mkdir_compat(
    payload: dict = Body(...),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    """Compatibility endpoint for legacy clients/tests that post {"path": "/a/b"}.
    This will create metadata for the final path segment owned by the current user.
    """
    import os

    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path required")

    # normalize and split into parent + name
    norm = path.rstrip("/")
    parent, name = os.path.split(norm)
    if parent == "/":
        parent = ""

    try:
        file_service.create_folder(parent or "", name, owner=user, db=db)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileOperationResponse(message="Folder created")


@router.put("/rename", response_model=FileOperationResponse)
async def rename_path(
    payload: RenameRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    audit_logger = get_audit_logger_db()
    try:
        file_service.rename_path(payload.old_path, payload.new_name, user=user, db=db)
    except PermissionDeniedError as exc:
        # Log unauthorized rename attempt
        audit_logger.log_authorization_failure(
            user=user.username,
            action="rename_file",
            resource=payload.old_path,
            required_permission="write",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileOperationResponse(message="Renamed")


@router.put("/move", response_model=FileOperationResponse)
async def move_path(
    payload: MoveRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    audit_logger = get_audit_logger_db()
    try:
        file_service.move_path(payload.source_path, payload.target_path, user=user, db=db)
    except PermissionDeniedError as exc:
        # Log unauthorized move attempt
        audit_logger.log_authorization_failure(
            user=user.username,
            action="move_file",
            resource=payload.source_path,
            required_permission="write",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Emit plugin hook for file move
    emit_hook(
        "on_file_moved",
        old_path=payload.source_path,
        new_path=payload.dest_path,
        user_id=user.id,
    )

    return FileOperationResponse(message="Moved")


@router.delete("/{resource_path:path}", response_model=FileOperationResponse)
async def delete_path_param(
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    """Delete a file or directory by path (registered after `/delete` routes).
    This ensures the static `/delete` endpoint can accept a JSON body without
    being captured by the parameterized route."""
    audit_logger = get_audit_logger_db()
    try:
        file_service.delete_path(resource_path, user=user, db=db)
    except PermissionDeniedError as exc:
        audit_logger.log_authorization_failure(
            user=user.username,
            action="delete_file",
            resource=resource_path,
            required_permission="delete",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Emit plugin hook for file deletion
    emit_hook("on_file_deleted", path=resource_path, user_id=user.id)

    return FileOperationResponse(message="Deleted")
