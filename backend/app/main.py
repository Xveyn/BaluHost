from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from pathlib import Path

from app.compat import apply_asyncio_patches

apply_asyncio_patches()

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db, get_db
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.services.users import ensure_admin_user
from app.services import disk_monitor, jobs, seed, telemetry, sync_background, raid as raid_service
from app.services import smart as smart_service
from app.services import power_monitor
from app.services import power_manager
from app.services import fan_control
from app.services.monitoring.orchestrator import start_monitoring, stop_monitoring
from app.services.network_discovery import NetworkDiscoveryService
from app.services.firebase_service import FirebaseService
from app.services.notification_scheduler import NotificationScheduler
from app.services.backup_scheduler import BackupScheduler
from app.middleware.device_tracking import DeviceTrackingMiddleware
from app.middleware.local_only import LocalOnlyMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.error_counter import ErrorCounterMiddleware
from app.services.service_status import (
    set_server_start_time,
    register_service,
    get_service_status_collector,
)
from app.services.monitoring.orchestrator import get_status as orchestrator_get_status

logger = logging.getLogger(__name__)

# Network discovery service instance
_discovery_service = None
# APScheduler instance for notifications
_notification_scheduler = None
# APScheduler instance for backups
_backup_scheduler = None


def _register_services() -> None:
    """Register all background services with the service status collector."""

    # Telemetry Monitor
    register_service(
        name="telemetry_monitor",
        display_name="Telemetry Monitor",
        get_status_fn=telemetry.get_status,
        stop_fn=telemetry.stop_telemetry_monitor,
        start_fn=telemetry.start_telemetry_monitor,
    )

    # Disk I/O Monitor
    register_service(
        name="disk_io_monitor",
        display_name="Disk I/O Monitor",
        get_status_fn=disk_monitor.get_status,
        stop_fn=disk_monitor.stop_monitoring,
        start_fn=disk_monitor.start_monitoring,
    )

    # Power Monitor
    register_service(
        name="power_monitor",
        display_name="Power Monitor",
        get_status_fn=power_monitor.get_status,
        stop_fn=power_monitor.stop_power_monitor,
        start_fn=lambda: power_monitor.start_power_monitor(get_db),
    )

    # Monitoring Orchestrator
    register_service(
        name="monitoring_orchestrator",
        display_name="Monitoring Orchestrator",
        get_status_fn=orchestrator_get_status,
        stop_fn=stop_monitoring,
        start_fn=lambda: start_monitoring(get_db),
    )

    # Power Manager
    register_service(
        name="power_manager",
        display_name="CPU Power Manager",
        get_status_fn=power_manager.get_status,
        stop_fn=power_manager.stop_power_manager,
        start_fn=power_manager.start_power_manager,
        config_enabled_fn=lambda: settings.power_management_enabled,
    )

    # Fan Control
    register_service(
        name="fan_control",
        display_name="Fan Control",
        get_status_fn=fan_control.get_service_status,
        stop_fn=fan_control.stop_fan_control,
        start_fn=fan_control.start_fan_control,
        config_enabled_fn=lambda: settings.fan_control_enabled,
    )

    # Sync Scheduler
    register_service(
        name="sync_scheduler",
        display_name="Sync Scheduler",
        get_status_fn=sync_background.get_status,
        stop_fn=sync_background.stop_sync_scheduler,
        start_fn=sync_background.start_sync_scheduler,
    )

    # Network Discovery
    def _get_network_discovery_status():
        if _discovery_service is None:
            return {"is_running": False}
        return _discovery_service.get_status()

    register_service(
        name="network_discovery",
        display_name="Network Discovery (mDNS)",
        get_status_fn=_get_network_discovery_status,
        stop_fn=lambda: _discovery_service.stop() if _discovery_service else None,
        start_fn=lambda: _discovery_service.start() if _discovery_service else None,
    )

    # Notification Scheduler
    def _get_notification_scheduler_status():
        is_running = _notification_scheduler is not None and _notification_scheduler.running
        return {
            "is_running": is_running,
            "interval_seconds": 3600,  # 1 hour
            "config_enabled": FirebaseService.is_available(),
        }

    register_service(
        name="notification_scheduler",
        display_name="Notification Scheduler",
        get_status_fn=_get_notification_scheduler_status,
        config_enabled_fn=FirebaseService.is_available,
    )

    # Backup Scheduler
    def _get_backup_scheduler_status():
        is_running = _backup_scheduler is not None and _backup_scheduler.running
        return {
            "is_running": is_running,
            "interval_seconds": settings.backup_auto_interval_hours * 3600 if settings.backup_auto_enabled else None,
            "config_enabled": settings.backup_auto_enabled,
        }

    register_service(
        name="backup_scheduler",
        display_name="Backup Scheduler",
        get_status_fn=_get_backup_scheduler_status,
        config_enabled_fn=lambda: settings.backup_auto_enabled,
    )

    # Health Monitor
    register_service(
        name="health_monitor",
        display_name="Health Monitor",
        get_status_fn=jobs.get_status,
        stop_fn=jobs.stop_health_monitor,
        start_fn=jobs.start_health_monitor,
        config_enabled_fn=lambda: not settings.is_dev_mode,
    )

    # RAID Scrub Scheduler
    register_service(
        name="raid_scrub_scheduler",
        display_name="RAID Scrub Scheduler",
        get_status_fn=raid_service.get_scrub_scheduler_status,
        stop_fn=raid_service.stop_scrub_scheduler,
        start_fn=raid_service.start_scrub_scheduler,
        config_enabled_fn=lambda: getattr(settings, "raid_scrub_enabled", False),
    )

    # SMART Scan Scheduler
    register_service(
        name="smart_scan_scheduler",
        display_name="SMART Scan Scheduler",
        get_status_fn=smart_service.get_smart_scheduler_status,
        stop_fn=smart_service.stop_smart_scheduler,
        start_fn=smart_service.start_smart_scheduler,
        config_enabled_fn=lambda: getattr(settings, "smart_scan_enabled", False),
    )


