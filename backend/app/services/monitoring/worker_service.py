"""
Monitoring Worker — runs the 4 monitoring services in a dedicated process.

Services managed:
- Telemetry (CPU/Memory/Network, 3s interval)
- Disk I/O Monitor (per-disk, 1s interval)
- Monitoring Orchestrator (collectors, 5s interval, DB persistence)
- Power Monitor (Tapo devices, 5s interval, DB persistence)

Communicates with web workers via /dev/shm/baluhost/ (atomic JSON files).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from app.services.monitoring.shm import (
    TELEMETRY_FILE,
    DISK_IO_FILE,
    POWER_MONITOR_FILE,
    ORCHESTRATOR_STATUS_FILE,
    ORCHESTRATOR_DATA_FILE,
    HEARTBEAT_FILE,
    write_shm,
    read_command,
    cleanup_shm,
)
from app.plugins.smart_device.poller import SmartDevicePoller

logger = logging.getLogger(__name__)

# Heartbeat interval (seconds)
_HEARTBEAT_INTERVAL = 10.0

# SHM snapshot intervals (seconds)
_TELEMETRY_SNAPSHOT_INTERVAL = 3.0
_DISK_IO_SNAPSHOT_INTERVAL = 1.0
_POWER_SNAPSHOT_INTERVAL = 5.0  # unused, kept for reference
_ORCHESTRATOR_SNAPSHOT_INTERVAL = 5.0
_ORCHESTRATOR_DATA_SNAPSHOT_INTERVAL = 5.0
_COMMAND_POLL_INTERVAL = 2.0
_SMART_DEVICES_SNAPSHOT_INTERVAL = 5.0


class MonitoringWorker:
    """
    Dedicated monitoring worker process.

    Starts all 4 monitoring services in an asyncio event loop and periodically
    writes snapshots to SHM for the web workers to read.
    """

    def __init__(self) -> None:
        self._running = False
        self._paused = False
        self._db_session_factory: Optional[Callable] = None
        self._services_started = False
        self._started_at: Optional[float] = None
        self._smart_device_poller: Optional[SmartDevicePoller] = None

    @property
    def running(self) -> bool:
        return self._running

    async def start(self, db_session_factory: Callable) -> None:
        """
        Start all monitoring services.

        Args:
            db_session_factory: SQLAlchemy session factory for DB access
        """
        self._db_session_factory = db_session_factory
        self._running = True
        self._started_at = time.time()

        logger.info("MonitoringWorker starting services...")

        # Start telemetry
        from app.services import telemetry
        await telemetry.start_telemetry_monitor()
        logger.info("Telemetry monitor started")

        # Start disk I/O monitor
        from app.services import disk_monitor
        disk_monitor.start_monitoring()
        logger.info("Disk I/O monitor started")

        # Start monitoring orchestrator
        from app.services.monitoring.orchestrator import start_monitoring
        await start_monitoring(db_session_factory)
        logger.info("Monitoring orchestrator started")

        # Start smart device poller (handles all device polling including power monitoring)
        try:
            self._smart_device_poller = SmartDevicePoller()
            await self._smart_device_poller.start(db_session_factory)
            logger.info("Smart device poller started")
        except Exception as exc:
            logger.warning("Smart device poller could not start: %s", exc)
            self._smart_device_poller = None

        self._services_started = True
        logger.info("All monitoring services started")

    async def run_loop(self) -> None:
        """
        Main loop: write SHM snapshots and process commands.

        Runs until shutdown() is called.
        """
        last_heartbeat = 0.0
        last_telemetry = 0.0
        last_disk_io = 0.0
        last_power = 0.0
        last_orchestrator = 0.0
        last_orchestrator_data = 0.0
        last_command_poll = 0.0
        last_smart_devices = 0.0

        while self._running:
            now = time.time()

            try:
                if not self._paused:
                    # Write telemetry snapshot
                    if now - last_telemetry >= _TELEMETRY_SNAPSHOT_INTERVAL:
                        self._write_telemetry_snapshot()
                        last_telemetry = now

                    # Write disk I/O snapshot
                    if now - last_disk_io >= _DISK_IO_SNAPSHOT_INTERVAL:
                        self._write_disk_io_snapshot()
                        last_disk_io = now

                    # Write orchestrator status snapshot
                    if now - last_orchestrator >= _ORCHESTRATOR_SNAPSHOT_INTERVAL:
                        self._write_orchestrator_snapshot()
                        last_orchestrator = now

                    # Write orchestrator collector data snapshot
                    if now - last_orchestrator_data >= _ORCHESTRATOR_DATA_SNAPSHOT_INTERVAL:
                        self._write_orchestrator_data_snapshot()
                        last_orchestrator_data = now

                    # Write smart devices snapshot
                    if now - last_smart_devices >= _SMART_DEVICES_SNAPSHOT_INTERVAL:
                        self._write_smart_devices_snapshot()
                        last_smart_devices = now

                # Write heartbeat (always, even when paused)
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    self._write_heartbeat()
                    last_heartbeat = now

                # Poll for commands
                if now - last_command_poll >= _COMMAND_POLL_INTERVAL:
                    await self._process_commands()
                    last_command_poll = now

            except Exception as exc:
                logger.error("MonitoringWorker loop error: %s", exc, exc_info=True)

            await asyncio.sleep(0.5)

    async def shutdown(self) -> None:
        """Stop all monitoring services and clean up."""
        logger.info("MonitoringWorker shutting down...")
        self._running = False

        if self._services_started:
            # Stop services in reverse order
            try:
                if self._smart_device_poller is not None:
                    await self._smart_device_poller.stop()
            except Exception as exc:
                logger.debug("Error stopping smart device poller: %s", exc)

            try:
                from app.services.monitoring.orchestrator import stop_monitoring
                await stop_monitoring()
            except Exception as exc:
                logger.debug("Error stopping orchestrator: %s", exc)

            try:
                from app.services import disk_monitor
                disk_monitor.stop_monitoring()
            except Exception as exc:
                logger.debug("Error stopping disk I/O monitor: %s", exc)

            try:
                from app.services import telemetry
                await telemetry.stop_telemetry_monitor()
            except Exception as exc:
                logger.debug("Error stopping telemetry: %s", exc)

            self._services_started = False

        cleanup_shm()
        logger.info("MonitoringWorker shutdown complete")

    # ===== SHM Snapshot Writers =====

    def _write_telemetry_snapshot(self) -> None:
        """Write current telemetry data to SHM."""
        try:
            from app.services import telemetry

            history = telemetry.get_history()
            latest_cpu = telemetry.get_latest_cpu_usage()
            latest_memory = telemetry.get_latest_memory_sample()

            data = {
                "cpu": [s.model_dump() for s in history.cpu],
                "memory": [s.model_dump() for s in history.memory],
                "network": [s.model_dump() for s in history.network],
                "latest_cpu_usage": latest_cpu,
                "latest_memory_sample": latest_memory.model_dump() if latest_memory else None,
                "timestamp": time.time(),
            }
            write_shm(TELEMETRY_FILE, data)
        except Exception as exc:
            logger.debug("Telemetry snapshot failed: %s", exc)

    def _write_disk_io_snapshot(self) -> None:
        """Write current disk I/O data to SHM."""
        try:
            from app.services import disk_monitor

            data = {
                "history": disk_monitor.get_disk_io_history(),
                "available_disks": disk_monitor.get_available_disks(),
                "latest": disk_monitor.get_latest_disk_io(),
                "timestamp": time.time(),
            }
            write_shm(DISK_IO_FILE, data)
        except Exception as exc:
            logger.debug("Disk I/O snapshot failed: %s", exc)

    def _write_orchestrator_snapshot(self) -> None:
        """Write orchestrator status to SHM."""
        try:
            from app.services.monitoring.orchestrator import get_status
            data = get_status()
            data["timestamp"] = time.time()
            write_shm(ORCHESTRATOR_STATUS_FILE, data)
        except Exception as exc:
            logger.debug("Orchestrator snapshot failed: %s", exc)

    def _write_orchestrator_data_snapshot(self) -> None:
        """Write orchestrator collector data (current + history) to SHM."""
        try:
            from app.services.monitoring.orchestrator import get_monitoring_orchestrator

            orch = get_monitoring_orchestrator()

            # Current values
            cpu_cur = orch.get_cpu_current()
            mem_cur = orch.get_memory_current()
            net_cur = orch.get_network_current()
            disk_io_cur = orch.get_disk_io_current()

            # History buffers
            cpu_hist = orch.get_cpu_history()
            mem_hist = orch.get_memory_history()
            net_hist = orch.get_network_history()
            disk_io_hist = orch.get_disk_io_history()

            # Interface type
            interface_type = orch.network_collector.get_active_interface_type()

            # Available disks
            available_disks = orch.disk_io_collector.get_available_disks()

            # Serialize via model_dump(mode="json") for datetime handling
            data = {
                "cpu_current": cpu_cur.model_dump(mode="json") if cpu_cur else None,
                "memory_current": mem_cur.model_dump(mode="json") if mem_cur else None,
                "network_current": net_cur.model_dump(mode="json") if net_cur else None,
                "disk_io_current": {
                    disk: s.model_dump(mode="json") if s else None
                    for disk, s in disk_io_cur.items()
                } if disk_io_cur else {},
                "cpu_history": [s.model_dump(mode="json") for s in cpu_hist],
                "memory_history": [s.model_dump(mode="json") for s in mem_hist],
                "network_history": [s.model_dump(mode="json") for s in net_hist],
                "disk_io_history": {
                    disk: [s.model_dump(mode="json") for s in samples]
                    for disk, samples in disk_io_hist.items()
                } if isinstance(disk_io_hist, dict) else {},
                "available_disks": available_disks,
                "interface_type": interface_type,
                "timestamp": time.time(),
            }
            write_shm(ORCHESTRATOR_DATA_FILE, data)
        except Exception as exc:
            logger.debug("Orchestrator data snapshot failed: %s", exc)

    def _write_smart_devices_snapshot(self) -> None:
        """Write current smart devices snapshot to SHM (if poller is running)."""
        if self._smart_device_poller is None:
            return
        try:
            # The poller writes its own SHM files during each poll loop; this
            # method provides an additional periodic flush in case the poller's
            # own write was skipped (e.g. no active devices).
            self._smart_device_poller._write_shm_snapshot()
        except Exception as exc:
            logger.debug("Smart devices snapshot failed: %s", exc)

    def _write_heartbeat(self) -> None:
        """Write heartbeat to SHM and service status to DB."""
        try:
            services = [
                "telemetry_monitor",
                "disk_io_monitor",
                "monitoring_orchestrator",
                "smart_device_poller",
            ]

            data = {
                "alive": True,
                "pid": os.getpid(),
                "paused": self._paused,
                "started_at": self._started_at,
                "services": services,
                "timestamp": time.time(),
            }
            write_shm(HEARTBEAT_FILE, data)
        except Exception as exc:
            logger.debug("Heartbeat SHM write failed: %s", exc)

        # Write service status to DB so web workers (primary + secondary) can
        # read accurate state for the 4 monitoring services on the dashboard.
        self._write_service_heartbeats_to_db()

    def _write_service_heartbeats_to_db(self) -> None:
        """Write monitoring service statuses to service_heartbeats table."""
        import json
        from app.models.service_heartbeat import ServiceHeartbeat
        from app.core.database import SessionLocal

        # Collect in-process status from each service (they run in this worker)
        service_status: dict[str, dict] = {}
        try:
            from app.services import telemetry
            service_status["telemetry_monitor"] = telemetry.get_status()
        except Exception:
            service_status["telemetry_monitor"] = {"is_running": False}

        try:
            from app.services import disk_monitor
            service_status["disk_io_monitor"] = disk_monitor.get_status()
        except Exception:
            service_status["disk_io_monitor"] = {"is_running": False}

        try:
            from app.services.monitoring.orchestrator import get_status as orch_status
            service_status["monitoring_orchestrator"] = orch_status()
        except Exception:
            service_status["monitoring_orchestrator"] = {"is_running": False}

        try:
            if self._smart_device_poller is not None:
                service_status["smart_device_poller"] = self._smart_device_poller.get_status()
            else:
                service_status["smart_device_poller"] = {"is_running": False}
        except Exception:
            service_status["smart_device_poller"] = {"is_running": False}

        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            for name, status in service_status.items():
                db.merge(ServiceHeartbeat(
                    name=name,
                    is_running=status.get("is_running", False),
                    details_json=json.dumps(status, default=str),
                    updated_at=now,
                ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.debug("Heartbeat DB write failed: %s", exc)
        finally:
            db.close()

    # ===== Command Processing =====

    async def _process_commands(self) -> None:
        """Poll and process commands from the web process."""
        cmd = read_command()
        if cmd is None:
            return

        action = cmd.get("action")
        logger.info("Received command: %s", action)

        if action == "pause_monitoring":
            await self._pause_services(cmd)
        elif action == "resume_monitoring":
            await self._resume_services()
        else:
            logger.warning("Unknown command action: %s", action)

    async def _pause_services(self, cmd: dict) -> None:
        """Pause monitoring services (e.g. for sleep mode)."""
        if self._paused:
            return

        self._paused = True
        pause_monitoring = cmd.get("pause_monitoring", True)
        pause_disk_io = cmd.get("pause_disk_io", True)
        reduced_telemetry_interval = cmd.get("reduced_telemetry_interval")

        if pause_monitoring:
            try:
                from app.services.monitoring.orchestrator import stop_monitoring
                await stop_monitoring()
                logger.info("Paused monitoring orchestrator (sleep mode)")
            except Exception as exc:
                logger.warning("Could not pause orchestrator: %s", exc)

        if pause_disk_io:
            try:
                from app.services import disk_monitor
                disk_monitor.stop_monitoring()
                logger.info("Paused disk I/O monitor (sleep mode)")
            except Exception as exc:
                logger.warning("Could not pause disk I/O monitor: %s", exc)

        if reduced_telemetry_interval:
            try:
                from app.services import telemetry
                await telemetry.stop_telemetry_monitor()
                await telemetry.start_telemetry_monitor(
                    interval_seconds=reduced_telemetry_interval
                )
                logger.info("Telemetry interval reduced to %ss", reduced_telemetry_interval)
            except Exception as exc:
                logger.warning("Could not adjust telemetry interval: %s", exc)

        logger.info("Monitoring services paused for sleep mode")

    async def _resume_services(self) -> None:
        """Resume monitoring services after sleep mode."""
        if not self._paused:
            return

        # Resume telemetry (default interval)
        try:
            from app.services import telemetry
            await telemetry.stop_telemetry_monitor()
            await telemetry.start_telemetry_monitor()
            logger.info("Telemetry interval restored")
        except Exception as exc:
            logger.warning("Could not restore telemetry: %s", exc)

        # Resume disk I/O
        try:
            from app.services import disk_monitor
            disk_monitor.start_monitoring()
            logger.info("Resumed disk I/O monitor")
        except Exception as exc:
            logger.warning("Could not resume disk I/O monitor: %s", exc)

        # Resume orchestrator
        try:
            from app.services.monitoring.orchestrator import start_monitoring
            if self._db_session_factory:
                await start_monitoring(self._db_session_factory)
                logger.info("Resumed monitoring orchestrator")
        except Exception as exc:
            logger.warning("Could not resume orchestrator: %s", exc)

        self._paused = False
        logger.info("Monitoring services resumed")
