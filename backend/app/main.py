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
from starlette.formparsers import MultiPartParser
from starlette.requests import Request as StarletteRequest

# Individual file size limit — class attribute, works correctly
MultiPartParser.max_file_size = 10 * 1024 * 1024 * 1024  # 10 GB (matches nginx client_max_body_size)

# Batch upload limits — must patch Request.form() because FastAPI calls it
# without arguments, and the defaults (1000) are hardcoded in the method signature.
# Class attributes on MultiPartParser do NOT work (constructor overrides them).
_orig_form = StarletteRequest.form

def _form_with_limits(self, *, max_files: int | float = float('inf'), max_fields: int | float = float('inf')):
    return _orig_form(self, max_files=max_files, max_fields=max_fields)

StarletteRequest.form = _form_with_limits  # type: ignore[assignment]
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db, get_db
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.services.users import ensure_admin_user
from app.services import disk_monitor, jobs, seed, telemetry
from app.services import power_monitor
from app.services import power_manager
from app.services import fan_control
from app.services.power import sleep as sleep_mode
from app.services.monitoring.orchestrator import start_monitoring, stop_monitoring
from app.services.network_discovery import NetworkDiscoveryService
from app.services.firebase_service import FirebaseService
from app.services.websocket_manager import init_websocket_manager
from app.services.email_service import init_email_service
from app.services.event_emitter import init_event_emitter
from app.middleware.device_tracking import DeviceTrackingMiddleware
from app.middleware.local_only import LocalOnlyMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.error_counter import ErrorCounterMiddleware
from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
from app.services.service_status import (
    set_server_start_time,
    register_service,
    get_service_status_collector,
)
from app.services.monitoring.orchestrator import get_status as orchestrator_get_status
from app.plugins.manager import PluginManager
from app.services.update_service import register_update_service

logger = logging.getLogger(__name__)

# Network discovery service instance
_discovery_service = None
# Plugin manager instance
_plugin_manager = None
# WebSocket manager instance
_websocket_manager = None