@asynccontextmanager
async def _lifespan(_: FastAPI):  # pragma: no cover - startup/shutdown hook
    global _discovery_service
    # Allow tests to skip full app initialization by setting SKIP_APP_INIT=1
    import os
    skip_init = os.environ.get('SKIP_APP_INIT') == '1'
    if skip_init:
        logger.info('SKIP_APP_INIT set; skipping full app startup (tests)')
        # Do not perform the normal initialization steps, but still enter
        # the lifespan so the `finally` block runs to perform cleanup.
        try:
            yield
        finally:
            # Proceed to cleanup below; avoid starting background services.
            pass
        return

    # Initialize database tables
    init_db()
    logger.info("Database initialized")

    ensure_admin_user(settings)
    logger.info("Admin user ensured with username '%s'", settings.admin_username)
    seed.seed_dev_data()
    await jobs.start_health_monitor()
    await telemetry.start_telemetry_monitor()
    await power_monitor.start_power_monitor(get_db)
    disk_monitor.start_monitoring()
    await start_monitoring(get_db)
    logger.info("System monitoring started")

    # Start CPU power management (if enabled)
    if settings.power_management_enabled:
        try:
            await power_manager.start_power_manager()
            logger.info("CPU power management started")
        except Exception as e:
            logger.warning(f"CPU power management could not start: {e}")

    # Start fan control (if enabled)
    if settings.fan_control_enabled:
        try:
            await fan_control.start_fan_control()
            logger.info("Fan control started")
        except Exception as e:
            logger.warning(f"Fan control could not start: {e}")

    await sync_background.start_sync_scheduler()
    logger.info("Sync scheduler started")
    
    # Start network discovery (mDNS/Bonjour)
    try:
        port = int(settings.api_port) if hasattr(settings, 'api_port') else 8000
        _discovery_service = NetworkDiscoveryService(
            port=port,
            hostname=settings.mdns_hostname
        )
        _discovery_service.start()
    except Exception as e:
        logger.warning(f"Network discovery could not start: {e}")
    
    # Initialize Firebase (optional, warnings if not configured)
    FirebaseService.initialize()
    
    # Start notification scheduler (only if Firebase is available)
    if FirebaseService.is_available():
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            global _notification_scheduler
            _notification_scheduler = BackgroundScheduler()
            
            # Run every hour to check for expiring devices
            _notification_scheduler.add_job(
                func=NotificationScheduler.run_periodic_check,
                trigger="interval",
                hours=1,
                id="device_expiration_check",
                name="Check and send device expiration warnings",
                replace_existing=True
            )
            
            _notification_scheduler.start()
            logger.info("✅ Notification scheduler started (running every hour)")
        except Exception as e:
            logger.warning(f"Notification scheduler could not start: {e}")
    else:
        logger.info("⏭️  Notification scheduler skipped (Firebase not configured)")

    # Start backup scheduler (if enabled in settings)
    if settings.backup_auto_enabled:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            global _backup_scheduler
            _backup_scheduler = BackgroundScheduler()

            _backup_scheduler.add_job(
                func=BackupScheduler.run_periodic_backup,
                trigger="interval",
                hours=settings.backup_auto_interval_hours,
                id="automated_backup",
                name=f"Automated {settings.backup_auto_type} backup",
                replace_existing=True
            )

            _backup_scheduler.start()
            logger.info(f"✅ Backup scheduler started (running every {settings.backup_auto_interval_hours}h, type: {settings.backup_auto_type})")
        except Exception as e:
            logger.warning(f"Backup scheduler could not start: {e}")
    else:
        logger.info("⏭️  Backup scheduler disabled (enable with BACKUP_AUTO_ENABLED=true)")

    # Start RAID scrub scheduler (if enabled in settings)
    try:
        raid_service.start_scrub_scheduler()
    except Exception as e:
        logger.warning(f"RAID scrub scheduler could not start: {e}")
    # Start SMART scheduler (if enabled in settings)
    try:
        smart_service.start_smart_scheduler()
    except Exception as e:
        logger.warning(f"SMART scheduler could not start: {e}")

    # Set server start time for uptime tracking
    set_server_start_time()

    # Register all services with the service status collector
    _register_services()

    # Set DB engine for pool monitoring
    from app.core.database import engine
    collector = get_service_status_collector()
    collector.set_db_engine(engine)

    logger.info("Service status collector initialized")

    try:
        yield
    finally:
        # Stop background services if they were started
        try:
            if not skip_init:
                await jobs.stop_health_monitor()
                await telemetry.stop_telemetry_monitor()
                await power_monitor.stop_power_monitor()
                disk_monitor.stop_monitoring()
                await stop_monitoring()
                logger.info("System monitoring stopped")
                await sync_background.stop_sync_scheduler()
                logger.info("Sync scheduler stopped")
                # Stop CPU power management
                try:
                    await power_manager.stop_power_manager()
                    logger.info("CPU power management stopped")
                except Exception:
                    logger.debug("Error stopping CPU power management")
                # Stop fan control
                try:
                    await fan_control.stop_fan_control()
                    logger.info("Fan control stopped")
                except Exception:
                    logger.debug("Error stopping fan control")
        except Exception:
            logger.debug("Error while stopping background services")

        # Always attempt to shutdown the upload progress manager to cancel any
        # pending cleanup tasks created during tests or runtime.
        try:
            from app.services.upload_progress import get_upload_progress_manager
            mgr = get_upload_progress_manager()
            await mgr.shutdown()
        except Exception:
            logger.debug("Upload progress manager shutdown skipped or failed")
        
        # Stop network discovery
        if _discovery_service:
            _discovery_service.stop()
        
        # Stop notification scheduler
        if _notification_scheduler:
            _notification_scheduler.shutdown()
            logger.info("Notification scheduler stopped")

        # Stop backup scheduler
        if _backup_scheduler:
            _backup_scheduler.shutdown()
            logger.info("Backup scheduler stopped")
        # Stop RAID scrub scheduler
        try:
            raid_service.stop_scrub_scheduler()
        except Exception:
            logger.debug("Error while stopping RAID scrub scheduler")
        # Stop SMART scheduler
        try:
            smart_service.stop_smart_scheduler()
        except Exception:
            logger.debug("Error while stopping SMART scheduler")


