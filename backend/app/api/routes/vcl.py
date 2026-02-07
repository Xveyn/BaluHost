"""VCL (Version Control Light) API Routes."""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.schemas.vcl import (
    VersionListResponse,
    VersionDetail,
    RestoreRequest,
    RestoreResponse,
    QuotaInfo,
    VCLSettingsResponse,
    VCLSettingsUpdate,
    AdminVCLOverview,
    AdminUserQuota,
    AdminStatsResponse,
    CleanupRequest,
    CleanupResponse,
)
from app.schemas.vcl_diff import VersionDiffResponse, DiffLine
from app.services.vcl import VCLService
from app.services.vcl_priority import VCLPriorityMode
from app.services.audit_logger_db import get_audit_logger_db
from app.models.vcl import VCLSettings, VCLStats, FileVersion
from app.models.user import User
from app.models.file_metadata import FileMetadata


def needs_cleanup(settings: VCLSettings) -> bool:
    """Check if cleanup is needed based on usage."""
    # Cast Columns for conditionals
    is_enabled: bool = bool(settings.is_enabled)  # type: ignore
    if not is_enabled:
        return False
    
    # Calculate headroom - cast Columns for arithmetic
    max_size: int = int(settings.max_size_bytes)  # type: ignore
    headroom_pct: int = int(settings.headroom_percent)  # type: ignore
    current_usage: int = int(settings.current_usage_bytes)  # type: ignore
    
    headroom_bytes = int(max_size * (headroom_pct / 100))
    target_usage = max_size - headroom_bytes
    
    return current_usage >= target_usage

router = APIRouter()


# ============================================================================
# USER ENDPOINTS
# ============================================================================

@router.get("/versions/{file_id}", response_model=VersionListResponse)
@user_limiter.limit(get_limit("file_list"))
async def list_file_versions(
    request: Request,
    response: Response,
    file_id: int,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> VersionListResponse:
    """
    List all versions of a specific file.
    
    Args:
        file_id: ID of the file
        limit: Maximum number of versions to return (default: 50)
        offset: Number of versions to skip (default: 0)
        
    Returns:
        List of file versions with metadata
        
    Raises:
        404: File not found or user has no access
    """
    # Check if file exists and user has access
    query_filters = [FileMetadata.id == file_id]
    if user.role != "admin":
        query_filters.append(FileMetadata.owner_id == user.id)
    file_meta = db.query(FileMetadata).filter(*query_filters).first()
    
    if not file_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or access denied"
        )
    
    # Get versions
    query = db.query(FileVersion).filter(
        FileVersion.file_id == file_id
    ).order_by(FileVersion.version_number.desc())
    
    total = query.count()
    versions = query.offset(offset).limit(limit).all()
    
    # Convert to response format - cast Columns to Python types
    version_details = []
    for v in versions:
        version_details.append(VersionDetail(
            id=int(v.id),  # type: ignore
            version_number=int(v.version_number),  # type: ignore
            file_size=int(v.file_size),  # type: ignore
            compressed_size=int(v.compressed_size),  # type: ignore
            compression_ratio=float(v.compression_ratio or 0.0),  # type: ignore
            checksum=str(v.checksum),  # type: ignore
            created_at=v.created_at,  # type: ignore
            is_high_priority=bool(v.is_high_priority),  # type: ignore
            change_type=str(v.change_type) if v.change_type else None,  # type: ignore
            comment=str(v.comment) if v.comment else None,  # type: ignore
            was_cached=bool(v.was_cached),  # type: ignore
            storage_type=str(v.storage_type),  # type: ignore
        ))
    
    return VersionListResponse(
        file_id=file_id,
        file_path=file_meta.path,
        total_versions=total,
        versions=version_details,
    )


