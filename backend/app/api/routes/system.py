from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import threading
import os
import logging
import signal
from datetime import datetime, timedelta, timezone

from app.api import deps
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.schemas.system import (
    AuditLoggingStatus,
    AuditLoggingToggle,
    ProcessListResponse,
    QuotaStatus,
    SmartStatusResponse,
    StorageBreakdownResponse,
    StorageInfo,
    SystemInfo,
    TelemetryHistoryResponse,
)
from app.schemas.user import UserPublic
from app.services.hardware import smart as smart_service
from app.services.audit.logger_db import get_audit_logger_db
from app.services import system as system_service
from app.services import telemetry as telemetry_service
from app.services.audit.logger import get_audit_logger

router = APIRouter()


@router.get("/mode")
@limiter.limit(get_limit("system_monitor"))
async def get_system_mode(request: Request, response: Response) -> dict:
    """Get system mode (dev/prod). Public endpoint for login page.

    In dev mode, includes the seeded admin credentials so the Login page
    can display an accurate default-credentials hint. In prod mode the
    credentials field is omitted entirely.
    """
    from app.core.config import settings
    payload: dict = {"dev_mode": settings.is_dev_mode}
    if settings.is_dev_mode:
        payload["dev_credentials"] = {
            "username": settings.admin_username,
            "password": settings.admin_password,
        }
    return payload


