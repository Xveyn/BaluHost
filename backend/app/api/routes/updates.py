"""Update service API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.core.database import get_db
from app.schemas.user import UserPublic
from app.schemas.update import (
    UpdateCheckResponse,
    UpdateStartRequest,
    UpdateStartResponse,
    UpdateProgressResponse,
    UpdateHistoryResponse,
    RollbackRequest,
    RollbackResponse,
    UpdateConfigResponse,
    UpdateConfigUpdate,
    VersionInfo,
    ReleaseNotesResponse,
)
from app.services.update_service import get_update_service, get_update_backend
from app.services.audit_logger_db import get_audit_logger_db

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("/version", response_model=VersionInfo)
@limiter.limit(get_limit("admin_operations"))
async def get_public_version(
    request: Request, response: Response,
) -> VersionInfo:
    """Get current version (public endpoint, no auth required).

    Returns the current installed version information including
    version string, commit hash, and tag.
    """
    backend = get_update_backend()
    return await backend.get_current_version()


@router.get("/release-notes", response_model=ReleaseNotesResponse)
@limiter.limit(get_limit("admin_operations"))
async def get_release_notes(
    request: Request, response: Response,
) -> ReleaseNotesResponse:
    """Get release notes for the current version (public endpoint, no auth required).

    Returns categorized changes between the previous and current version tag.
    """
    backend = get_update_backend()
    return await backend.get_release_notes()


@router.get("/check", response_model=UpdateCheckResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def check_for_updates(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateCheckResponse:
    """Check if updates are available.

    Returns current version, latest available version, changelog,
    and any blockers that would prevent updating.

    Requires admin privileges.
    """
    service = get_update_service(db)
    audit_logger = get_audit_logger_db()

    result = await service.check_for_updates()

    audit_logger.log_event(
        event_type="UPDATE",
        action="check_updates",
        user=current_user.username,
        resource="system",
        success=True,
        details={
            "current_version": result.current_version.version,
            "update_available": result.update_available,
            "latest_version": result.latest_version.version if result.latest_version else None,
        },
        db=db,
    )

    return result


@router.post("/start", response_model=UpdateStartResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_update(
    request: Request, response: Response,
    body: Optional[UpdateStartRequest] = None,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateStartResponse:
    """Start the update process.

    Initiates an update to the latest available version (or specified version).
    The update runs in the background and progress can be monitored via
    the /progress/{id} endpoint.

    Requires admin privileges.
    """
    service = get_update_service(db)
    audit_logger = get_audit_logger_db()

    req = body or UpdateStartRequest()

    result = await service.start_update(
        user_id=current_user.id,
        target_version=req.target_version,
        skip_backup=req.skip_backup,
        force=req.force,
    )

    audit_logger.log_event(
        event_type="UPDATE",
        action="start_update",
        user=current_user.username,
        resource="system",
        success=result.success,
        details={
            "update_id": result.update_id,
            "target_version": req.target_version,
            "skip_backup": req.skip_backup,
            "force": req.force,
            "message": result.message,
            "blockers": result.blockers,
        },
        db=db,
    )

    if not result.success and result.blockers:
        # Return 409 Conflict if blocked
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": result.message,
                "blockers": result.blockers,
            }
        )

    return result


@router.get("/progress/{update_id}", response_model=UpdateProgressResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_update_progress(
    request: Request, response: Response,
    update_id: int,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateProgressResponse:
    """Get progress of an update.

    Returns current status, progress percentage, and current step
    for the specified update.

    Requires admin privileges.
    """
    service = get_update_service(db)

    result = service.get_update_progress(update_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Update {update_id} not found",
        )

    return result


@router.get("/current", response_model=Optional[UpdateProgressResponse])
@user_limiter.limit(get_limit("admin_operations"))
async def get_current_update(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> Optional[UpdateProgressResponse]:
    """Get the currently running update, if any.

    Returns None if no update is in progress.

    Requires admin privileges.
    """
    from app.models.update_history import UpdateHistory, UpdateStatus

    # Find any running update
    running = (
        db.query(UpdateHistory)
        .filter(UpdateHistory.status.in_([
            UpdateStatus.PENDING.value,
            UpdateStatus.CHECKING.value,
            UpdateStatus.DOWNLOADING.value,
            UpdateStatus.BACKING_UP.value,
            UpdateStatus.INSTALLING.value,
            UpdateStatus.MIGRATING.value,
            UpdateStatus.RESTARTING.value,
            UpdateStatus.HEALTH_CHECK.value,
        ]))
        .first()
    )

    if not running:
        return None

    service = get_update_service(db)
    return service.get_update_progress(running.id)


@router.post("/rollback", response_model=RollbackResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def rollback_update(
    request: Request, response: Response,
    body: Optional[RollbackRequest] = None,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> RollbackResponse:
    """Rollback to a previous version.

    Can specify a target update ID or commit to rollback to.
    If not specified, rolls back to the previous successful update.

    Requires admin privileges.
    """
    service = get_update_service(db)
    audit_logger = get_audit_logger_db()

    req = body or RollbackRequest()

    result = await service.rollback(req, current_user.id)

    audit_logger.log_event(
        event_type="UPDATE",
        action="rollback",
        user=current_user.username,
        resource="system",
        success=result.success,
        details={
            "target_update_id": req.target_update_id,
            "target_commit": req.target_commit,
            "restore_backup": req.restore_backup,
            "rolled_back_to": result.rolled_back_to,
            "message": result.message,
        },
        db=db,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return result


@router.get("/history", response_model=UpdateHistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_update_history(
    request: Request, response: Response,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateHistoryResponse:
    """Get update history.

    Returns paginated list of past updates with status and details.

    Requires admin privileges.
    """
    service = get_update_service(db)
    return service.get_history(page=page, page_size=page_size)


@router.get("/config", response_model=UpdateConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_update_config(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateConfigResponse:
    """Get update service configuration.

    Returns auto-check settings, update channel, backup preferences, etc.

    Requires admin privileges.
    """
    service = get_update_service(db)
    return service.get_config()


@router.put("/config", response_model=UpdateConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_config(
    request: Request, response: Response,
    config: UpdateConfigUpdate,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateConfigResponse:
    """Update service configuration.

    Allows modifying auto-check settings, update channel, etc.

    Requires admin privileges.
    """
    service = get_update_service(db)
    audit_logger = get_audit_logger_db()

    result = service.update_config(config, current_user.id)

    audit_logger.log_event(
        event_type="UPDATE",
        action="update_config",
        user=current_user.username,
        resource="update_config",
        success=True,
        details=config.model_dump(exclude_unset=True),
        db=db,
    )

    return result