@router.post("/restore", response_model=RestoreResponse)
@user_limiter.limit(get_limit("file_write"))
async def restore_file_version(
    request: Request,
    response: Response,
    restore_req: RestoreRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> RestoreResponse:
    """
    Restore a file to a specific version.
    
    Args:
        restore_req: Restore request with version_id
        
    Returns:
        Restore confirmation with new file metadata
        
    Raises:
        404: Version not found or user has no access
        500: Restore operation failed
    """
    import shutil
    from pathlib import Path
    from app.core.config import settings
    
    audit_logger = get_audit_logger_db()
    
    # Get version
    version = db.query(FileVersion).filter(
        FileVersion.id == restore_req.version_id,
        FileVersion.user_id == user.id
    ).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found or access denied"
        )
    
    # Get file metadata
    file_meta = db.query(FileMetadata).filter(
        FileMetadata.id == version.file_id
    ).first()
    
    if not file_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File metadata not found"
        )
    
    try:
        vcl_service = VCLService(db)
        
        # Get version content (decompress if needed)
        blob_id_val: int = int(version.blob_id) if version.blob_id else 0  # type: ignore
        if blob_id_val:
            blob = version.blob
            if not blob:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Version blob not found"
                )
            
            # Read and decompress content
            blob_storage_path: str = str(blob.storage_path)  # type: ignore
            blob_path = Path(settings.nas_storage_path) / blob_storage_path
            if not blob_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Version content not found on disk"
                )
            
            with open(blob_path, 'rb') as f:
                compressed_content = f.read()
            
            content = vcl_service.decompress_content(compressed_content)
        else:
            # Direct storage - read from file path
            version_path = Path(settings.nas_storage_path) / file_meta.path
            if not version_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Version file not found on disk"
                )
            
            with open(version_path, 'rb') as f:
                content = f.read()
        
        # Write restored content to file
        file_meta_path: str = str(file_meta.path)  # type: ignore
        file_path = Path(settings.nas_storage_path) / file_meta_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Update file metadata - use SQL update to avoid Column assignment
        from sqlalchemy import update as sql_update
        db.execute(
            sql_update(FileMetadata).
            where(FileMetadata.id == file_meta.id).
            values(size_bytes=len(content))
        )
        db.commit()
        
        # Log restore action
        vers_id: int = int(version.id)  # type: ignore
        vers_number: int = int(version.version_number)  # type: ignore
        
        audit_logger.log_file_access(
            user=user.username,
            file_path=file_meta_path,
            action="restore_version",
            success=True,
            metadata={
                "version_id": vers_id,
                "version_number": vers_number,
                "file_size": len(content),
            },
            db=db
        )
        
        file_meta_id: int = int(file_meta.id)  # type: ignore
        
        return RestoreResponse(
            success=True,
            message=f"File restored to version {vers_number}",
            file_id=file_meta_id,
            file_path=file_meta_path,
            restored_version=vers_number,
            file_size=len(content),
        )
        
    except Exception as e:
        audit_logger.log_file_access(
            user=user.username,
            file_path=file_meta.path,
            action="restore_version",
            success=False,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore file: {str(e)}"
        )


