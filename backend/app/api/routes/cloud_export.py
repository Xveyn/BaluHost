"""Cloud export API endpoints."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.cloud_export import (
    CheckScopeRequest,
    CheckScopeResponse,
    CloudExportJobResponse,
    CloudExportRequest,
    CloudExportStatistics,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import AuditLoggerDB
from app.services.cloud.export_service import CloudExportService
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_export(
    request: Request,
    response: Response,
    body: CloudExportRequest,
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a cloud export job (upload + share link)."""
    service = CloudExportService(db)
    try:
        job = service.start_export(
            connection_id=body.connection_id,
            user_id=current_user.id,
            source_path=body.source_path,
            cloud_folder=body.cloud_folder,
            link_type=body.link_type,
            expires_at=body.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Execute in background
    background_tasks.add_task(_run_export_async, job.id, db)

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="FILE_OPERATION",
        action="cloud_export_started",
        user=current_user.username,
        resource=body.source_path,
        db=db,
    )

    return CloudExportJobResponse.model_validate(job)


@router.get("/jobs", response_model=list[CloudExportJobResponse])
@user_limiter.limit(get_limit("admin_operations"))
async def list_exports(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all export jobs for the current user."""
    service = CloudExportService(db)
    jobs = service.get_user_exports(current_user.id, limit=limit)
    return [CloudExportJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_export_status(
    request: Request,
    response: Response,
    job_id: int,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a specific export job."""
    service = CloudExportService(db)
    job = service.get_export_status(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return CloudExportJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/revoke")
@user_limiter.limit(get_limit("admin_operations"))
async def revoke_export(
    request: Request,
    response: Response,
    job_id: int,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a cloud export (delete cloud file + invalidate link)."""
    service = CloudExportService(db)
    success = service.revoke_export(job_id, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot revoke this export")

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="FILE_OPERATION",
        action="cloud_export_revoked",
        user=current_user.username,
        resource=f"job:{job_id}",
        db=db,
    )

    return {"success": True, "message": "Export revoked"}


@router.post("/jobs/{job_id}/retry", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def retry_export(
    request: Request,
    response: Response,
    job_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry a failed export job."""
    service = CloudExportService(db)
    job = service.retry_export(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=400, detail="Cannot retry this export (not failed)")

    background_tasks.add_task(_run_export_async, job.id, db)
    return CloudExportJobResponse.model_validate(job)


@router.get("/statistics", response_model=CloudExportStatistics)
@user_limiter.limit(get_limit("admin_operations"))
async def get_statistics(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get cloud export statistics for the Shares page."""
    service = CloudExportService(db)
    return service.get_export_statistics(current_user.id)


@router.post("/check-scope", response_model=CheckScopeResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def check_scope(
    request: Request,
    response: Response,
    body: CheckScopeRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if a cloud connection has export-capable scope."""
    service = CloudService(db)
    try:
        result = service.check_connection_scope(body.connection_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return CheckScopeResponse(**result)


@router.post("/scope-upgrade")
@user_limiter.limit(get_limit("admin_operations"))
async def scope_upgrade(
    request: Request,
    response: Response,
    body: CheckScopeRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get OAuth URL for upgrading a connection to export-capable scope."""
    from app.api.routes.cloud import _build_oauth_redirect_uri

    service = CloudService(db)
    conn = service.get_connection(body.connection_id, current_user.id)
    redirect_uri = _build_oauth_redirect_uri(request)
    try:
        url = service.get_export_oauth_url(
            conn.provider, current_user.id, body.connection_id,
            redirect_uri=redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"oauth_url": url}


# ─── Background task helper ──────────────────────────────────

async def _run_export_async(job_id: int, db: Session) -> None:
    """Execute export job in background."""
    try:
        service = CloudExportService(db)
        await service.execute_export(job_id)
    except Exception as e:
        logger.exception("Background export failed for job %d: %s", job_id, e)
