from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import asyncio
import threading
import os
import logging
import signal
from datetime import datetime, timedelta, timezone

from app.api import deps
from app.core.network_utils import is_private_or_local_ip
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.models.user import User as UserModel
from app.schemas.system import (
    AuditLoggingStatus,
    AuditLoggingToggle,
    ChannelStatusResponse,
    ProcessListResponse,
    QuotaStatus,
    SmartStatusResponse,
    StorageBreakdownResponse,
    StorageInfo,
    SystemInfo,
    SystemRestartAllRequest,
    SystemRestartAllResponse,
    TelemetryHistoryResponse,
    UnitRestartResult,
)
from app.schemas.user import UserPublic
from app.services import step_up, system_restart
from app.services.hardware import smart as smart_service
from app.services.audit.logger_db import get_audit_logger_db
from app.services import system as system_service
from app.services import telemetry as telemetry_service

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


@router.get("/channel-status", response_model=ChannelStatusResponse)
async def get_channel_status(
    request: Request,
    _: UserPublic = Depends(deps.get_current_user),
) -> ChannelStatusResponse:
    """Returns whether the current connection is via the local channel.

    Used by the web UI to disable destructive-action buttons and show a
    hint that the Companion app is required. Auth: any authenticated user.
    """
    return ChannelStatusResponse(channel=getattr(request.state, "channel", "remote"))


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
    # DB audit, not the old file logger: the admin audit view reads
    # audit_logs, and the file entry never showed up there (#727).
    get_audit_logger_db().log_system_event(
        action="shutdown_initiated", user=user.username, details={"method": "api"}, success=True,
    )
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

    # DB audit, not the old file logger (#727) - see shutdown_system.
    get_audit_logger_db().log_system_event(
        action="restart_initiated", user=user.username, details={"method": "api"}, success=True,
    )
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


def _is_api_key_request(request: Request) -> bool:
    """deps.get_current_user setzt diesen Marker für den API-Key-Pfad."""
    return getattr(request.state, "auth_method", None) == "api_key"


def _totp_enabled_for(user_record) -> bool:
    """Eigene Funktion, damit Tests die 2FA-Variante ohne Secret erreichen."""
    return bool(getattr(user_record, "totp_enabled", False))


def _log_backend_restart_outcome(result: system_restart.UnitResult) -> None:
    """Den Ausgang des Selbst-Neustarts protokollieren — eigener Helfer, damit
    er ohne Timer pruefbar ist.

    Ein negativer Rueckgabecode heisst: unser eigener systemctl-Aufruf wurde
    von einem Signal beendet. Beim Stoppen der alten Unit raeumt systemd die
    cgroup ab, in der dieser Aufruf steckt — das IST der gelungene
    Selbst-Neustart. Frueher stand dafuer eine ERROR-Zeile im Journal, die das
    Gegenteil behauptete, und zwar bei jedem erfolgreichen Sammelneustart
    (#704).
    """
    logger = logging.getLogger(__name__)
    if result.success:
        return
    if result.returncode is not None and result.returncode < 0:
        logger.info(
            "restart of %s: our own systemctl child was terminated by the unit "
            "teardown (%s) — that is the expected outcome of a self-restart",
            result.name,
            result.message,
        )
        return
    logger.error(
        "restart of %s failed: %s — the service is still running the old process",
        result.name,
        result.message,
    )


def _schedule_backend_restart(eta: float = 1.0) -> None:
    """Das Backend zuletzt neu starten, nachdem die Antwort draußen ist.

    Bewusst als eigener Helfer und nicht im Route-Körper: Tests müssen ihn
    ersetzen können, sonst beendet der Timer den Testlauf.

    **Kein SIGINT-Fallback.** Das bestehende `/api/system/restart` fällt bei
    einem Fehlschlag auf `os.kill(os.getpid(), SIGINT)` zurück; bei
    `uvicorn --workers 4` trifft das einen Kindprozess, den uvicorn binnen
    einer halben Sekunde neu startet, während drei Worker unverändert
    weiterlaufen — und der Aufrufer hat "Neustart geplant" gelesen. Issue #695.
    Hier wird ein Fehlschlag protokolliert und sonst nichts getan.
    `/api/system/restart` bleibt unangetastet, weil die Companion-App und
    `localApi.ts` daran hängen.
    """
    from app.core.config import settings

    def _perform() -> None:
        logger = logging.getLogger(__name__)
        if settings.is_dev_mode:
            # Dort läuft ein einzelner Prozess — dort stimmt SIGINT.
            logger.info("Dev mode: sending SIGINT to trigger restart")
            os.kill(os.getpid(), signal.SIGINT)
            return
        _log_backend_restart_outcome(
            system_restart.restart_unit(system_restart.BACKEND_UNIT)
        )

    timer = threading.Timer(float(eta), _perform)
    timer.daemon = True
    timer.start()