@router.get("/versions/diff", response_model=VersionDiffResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_version_diff(
    request: Request,
    response: Response,
    version_id_old: int,
    version_id_new: int,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> VersionDiffResponse:
    """
    Get diff between two file versions.
    
    Args:
        version_id_old: ID of older version
        version_id_new: ID of newer version
        
    Returns:
        Diff between versions (line-by-line for text, binary marker otherwise)
        
    Raises:
        404: Version not found or user has no access
        400: Both versions must belong to same file
    """
    import difflib
    from pathlib import Path
    
    # Get both versions
    version_old = db.query(FileVersion).filter(
        FileVersion.id == version_id_old,
        FileVersion.user_id == user.id
    ).first()
    
    version_new = db.query(FileVersion).filter(
        FileVersion.id == version_id_new,
        FileVersion.user_id == user.id
    ).first()
    
    if not version_old or not version_new:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both versions not found"
        )
    
    # Check they belong to same file
    if version_old.file_id != version_new.file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Versions must belong to the same file"
        )
    
    # Get file metadata for name
    file_meta = db.query(FileMetadata).filter(FileMetadata.id == version_old.file_id).first()
    if not file_meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    
    file_name = Path(file_meta.path).name
    
    # Helper to check if file is binary
    def is_binary_content(content: bytes) -> bool:
        """Check if content is binary."""
        # Check for null bytes
        if b'\x00' in content[:1024]:
            return True
        # Check for high ratio of non-text bytes
        text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x7f)))
        non_text = len([b for b in content[:1024] if b not in text_chars])
        return non_text / min(len(content[:1024]), 1024) > 0.3
    
    # Read content from storage
    vcl_service = VCLService(db)
    try:
        content_old = vcl_service.get_version_content(version_old)
        content_new = vcl_service.get_version_content(version_new)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read version content: {str(e)}"
        )
    
    # Check if binary
    is_binary = is_binary_content(content_old) or is_binary_content(content_new)
    
    if is_binary:
        return VersionDiffResponse(
            version_id_old=version_id_old,
            version_id_new=version_id_new,
            file_name=file_name,
            is_binary=True,
            old_size=len(content_old),
            new_size=len(content_new),
            message="Binary files cannot be compared line-by-line"
        )
    
    # Text diff
    try:
        text_old = content_old.decode('utf-8')
        text_new = content_new.decode('utf-8')
    except UnicodeDecodeError:
        return VersionDiffResponse(
            version_id_old=version_id_old,
            version_id_new=version_id_new,
            file_name=file_name,
            is_binary=True,
            old_size=len(content_old),
            new_size=len(content_new),
            message="File encoding not supported"
        )
    
    lines_old = text_old.splitlines(keepends=True)
    lines_new = text_new.splitlines(keepends=True)
    
    # Generate unified diff
    diff = list(difflib.unified_diff(lines_old, lines_new, lineterm=''))
    
    # Parse diff into structured format
    diff_lines = []
    old_line_num = 0
    new_line_num = 0
    
    for line in diff[2:]:  # Skip header lines
        if line.startswith('@@'):
            # Parse line numbers from @@ -old_start,old_count +new_start,new_count @@
            import re
            match = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if match:
                old_line_num = int(match.group(1)) - 1
                new_line_num = int(match.group(2)) - 1
            continue
        
        if line.startswith('-'):
            old_line_num += 1
            diff_lines.append(DiffLine(
                line_number_old=old_line_num,
                line_number_new=None,
                content=line[1:],
                type='removed'
            ))
        elif line.startswith('+'):
            new_line_num += 1
            diff_lines.append(DiffLine(
                line_number_old=None,
                line_number_new=new_line_num,
                content=line[1:],
                type='added'
            ))
        else:
            old_line_num += 1
            new_line_num += 1
            diff_lines.append(DiffLine(
                line_number_old=old_line_num,
                line_number_new=new_line_num,
                content=line[1:] if line.startswith(' ') else line,
                type='unchanged'
            ))
    
    return VersionDiffResponse(
        version_id_old=version_id_old,
        version_id_new=version_id_new,
        file_name=file_name,
        is_binary=False,
        old_size=len(content_old),
        new_size=len(content_new),
        diff_lines=diff_lines
    )


