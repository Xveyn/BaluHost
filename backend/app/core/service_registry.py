"""
Service registration for the admin status dashboard.

Registers all background services (monitors, schedulers, workers) with the
service status collector so their health is visible in the admin UI.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.services.service_status import register_service, _service_registry

logger = logging.getLogger(__name__)

# Services that run exclusively on the primary worker (or monitoring_worker in prod).
# On secondary workers, their status function is replaced by a DB reader.
PRIMARY_ONLY_SERVICES = [
    "telemetry_monitor",
    "disk_io_monitor",
    "smart_device_poller",
    "monitoring_orchestrator",
    "power_manager",
    "fan_control",
    "sleep_mode",
    "network_discovery",
    "pihole_query_collector",
]

# Monitoring services that are offloaded to monitoring_worker in prod mode.
# In prod, even the primary web worker reads from SHM/DB instead of in-process.
MONITORING_WORKER_SERVICES = [
    "telemetry_monitor",
    "disk_io_monitor",
    "smart_device_poller",
    "monitoring_orchestrator",
]


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


def make_db_status_reader(service_name: str):
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


def register_all_services(
    *,
    is_primary_worker: bool,
    discovery_service,
) -> None:
    """Register all background services with the service status collector.

    Args:
        is_primary_worker: Whether this process is the primary worker.
        discovery_service: The NetworkDiscoveryService instance (or None).
    """
    from app.services import disk_monitor, jobs, telemetry
    from app.services.power import manager as power_manager
    from app.services.power import fan_control
    from app.services.power import sleep as sleep_mode
    from app.services.monitoring.orchestrator import (
        start_monitoring, stop_monitoring,
        get_status as orchestrator_get_status,
    )
    from app.services.notifications.firebase import FirebaseService
    from app.core.database import get_db

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

    # Smart Device Poller (replaces old power monitor)
    def _get_smart_device_poller_status():
        try:
            from app.services.monitoring.shm import read_shm, SMART_DEVICES_FILE
            data = read_shm(SMART_DEVICES_FILE, max_age_seconds=30.0)
            if data:
                return {
                    "is_running": True,
                    "devices_count": len(data.get("devices", {})),
                }
            return {"is_running": False}
        except Exception:
            return {"is_running": False}

    register_service(
        name="smart_device_poller",
        display_name="Smart Device Poller",
        get_status_fn=_get_smart_device_poller_status,
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
        if discovery_service is None:
            return {"is_running": False}
        return discovery_service.get_status()

    register_service(
        name="network_discovery",
        display_name="Network Discovery (mDNS)",
        get_status_fn=_get_network_discovery_status,
        stop_fn=lambda: discovery_service.stop() if discovery_service else None,
        start_fn=lambda: discovery_service.start() if discovery_service else None,
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

        db = _SL()
        try:
            state = db.query(WebdavState).first()
            if state is None:
                return {"is_running": False}
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
        from app.services.scheduler.execution import is_worker_healthy_global
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
        from app.services.monitoring.shm import read_shm, HEARTBEAT_FILE
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
        config_enabled_fn=lambda: True,
    )

    # Pi-hole DNS Query Collector
    def _get_pihole_collector_status():
        from app.services.pihole.query_collector import get_dns_query_collector
        try:
            status = get_dns_query_collector().get_status()
            return {"is_running": status.get("running", False)}
        except Exception:
            return {"is_running": False}

    register_service(
        name="pihole_query_collector",
        display_name="DNS Query Collector",
        get_status_fn=_get_pihole_collector_status,
        config_enabled_fn=lambda: True,
    )

    # On secondary workers: replace in-process status functions for
    # primary-only services with DB readers so the dashboard shows
    # consistent data regardless of which worker handles the request.
    if not is_primary_worker:
        for svc_name in PRIMARY_ONLY_SERVICES:
            if svc_name in _service_registry:
                _service_registry[svc_name]["get_status"] = make_db_status_reader(svc_name)

    # In prod mode, the primary worker also doesn't run monitoring in-process,
    # so it needs DB readers for the 4 monitoring services too.
    if is_primary_worker and not settings.is_dev_mode:
        for svc_name in MONITORING_WORKER_SERVICES:
            if svc_name in _service_registry:
                _service_registry[svc_name]["get_status"] = make_db_status_reader(svc_name)