def create_app() -> FastAPI:
    # Configure structured logging before any other setup
    from app.core.logging_config import setup_logging
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=_lifespan,
        docs_url=None,  # Disable default docs
        redoc_url=None,  # Disable default redoc
    )
    
    # Add rate limiting state and exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Map specific validation errors (e.g. SSH private key format) to 400
    def _validation_exception_handler(request, exc: RequestValidationError):
        try:
            errors = exc.errors()
            # If any validation message mentions PRIVATE KEY, return 400
            for e in errors:
                msg = e.get("msg", "")
                if "PRIVATE KEY" in str(msg).upper():
                    return JSONResponse(status_code=400, content={"detail": msg})
        except Exception:
            pass

        # Convert errors to JSON-serializable format (fixes Python 3.13 compatibility)
        serializable_errors = []
        try:
            errors = exc.errors()
            for error in errors:
                serializable_error = {}
                for key, value in error.items():
                    # Convert non-serializable objects (like ValueError) to strings
                    if isinstance(value, (str, int, float, bool, type(None))):
                        serializable_error[key] = value
                    elif isinstance(value, (list, tuple)):
                        serializable_error[key] = [str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for v in value]
                    else:
                        serializable_error[key] = str(value)
                serializable_errors.append(serializable_error)
        except Exception:
            # Fallback: convert entire error to string
            serializable_errors = [{"msg": str(exc)}]

        # Default behavior: return standard 422 response body
        return JSONResponse(status_code=422, content={"detail": serializable_errors})

    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    # ✅ Security Fix #2: Add security headers to all responses
    # Adds: Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, HSTS
    app.add_middleware(SecurityHeadersMiddleware)

    # Add error counter middleware for admin metrics
    app.add_middleware(ErrorCounterMiddleware)

    # Add local-only enforcement middleware (Option B security)
    if settings.enforce_local_only:
        app.add_middleware(
            LocalOnlyMiddleware,
            enforce=True,
            protected_prefixes=[
                "/api/server-profiles",
                "/api/auth/login",
                "/api/auth/register",
            ]
        )

    # Add device tracking middleware (updates last_seen for mobile devices)
    app.add_middleware(DeviceTrackingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    
    # Mount static files for avatars
    avatars_path = Path("storage/avatars")
    avatars_path.mkdir(parents=True, exist_ok=True)
    app.mount("/avatars", StaticFiles(directory=str(avatars_path)), name="avatars")
    
    # Include custom styled docs
    from app.api.docs import router as docs_router
    app.include_router(docs_router)

    return app


app = create_app()


def run(**kwargs: Any) -> None:  # pragma: no cover - convenience launcher
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
        **kwargs,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