@router.post("/restart-all", response_model=SystemRestartAllResponse)
@user_limiter.limit(get_limit("system_restart"))
async def restart_all_services(
    payload: SystemRestartAllRequest,
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(deps.get_db),
) -> SystemRestartAllResponse:
    """Alle BaluHost-Units neu starten (Admin + lokales Netz + Step-up).

    Die vier Nebendienste laufen synchron, damit ihr Ergebnis in die Antwort
    passt. `baluhost-backend` kommt zuletzt und per Timer — die Antwort muss
    raus sein, bevor der Prozess stirbt.
    """
    # settings lokal, wie in den übrigen Routen dieser Datei;
    # get_audit_logger_db steht bereits oben im Modul.
    from app.core.config import settings

    audit = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    if _is_api_key_request(request):
        audit.log_security_event(
            action="restart_all_api_key_denied",
            user=user.username,
            details={"ip_address": ip_address},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "api_key_not_allowed",
                "message": (
                    "Dieser Vorgang verlangt eine erneute Anmeldung und ist "
                    "mit einem API-Schlüssel nicht möglich."
                ),
            },
        )

    # LAN-Gate (echte Client-IP über --proxy-headers), Muster wie
    # /api/auth/recovery-reset. Grund: :8000 lauscht auf 0.0.0.0 und es läuft
    # kein Paketfilter (#698) — ohne dieses Gate wäre der Endpunkt aus LAN und
    # VPN an nginx und dessen Rate-Limits vorbei erreichbar.
    if not is_private_or_local_ip(ip_address):
        audit.log_security_event(
            action="restart_all_denied",
            user=user.username,
            details={"ip_address": ip_address, "reason": "non_local"},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_network_required",
                "message": (
                    "Der Sammelneustart ist nur aus dem lokalen Netz möglich."
                ),
            },
        )

    user_record = db.query(UserModel).filter(UserModel.id == user.id).first()
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    totp_required = _totp_enabled_for(user_record)
    if not step_up.verify_step_up(
        db, user_record, payload.current_password, payload.code
    ):
        audit.log_security_event(
            action="restart_all_step_up_failed",
            user=user.username,
            details={"ip_address": ip_address},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "step_up_failed",
                # Sagt dem Client, welches Feld die Route erwartet. Zuverlässiger
                # als ein vorher abgefragter 2FA-Status, der bei abgelaufenem
                # Token leer zurückkommt.
                "totp_required": totp_required,
                "message": (
                    "Erneute Anmeldung fehlgeschlagen. Passwort bzw. "
                    "2FA-Code prüfen."
                ),
            },
        )

    if settings.is_dev_mode:
        # Kein systemctl: die übrigen Units gibt es im Dev-Mode nicht.
        results: list[system_restart.UnitResult] = []
    else:
        results = await asyncio.to_thread(system_restart.restart_support_units)

    audit.log_system_event(
        action="restart_all_initiated",
        user=user.username,
        details={
            "units": [r.name for r in results],
            "failed": [r.name for r in results if not r.success],
            "dev_mode": settings.is_dev_mode,
            "ip_address": ip_address,
        },
        success=all(r.success for r in results),
        db=db,
    )
    logging.getLogger(__name__).info(
        "Restart-all requested via API by user %s", user.username
    )

    _schedule_backend_restart()

    return SystemRestartAllResponse(
        units=[
            UnitRestartResult(name=r.name, success=r.success, message=r.message)
            for r in results
        ],
        backend_restart_scheduled=True,
        eta_seconds=1,
        initiated_by=user.username,
    )


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

# Include status-strip sub-router (serves /api/system/statusbar/...)
from app.api.routes.status_bar import router as status_bar_router
router.include_router(status_bar_router)