@router.get("/info", response_model=SystemInfo)
@user_limiter.limit(get_limit("system_monitor"))
def get_system_info(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> SystemInfo:
    return system_service.get_system_info()


@router.get("/info/local", response_model=SystemInfo)
@limiter.limit(get_limit("system_monitor"))
def get_system_info_local(request: Request, response: Response) -> SystemInfo:
    """Local-only unauthenticated access for trusted localhost clients.

    This endpoint is intended for desktop integrations running on the same
    host (e.g. the Baludesk C++ backend). It rejects requests that do not
    originate from localhost to avoid exposing system telemetry over the
    network without authentication.
    """
    client_host = request.client.host if request.client else None
    allowed = {"127.0.0.1", "::1", "localhost"}
    if client_host not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
    return system_service.get_system_info()


@router.get("/storage", response_model=StorageInfo)
@user_limiter.limit(get_limit("system_monitor"))
def get_storage_info(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> StorageInfo:
    return system_service.get_storage_info()


@router.get("/storage/aggregated", response_model=StorageInfo)
@user_limiter.limit(get_limit("system_monitor"))
def get_aggregated_storage_info(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> StorageInfo:
    """Gibt aggregierte Speicherinformationen über alle Festplatten zurück.

    Berücksichtigt SMART-Daten aller Festplatten und RAID-Arrays.
    Bei RAID wird die effektive Kapazität berechnet.
    """
    return system_service.get_aggregated_storage_info()


@router.get("/storage/breakdown", response_model=StorageBreakdownResponse)
@user_limiter.limit(get_limit("system_monitor"))
def get_storage_breakdown(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> StorageBreakdownResponse:
    """Per-array/device storage breakdown with usage data."""
    return system_service.get_storage_breakdown()


@router.get("/quota", response_model=QuotaStatus)
@user_limiter.limit(get_limit("system_monitor"))
def get_quota(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> QuotaStatus:
    return system_service.get_quota_status()


@router.get("/processes", response_model=ProcessListResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_process_list(
    request: Request,
    response: Response,
    limit: int = 20,
    _: UserPublic = Depends(deps.get_current_user),
) -> ProcessListResponse:
    return system_service.get_process_list(limit=limit)


def _telemetry_history_from_db(db: Session) -> TelemetryHistoryResponse:
    """Build a TelemetryHistoryResponse from the monitoring DB tables.

    Used as fallback on secondary workers whose in-memory telemetry buffer is
    empty.  Converts the newer monitoring schema samples into the legacy
    telemetry format consumed by the Dashboard.
    """
    from app.models.monitoring import CpuSample, MemorySample, NetworkSample
    from app.schemas.system import CpuTelemetrySample, MemoryTelemetrySample, NetworkTelemetrySample
    import time
    from typing import Any

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)

    cpu_rows: list[Any] = (
        db.query(CpuSample)
        .filter(CpuSample.timestamp >= cutoff)
        .order_by(CpuSample.timestamp.asc())
        .limit(60)
        .all()
    )
    mem_rows: list[Any] = (
        db.query(MemorySample)
        .filter(MemorySample.timestamp >= cutoff)
        .order_by(MemorySample.timestamp.asc())
        .limit(60)
        .all()
    )
    net_rows: list[Any] = (
        db.query(NetworkSample)
        .filter(NetworkSample.timestamp >= cutoff)
        .order_by(NetworkSample.timestamp.asc())
        .limit(60)
        .all()
    )

    cpu_samples = [
        CpuTelemetrySample(
            timestamp=int(r.timestamp.timestamp() * 1000) if isinstance(r.timestamp, datetime) else int(time.time() * 1000),
            usage=round(r.usage_percent, 2),
            frequency_mhz=r.frequency_mhz,
            temperature_celsius=r.temperature_celsius,
        )
        for r in cpu_rows
    ]
    memory_samples = [
        MemoryTelemetrySample(
            timestamp=int(r.timestamp.timestamp() * 1000) if isinstance(r.timestamp, datetime) else int(time.time() * 1000),
            used=r.used_bytes,
            total=r.total_bytes,
            percent=round(r.percent, 2),
        )
        for r in mem_rows
    ]
    network_samples = [
        NetworkTelemetrySample(
            timestamp=int(r.timestamp.timestamp() * 1000) if isinstance(r.timestamp, datetime) else int(time.time() * 1000),
            downloadMbps=round(r.download_mbps, 2),
            uploadMbps=round(r.upload_mbps, 2),
        )
        for r in net_rows
    ]

    return TelemetryHistoryResponse(
        cpu=cpu_samples,
        memory=memory_samples,
        network=network_samples,
    )


@router.get("/telemetry/history", response_model=TelemetryHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_telemetry_history(
    request: Request,
    response: Response,
    _: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
) -> TelemetryHistoryResponse:
    history = telemetry_service.get_history()

    # On secondary workers the in-memory buffer is empty.  Fall back to the
    # monitoring DB tables so the dashboard still shows recent data.
    if not history.cpu and not history.memory and not history.network:
        history = _telemetry_history_from_db(db)

    return history


@router.post("/shutdown")
@user_limiter.limit(get_limit("admin_operations"))
async def shutdown_system(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
) -> dict:
    """Schedule a graceful application shutdown (admin only).

    This endpoint returns immediately and schedules a short-timer that
    will exit the process, allowing the response to be delivered to the
    caller. An audit log entry is written.
    """
    audit = get_audit_logger()
    audit.log_system_event(action="shutdown_initiated", user=user.username, details={"method": "api"}, success=True)
    logging.getLogger(__name__).info("Shutdown requested via API by user %s", user.username)

    def _perform_exit() -> None:
        logging.getLogger(__name__).info("Performing graceful shutdown (sending SIGINT to process)")
        try:
            current_pid = os.getpid()
            parent_pid = os.getppid()

            # Try to send SIGTERM to parent process (start_dev.py) first
            # This ensures both backend and frontend are shut down
            try:
                import psutil
                parent = psutil.Process(parent_pid)
                parent_name = parent.name().lower()

                # Check if parent is Python (start_dev.py)
                if 'python' in parent_name:
                    logging.getLogger(__name__).info(f"Sending SIGTERM to parent process {parent_pid} ({parent_name})")
                    os.kill(parent_pid, signal.SIGTERM)
                    return
            except Exception as e:
                logging.getLogger(__name__).debug(f"Could not terminate parent: {e}")

            # Fallback: terminate current process
            os.kill(current_pid, signal.SIGINT)
        except Exception as e:
            # Fallback to hard exit if signal fails
            logging.getLogger(__name__).warning(f"Signal failed: {e}, falling back to os._exit")
            os._exit(0)

    # Give 1 second for the HTTP response to be delivered and for proxies
    # to flush. Then trigger shutdown.
    eta = 1
    timer = threading.Timer(float(eta), _perform_exit)
    timer.daemon = True
    timer.start()

    return {"message": "Shutdown scheduled", "initiated_by": user.username, "eta_seconds": eta}


@router.post("/restart")
@user_limiter.limit(get_limit("admin_operations"))
async def restart_system(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
) -> dict:
    """Schedule a graceful application restart (admin only).

    In production this restarts the systemd service. In dev mode it sends
    SIGINT so the dev launcher can detect the exit and the client can
    reconnect.
    """
    from app.core.config import settings

    audit = get_audit_logger()
    audit.log_system_event(action="restart_initiated", user=user.username, details={"method": "api"}, success=True)
    logging.getLogger(__name__).info("Restart requested via API by user %s", user.username)

    def _perform_restart() -> None:
        logger = logging.getLogger(__name__)
        if not settings.is_dev_mode:
            logger.info("Performing production restart via systemctl")
            try:
                import subprocess
                subprocess.run(
                    ["sudo", "systemctl", "restart", "baluhost-backend"],
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"systemctl restart failed: {e}, falling back to SIGINT")
                os.kill(os.getpid(), signal.SIGINT)
        else:
            logger.info("Dev mode: sending SIGINT to trigger restart")
            os.kill(os.getpid(), signal.SIGINT)

    eta = 1
    timer = threading.Timer(float(eta), _perform_restart)
    timer.daemon = True
    timer.start()

    return {"message": "Restart scheduled", "initiated_by": user.username, "eta_seconds": eta}


@router.get("/smart/status", response_model=SmartStatusResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_smart_status(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> SmartStatusResponse:
    return smart_service.get_smart_status()


@router.get("/smart/mode")
@user_limiter.limit(get_limit("system_monitor"))
async def get_smart_mode(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> dict[str, str]:
    """Get current SMART data mode in Dev-Mode (mock or real)."""
    from app.core.config import settings
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMART mode toggle is only available in dev mode"
        )
    mode = smart_service.get_dev_mode_state()
    return {"mode": mode}


@router.post("/smart/toggle-mode")
@user_limiter.limit(get_limit("system_monitor"))
async def toggle_smart_mode(request: Request, response: Response, _: UserPublic = Depends(deps.get_current_user)) -> dict[str, str]:
    """Toggle between mock and real SMART data in Dev-Mode."""
    from app.core.config import settings
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMART mode toggle is only available in dev mode"
        )
    new_mode = smart_service.toggle_dev_mode()
    return {"mode": new_mode, "message": f"SMART mode switched to {new_mode}"}


@router.get("/audit-logging", response_model=AuditLoggingStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def get_audit_logging_status(
    request: Request,
    response: Response,
    _: UserPublic = Depends(deps.get_current_admin),
) -> AuditLoggingStatus:
    """Get audit logging status (admin only)."""
    from app.core.config import settings
    audit_logger = get_audit_logger_db()

    return AuditLoggingStatus(
        enabled=audit_logger.is_enabled(),
        can_toggle=settings.is_dev_mode,
        dev_mode=settings.is_dev_mode
    )


@router.post("/audit-logging", response_model=AuditLoggingStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_audit_logging(
    request: Request,
    response: Response,
    payload: AuditLoggingToggle,
    current_admin: UserPublic = Depends(deps.get_current_admin),
) -> AuditLoggingStatus:
    """Toggle audit logging (admin only, dev mode only)."""
    from app.core.config import settings
    audit_logger = get_audit_logger_db()

    # Only allow toggling in dev mode
    if not settings.is_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit logging can only be toggled in development mode"
        )

    # Toggle the audit logger
    if payload.enabled:
        audit_logger.enable()
        audit_logger.log_system_config_change(
            action="audit_logging_enabled",
            user=current_admin.username,
            config_key="audit_logging",
            old_value=False,
            new_value=True,
            success=True
        )
    else:
        audit_logger.log_system_config_change(
            action="audit_logging_disabled",
            user=current_admin.username,
            config_key="audit_logging",
            old_value=True,
            new_value=False,
            success=True
        )
        audit_logger.disable()

    return AuditLoggingStatus(
        enabled=audit_logger.is_enabled(),
        can_toggle=settings.is_dev_mode,
        dev_mode=settings.is_dev_mode
    )


# Include RAID sub-router
from app.api.routes.system_raid import router as raid_router
router.include_router(raid_router)