@router.get("/quota", response_model=QuotaInfo)
@user_limiter.limit(get_limit("file_list"))
async def get_user_quota(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> QuotaInfo:
    """
    Get VCL quota information for current user.
    
    Returns:
        Quota info including usage, limits, and settings
    """
    # Get or create user settings
    settings = db.query(VCLSettings).filter(
        VCLSettings.user_id == user.id
    ).first()
    
    if not settings:
        # Create default settings
        from app.services.vcl import VCLService
        vcl_service = VCLService(db)
        settings = vcl_service.get_or_create_user_settings(user.id)
    
    # Calculate percentage - cast Columns
    current_usage: int = int(settings.current_usage_bytes)  # type: ignore
    max_size: int = int(settings.max_size_bytes)  # type: ignore
    usage_percent = (current_usage / max_size * 100) if max_size > 0 else 0
    
    # Determine quota warning level
    quota_warning = None
    if usage_percent >= 95:
        quota_warning = 'critical'
    elif usage_percent >= 80:
        quota_warning = 'warning'
    
    # Check if cleanup needed
    cleanup_needed = needs_cleanup(settings)
    
    return QuotaInfo(
        max_size_bytes=max_size,
        current_usage_bytes=current_usage,
        available_bytes=max(0, max_size - current_usage),
        usage_percent=usage_percent,
        is_enabled=bool(settings.is_enabled),  # type: ignore
        depth=int(settings.depth),  # type: ignore
        compression_enabled=bool(settings.compression_enabled),  # type: ignore
        dedupe_enabled=bool(settings.dedupe_enabled),  # type: ignore
        cleanup_needed=cleanup_needed,
        quota_warning=quota_warning,
    )


@router.get("/settings", response_model=VCLSettingsResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_vcl_settings(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> VCLSettingsResponse:
    """
    Get VCL settings for current user.
    
    Returns:
        Complete VCL settings
    """
    settings = db.query(VCLSettings).filter(
        VCLSettings.user_id == user.id
    ).first()
    
    if not settings:
        # Create default settings
        from app.services.vcl import VCLService
        vcl_service = VCLService(db)
        settings = vcl_service.get_or_create_user_settings(user.id)
    
    # Cast all Columns to Python types for Pydantic schema
    return VCLSettingsResponse(
        user_id=int(settings.user_id) if settings.user_id else None,  # type: ignore
        max_size_bytes=int(settings.max_size_bytes),  # type: ignore
        current_usage_bytes=int(settings.current_usage_bytes),  # type: ignore
        depth=int(settings.depth),  # type: ignore
        headroom_percent=int(settings.headroom_percent),  # type: ignore
        is_enabled=bool(settings.is_enabled),  # type: ignore
        compression_enabled=bool(settings.compression_enabled),  # type: ignore
        dedupe_enabled=bool(settings.dedupe_enabled),  # type: ignore
        debounce_window_seconds=int(settings.debounce_window_seconds),  # type: ignore
        max_batch_window_seconds=int(settings.max_batch_window_seconds),  # type: ignore
        created_at=settings.created_at,  # type: ignore
        updated_at=settings.updated_at,  # type: ignore
    )


@router.put("/settings", response_model=VCLSettingsResponse)
@user_limiter.limit(get_limit("file_write"))
async def update_vcl_settings(
    request: Request,
    response: Response,
    settings_update: VCLSettingsUpdate,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> VCLSettingsResponse:
    """
    Update VCL settings for current user.
    
    Args:
        settings_update: Updated settings
        
    Returns:
        Updated VCL settings
    """
    from app.services.vcl import VCLService
    
    vcl_service = VCLService(db)
    settings = vcl_service.get_or_create_user_settings(user.id)
    
    # Build update dict
    update_values = {}
    if settings_update.max_size_bytes is not None:
        update_values['max_size_bytes'] = settings_update.max_size_bytes
    if settings_update.depth is not None:
        update_values['depth'] = settings_update.depth
    if settings_update.headroom_percent is not None:
        update_values['headroom_percent'] = settings_update.headroom_percent
    if settings_update.is_enabled is not None:
        update_values['is_enabled'] = settings_update.is_enabled
    if settings_update.compression_enabled is not None:
        update_values['compression_enabled'] = settings_update.compression_enabled
    if settings_update.dedupe_enabled is not None:
        update_values['dedupe_enabled'] = settings_update.dedupe_enabled
    if settings_update.debounce_window_seconds is not None:
        update_values['debounce_window_seconds'] = settings_update.debounce_window_seconds
    if settings_update.max_batch_window_seconds is not None:
        update_values['max_batch_window_seconds'] = settings_update.max_batch_window_seconds
    
    # Apply updates with SQL to avoid Column assignment issues
    if update_values:
        from sqlalchemy import update as sql_update
        db.execute(
            sql_update(VCLSettings).
            where(VCLSettings.user_id == user.id).
            values(**update_values)
        )
        db.commit()
        db.refresh(settings)
    
    # Log settings change
    audit_logger = get_audit_logger_db()
    audit_logger.log_system_event(
        event_type="vcl_settings_update",
        description=f"User {user.username} updated VCL settings",
        metadata=settings_update.model_dump(),
        db=db
    )
    
    # Cast Columns for response
    return VCLSettingsResponse(
        user_id=int(settings.user_id) if settings.user_id else None,  # type: ignore
        max_size_bytes=int(settings.max_size_bytes),  # type: ignore
        current_usage_bytes=int(settings.current_usage_bytes),  # type: ignore
        depth=int(settings.depth),  # type: ignore
        headroom_percent=int(settings.headroom_percent),  # type: ignore
        is_enabled=bool(settings.is_enabled),  # type: ignore
        compression_enabled=bool(settings.compression_enabled),  # type: ignore
        dedupe_enabled=bool(settings.dedupe_enabled),  # type: ignore
        debounce_window_seconds=int(settings.debounce_window_seconds),  # type: ignore
        max_batch_window_seconds=int(settings.max_batch_window_seconds),  # type: ignore
        created_at=settings.created_at,  # type: ignore
        updated_at=settings.updated_at,  # type: ignore
    )


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.get("/admin/overview", response_model=AdminVCLOverview)
@user_limiter.limit(get_limit("admin"))
async def get_vcl_overview(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AdminVCLOverview:
    """
    Get global VCL statistics and overview (Admin only).
    
    Returns:
        Global VCL statistics
    """
    stats = db.query(VCLStats).first()
    
    if not stats:
        # Create initial stats
        from app.services.vcl import VCLService
        vcl_service = VCLService(db)
        try:
            vcl_service.recalculate_stats()
            db.commit()
            stats = db.query(VCLStats).first()
        except Exception as e:
            db.rollback()
            # If stats creation fails, return empty stats
            stats = None
    
    # Get total users count
    total_users = db.query(VCLSettings).count()
    
    # Calculate average compression ratio - cast Columns
    total_comp: int = int(stats.total_compressed_bytes) if stats else 0  # type: ignore
    total_size: int = int(stats.total_size_bytes) if stats else 0  # type: ignore
    
    compression_ratio = 0.0
    if total_comp > 0 and total_size > 0:
        compression_ratio = (1 - total_comp / total_size) * 100
    
    # Cast all stat Columns for response
    total_versions: int = int(stats.total_versions) if stats else 0  # type: ignore
    total_blobs: int = int(stats.total_blobs) if stats else 0  # type: ignore
    unique_blobs: int = int(stats.unique_blobs) if stats else 0  # type: ignore
    dedup_savings: int = int(stats.deduplication_savings_bytes) if stats else 0  # type: ignore
    comp_savings: int = int(stats.compression_savings_bytes) if stats else 0  # type: ignore
    priority_count: int = int(stats.priority_count) if stats else 0  # type: ignore
    cached_count: int = int(stats.cached_versions_count) if stats else 0  # type: ignore
    
    return AdminVCLOverview(
        total_versions=total_versions,
        total_size_bytes=total_size,
        total_compressed_bytes=total_comp,
        total_blobs=total_blobs,
        unique_blobs=unique_blobs,
        deduplication_savings_bytes=dedup_savings,
        compression_savings_bytes=comp_savings,
        total_savings_bytes=dedup_savings + comp_savings,
        compression_ratio=compression_ratio,
        priority_count=priority_count,
        cached_versions_count=cached_count,
        total_users=total_users,
        last_cleanup_at=stats.last_cleanup_at if stats else None,  # type: ignore
        last_priority_mode_at=stats.last_priority_mode_at if stats else None,  # type: ignore
        updated_at=stats.updated_at if stats else None,  # type: ignore
    )


@router.get("/admin/users", response_model=List[AdminUserQuota])
@user_limiter.limit(get_limit("admin"))
async def list_user_quotas(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> List[AdminUserQuota]:
    """
    List VCL quota information for all users (Admin only).
    
    Returns:
        List of user quotas
    """
    # Get ALL users first
    all_users = db.query(User).all()
    
    # Get all existing settings in one query
    existing_settings = {
        s.user_id: s 
        for s in db.query(VCLSettings).filter(
            VCLSettings.user_id.in_([u.id for u in all_users])
        ).all()
    }
    
    # Create missing settings in batch (avoid locks)
    from app.services.vcl import VCLService
    vcl_service = VCLService(db)
    
    for user_obj in all_users:
        if user_obj.id not in existing_settings:
            # Create default settings
            new_settings = VCLSettings(
                user_id=user_obj.id,
                max_size_bytes=10 * 1024 * 1024 * 1024,  # 10 GB default
                current_usage_bytes=0,
                depth=5,
                headroom_percent=10,
                is_enabled=True,
                compression_enabled=True,
                dedupe_enabled=True,
                debounce_window_seconds=30,
                max_batch_window_seconds=300,
            )
            db.add(new_settings)
            existing_settings[user_obj.id] = new_settings
    
    # Commit all new settings at once
    db.commit()
    
    result = []
    for user_obj in all_users:
        settings = existing_settings[user_obj.id]
        
        # Count total versions for this user
        total_versions = db.query(func.count(FileVersion.id)).filter(
            FileVersion.user_id == user_obj.id
        ).scalar() or 0
        
        usage_percent = (settings.current_usage_bytes / settings.max_size_bytes * 100) if settings.max_size_bytes > 0 else 0
        cleanup_needed = needs_cleanup(settings)
        
        result.append(AdminUserQuota(
            user_id=user_obj.id,
            username=user_obj.username,
            max_size_bytes=settings.max_size_bytes,
            current_usage_bytes=settings.current_usage_bytes,
            usage_percent=usage_percent,
            total_versions=total_versions,
            is_enabled=settings.is_enabled,
            cleanup_needed=cleanup_needed,
        ))
    
    return result


@router.put("/admin/settings/{user_id}", response_model=VCLSettingsResponse)
@user_limiter.limit(get_limit("admin"))
async def admin_update_user_settings(
    request: Request,
    response: Response,
    user_id: int,
    settings_update: VCLSettingsUpdate,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> VCLSettingsResponse:
    """
    Update VCL settings for specific user (Admin only).
    
    Args:
        user_id: Target user ID
        settings_update: Updated settings
        
    Returns:
        Updated VCL settings
    """
    from app.services.vcl import VCLService
    
    vcl_service = VCLService(db)
    settings = vcl_service.get_or_create_user_settings(user_id)
    
    # Update fields
    if settings_update.max_size_bytes is not None:
        settings.max_size_bytes = settings_update.max_size_bytes
    if settings_update.depth is not None:
        settings.depth = settings_update.depth
    if settings_update.headroom_percent is not None:
        settings.headroom_percent = settings_update.headroom_percent
    if settings_update.is_enabled is not None:
        settings.is_enabled = settings_update.is_enabled
    if settings_update.compression_enabled is not None:
        settings.compression_enabled = settings_update.compression_enabled
    if settings_update.dedupe_enabled is not None:
        settings.dedupe_enabled = settings_update.dedupe_enabled
    if settings_update.debounce_window_seconds is not None:
        settings.debounce_window_seconds = settings_update.debounce_window_seconds
    if settings_update.max_batch_window_seconds is not None:
        settings.max_batch_window_seconds = settings_update.max_batch_window_seconds
    
    db.commit()
    db.refresh(settings)
    
    # Log admin action
    audit_logger = get_audit_logger_db()
    audit_logger.log_system_config_change(
        action="update_user_vcl_settings",
        user=admin.username,
        config_key=f"vcl_settings:user_id:{user_id}",
        new_value=settings_update.model_dump(),
        db=db
    )
    
    return VCLSettingsResponse(
        user_id=settings.user_id,
        max_size_bytes=settings.max_size_bytes,
        current_usage_bytes=settings.current_usage_bytes,
        depth=settings.depth,
        headroom_percent=settings.headroom_percent,
        is_enabled=settings.is_enabled,
        compression_enabled=settings.compression_enabled,
        dedupe_enabled=settings.dedupe_enabled,
        debounce_window_seconds=settings.debounce_window_seconds,
        max_batch_window_seconds=settings.max_batch_window_seconds,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.post("/admin/cleanup", response_model=CleanupResponse)
@user_limiter.limit(get_limit("admin"))
async def trigger_manual_cleanup(
    request: Request,
    response: Response,
    cleanup_req: CleanupRequest,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> CleanupResponse:
    """
    Manually trigger VCL cleanup for specific user or all users (Admin only).
    
    Args:
        cleanup_req: Cleanup request with optional user_id
        
    Returns:
        Cleanup results
    """
    audit_logger = get_audit_logger_db()
    vcl_service = VCLService(db)
    priority_mode = VCLPriorityMode(db)
    
    try:
        if cleanup_req.user_id:
            # Cleanup specific user
            settings = db.query(VCLSettings).filter(
                VCLSettings.user_id == cleanup_req.user_id
            ).first()
            
            if not settings:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User VCL settings not found"
                )
            
            if cleanup_req.dry_run:
                # Dry run - only calculate what would be deleted
                # Count versions that would be deleted
                deleted = 0
                freed_bytes = 0
                # Simple estimation: count old versions
                versions = db.query(FileVersion).filter(
                    FileVersion.user_id == cleanup_req.user_id
                ).order_by(FileVersion.created_at.desc()).offset(10).all()
                deleted = len(versions)
                freed_bytes = sum(v.file_size for v in versions)
            else:
                # Actually perform cleanup
                deleted, freed_bytes = priority_mode.cleanup_user_versions(cleanup_req.user_id)
                
                # Also enforce depth limit
                priority_mode.enforce_depth_limit(cleanup_req.user_id)
                
                # Commit changes
                db.commit()
                
                # Update stats
                try:
                    vcl_service.recalculate_stats()
                    db.commit()
                except Exception:
                    # Stats recalculation is not critical
                    pass
            
            audit_logger.log_system_config_change(
                action="manual_vcl_cleanup" + ("_dry_run" if cleanup_req.dry_run else ""),
                user=admin.username,
                config_key=f"vcl_cleanup:user_id:{cleanup_req.user_id}",
                new_value={"deleted_versions": deleted, "freed_bytes": freed_bytes},
                db=db
            )
            
            return CleanupResponse(
                success=True,
                message=f"{'[DRY RUN] Would cleanup' if cleanup_req.dry_run else 'Cleanup completed'} for user {cleanup_req.user_id}",
                deleted_versions=deleted,
                freed_bytes=freed_bytes,
                affected_users=1,
            )
        else:
            # Cleanup all users
            all_settings = db.query(VCLSettings).all()
            total_deleted = 0
            total_freed = 0
            affected = 0
            
            for settings in all_settings:
                if needs_cleanup(settings):
                    if cleanup_req.dry_run:
                        # Dry run estimation
                        versions = db.query(FileVersion).filter(
                            FileVersion.user_id == settings.user_id
                        ).order_by(FileVersion.created_at.desc()).offset(10).all()
                        total_deleted += len(versions)
                        total_freed += sum(v.file_size for v in versions)
                        affected += 1
                    else:
                        deleted, freed_bytes = priority_mode.cleanup_user_versions(settings.user_id)
                        total_deleted += deleted
                        total_freed += freed_bytes
                        affected += 1
                    
                        # Enforce depth limit
                        priority_mode.enforce_depth_limit(settings.user_id)
            
            if not cleanup_req.dry_run:
                # Commit all changes
                db.commit()
                
                # Update stats
                try:
                    vcl_service.recalculate_stats()
                    db.commit()
                except Exception:
                    # Stats recalculation is not critical
                    pass
            
            audit_logger.log_system_config_change(
                action="manual_vcl_cleanup_all" + ("_dry_run" if cleanup_req.dry_run else ""),
                user=admin.username,
                config_key="vcl_cleanup:all_users",
                new_value={
                    "deleted_versions": total_deleted,
                    "freed_bytes": total_freed,
                    "affected_users": affected,
                },
                db=db
            )
            
            return CleanupResponse(
                success=True,
                message=f"{'[DRY RUN] Would cleanup' if cleanup_req.dry_run else 'Cleanup completed'} for {affected} users",
                deleted_versions=total_deleted,
                freed_bytes=total_freed,
                affected_users=affected,
            )
            
    except Exception as e:
        audit_logger.log_system_config_change(
            action="manual_vcl_cleanup_failed",
            user=admin.username,
            config_key=f"vcl_cleanup:{f'user_id:{cleanup_req.user_id}' if cleanup_req.user_id else 'all_users'}",
            new_value={"error": str(e)},
            success=False,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/admin/stats", response_model=AdminStatsResponse)
@user_limiter.limit(get_limit("admin"))
async def get_detailed_stats(
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AdminStatsResponse:
    """
    Get detailed VCL statistics (Admin only).
    
    Returns:
        Detailed statistics including deduplication and compression ratios
    """
    stats = db.query(VCLStats).first()
    
    if not stats:
        from app.services.vcl import VCLService
        vcl_service = VCLService(db)
        vcl_service.recalculate_stats()
        stats = db.query(VCLStats).first()
    
    # Calculate ratios
    dedup_ratio = (stats.deduplication_savings_bytes / stats.total_size_bytes * 100) if stats.total_size_bytes > 0 else 0
    compression_ratio = (stats.compression_savings_bytes / stats.total_size_bytes * 100) if stats.total_size_bytes > 0 else 0
    total_savings_ratio = ((stats.deduplication_savings_bytes + stats.compression_savings_bytes) / stats.total_size_bytes * 100) if stats.total_size_bytes > 0 else 0
    
    return AdminStatsResponse(
        total_versions=stats.total_versions,
        total_size_bytes=stats.total_size_bytes,
        total_compressed_bytes=stats.total_compressed_bytes,
        total_blobs=stats.total_blobs,
        unique_blobs=stats.unique_blobs,
        deduplication_savings_bytes=stats.deduplication_savings_bytes,
        compression_savings_bytes=stats.compression_savings_bytes,
        deduplication_ratio_percent=dedup_ratio,
        compression_ratio_percent=compression_ratio,
        total_savings_ratio_percent=total_savings_ratio,
        priority_count=stats.priority_count,
        cached_versions_count=stats.cached_versions_count,
        last_cleanup_at=stats.last_cleanup_at,
        last_priority_mode_at=stats.last_priority_mode_at,
        last_deduplication_scan=stats.last_deduplication_scan,
        updated_at=stats.updated_at,
    )
