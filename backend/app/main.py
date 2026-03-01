from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    _service_registry,
)
from app.services.monitoring.orchestrator import get_status as orchestrator_get_status
from app.plugins.manager import PluginManager
from app.services.update.api import register_update_service, finalize_pending_updates

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PRIMARY_WORKER guard
# ---------------------------------------------------------------------------
# Hardware-controlling tasks (fan, power, telemetry, mDNS, disk I/O) must
# only run in one process to avoid conflicts.
#
# Detection strategy (in order):
# 1. If BALUHOST_PRIMARY_WORKER is explicitly set to "0", this worker is
#    secondary (env-var override, useful for manual control).
# 2. Otherwise, attempt to acquire an exclusive file lock on
#    /tmp/baluhost-primary.lock.  The first worker to succeed becomes
#    primary; the OS releases the lock automatically if the process dies,
#    so another worker can take over.
# 3. On Windows / dev-mode, the flock path is skipped and every process
#    defaults to primary (single-worker is the norm there).
# ---------------------------------------------------------------------------
_primary_lock_fd = None  # kept open to hold the lock for the process lifetime


def _try_become_primary() -> bool:
    """Try to acquire the primary-worker file lock (non-blocking).

    Returns True if this process is now the primary worker.
    """
    # Explicit opt-out via env var
    env_val = os.environ.get("BALUHOST_PRIMARY_WORKER")
    if env_val == "0":
        return False

    # On non-Linux (Windows dev-mode), skip file locking
    try:
        import fcntl
    except ImportError:
        return True

    global _primary_lock_fd
    lock_path = Path("/tmp/baluhost-primary.lock")

    # Do NOT unlink before open — that creates a race where two workers
    # each unlink+create different inodes and both acquire the lock.
    # Stale lock cleanup is handled by ExecStartPre / start_prod.py.
    try:
        fd = open(lock_path, "a")
    except OSError as exc:
        logger.error("Cannot open primary lock file %s: %s", lock_path, exc)
        return False

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        fd.close()
        return False

    fd.seek(0)
    fd.truncate()
    fd.write(str(os.getpid()))
    fd.flush()
    _primary_lock_fd = fd  # keep fd open — lock released on process exit
    return True


IS_PRIMARY_WORKER = False  # Determined in _lifespan() after fork

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


# ---------------------------------------------------------------------------
# Service heartbeat: primary → DB, secondary reads from DB
# ---------------------------------------------------------------------------
# Services that only run on the primary worker.  On secondary workers their
# status function is replaced by a DB reader so the dashboard always shows
# the correct state regardless of which worker handles the request.
# Services that run exclusively on the primary worker (or monitoring_worker in prod).
# On secondary workers, their status function is replaced by a DB reader.
PRIMARY_ONLY_SERVICES = [
    "telemetry_monitor",
    "disk_io_monitor",
    "power_monitor",
    "monitoring_orchestrator",
    "power_manager",
    "fan_control",
    "sleep_mode",
    "network_discovery",
]

# Monitoring services that are offloaded to monitoring_worker in prod mode.
# In prod, even the primary web worker reads from SHM/DB instead of in-process.
_MONITORING_WORKER_SERVICES = [
    "telemetry_monitor",
    "disk_io_monitor",
    "power_monitor",
    "monitoring_orchestrator",
]