def _get_worker_scheduler_status(scheduler_name: str) -> dict:
    """Read scheduler status from scheduler_state table (written by worker process)."""
    from app.models.scheduler_state import SchedulerState
    from app.core.database import SessionLocal as _SL
    db = _SL()
    try:
        state = (
            db.query(SchedulerState)
            .filter(SchedulerState.scheduler_name == scheduler_name)
            .first()
        )
        if state is None:
            return {"is_running": False}
        return {
            "is_running": state.is_running,
            "is_executing": state.is_executing,
            "next_run": state.next_run_at.isoformat() if state.next_run_at else None,
            "last_heartbeat": state.last_heartbeat.isoformat() if state.last_heartbeat else None,
            "worker_pid": state.worker_pid,
        }
    except Exception:
        return {"is_running": False}
    finally:
        db.close()


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

    # Sleep Mode
    register_service(
        name="sleep_mode",
        display_name="Sleep Mode",
        get_status_fn=sleep_mode.get_service_status,
        stop_fn=sleep_mode.stop_sleep_manager,
        start_fn=sleep_mode.start_sleep_manager,
        config_enabled_fn=lambda: settings.sleep_mode_enabled,
    )

    # Sync Scheduler (managed by scheduler_worker process)
    register_service(
        name="sync_scheduler",
        display_name="Sync Scheduler",
        get_status_fn=lambda: _get_worker_scheduler_status("sync_check"),
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

    # Notification Scheduler (managed by scheduler_worker process)
    register_service(
        name="notification_scheduler",
        display_name="Notification Scheduler",
        get_status_fn=lambda: _get_worker_scheduler_status("notification_check"),
        config_enabled_fn=FirebaseService.is_available,
    )

    # Backup Scheduler (managed by scheduler_worker process)
    register_service(
        name="backup_scheduler",
        display_name="Backup Scheduler",
        get_status_fn=lambda: _get_worker_scheduler_status("backup"),
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

    # RAID Scrub Scheduler (managed by scheduler_worker process)
    register_service(
        name="raid_scrub_scheduler",
        display_name="RAID Scrub Scheduler",
        get_status_fn=lambda: _get_worker_scheduler_status("raid_scrub"),
        config_enabled_fn=lambda: getattr(settings, "raid_scrub_enabled", False),
    )

    # SMART Scan Scheduler (managed by scheduler_worker process)
    register_service(
        name="smart_scan_scheduler",
        display_name="SMART Scan Scheduler",
        get_status_fn=lambda: _get_worker_scheduler_status("smart_scan"),
        config_enabled_fn=lambda: getattr(settings, "smart_scan_enabled", False),
    )

    # WebDAV Server (managed by webdav_worker process)
    def _get_webdav_status():
        from app.models.webdav_state import WebdavState
        from app.core.database import SessionLocal as _SL
        from datetime import datetime, timezone
        db = _SL()
        try:
            state = db.query(WebdavState).first()
            if state is None:
                return {"is_running": False}
            # Consider stale if heartbeat is older than 30s
            is_fresh = False
            if state.last_heartbeat:
                age = (datetime.now(timezone.utc) - state.last_heartbeat).total_seconds()
                is_fresh = age < 30
            return {
                "is_running": state.is_running and is_fresh,
                "port": state.port,
                "ssl_enabled": state.ssl_enabled,
                "started_at": state.started_at.isoformat() if state.started_at else None,
                "worker_pid": state.worker_pid,
                "error_message": state.error_message,
            }
        except Exception:
            return {"is_running": False}
        finally:
            db.close()

    register_service(
        name="webdav_server",
        display_name="WebDAV Server",
        get_status_fn=_get_webdav_status,
        config_enabled_fn=lambda: settings.webdav_enabled,
    )

    # Scheduler Worker Process Health
    def _get_scheduler_worker_status():
        from app.services.scheduler_service import is_worker_healthy_global
        healthy = is_worker_healthy_global()
        return {
            "is_running": healthy is True,
            "config_enabled": True,
        }

    register_service(
        name="scheduler_worker",
        display_name="Scheduler Worker",
        get_status_fn=_get_scheduler_worker_status,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):  # pragma: no cover - startup/shutdown hook
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

    # Recover stale benchmarks and kill orphan fio processes from previous runs
    from app.services.benchmark_service import recover_stale_benchmarks, kill_orphan_fio_processes
    from app.core.database import SessionLocal
    with SessionLocal() as bench_db:
        recovered = recover_stale_benchmarks(bench_db)
        if recovered:
            logger.info("Recovered %d stale benchmark(s) from previous run", recovered)
    kill_orphan_fio_processes()

    # Recover stale scheduler executions from previous run
    from app.services.scheduler_service import recover_stale_executions
    with SessionLocal() as sched_db:
        recovered = recover_stale_executions(sched_db)
        if recovered:
            logger.info("Recovered %d stale scheduler execution(s) from previous run", recovered)

    # Ensure home directories for all users and Shared folder
    from app.services.users import ensure_user_home_directories
    ensure_user_home_directories()
    logger.info("User home directories ensured")

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
            await power_manager.check_and_notify_permissions()
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

    # Start sleep mode (if enabled)
    if settings.sleep_mode_enabled:
        try:
            await sleep_mode.start_sleep_manager()
            logger.info("Sleep mode service started")
        except Exception as e:
            logger.warning(f"Sleep mode service could not start: {e}")

    # NOTE: Sync/backup/RAID-scrub/SMART/notification schedulers are now
    # managed by the separate scheduler_worker process (scheduler_worker.py).
    # The web process no longer starts APScheduler instances for these jobs.

    # Start network discovery (mDNS/Bonjour)
    try:
        port = int(settings.api_port) if hasattr(settings, 'api_port') else 8000
        _discovery_service = NetworkDiscoveryService(
            port=port,
            webdav_port=settings.webdav_port,
            hostname=settings.mdns_hostname,
            webdav_ssl_enabled=settings.webdav_ssl_enabled,
        )
        _discovery_service.start()
    except Exception as e:
        logger.warning(f"Network discovery could not start: {e}")
    
    # Initialize Firebase (optional, warnings if not configured)
    FirebaseService.initialize()

    # Initialize notification system services
    global _websocket_manager
    try:
        from app.core.database import SessionLocal
        _websocket_manager = init_websocket_manager()
        init_email_service()
        init_event_emitter(SessionLocal)
        logger.info("Notification system initialized")
    except Exception as e:
        logger.warning(f"Notification system could not initialize: {e}")
    
    # Scheduler jobs (backup, RAID scrub, SMART, notification, sync)
    # are now handled by the scheduler_worker process.

    # Set server start time for uptime tracking
    set_server_start_time()

    # Register all services with the service status collector
    _register_services()

    # Register update service
    register_update_service()

    # Set DB engine for pool monitoring
    from app.core.database import engine
    collector = get_service_status_collector()
    collector.set_db_engine(engine)

    logger.info("Service status collector initialized")

    # Initialize plugin system
    global _plugin_manager
    try:
        _plugin_manager = PluginManager.get_instance()
        # Get a database session for plugin loading
        from app.core.database import SessionLocal
        with SessionLocal() as plugin_db:
            await _plugin_manager.load_enabled_plugins(plugin_db)
        # Mount plugin API routes dynamically
        plugin_router = _plugin_manager.get_router()
        if plugin_router.routes:
            app.include_router(plugin_router, prefix="/api")
            logger.info(f"Mounted {len(plugin_router.routes)} plugin routes")
        # Emit system startup hook
        _plugin_manager.emit_hook("on_system_startup")
        logger.info("Plugin system initialized")
    except Exception as e:
        logger.warning(f"Plugin system could not initialize: {e}")

    try:
        yield
    finally:
        # Shutdown active benchmarks and kill orphan fio processes
        try:
            if not skip_init:
                from app.services.benchmark_service import shutdown_benchmarks
                from app.core.database import SessionLocal
                with SessionLocal() as bench_db:
                    await shutdown_benchmarks(bench_db)
                logger.info("Benchmark shutdown complete")
        except Exception:
            logger.debug("Error during benchmark shutdown")

        # Stop background services if they were started
        try:
            if not skip_init:
                await jobs.stop_health_monitor()
                await telemetry.stop_telemetry_monitor()
                await power_monitor.stop_power_monitor()
                disk_monitor.stop_monitoring()
                await stop_monitoring()
                logger.info("System monitoring stopped")
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
                # Stop sleep mode
                try:
                    await sleep_mode.stop_sleep_manager()
                    logger.info("Sleep mode service stopped")
                except Exception:
                    logger.debug("Error stopping sleep mode service")
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

        # Shutdown chunked upload manager (cancel cleanup loop, remove temp files)
        try:
            from app.services.files.chunked_upload import get_chunked_upload_manager
            await get_chunked_upload_manager().shutdown()
        except Exception:
            logger.debug("Chunked upload manager shutdown skipped or failed")
        
        # Stop network discovery
        if _discovery_service:
            _discovery_service.stop()
        
        # Scheduler jobs are stopped by the scheduler_worker process.

        # Shutdown plugin system
        if _plugin_manager:
            try:
                _plugin_manager.emit_hook("on_system_shutdown")
                await _plugin_manager.shutdown_all()
                logger.info("Plugin system shut down")
            except Exception:
                logger.debug("Error while shutting down plugin system")


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

    # Add sleep auto-wake middleware (counts requests + auto-wakes from soft sleep)
    app.add_middleware(SleepAutoWakeMiddleware)

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
    avatars_path = Path(settings.nas_storage_path) / ".system" / "avatars"
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
