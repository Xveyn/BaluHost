"""Scheduler API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.core.database import get_db
from app.schemas.user import UserPublic
from app.schemas.scheduler import (
    SchedulerStatusResponse,
    SchedulerListResponse,
    SchedulerHistoryResponse,
    SchedulerConfigUpdate,
    RunNowRequest,
    RunNowResponse,
    SchedulerToggleRequest,
    SchedulerToggleResponse,
    RebootPreviewResponse,
)
from app.services.audit.logger_db import get_audit_logger_db
from app.services.scheduler import get_scheduler_service


router = APIRouter()


@router.get("/", response_model=SchedulerListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_schedulers(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all system schedulers with their status.

    Returns information about all system schedulers:
    - RAID Scrub: Periodic data integrity check
    - SMART Scan: Disk health monitoring
    - Backup: Automated system backups
    - Sync Check: User sync schedule execution
    - Notification Check: Device expiration warnings
    - Upload Cleanup: Expired upload removal
    """
    service = get_scheduler_service(db)
    return service.get_all_schedulers()


@router.get("/system_reboot/preview", response_model=RebootPreviewResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_reboot_preview(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Nächster Neustart-Termin und seine Kollision mit der Kernbetriebszeit.

    `reachable: false` heißt: der Termin liegt in einem Kernbetriebszeit-Fenster,
    das erst NACH Ablauf der Nachholfrist endet — der Neustart läuft so nie.

    Diese Route MUSS vor `GET /{name}` registriert sein, sonst fängt der
    Platzhalter sie ab und `/system_reboot/preview` landet als Scheduler-Name
    `system_reboot` im Detail-Endpunkt.
    """
    return get_scheduler_service(db).get_reboot_preview()


@router.get("/{name}", response_model=SchedulerStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_scheduler(
    request: Request, response: Response,
    name: str,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get detailed status of a specific scheduler (Admin only).

    Returns current status, timing information, and last execution result.
    """
    service = get_scheduler_service(db)
    scheduler = service.get_scheduler(name)

    if not scheduler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler '{name}' not found",
        )

    return scheduler


@router.post("/{name}/run-now", response_model=RunNowResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def run_scheduler_now(
    request: Request, response: Response,
    name: str,
    body: RunNowRequest = RunNowRequest(),
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Trigger a scheduler to run immediately (Admin only).

    Creates a "requested" execution record. The scheduler worker
    process picks it up and executes the job asynchronously.
    Use force=true to run even if the scheduler is already running.
    """
    service = get_scheduler_service(db)
    result = await service.run_scheduler_now(name, current_user.id, body.force)

    if not result.success and result.status == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return result


@router.get("/{name}/history", response_model=SchedulerHistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_scheduler_history(
    request: Request, response: Response,
    name: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        default=None,
        description="Filter by status (running, completed, failed, cancelled)",
    ),
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get execution history for a specific scheduler (Admin only).

    Returns paginated list of past executions with their results.
    """
    service = get_scheduler_service(db)
    return service.get_scheduler_history(
        name=name,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )


@router.get("/history/all", response_model=SchedulerHistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_all_scheduler_history(
    request: Request, response: Response,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        default=None,
        description="Filter by status (running, completed, failed, cancelled)",
    ),
    scheduler_filter: Optional[str] = Query(
        default=None,
        description="Filter by scheduler name",
    ),
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get execution history for all schedulers (Admin only).

    Returns paginated list of all scheduler executions.
    """
    service = get_scheduler_service(db)
    return service.get_scheduler_history(
        name=scheduler_filter,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )


@router.put("/{name}/config", status_code=status.HTTP_200_OK)
@user_limiter.limit(get_limit("admin_operations"))
async def update_scheduler_config(
    request: Request, response: Response,
    name: str,
    config: SchedulerConfigUpdate,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Update scheduler configuration (Admin only).

    Changes to interval may require a scheduler restart to take effect.
    Note: Some schedulers have fixed intervals and cannot be configured.
    """
    if name == "system_reboot" and config.extra_config is not None:
        # Für diesen einen Scheduler ist extra_config kein freies Dict.
        # Pydantic wirft ValidationError -> FastAPI antwortet 422.
        from app.schemas.scheduler import RebootScheduleConfig

        try:
            validated = RebootScheduleConfig(**config.extra_config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        config = config.model_copy(update={"extra_config": validated.model_dump()})

        get_audit_logger_db().log_event(
            event_type="admin",
            user=current_user.username,
            action="update_reboot_schedule",
            resource="system_reboot",
            details=validated.model_dump(),
            success=True,
        )

    service = get_scheduler_service(db)
    success = service.update_scheduler_config(
        name=name,
        interval_seconds=config.interval_seconds,
        is_enabled=config.is_enabled,
        user_id=current_user.id,
        extra_config=config.extra_config,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler '{name}' not found",
        )

    return {"success": True, "message": f"Configuration updated for {name}"}


@router.post("/{name}/toggle", response_model=SchedulerToggleResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_scheduler(
    request: Request, response: Response,
    name: str,
    body: SchedulerToggleRequest,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Enable or disable a scheduler (Admin only).

    When disabled, the scheduler's background job will be stopped.
    When enabled, it will be started with the configured interval.
    """
    service = get_scheduler_service(db)
    result = service.toggle_scheduler(name, body.enabled, current_user.id)

    if name == "system_reboot":
        get_audit_logger_db().log_event(
            event_type="admin",
            user=current_user.username,
            action="toggle_reboot_schedule",
            resource="system_reboot",
            details={"enabled": body.enabled},
            success=True,
        )

    return result
