"""
Application lifespan management.

Handles startup initialization, background service orchestration,
primary-worker election, and graceful shutdown.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

from app.core.config import settings
from app.core.service_registry import (
    MONITORING_WORKER_SERVICES,
    make_db_status_reader,
    register_all_services,
)
from app.services.service_status import (
    set_server_start_time,
    get_service_status_collector,
    _service_registry,
)

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

IS_PRIMARY_WORKER = False  # Determined in _lifespan() after fork

# Instance references for services managed within the lifespan
_discovery_service = None
_plugin_manager = None
_websocket_manager = None


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
        import fcntl as _fcntl  # type: ignore[import-not-found]
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
        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)  # type: ignore[attr-defined]
    except (IOError, OSError):
        fd.close()
        return False

    fd.seek(0)
    fd.truncate()
    fd.write(str(os.getpid()))
    fd.flush()
    _primary_lock_fd = fd  # keep fd open — lock released on process exit
    return True


# ---------------------------------------------------------------------------
# Service heartbeat: primary → DB, secondary reads from DB
# ---------------------------------------------------------------------------

def _do_heartbeat_write_sync() -> None:
    """Write current service states to the service_heartbeats table (sync, thread-safe)."""
    from app.models.service_heartbeat import ServiceHeartbeat
    from app.core.database import SessionLocal

    # In prod mode, monitoring_worker writes its own heartbeats for these 4
    # services.  Skip them here to avoid the circular DB-read-write loop
    # (their get_status is a DB reader on the primary worker in prod).
    skip = set(MONITORING_WORKER_SERVICES) if not settings.is_dev_mode else set()

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


async def _do_heartbeat_write() -> None:
    """Write current service states to the service_heartbeats table once."""
    await asyncio.to_thread(_do_heartbeat_write_sync)


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
                    interval = int(svc.get_config().health_check_interval or 30)  # type: ignore[arg-type]
            finally:
                db.close()
        except Exception as e:
            logger.warning("Pi-hole health check error: %s", e)
        await asyncio.sleep(interval)


def _log_dev_mode_summary() -> None:
    """Log which backends are active in dev mode (runtime verification)."""
    if not settings.is_dev_mode:
        return

    def _backend_name(get_obj, *attrs):
        """Safely traverse attribute chain and return class name."""
        obj = get_obj()
        for attr in attrs:
            obj = getattr(obj, attr, None)
            if obj is None:
                return "not started"
        return type(obj).__name__

    from app.services.hardware.raid.api import _backend as raid_backend
    from app.services.power.manager import PowerManagerService
    from app.services.power.fan_control import FanControlService
    from app.services.power.sleep import SleepManagerService

    lines = ["Dev mode backends active:"]
    lines.append(f"  RAID: {type(raid_backend).__name__}")
    lines.append(f"  Power: {_backend_name(lambda: PowerManagerService._instance, '_backend')}")
    lines.append(f"  Fans: {_backend_name(lambda: FanControlService._instance, '_backend')}")
    lines.append(f"  Sleep: {_backend_name(lambda: SleepManagerService._instance, '_backend')}")
    lines.append("  Sensors: dev-mock")
    logger.info("\n".join(lines))


# ---------------------------------------------------------------------------
# Startup / shutdown steps
# ---------------------------------------------------------------------------

async def _startup(app: FastAPI) -> None:
    """Run all startup initialization steps."""
    global _discovery_service, _websocket_manager, _plugin_manager, IS_PRIMARY_WORKER

    from app.core.database import init_db, SessionLocal, engine
    from app.services.users import ensure_admin_user, ensure_user_home_directories
    from app.services import jobs, seed
    from app.services.power import monitor as power_monitor
    from app.services.power import manager as power_manager
    from app.services.power import fan_control
    from app.services.power import sleep as sleep_mode
    from app.services.network_discovery import NetworkDiscoveryService
    from app.services.notifications.firebase import FirebaseService
    from app.services.websocket_manager import init_websocket_manager
    from app.services.notifications.events import init_event_emitter
    from app.services.update.api import register_update_service, finalize_pending_updates
    from app.plugins.manager import PluginManager

    # Wire the log buffer handler to the running event loop for SSE streaming
    from app.services.log_buffer import get_log_buffer_handler
    get_log_buffer_handler().set_event_loop(asyncio.get_running_loop())

    # Initialize database tables
    init_db()
    logger.info("Database initialized")

    ensure_admin_user(settings)
    logger.info("Admin user ensured with username '%s'", settings.admin_username)
    seed.seed_dev_data()

    # Record current version in database
    from app.services.version_tracker import record_version_on_startup
    with SessionLocal() as version_db:
        record_version_on_startup(version_db)

    # Recover stale benchmarks and kill orphan fio processes from previous runs
    from app.services.benchmark.lifecycle import recover_stale_benchmarks, kill_orphan_fio_processes
    with SessionLocal() as bench_db:
        recovered = recover_stale_benchmarks(bench_db)
        if recovered:
            logger.info("Recovered %d stale benchmark(s) from previous run", recovered)
    kill_orphan_fio_processes()

    # Ensure home directories for all users and Shared folder
    ensure_user_home_directories()
    logger.info("User home directories ensured")

    await jobs.start_health_monitor()

    # Acquire primary-worker lock *after* fork (lifespan runs per-worker).
    IS_PRIMARY_WORKER = _try_become_primary()
    logger.info("Primary worker: %s (PID %d)", IS_PRIMARY_WORKER, os.getpid())

    # Hardware-controlling background tasks only run on the primary worker.
    if IS_PRIMARY_WORKER:
        logger.info("Monitoring managed by monitoring_worker process")

        if settings.power_management_enabled:
            try:
                await power_manager.start_power_manager()
                await power_manager.check_and_notify_permissions()
                logger.info("CPU power management started")
            except Exception as e:
                logger.warning(f"CPU power management could not start: {e}")

        if settings.fan_control_enabled:
            try:
                await fan_control.start_fan_control()
                logger.info("Fan control started")
            except Exception as e:
                logger.warning(f"Fan control could not start: {e}")

        if settings.sleep_mode_enabled:
            try:
                await sleep_mode.start_sleep_manager()
                logger.info("Sleep mode service started")
            except Exception as e:
                logger.warning(f"Sleep mode service could not start: {e}")

        try:
            _discovery_service = NetworkDiscoveryService(
                port=settings.port,
                webdav_port=settings.webdav_port,
                hostname=settings.mdns_hostname,
                webdav_ssl_enabled=settings.webdav_ssl_enabled,
            )
            _discovery_service.start()
        except Exception as e:
            logger.warning(f"Network discovery could not start: {e}")
    else:
        logger.info("Secondary worker — skipping hardware services")
        if settings.fan_control_enabled:
            try:
                await fan_control.start_fan_control(monitoring=False)
                logger.info("Fan control initialized (read-only, secondary worker)")
            except Exception as e:
                logger.warning("Fan control init failed on secondary worker: %s", e)

    # Initialize Firebase (optional)
    FirebaseService.initialize()

    # Initialize notification system services
    try:
        _websocket_manager = init_websocket_manager()
        init_event_emitter(SessionLocal)
        logger.info("Notification system initialized")
    except Exception as e:
        logger.warning(f"Notification system could not initialize: {e}")

    # Set server start time for uptime tracking
    set_server_start_time()

    # Register all services with the service status collector
    register_all_services(
        is_primary_worker=IS_PRIMARY_WORKER,
        discovery_service=_discovery_service,
    )

    _log_dev_mode_summary()

    # Start heartbeat writer and background loops on primary worker
    if IS_PRIMARY_WORKER:
        asyncio.create_task(_write_service_heartbeats())
        asyncio.create_task(_pihole_health_loop())

        try:
            from app.services.pihole.query_collector import get_dns_query_collector
            get_dns_query_collector().start(SessionLocal)
            logger.info("DNS query collector started")
        except Exception as e:
            logger.warning("DNS query collector could not start: %s", e)

    # Register update service
    register_update_service()

    # Finalize any updates that were in progress when the backend last stopped
    if not settings.is_dev_mode:
        try:
            with SessionLocal() as update_db:
                finalized = finalize_pending_updates(update_db)
                if finalized:
                    logger.info("Finalized %d pending update(s) from previous run", finalized)
        except Exception as e:
            logger.warning(f"Failed to finalize pending updates: {e}")

    # Set DB engine for pool monitoring
    collector = get_service_status_collector()
    collector.set_db_engine(engine)
    logger.info("Service status collector initialized")

    # Initialize plugin system
    try:
        _plugin_manager = PluginManager.get_instance()
        with SessionLocal() as plugin_db:
            await _plugin_manager.load_enabled_plugins(plugin_db)
        plugin_router = _plugin_manager.get_router()
        if plugin_router.routes:
            app.include_router(plugin_router, prefix=settings.api_prefix)
            logger.info(f"Mounted {len(plugin_router.routes)} plugin routes")
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


async def _shutdown() -> None:
    """Run all graceful shutdown steps."""
    from app.services import jobs
    from app.services.power import manager as power_manager
    from app.services.power import fan_control
    from app.services.power import sleep as sleep_mode

    # Notify BaluPi companion device that NAS is going offline
    if IS_PRIMARY_WORKER and settings.balupi_enabled:
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
        from app.services.benchmark.lifecycle import shutdown_benchmarks
        from app.core.database import SessionLocal
        with SessionLocal() as bench_db:
            await shutdown_benchmarks(bench_db)
        logger.info("Benchmark shutdown complete")
    except Exception:
        logger.debug("Error during benchmark shutdown")

    # Stop background services
    try:
        await jobs.stop_health_monitor()
        if IS_PRIMARY_WORKER:
            try:
                await power_manager.stop_power_manager()
                logger.info("CPU power management stopped")
            except Exception:
                logger.debug("Error stopping CPU power management")
            try:
                await fan_control.stop_fan_control()
                logger.info("Fan control stopped")
            except Exception:
                logger.debug("Error stopping fan control")
            try:
                await sleep_mode.stop_sleep_manager()
                logger.info("Sleep mode service stopped")
            except Exception:
                logger.debug("Error stopping sleep mode service")
    except Exception:
        logger.debug("Error while stopping background services")

    # Shutdown upload managers
    try:
        from app.services.upload_progress import get_upload_progress_manager
        await get_upload_progress_manager().shutdown()
    except Exception:
        logger.debug("Upload progress manager shutdown skipped or failed")

    try:
        from app.services.files.chunked_upload import get_chunked_upload_manager
        await get_chunked_upload_manager().shutdown()
    except Exception:
        logger.debug("Chunked upload manager shutdown skipped or failed")

    # Stop DNS query collector
    try:
        from app.services.pihole.query_collector import get_dns_query_collector
        await get_dns_query_collector().stop()
    except Exception:
        logger.debug("DNS query collector shutdown skipped or failed")

    # Stop network discovery
    if _discovery_service:
        _discovery_service.stop()

    # Shutdown plugin system
    if _plugin_manager:
        try:
            _plugin_manager.emit_hook("on_system_shutdown")
            await _plugin_manager.shutdown_all()
            logger.info("Plugin system shut down")
        except Exception:
            logger.debug("Error while shutting down plugin system")


# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - startup/shutdown hook
    # Allow tests to skip full app initialization by setting SKIP_APP_INIT=1
    skip_init = os.environ.get('SKIP_APP_INIT') == '1'
    if skip_init:
        logger.info('SKIP_APP_INIT set; skipping full app startup (tests)')
        try:
            yield
        finally:
            pass
        return

    await _startup(app)

    try:
        yield
    finally:
        await _shutdown()
