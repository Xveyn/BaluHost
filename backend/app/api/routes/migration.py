"""Data migration API routes (VCL HDD -> SSD)."""
import logging
import os
from pathlib import PurePosixPath

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.migration_job import MigrationJob
from app.schemas.migration import (
    DirectoryEntry,
    MigrationJobResponse,
    VCLCleanupRequest,
    VCLMigrationStartRequest,
    VCLVerifyRequest,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.cache.migration import MigrationService

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_to_response(job: MigrationJob) -> MigrationJobResponse:
    """Convert ORM model to response schema."""
    total = int(job.total_files) if job.total_files else 0
    processed = int(job.processed_files) if job.processed_files else 0
    progress = (processed / total * 100) if total > 0 else 0.0

    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()

    return MigrationJobResponse(
        id=int(job.id),
        job_type=str(job.job_type),
        status=str(job.status),
        source_path=str(job.source_path),
        dest_path=str(job.dest_path),
        total_files=total,
        processed_files=processed,
        skipped_files=int(job.skipped_files) if job.skipped_files else 0,
        failed_files=int(job.failed_files) if job.failed_files else 0,
        total_bytes=int(job.total_bytes) if job.total_bytes else 0,
        processed_bytes=int(job.processed_bytes) if job.processed_bytes else 0,
        current_file=job.current_file,
        progress_percent=round(progress, 1),
        error_message=job.error_message,
        dry_run=bool(job.dry_run),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=round(duration, 1) if duration is not None else None,
    )


# ─── Directory Browse ────────────────────────────────────────────


@router.get("/migration/browse", response_model=list[DirectoryEntry])
@user_limiter.limit(get_limit("admin_operations"))
async def browse_directories(
    request: Request,
    response: Response,
    path: str = Query(default="/mnt", description="Absolute path to browse"),
    admin: UserPublic = Depends(deps.get_current_admin),
) -> list[DirectoryEntry]:
    """List directories at the given absolute path (Admin only)."""
    # Reject path traversal
    if ".." in path:
        raise HTTPException(status_code=400, detail="Path must not contain '..'")

    # Normalize and validate absolute path
    normalized = str(PurePosixPath(path))
    if not normalized.startswith("/"):
        raise HTTPException(status_code=400, detail="Path must be absolute")

    if not os.path.isdir(normalized):
        raise HTTPException(status_code=404, detail="Directory not found")

    entries: list[DirectoryEntry] = []
    try:
        for entry in sorted(os.scandir(normalized), key=lambda e: e.name):
            if not entry.is_dir(follow_symlinks=False):
                continue
            full_path = os.path.join(normalized, entry.name)
            entries.append(DirectoryEntry(
                name=entry.name,
                path=full_path,
                is_mountpoint=os.path.ismount(full_path),
            ))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return entries


# ─── VCL Migration ──────────────────────────────────────────────


@router.post("/migration/vcl/start", response_model=MigrationJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_vcl_migration(
    request: Request,
    response: Response,
    body: VCLMigrationStartRequest,
    background_tasks: BackgroundTasks,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> MigrationJobResponse:
    """Start VCL blob migration from HDD to SSD (Admin only)."""
    service = MigrationService(db)
    try:
        job = service.start_vcl_migration(
            source=body.source_path,
            dest=body.dest_path,
            dry_run=body.dry_run,
            user_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit = get_audit_logger_db()
    audit.log_system_event(
        action="vcl_migration_start",
        user=admin.username,
        details={
            "job_id": job.id,
            "source": body.source_path,
            "dest": body.dest_path,
            "dry_run": body.dry_run,
        },
        db=db,
    )

    background_tasks.add_task(service.run_vcl_migration, job.id)
    return _job_to_response(job)


@router.post("/migration/vcl/verify", response_model=MigrationJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_vcl_verify(
    request: Request,
    response: Response,
    body: VCLVerifyRequest,
    background_tasks: BackgroundTasks,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> MigrationJobResponse:
    """Start VCL migration integrity verification (Admin only)."""
    service = MigrationService(db)
    try:
        job = service.start_vcl_verify(dest=body.dest_path, user_id=admin.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit = get_audit_logger_db()
    audit.log_system_event(
        action="vcl_verify_start",
        user=admin.username,
        details={"job_id": job.id, "dest": body.dest_path},
        db=db,
    )

    background_tasks.add_task(service.run_vcl_verify, job.id)
    return _job_to_response(job)


@router.post("/migration/vcl/cleanup", response_model=MigrationJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_vcl_cleanup(
    request: Request,
    response: Response,
    body: VCLCleanupRequest,
    background_tasks: BackgroundTasks,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> MigrationJobResponse:
    """Start cleanup of source VCL blobs after migration (Admin only)."""
    service = MigrationService(db)
    try:
        job = service.start_vcl_cleanup(
            source=body.source_path,
            dry_run=body.dry_run,
            user_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit = get_audit_logger_db()
    audit.log_system_event(
        action="vcl_cleanup_start",
        user=admin.username,
        details={
            "job_id": job.id,
            "source": body.source_path,
            "dry_run": body.dry_run,
        },
        db=db,
    )

    background_tasks.add_task(service.run_vcl_cleanup, job.id)
    return _job_to_response(job)


# ─── Job Management ─────────────────────────────────────────────


@router.get("/migration/jobs", response_model=list[MigrationJobResponse])
@user_limiter.limit(get_limit("admin_operations"))
async def list_migration_jobs(
    request: Request,
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> list[MigrationJobResponse]:
    """List all migration jobs, newest first (Admin only)."""
    service = MigrationService(db)
    jobs = service.list_jobs(limit=limit)
    return [_job_to_response(j) for j in jobs]


@router.get("/migration/jobs/{job_id}", response_model=MigrationJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_migration_job(
    job_id: int,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> MigrationJobResponse:
    """Get status of a specific migration job (Admin only)."""
    service = MigrationService(db)
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found")
    return _job_to_response(job)


@router.post("/migration/jobs/{job_id}/cancel")
@user_limiter.limit(get_limit("admin_operations"))
async def cancel_migration_job(
    job_id: int,
    request: Request,
    response: Response,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel a running or pending migration job (Admin only)."""
    service = MigrationService(db)
    success = service.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Job cannot be cancelled (not running or pending)",
        )

    audit = get_audit_logger_db()
    audit.log_system_event(
        action="migration_job_cancel",
        user=admin.username,
        details={"job_id": job_id},
        db=db,
    )

    return {"cancelled": True}
