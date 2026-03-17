"""VCL (Version Control Light) API Routes — Admin Endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.schemas.vcl import (
    AdminVCLOverview,
    AdminUserQuota,
    AdminStatsResponse,
    CleanupRequest,
    CleanupResponse,
    VCLStorageInfo,
    VCLSettingsResponse,
    VCLSettingsUpdate,
    ReconciliationPreview,
    ReconciliationMismatch,
    ReconciliationRequest,
    ReconciliationResult,
    AffectedUser,
    QuotaTransfer,
)
from app.services.versioning.vcl import VCLService
from app.services.versioning.priority import VCLPriorityMode
from app.services.versioning.reconciliation import VCLReconciliation
from app.services.audit.logger_db import get_audit_logger_db
from app.models.vcl import VCLSettings, VCLStats, FileVersion, VersionBlob
from app.models.user import User
from app.api.routes.vcl import needs_cleanup

router = APIRouter()


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.get("/admin/storage-info", response_model=VCLStorageInfo)
@user_limiter.limit(get_limit("admin_operations"))
async def get_vcl_storage_info(
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> VCLStorageInfo:
    """
    Get VCL storage location and disk usage info (Admin only).

    Returns:
        Storage path, blob count, disk usage
    """
    import shutil
    from pathlib import Path
    from app.core.config import settings

    vcl_base = settings.vcl_storage_path.strip()
    is_custom = bool(vcl_base)
    if vcl_base:
        storage_path = Path(vcl_base)
    else:
        storage_path = Path(settings.nas_storage_path) / ".system" / "versions"

    # Count blobs and total compressed size from DB
    blob_count: int = db.query(func.count(VersionBlob.id)).scalar() or 0
    total_compressed: int = db.query(func.sum(VersionBlob.compressed_size)).scalar() or 0

    # Disk usage for the storage path
    try:
        disk_usage = shutil.disk_usage(str(storage_path))
        disk_total = disk_usage.total
        disk_available = disk_usage.free
        disk_used_percent = ((disk_usage.total - disk_usage.free) / disk_usage.total * 100) if disk_usage.total > 0 else 0.0
    except OSError:
        disk_total = 0
        disk_available = 0
        disk_used_percent = 0.0

    return VCLStorageInfo(
        storage_path=str(storage_path),
        is_custom_path=is_custom,
        blob_count=blob_count,
        total_compressed_bytes=total_compressed,
        disk_total_bytes=disk_total,
        disk_available_bytes=disk_available,
        disk_used_percent=round(disk_used_percent, 1),
    )


@router.get("/admin/overview", response_model=AdminVCLOverview)
@user_limiter.limit(get_limit("admin_operations"))
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
        from app.services.versioning.vcl import VCLService
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
@user_limiter.limit(get_limit("admin_operations"))
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
    existing_settings: dict[int, VCLSettings] = {
        int(s.user_id): s  # type: ignore
        for s in db.query(VCLSettings).filter(
            VCLSettings.user_id.in_([u.id for u in all_users])
        ).all()
    }

    # Create missing settings in batch (avoid locks)
    from app.services.versioning.vcl import VCLService
    vcl_service = VCLService(db)

    for user_obj in all_users:
        if user_obj.id not in existing_settings:
            # Create default settings
            new_settings = VCLSettings(
                user_id=user_obj.id,  # type: ignore
                max_size_bytes=10 * 1024 * 1024 * 1024,  # type: ignore  # 10 GB default
                current_usage_bytes=0,  # type: ignore
                depth=5,  # type: ignore
                headroom_percent=10,  # type: ignore
                is_enabled=True,  # type: ignore
                compression_enabled=True,  # type: ignore
                dedupe_enabled=True,  # type: ignore
                debounce_window_seconds=30,  # type: ignore
                max_batch_window_seconds=300,  # type: ignore
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

        # Cast Columns for arithmetic and conditionals
        max_size: int = int(settings.max_size_bytes)  # type: ignore
        current_usage: int = int(settings.current_usage_bytes)  # type: ignore
        usage_percent = (current_usage / max_size * 100) if max_size > 0 else 0
        cleanup_needed = needs_cleanup(settings)

        result.append(AdminUserQuota(
            user_id=user_obj.id,
            username=user_obj.username,
            max_size_bytes=max_size,
            current_usage_bytes=current_usage,
            usage_percent=usage_percent,
            total_versions=total_versions,
            is_enabled=bool(settings.is_enabled),  # type: ignore
            cleanup_needed=cleanup_needed,
            vcl_mode=str(settings.vcl_mode) if settings.vcl_mode else "automatic",  # type: ignore
        ))

    return result


@router.put("/admin/settings/{user_id}", response_model=VCLSettingsResponse)
@user_limiter.limit(get_limit("admin_operations"))
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
    from app.services.versioning.vcl import VCLService

    vcl_service = VCLService(db)
    settings = vcl_service.get_or_create_user_settings(user_id)

    # Build update dict to avoid Column assignment issues
    from sqlalchemy import update as sql_update

    update_values: dict = {}
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
    if settings_update.vcl_mode is not None:
        update_values['vcl_mode'] = settings_update.vcl_mode

    if update_values:
        db.execute(
            sql_update(VCLSettings).
            where(VCLSettings.user_id == user_id).
            values(**update_values)
        )
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
        vcl_mode=str(settings.vcl_mode) if settings.vcl_mode else "automatic",  # type: ignore
        created_at=settings.created_at,  # type: ignore
        updated_at=settings.updated_at,  # type: ignore
    )


@router.post("/admin/cleanup", response_model=CleanupResponse)
@user_limiter.limit(get_limit("admin_operations"))
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
                freed_bytes = sum(int(v.file_size) for v in versions)  # type: ignore
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
                    uid = int(settings.user_id)  # type: ignore
                    if cleanup_req.dry_run:
                        # Dry run estimation
                        versions = db.query(FileVersion).filter(
                            FileVersion.user_id == uid
                        ).order_by(FileVersion.created_at.desc()).offset(10).all()
                        total_deleted += len(versions)
                        total_freed += sum(int(v.file_size) for v in versions)  # type: ignore
                        affected += 1
                    else:
                        deleted, freed_bytes = priority_mode.cleanup_user_versions(uid)
                        total_deleted += deleted
                        total_freed += freed_bytes
                        affected += 1

                        # Enforce depth limit
                        priority_mode.enforce_depth_limit(uid)

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
@user_limiter.limit(get_limit("admin_operations"))
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
        from app.services.versioning.vcl import VCLService
        vcl_service = VCLService(db)
        vcl_service.recalculate_stats()
        stats = db.query(VCLStats).first()

    if not stats:
        return AdminStatsResponse(
            total_versions=0, total_size_bytes=0, total_compressed_bytes=0,
            total_blobs=0, unique_blobs=0, deduplication_savings_bytes=0,
            compression_savings_bytes=0, deduplication_ratio_percent=0,
            compression_ratio_percent=0, total_savings_ratio_percent=0,
            priority_count=0, cached_versions_count=0,
            last_cleanup_at=None, last_priority_mode_at=None,
            last_deduplication_scan=None, updated_at=None,
        )

    # Cast Columns for arithmetic
    total_size: int = int(stats.total_size_bytes)  # type: ignore
    dedup_savings: int = int(stats.deduplication_savings_bytes)  # type: ignore
    comp_savings: int = int(stats.compression_savings_bytes)  # type: ignore

    # Calculate ratios
    dedup_ratio = (dedup_savings / total_size * 100) if total_size > 0 else 0
    compression_ratio = (comp_savings / total_size * 100) if total_size > 0 else 0
    total_savings_ratio = ((dedup_savings + comp_savings) / total_size * 100) if total_size > 0 else 0

    return AdminStatsResponse(
        total_versions=int(stats.total_versions),  # type: ignore
        total_size_bytes=total_size,
        total_compressed_bytes=int(stats.total_compressed_bytes),  # type: ignore
        total_blobs=int(stats.total_blobs),  # type: ignore
        unique_blobs=int(stats.unique_blobs),  # type: ignore
        deduplication_savings_bytes=dedup_savings,
        compression_savings_bytes=comp_savings,
        deduplication_ratio_percent=dedup_ratio,
        compression_ratio_percent=compression_ratio,
        total_savings_ratio_percent=total_savings_ratio,
        priority_count=int(stats.priority_count),  # type: ignore
        cached_versions_count=int(stats.cached_versions_count),  # type: ignore
        last_cleanup_at=stats.last_cleanup_at,  # type: ignore
        last_priority_mode_at=stats.last_priority_mode_at,  # type: ignore
        last_deduplication_scan=stats.last_deduplication_scan,  # type: ignore
        updated_at=stats.updated_at,  # type: ignore
    )


# ============================================================================
# ADMIN RECONCILIATION ENDPOINTS
# ============================================================================

@router.post("/admin/reconcile/preview", response_model=ReconciliationPreview)
@user_limiter.limit(get_limit("admin_operations"))
async def reconcile_preview(
    request: Request,
    response: Response,
    reconcile_req: ReconciliationRequest,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> ReconciliationPreview:
    """Scan for ownership mismatches between FileVersion and FileMetadata (Admin only)."""
    reconciler = VCLReconciliation(db)
    mismatches_raw = reconciler.scan_mismatches(reconcile_req.user_id)

    # Build username cache
    user_ids = set()
    for m in mismatches_raw:
        user_ids.add(m["version_user_id"])
        user_ids.add(m["file_owner_id"])
    username_map = {
        u.id: u.username
        for u in db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    mismatches = [
        ReconciliationMismatch(
            file_id=m["file_id"],
            file_path=m["file_path"],
            version_id=m["version_id"],
            version_number=m["version_number"],
            current_version_user_id=m["version_user_id"],
            current_version_username=username_map.get(m["version_user_id"], "unknown"),
            current_file_owner_id=m["file_owner_id"],
            current_file_owner_username=username_map.get(m["file_owner_id"], "unknown"),
            compressed_size=m["compressed_size"],
        )
        for m in mismatches_raw
    ]

    # Calculate affected users quota impact
    quota_deltas: dict[int, int] = {}
    for m in mismatches_raw:
        if m["storage_type"] == "stored":
            old_uid = m["version_user_id"]
            new_uid = m["file_owner_id"]
            quota_deltas[old_uid] = quota_deltas.get(old_uid, 0) - m["compressed_size"]
            quota_deltas[new_uid] = quota_deltas.get(new_uid, 0) + m["compressed_size"]

    affected_users = []
    if quota_deltas:
        settings_map: dict[int, VCLSettings] = {
            int(s.user_id): s  # type: ignore
            for s in db.query(VCLSettings).filter(
                VCLSettings.user_id.in_(quota_deltas.keys())
            ).all()
        }
        for uid, delta in quota_deltas.items():
            s = settings_map.get(uid)
            current = int(s.current_usage_bytes) if s else 0  # type: ignore[arg-type]
            max_size = int(s.max_size_bytes) if s else 10 * 1024 * 1024 * 1024  # type: ignore[arg-type]
            affected_users.append(AffectedUser(
                user_id=uid,
                username=username_map.get(uid, "unknown"),
                quota_delta=delta,
                current_usage=current,
                max_size=max_size,
                would_exceed_quota=(current + delta) > max_size if delta > 0 else False,
            ))

    return ReconciliationPreview(
        total_mismatches=len(mismatches),
        mismatches=mismatches,
        affected_users=affected_users,
    )


@router.post("/admin/reconcile/apply", response_model=ReconciliationResult)
@user_limiter.limit(get_limit("admin_operations"))
async def reconcile_apply(
    request: Request,
    response: Response,
    reconcile_req: ReconciliationRequest,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> ReconciliationResult:
    """Apply ownership reconciliation (Admin only)."""
    reconciler = VCLReconciliation(db)
    result = reconciler.reconcile(
        dry_run=False,
        user_id=reconcile_req.user_id,
        force_over_quota=reconcile_req.force_over_quota,
    )
    db.commit()

    # Audit log
    audit_logger = get_audit_logger_db()
    audit_logger.log_system_config_change(
        action="vcl_reconcile_apply",
        user=admin.username,
        config_key="vcl_reconciliation",
        new_value={
            "reconciled_versions": result["reconciled_versions"],
            "skipped": result["skipped_due_to_quota"],
            "force_over_quota": reconcile_req.force_over_quota,
        },
        db=db,
    )

    return ReconciliationResult(
        success=result["success"],
        reconciled_versions=result["reconciled_versions"],
        skipped_due_to_quota=result["skipped_due_to_quota"],
        quota_transfers=[QuotaTransfer(**qt) for qt in result["quota_transfers"]],
        message=result["message"],
    )