async def _do_heartbeat_write() -> None:
    """Write current service states to the service_heartbeats table once."""
    from app.models.service_heartbeat import ServiceHeartbeat
    from app.core.database import SessionLocal

    # In prod mode, monitoring_worker writes its own heartbeats for these 4
    # services.  Skip them here to avoid the circular DB-read-write loop
    # (their get_status is a DB reader on the primary worker in prod).
    skip = set(_MONITORING_WORKER_SERVICES) if not settings.is_dev_mode else set()

    db = SessionLocal()
    try:
        for name, registry in _service_registry.items():
            if name in skip:
                continue
            try:
                status = registry["get_status"]()
            except Exception:
                status = {"is_running": False}
            db.merge(ServiceHeartbeat(
                name=name,
                is_running=status.get("is_running", False),
                details_json=json.dumps(status, default=str),
                updated_at=datetime.now(timezone.utc),
            ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def _write_service_heartbeats() -> None:
    """Periodically write service states to DB for secondary workers (primary only)."""
    # Write initial heartbeat immediately so secondary workers
    # have data from the very first request (instead of waiting 15s).
    await _do_heartbeat_write()

    while True:
        await asyncio.sleep(15)
        await _do_heartbeat_write()


async def _pihole_health_loop() -> None:
    """Periodically check remote Pi-hole health and trigger failover/failback."""
    from app.core.database import SessionLocal
    from app.services.pihole.service import PiholeService

    # Wait a bit on startup before first check
    await asyncio.sleep(10)

    # Register .local DNS records on first run (best-effort)
    try:
        db = SessionLocal()
        try:
            svc = PiholeService(db)
            await svc.ensure_local_dns_records()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Pi-hole DNS registration on startup failed: %s", e)

    while True:
        interval = 30
        try:
            db = SessionLocal()
            try:
                svc = PiholeService(db)
                if svc.has_remote_pi():
                    await svc.check_health_and_failover()
                    interval = svc.get_config().health_check_interval or 30
            finally:
                db.close()
        except Exception as e:
            logger.warning("Pi-hole health check error: %s", e)
        await asyncio.sleep(interval)


def _make_db_status_reader(service_name: str):
    """Return a status function that reads from the service_heartbeats table."""
    def read_status():
        from app.models.service_heartbeat import ServiceHeartbeat
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            hb = db.query(ServiceHeartbeat).filter_by(name=service_name).first()
            if hb and hb.updated_at:
                age = (datetime.now(timezone.utc) - hb.updated_at).total_seconds()
                if age < 45:  # heartbeat writes every 15s, allow some slack
                    if hb.details_json:
                        return json.loads(hb.details_json)
                    return {"is_running": hb.is_running}
            return {"is_running": False}
        except Exception:
            return {"is_running": False}
        finally:
            db.close()
    return read_status


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

    # Monitoring Worker Process Health (prod only)
    def _get_monitoring_worker_status():
        from app.services.monitoring.shm import is_monitoring_worker_alive, read_shm, HEARTBEAT_FILE
        hb = read_shm(HEARTBEAT_FILE, max_age_seconds=30.0)
        alive = hb is not None and hb.get("alive", False)
        return {
            "is_running": alive,
            "pid": hb.get("pid") if hb else None,
            "paused": hb.get("paused", False) if hb else False,
            "services": hb.get("services", []) if hb else [],
            "config_enabled": not settings.is_dev_mode,
        }

    if not settings.is_dev_mode:
        register_service(
            name="monitoring_worker",
            display_name="Monitoring Worker",
            get_status_fn=_get_monitoring_worker_status,
        )

    # Pi-hole DNS Integration
    def _get_pihole_status():
        from app.services.pihole.service import PiholeService
        from app.core.database import SessionLocal as _SL
        db = _SL()
        try:
            svc = PiholeService(db)
            return svc.get_service_status()
        except Exception:
            return {"is_running": False}
        finally:
            db.close()

    register_service(
        name="pihole_dns",
        display_name="Pi-hole DNS",
        get_status_fn=_get_pihole_status,
        config_enabled_fn=lambda: settings.pihole_enabled,
    )

    # On secondary workers: replace in-process status functions for
    # primary-only services with DB readers so the dashboard shows
    # consistent data regardless of which worker handles the request.
    if not IS_PRIMARY_WORKER:
        for svc_name in PRIMARY_ONLY_SERVICES:
            if svc_name in _service_registry:
                _service_registry[svc_name]["get_status"] = _make_db_status_reader(svc_name)

    # In prod mode, the primary worker also doesn't run monitoring in-process,
    # so it needs DB readers for the 4 monitoring services too.
    if IS_PRIMARY_WORKER and not settings.is_dev_mode:
        for svc_name in _MONITORING_WORKER_SERVICES:
            if svc_name in _service_registry:
                _service_registry[svc_name]["get_status"] = _make_db_status_reader(svc_name)


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

    # Acquire primary-worker lock *after* fork (lifespan runs per-worker).
    global IS_PRIMARY_WORKER
    IS_PRIMARY_WORKER = _try_become_primary()
    logger.info("Primary worker: %s (PID %d)", IS_PRIMARY_WORKER, os.getpid())

    # Hardware-controlling background tasks only run on the primary worker.
    # Secondary workers skip these to avoid duplicate hardware writes.
    if IS_PRIMARY_WORKER:
        if settings.is_dev_mode:
            # Dev mode: all monitoring services run in-process (like before)
            await telemetry.start_telemetry_monitor()
            await power_monitor.start_power_monitor(get_db)
            disk_monitor.start_monitoring()
            await start_monitoring(get_db)
            logger.info("System monitoring started in-process (dev mode, primary worker)")
        else:
            # Production: monitoring_worker process handles these 4 services
            logger.info("Monitoring managed by monitoring_worker process (prod mode)")

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
    else:
        logger.info("Secondary worker — skipping hardware services")
        # Initialize fan control read-only (backend + configs, no monitoring loop)
        if settings.fan_control_enabled:
            try:
                await fan_control.start_fan_control(monitoring=False)
                logger.info("Fan control initialized (read-only, secondary worker)")
            except Exception as e:
                logger.warning("Fan control init failed on secondary worker: %s", e)

    # NOTE: Sync/backup/RAID-scrub/SMART/notification schedulers are now
    # managed by the separate scheduler_worker process (scheduler_worker.py).
    # The web process no longer starts APScheduler instances for these jobs.
    
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

    # Start heartbeat writer on primary worker so secondary workers can
    # read accurate service status from the database.
    if IS_PRIMARY_WORKER:
        asyncio.create_task(_write_service_heartbeats())
        asyncio.create_task(_pihole_health_loop())

    # Register update service
    register_update_service()

    # Finalize any updates that were in progress when the backend last stopped
    # (e.g. after the detached update script restarted us)
    if not settings.is_dev_mode:
        try:
            from app.core.database import SessionLocal
            with SessionLocal() as update_db:
                finalized = finalize_pending_updates(update_db)
                if finalized:
                    logger.info("Finalized %d pending update(s) from previous run", finalized)
        except Exception as e:
            logger.warning(f"Failed to finalize pending updates: {e}")

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

    # Notify BaluPi companion device that NAS is online
    if IS_PRIMARY_WORKER and settings.balupi_enabled:
        try:
            from app.services.balupi_handshake import notify_balupi_startup
            await notify_balupi_startup()
        except Exception as exc:
            logger.warning("BaluPi startup notification failed: %s", exc)

    try:
        yield
    finally:
        # Notify BaluPi companion device that NAS is going offline
        if not skip_init and IS_PRIMARY_WORKER and settings.balupi_enabled:
            try:
                from app.services.snapshot_export import create_shutdown_snapshot
                from app.services.balupi_handshake import notify_balupi_shutdown, close_client
                from app.core.database import SessionLocal
                with SessionLocal() as snap_db:
                    snapshot = create_shutdown_snapshot(snap_db)
                await notify_balupi_shutdown(snapshot)
                await close_client()
            except Exception as exc:
                logger.warning("BaluPi shutdown notification failed: %s", exc)

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
                if IS_PRIMARY_WORKER and settings.is_dev_mode:
                    # Only stop monitoring in dev mode (prod uses monitoring_worker)
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
