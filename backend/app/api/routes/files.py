from typing import Optional
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, Request, Response, UploadFile, status
from fastapi import Body
from pydantic import BaseModel
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
    FileItem,
    OwnershipTransferRequest,
    OwnershipTransferResponse,
    ConflictInfo,
    EnforceResidencyRequest,
    EnforceResidencyResponse,
    ResidencyViolation,
)
from app.schemas.user import UserPublic
from app.services import files as file_service
from app.services.files.operations import is_path_shared_with_user, SHARED_WITH_ME_DIR
from app.services.permissions import PermissionDeniedError, is_privileged
from app.services.audit_logger_db import get_audit_logger_db
from app.services.shares import ShareService
from app.models.file_metadata import FileMetadata
from app.plugins.emit import emit_hook

SHARED_DIR_NAME = "Shared"


def _jail_path(path: str, user: UserPublic, db: Session | None = None) -> str:
    """Validate and sanitize a user-facing path.

    * Admin: path returned unchanged.
    * Normal user:
      - ``"Shared"`` / ``"Shared/..."`` -> passthrough
      - ``"Shared with me"`` -> passthrough (virtual folder)
      - ``"{username}"`` / ``"{username}/..."`` -> passthrough (own home dir)
      - paths shared via FileShare -> passthrough
      - ``""`` (root) -> raises 403 (root listing handled separately in list_files)
      - anything else -> raises 403
    * Path-traversal components (``..``) are rejected.
    """
    if is_privileged(user):
        return path

    # Sanitize
    stripped = path.strip("/")
    if stripped:
        parts = PurePosixPath(stripped).parts
        if ".." in parts:
            raise HTTPException(status_code=400, detail="Invalid path")
        normalized = PurePosixPath(*parts).as_posix()
    else:
        normalized = ""

    # "Shared with me" virtual folder
    if normalized == SHARED_WITH_ME_DIR:
        return normalized

    # Shared passthrough
    if normalized == SHARED_DIR_NAME or normalized.startswith(f"{SHARED_DIR_NAME}/"):
        return normalized

    # User's own home directory
    if normalized == user.username or normalized.startswith(f"{user.username}/"):
        return normalized

    # Check if path is shared with user via FileShare
    if normalized and db is not None and is_path_shared_with_user(db, normalized, user.id):
        return normalized

    # Root or other paths: block (root listing handled separately in list_files)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _unjail_path(path: str, user: UserPublic) -> str:
    """No-op — paths are real storage-relative paths for all users."""
    return path


router = APIRouter()


# --- Duplicate Check Endpoint ---

class CheckExistsRequest(BaseModel):
    filenames: list[str]
    target_path: str = ""


class ExistingFileInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_at: str
    checksum: str | None = None


