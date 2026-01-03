"""VCL (Version Control Light) API Routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

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
from app.services.vcl import VCLService
from app.services.vcl_priority import VCLPriorityMode
from app.services.audit_logger_db import get_audit_logger_db
from app.models.vcl import VCLSettings, VCLStats


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
    from app.models.file_metadata import FileMetadata
    from app.models.vcl import FileVersion
    
    # Check if file exists and user has access
    file_meta = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == user.id
    ).first()
    
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
    from app.models.vcl import FileVersion
    from app.models.file_metadata import FileMetadata
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
        if version.blob_id:
            blob = version.blob
            if not blob:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Version blob not found"
                )
            
            # Read and decompress content
            blob_path = Path(settings.nas_storage_path) / blob.storage_path
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
        file_path = Path(settings.nas_storage_path) / file_meta.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Update file metadata
        file_meta.size = len(content)
        db.commit()
        
        # Log restore action
        audit_logger.log_file_access(
            user=user.username,
            file_path=file_meta.path,
            action="restore_version",
            success=True,
            metadata={
                "version_id": version.id,
                "version_number": version.version_number,
                "file_size": len(content),
            },
            db=db
        )
        
        return RestoreResponse(
            success=True,
            message=f"File restored to version {version.version_number}",
            file_id=file_meta.id,
            file_path=file_meta.path,
            restored_version=version.version_number,
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
        settings = vcl_service.get_or_create_settings(user.id)
    
    # Calculate percentage
    usage_percent = (settings.current_usage_bytes / settings.max_size_bytes * 100) if settings.max_size_bytes > 0 else 0
    
    # Check if cleanup needed
    cleanup_needed = needs_cleanup(settings)
    
    return QuotaInfo(
        max_size_bytes=settings.max_size_bytes,
        current_usage_bytes=settings.current_usage_bytes,
        available_bytes=max(0, settings.max_size_bytes - settings.current_usage_bytes),
        usage_percent=usage_percent,
        is_enabled=settings.is_enabled,
        depth=settings.depth,
        compression_enabled=settings.compression_enabled,
        dedupe_enabled=settings.dedupe_enabled,
        cleanup_needed=cleanup_needed,
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
        settings = vcl_service.get_or_create_settings(user.id)
    
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
    settings = vcl_service.get_or_create_settings(user.id)
    
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
    
    # Log settings change
    audit_logger = get_audit_logger_db()
    audit_logger.log_settings_change(
        user=user.username,
        setting_name="vcl_settings",
        old_value="<settings>",
        new_value=settings_update.model_dump_json(),
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
        vcl_service.recalculate_stats()
        stats = db.query(VCLStats).first()
    
    # Get total users count
    total_users = db.query(VCLSettings).count()
    
    # Calculate average compression ratio
    compression_ratio = 0.0
    if stats.total_compressed_bytes > 0:
        compression_ratio = (1 - stats.total_compressed_bytes / stats.total_size_bytes) * 100
    
    return AdminVCLOverview(
        total_versions=stats.total_versions,
        total_size_bytes=stats.total_size_bytes,
        total_compressed_bytes=stats.total_compressed_bytes,
        total_blobs=stats.total_blobs,
        unique_blobs=stats.unique_blobs,
        deduplication_savings_bytes=stats.deduplication_savings_bytes,
        compression_savings_bytes=stats.compression_savings_bytes,
        total_savings_bytes=stats.deduplication_savings_bytes + stats.compression_savings_bytes,
        compression_ratio=compression_ratio,
        priority_count=stats.priority_count,
        cached_versions_count=stats.cached_versions_count,
        total_users=total_users,
        last_cleanup_at=stats.last_cleanup_at,
        last_priority_mode_at=stats.last_priority_mode_at,
        updated_at=stats.updated_at,
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
    from app.models.user import User
    
    settings_list = db.query(VCLSettings).all()
    
    result = []
    for settings in settings_list:
        user_obj = db.query(User).filter(User.id == settings.user_id).first()
        if not user_obj:
            continue
        
        usage_percent = (settings.current_usage_bytes / settings.max_size_bytes * 100) if settings.max_size_bytes > 0 else 0
        cleanup_needed = needs_cleanup(settings)
        
        result.append(AdminUserQuota(
            user_id=settings.user_id,
            username=user_obj.username,
            max_size_bytes=settings.max_size_bytes,
            current_usage_bytes=settings.current_usage_bytes,
            usage_percent=usage_percent,
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
    settings = vcl_service.get_or_create_settings(user_id)
    
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
    audit_logger.log_admin_action(
        admin=admin.username,
        action="update_user_vcl_settings",
        target=f"user_id:{user_id}",
        metadata=settings_update.model_dump(),
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
            
            deleted, freed_bytes = priority_mode.cleanup_user_versions(cleanup_req.user_id)
            
            # Also enforce depth limit
            priority_mode.enforce_depth_limit(cleanup_req.user_id)
            
            # Update stats
            vcl_service.recalculate_stats()
            
            audit_logger.log_admin_action(
                admin=admin.username,
                action="manual_vcl_cleanup",
                target=f"user_id:{cleanup_req.user_id}",
                metadata={"deleted_versions": deleted, "freed_bytes": freed_bytes},
                db=db
            )
            
            return CleanupResponse(
                success=True,
                message=f"Cleanup completed for user {cleanup_req.user_id}",
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
                    deleted, freed_bytes = priority_mode.cleanup_user_versions(settings.user_id)
                    total_deleted += deleted
                    total_freed += freed_bytes
                    affected += 1
                
                # Enforce depth limit
                priority_mode.enforce_depth_limit(settings.user_id)
            
            # Update stats
            vcl_service.recalculate_stats()
            
            audit_logger.log_admin_action(
                admin=admin.username,
                action="manual_vcl_cleanup_all",
                target="all_users",
                metadata={
                    "deleted_versions": total_deleted,
                    "freed_bytes": total_freed,
                    "affected_users": affected,
                },
                db=db
            )
            
            return CleanupResponse(
                success=True,
                message=f"Cleanup completed for {affected} users",
                deleted_versions=total_deleted,
                freed_bytes=total_freed,
                affected_users=affected,
            )
            
    except Exception as e:
        audit_logger.log_admin_action(
            admin=admin.username,
            action="manual_vcl_cleanup_failed",
            target=f"user_id:{cleanup_req.user_id}" if cleanup_req.user_id else "all_users",
            metadata={"error": str(e)},
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