@router.post("/check-exists")
@user_limiter.limit(get_limit("file_list"))
async def check_files_exist(
    request: Request,
    response: Response,
    payload: CheckExistsRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Check which files already exist in the target directory."""
    from datetime import datetime as dt, timezone as tz
    from app.services.files.operations import _resolve_path, ROOT_DIR
    from app.services import file_metadata_db

    jailed = _jail_path(payload.target_path, user, db)
    target_dir = _resolve_path(jailed)

    duplicates: list[dict] = []
    for filename in payload.filenames:
        # Reject path traversal attempts
        if "/" in filename or "\\" in filename or ".." in filename:
            continue
        file_path = target_dir / filename
        if file_path.exists() and file_path.is_file():
            rel = file_path.relative_to(ROOT_DIR).as_posix()
            meta = file_metadata_db.get_metadata(rel, db=db)
            stat = file_path.stat()
            duplicates.append(ExistingFileInfo(
                filename=filename,
                size_bytes=stat.st_size,
                modified_at=dt.fromtimestamp(stat.st_mtime, tz=tz.utc).isoformat(),
                checksum=meta.checksum if meta else None,
            ).model_dump())
    return {"duplicates": duplicates}


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
    path = _jail_path(path, user, db)
    metadata = file_metadata_db.ensure_metadata(path, requesting_user_id=user.id, db=db)
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
    """
    Set permission rules (shares) for a file.
    
    NOTE: owner_id in payload is ignored for backwards compatibility.
    To change ownership, use POST /api/files/transfer-ownership instead.
    """
    from app.services import file_metadata_db
    from app.models.file_share import FileShare
    # Nur Owner/Admin darf setzen
    payload.path = _jail_path(payload.path, user, db)
    metadata = file_metadata_db.ensure_metadata(payload.path, requesting_user_id=user.id, db=db)
    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")
    from app.services.permissions import ensure_owner_or_privileged
    ensure_owner_or_privileged(user, str(metadata.owner_id))
    
    # NOTE: owner_id changes are NOT applied here anymore.
    # Use POST /api/files/transfer-ownership for ownership changes.
    # This preserves the residency invariant (files must live in owner's directory).
    current_owner_id = metadata.owner_id
    
    # Bestehende Regeln löschen
    db.query(FileShare).filter(FileShare.file_id == metadata.id).delete()
    # Neue Regeln speichern
    for rule in payload.rules:
        share = FileShare(
            file_id=metadata.id,
            owner_id=current_owner_id,  # Use actual owner, not payload.owner_id
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
        owner_id=current_owner_id,  # Return actual owner
        rules=[FilePermissionRule(**rule) for rule in rules]
    )


@router.get("/mountpoints")
@user_limiter.limit(get_limit("file_list"))
async def get_mountpoints(
    request: Request,
    response: Response,
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
        # Production Mode: Single storage mountpoint at the storage root.
        import logging as _logging
        import shutil
        import psutil
        from app.services.files.operations import ROOT_DIR
        from app.services.hardware.raid import find_raid_mountpoint

        _logger = _logging.getLogger(__name__)

        raid_arrays = raid_status.arrays
        if raid_arrays:
            primary = raid_arrays[0]

            # Try to find the actual RAID mountpoint via /proc/mounts
            raid_mountpoint = find_raid_mountpoint(primary.name)
            if raid_mountpoint:
                usage = psutil.disk_usage(raid_mountpoint)
                size_bytes = usage.total
                used_bytes = usage.used
                available_bytes = usage.free
            else:
                # RAID not mounted — use ROOT_DIR consistently (both total AND used)
                # to avoid mixing RAID capacity with OS-SSD usage
                _logger.warning("RAID %s not mounted. Showing ROOT_DIR values.", primary.name)
                try:
                    fallback = shutil.disk_usage(ROOT_DIR)
                    size_bytes = fallback.total
                    used_bytes = fallback.used
                    available_bytes = fallback.free
                except Exception:
                    size_bytes = 0
                    used_bytes = 0
                    available_bytes = 0

            worst_status = "optimal"
            for a in raid_arrays:
                if a.status == "degraded":
                    worst_status = "degraded"
                    break
                if a.status == "rebuilding" and worst_status != "degraded":
                    worst_status = "rebuilding"

            mountpoints.append(StorageMountpoint(
                id=primary.name,
                name=f"{primary.level.upper()} Storage - {primary.name}",
                type="raid",
                path="",
                size_bytes=size_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                raid_level=primary.level,
                status=worst_status,
                is_default=True,
            ))
        else:
            # No RAID: use shutil.disk_usage on ROOT_DIR
            try:
                disk_usage = shutil.disk_usage(ROOT_DIR)
                size_bytes = disk_usage.total
                used_bytes = disk_usage.used
                available_bytes = disk_usage.free
            except Exception:
                size_bytes = 0
                used_bytes = 0
                available_bytes = 0

            mountpoints.append(StorageMountpoint(
                id="storage",
                name="Storage",
                type="storage",
                path="",
                size_bytes=size_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                raid_level=None,
                status="optimal",
                is_default=True,
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
    original_path = path

    # ── Non-admin root listing: show only Shared + user's home dir + Shared with me ──
    if not is_privileged(user) and not original_path.strip("/"):
        from datetime import datetime, timezone
        from sqlalchemy import select, func, or_
        from app.services.files.operations import _resolve_path
        from app.services.users import _create_home_directory
        from app.models.file_share import FileShare

        # Ensure home dir exists
        try:
            _create_home_directory(user.username, user.id, db=db)
        except Exception:
            pass

        entries: list[FileItem] = []

        # Shared directory
        shared_path = _resolve_path(SHARED_DIR_NAME)
        if shared_path.exists():
            stats = shared_path.stat()
            entries.append(FileItem(
                name=SHARED_DIR_NAME,
                path=SHARED_DIR_NAME,
                size=0,
                type="directory",
                modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
                owner_id=None,
                mime_type=None,
                file_id=None,
            ))

        # User's home directory
        home_path = _resolve_path(user.username)
        if home_path.exists():
            stats = home_path.stat()
            entries.append(FileItem(
                name=user.username,
                path=user.username,
                size=0,
                type="directory",
                modified_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
                owner_id=str(user.id),
                mime_type=None,
                file_id=None,
            ))

        # "Shared with me" virtual folder — only show if user has active shares
        now = datetime.now(timezone.utc)
        share_count = db.execute(
            select(func.count(FileShare.id)).where(
                FileShare.shared_with_user_id == user.id,
                FileShare.owner_id != user.id,
                FileShare.can_read.is_(True),
                or_(
                    FileShare.expires_at.is_(None),
                    FileShare.expires_at > now,
                ),
            )
        ).scalar_one()
        if share_count > 0:
            entries.append(FileItem(
                name=SHARED_WITH_ME_DIR,
                path=SHARED_WITH_ME_DIR,
                size=0,
                type="directory",
                modified_at=datetime.now(timezone.utc),
                owner_id=None,
                mime_type=None,
                file_id=None,
            ))

        return FileListResponse(files=entries)

    # ── "Shared with me" virtual listing ──
    if not is_privileged(user) and original_path.strip("/") == SHARED_WITH_ME_DIR:
        from datetime import datetime, timezone
        from sqlalchemy import select, or_
        from app.models.file_share import FileShare

        now = datetime.now(timezone.utc)
        shares = db.execute(
            select(FileShare).where(
                FileShare.shared_with_user_id == user.id,
                FileShare.owner_id != user.id,
                FileShare.can_read.is_(True),
                or_(
                    FileShare.expires_at.is_(None),
                    FileShare.expires_at > now,
                ),
            )
        ).scalars().all()

        entries: list[FileItem] = []
        for share in shares:
            file_meta = db.get(FileMetadata, share.file_id)
            if not file_meta:
                continue
            from app.models.user import User as UserModel
            owner = db.get(UserModel, share.owner_id)
            owner_name = owner.username if owner else str(share.owner_id)
            entries.append(FileItem(
                name=f"{file_meta.name} (from {owner_name})",
                path=file_meta.path,
                size=file_meta.size_bytes,
                type="directory" if file_meta.is_directory else "file",
                modified_at=file_meta.updated_at or file_meta.created_at,
                owner_id=str(share.owner_id),
                mime_type=file_meta.mime_type,
                file_id=file_meta.id,
            ))

        return FileListResponse(files=entries)

    # ── Admin or non-root path: normal behavior ──
    jailed_path = _jail_path(path, user, db)

    try:
        entries = list(file_service.list_directory(jailed_path, user=user, db=db))
    except PermissionDeniedError as exc:
        audit_logger.log_authorization_failure(
            user=user.username,
            action="list_directory",
            resource=jailed_path,
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
    resource_path = _jail_path(resource_path, user, db)
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
@user_limiter.limit(get_limit("file_download"))
async def download_file_by_id(
    file_id: int,
    request: Request,
    response: Response,
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
    path = _jail_path(path, user, db)
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

    return FileUploadResponse(message="Files uploaded", uploaded=len(saved), upload_ids=upload_ids)


@router.get("/storage/available")
@user_limiter.limit(get_limit("file_list"))
async def get_available_storage(
    request: Request,
    response: Response,
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
    resource_path = _jail_path(resource_path, user, db)
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
@user_limiter.limit(get_limit("file_delete"))
async def delete_path_body(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path required")
    path = _jail_path(path, user, db)
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
@user_limiter.limit(get_limit("file_delete"))
async def delete_path_post(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    # Delegate to delete_by_body logic
    return await delete_path_body(request=request, response=response, payload=payload, user=user, db=db)


@router.post("/folder", response_model=FileOperationResponse)
@user_limiter.limit(get_limit("file_write"))
async def create_folder(
    request: Request,
    response: Response,
    payload: FolderCreateRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    if not payload.name:
        raise HTTPException(status_code=400, detail="Folder name required")

    jailed_parent = _jail_path(payload.path or "", user, db)
    try:
        file_service.create_folder(jailed_parent, payload.name, owner=user, db=db)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileOperationResponse(message="Folder created")


@router.post("/mkdir", response_model=FileOperationResponse)
@user_limiter.limit(get_limit("file_write"))
async def mkdir_compat(
    request: Request,
    response: Response,
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

    jailed_parent = _jail_path(parent or "", user, db)
    try:
        file_service.create_folder(jailed_parent, name, owner=user, db=db)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileOperationResponse(message="Folder created")


@router.put("/rename", response_model=FileOperationResponse)
@user_limiter.limit(get_limit("file_write"))
async def rename_path(
    request: Request,
    response: Response,
    payload: RenameRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    jailed_old_path = _jail_path(payload.old_path, user, db)
    audit_logger = get_audit_logger_db()
    try:
        file_service.rename_path(jailed_old_path, payload.new_name, user=user, db=db)
    except PermissionDeniedError as exc:
        # Log unauthorized rename attempt
        audit_logger.log_authorization_failure(
            user=user.username,
            action="rename_file",
            resource=jailed_old_path,
            required_permission="write",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileOperationResponse(message="Renamed")


@router.put("/move", response_model=FileOperationResponse)
@user_limiter.limit(get_limit("file_write"))
async def move_path(
    request: Request,
    response: Response,
    payload: MoveRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    jailed_source = _jail_path(payload.source_path, user, db)
    jailed_target = _jail_path(payload.target_path, user, db)
    audit_logger = get_audit_logger_db()
    try:
        file_service.move_path(jailed_source, jailed_target, user=user, db=db)
    except PermissionDeniedError as exc:
        # Log unauthorized move attempt
        audit_logger.log_authorization_failure(
            user=user.username,
            action="move_file",
            resource=jailed_source,
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
@user_limiter.limit(get_limit("file_delete"))
async def delete_path_param(
    request: Request,
    response: Response,
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileOperationResponse:
    """Delete a file or directory by path (registered after `/delete` routes).
    This ensures the static `/delete` endpoint can accept a JSON body without
    being captured by the parameterized route."""
    resource_path = _jail_path(resource_path, user, db)
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


# ============================================================================
# Ownership Transfer Endpoints
# ============================================================================

@router.post("/transfer-ownership")
@user_limiter.limit(get_limit("file_delete"))  # Use stricter rate limit
async def transfer_ownership(
    request: Request,
    response: Response,
    payload: OwnershipTransferRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> OwnershipTransferResponse:
    """
    Transfer ownership of a file or directory to another user.
    
    Only the current owner or an admin can transfer ownership.
    For files outside Shared/, this will physically move the file
    to the new owner's directory to maintain the residency invariant.
    
    Conflict strategies:
    - rename: Add (2), (3), etc. to avoid conflicts
    - skip: Don't transfer if conflict exists
    - overwrite: Replace existing file (dangerous)
    """
    from app.services.files.ownership import transfer_ownership as do_transfer, OwnershipTransferResult
    from app.services.permissions import is_privileged
    
    # Validate and jail the path
    payload.path = _jail_path(payload.path, user, db)
    
    # Perform the transfer
    result: OwnershipTransferResult = do_transfer(
        path=payload.path,
        new_owner_id=payload.new_owner_id,
        requesting_user_id=user.id,
        requesting_user_is_admin=is_privileged(user),
        db=db,
        recursive=payload.recursive,
        conflict_strategy=payload.conflict_strategy,
    )
    
    if not result.success and result.error in ("NOT_FOUND", "DISK_NOT_FOUND"):
        raise HTTPException(status_code=404, detail=result.message)
    elif not result.success and result.error == "UNAUTHORIZED":
        raise HTTPException(status_code=403, detail=result.message)
    elif not result.success and result.error == "INVALID_TARGET_USER":
        raise HTTPException(status_code=400, detail=result.message)
    elif not result.success and result.error == "HOME_DIRECTORY":
        raise HTTPException(status_code=400, detail=result.message)
    
    return OwnershipTransferResponse(
        success=result.success,
        message=result.message,
        transferred_count=result.transferred_count,
        skipped_count=result.skipped_count,
        new_path=result.new_path,
        conflicts=[
            ConflictInfo(
                original_path=c.original_path,
                resolved_path=c.resolved_path,
                action=c.action
            )
            for c in result.conflicts
        ],
        error=result.error,
    )


@router.post("/enforce-residency")
@user_limiter.limit(get_limit("admin"))  # Admin-only rate limit
async def enforce_residency_endpoint(
    request: Request,
    response: Response,
    payload: EnforceResidencyRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> EnforceResidencyResponse:
    """
    Scan for and optionally fix residency violations (Admin only).
    
    A residency violation occurs when a file's owner doesn't match
    the top-level directory containing it (except for Shared/).
    
    Set dry_run=True to only scan without fixing.
    Set scope to a username to limit the scan to that user's files.
    """
    from app.services.files.ownership import enforce_residency, ResidencyEnforcementResult
    
    # Admin only
    if not is_privileged(user):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can enforce residency"
        )
    
    result: ResidencyEnforcementResult = enforce_residency(
        db=db,
        dry_run=payload.dry_run,
        scope=payload.scope,
        requesting_user_id=user.id,
        conflict_strategy="rename",
    )
    
    return EnforceResidencyResponse(
        violations=[
            ResidencyViolation(
                path=v.path,
                current_owner_id=v.current_owner_id,
                current_owner_username=v.current_owner_username,
                expected_directory=v.expected_directory,
                actual_directory=v.actual_directory
            )
            for v in result.violations
        ],
        fixed_count=result.fixed_count,
    )

