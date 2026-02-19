"""
Sleep mode service for BaluHost.

Provides a two-stage sleep system:
- Soft Sleep: Server reachable, CPU on IDLE, services reduced, disks spun down
- True Suspend: systemctl suspend, server unreachable (~1-2W)

Uses a state machine (AWAKE -> SOFT_SLEEP -> TRUE_SUSPEND) with auto-idle
detection, manual controls, and schedule support.
"""
from __future__ import annotations

import abc
import asyncio
import json
import logging
import shutil
import socket
import struct
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func as sa_func, desc

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.sleep import SleepConfig as SleepConfigModel, SleepStateLog
from app.schemas.sleep import (
    SleepState,
    SleepTrigger,
    ScheduleMode,
    ActivityMetrics,
    SleepStatusResponse,
    SleepConfigResponse,
    SleepConfigUpdate,
    SleepCapabilities,
    SleepHistoryEntry,
    SleepHistoryResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend Abstraction
# ---------------------------------------------------------------------------


class SleepBackend(abc.ABC):
    """Abstract backend for sleep mode system operations."""

    @abc.abstractmethod
    async def spindown_disks(self, devices: list[str]) -> list[str]:
        """Spin down given disk devices. Returns list of successfully spun-down devices."""

    @abc.abstractmethod
    async def spinup_disks(self, devices: list[str]) -> list[str]:
        """Spin up given disk devices. Returns list of successfully spun-up devices."""

    @abc.abstractmethod
    async def suspend_system(self) -> bool:
        """Suspend the system. Returns True on success."""

    @abc.abstractmethod
    async def schedule_rtc_wake(self, wake_at: datetime) -> bool:
        """Schedule an RTC wakeup. Returns True on success."""

    @abc.abstractmethod
    async def send_wol_packet(self, mac_address: str, broadcast_address: str) -> bool:
        """Send a Wake-on-LAN magic packet. Returns True on success."""

    @abc.abstractmethod
    async def get_wol_capability(self) -> list[str]:
        """Return list of network interfaces with WoL support."""

    @abc.abstractmethod
    async def get_data_disk_devices(self) -> list[str]:
        """Return list of data disk device paths (excludes OS disk)."""

    @abc.abstractmethod
    async def check_tool_available(self, tool: str) -> bool:
        """Check if a system tool is available (hdparm, rtcwake, systemctl)."""


class DevSleepBackend(SleepBackend):
    """Development backend that simulates all sleep operations in-memory."""

    def __init__(self) -> None:
        self._spun_down: set[str] = set()
        self._suspended = False

    async def spindown_disks(self, devices: list[str]) -> list[str]:
        self._spun_down.update(devices)
        logger.info("[DEV] Simulated disk spindown: %s", devices)
        return devices

    async def spinup_disks(self, devices: list[str]) -> list[str]:
        self._spun_down.discard(*devices) if len(devices) == 1 else self._spun_down.difference_update(devices)
        logger.info("[DEV] Simulated disk spinup: %s", devices)
        return devices

    async def suspend_system(self) -> bool:
        self._suspended = True
        logger.info("[DEV] Simulated system suspend")
        # Simulate waking up after a short delay
        await asyncio.sleep(2)
        self._suspended = False
        logger.info("[DEV] Simulated system wake from suspend")
        return True

    async def schedule_rtc_wake(self, wake_at: datetime) -> bool:
        logger.info("[DEV] Simulated RTC wake scheduled for %s", wake_at.isoformat())
        return True

    async def send_wol_packet(self, mac_address: str, broadcast_address: str) -> bool:
        logger.info("[DEV] Simulated WoL packet sent to %s via %s", mac_address, broadcast_address)
        return True

    async def get_wol_capability(self) -> list[str]:
        return ["eth0"]

    async def get_data_disk_devices(self) -> list[str]:
        return ["/dev/sda", "/dev/sdb"]

    async def check_tool_available(self, tool: str) -> bool:
        return True


class LinuxSleepBackend(SleepBackend):
    """Linux production backend using real system commands."""

    async def _run_cmd(self, cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a subprocess command safely with list args."""
        import subprocess
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out: %s", cmd)
            return False, "timeout"
        except Exception as e:
            logger.warning("Command failed: %s — %s", cmd, e)
            return False, str(e)

    async def spindown_disks(self, devices: list[str]) -> list[str]:
        spun_down = []
        for device in devices:
            ok, output = await self._run_cmd(["hdparm", "-y", device])
            if ok:
                spun_down.append(device)
                logger.info("Disk spindown: %s", device)
            else:
                logger.warning("Failed to spin down %s: %s", device, output)
        return spun_down

    async def spinup_disks(self, devices: list[str]) -> list[str]:
        spun_up = []
        for device in devices:
            # Reading from disk triggers spinup
            ok, output = await self._run_cmd(["hdparm", "-C", device])
            if ok:
                spun_up.append(device)
                logger.info("Disk spinup: %s", device)
            else:
                logger.warning("Failed to spin up %s: %s", device, output)
        return spun_up

    async def suspend_system(self) -> bool:
        ok, output = await self._run_cmd(["sudo", "systemctl", "suspend"], timeout=30)
        if not ok:
            logger.error("System suspend failed: %s", output)
        return ok

    async def schedule_rtc_wake(self, wake_at: datetime) -> bool:
        timestamp = str(int(wake_at.timestamp()))
        ok, output = await self._run_cmd(["sudo", "rtcwake", "-m", "no", "-l", "-t", timestamp])
        if not ok:
            logger.error("RTC wake schedule failed: %s", output)
        return ok

    async def send_wol_packet(self, mac_address: str, broadcast_address: str) -> bool:
        """Send WoL magic packet via raw socket (no subprocess needed)."""
        try:
            mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
            magic = b'\xff' * 6 + mac_bytes * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast_address, 9))
            sock.close()
            logger.info("WoL packet sent to %s via %s", mac_address, broadcast_address)
            return True
        except Exception as e:
            logger.error("Failed to send WoL packet: %s", e)
            return False

    async def get_wol_capability(self) -> list[str]:
        """Check which interfaces support WoL via ethtool."""
        import subprocess
        interfaces = []
        # Get network interface names
        try:
            result = subprocess.run(
                ["ip", "-o", "link", "show"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        iface = parts[1].strip()
                        if iface != "lo":
                            # Check WoL support
                            wol_result = subprocess.run(
                                ["ethtool", iface],
                                capture_output=True, text=True, timeout=5,
                            )
                            if wol_result.returncode == 0 and "Wake-on:" in wol_result.stdout:
                                for wol_line in wol_result.stdout.splitlines():
                                    if "Wake-on:" in wol_line and "d" not in wol_line.split(":")[-1]:
                                        interfaces.append(iface)
                                        break
        except Exception as e:
            logger.warning("Failed to check WoL capability: %s", e)
        return interfaces

    async def get_data_disk_devices(self) -> list[str]:
        """Get data disk devices excluding the OS disk (same pattern as RAID backend)."""
        import subprocess
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINTS"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            os_disk_name: Optional[str] = None
            all_disks: list[str] = []

            def _check_mountpoints(device: dict) -> bool:
                """Recursively check if device or children have root mount."""
                mps = device.get("mountpoints", [])
                if mps and "/" in mps:
                    return True
                for child in device.get("children", []):
                    if _check_mountpoints(child):
                        return True
                return False

            for device in data.get("blockdevices", []):
                if device.get("type") == "disk":
                    name = device["name"]
                    if _check_mountpoints(device):
                        os_disk_name = name
                    else:
                        all_disks.append(f"/dev/{name}")

            if os_disk_name:
                logger.debug("OS disk detected: %s (excluded from spindown)", os_disk_name)

            return all_disks
        except Exception as e:
            logger.warning("Failed to enumerate data disks: %s", e)
            return []

    async def check_tool_available(self, tool: str) -> bool:
        return shutil.which(tool) is not None


# ---------------------------------------------------------------------------
# Sleep Manager Service
# ---------------------------------------------------------------------------

# HTTP request counter for idle detection
_http_request_timestamps: deque[float] = deque(maxlen=600)  # ~10 min of per-request timestamps


def record_http_request() -> None:
    """Record an HTTP request timestamp (called by middleware)."""
    _http_request_timestamps.append(time.monotonic())


def get_http_requests_per_minute() -> float:
    """Calculate HTTP requests per minute over the last 60 seconds."""
    now = time.monotonic()
    cutoff = now - 60.0
    count = sum(1 for t in _http_request_timestamps if t > cutoff)
    return float(count)


class SleepManagerService:
    """
    Manages the server sleep state machine.

    Coordinates power profiles, service pausing, disk spindown, and
    system suspend to implement a two-stage sleep system.
    """

    _instance: Optional["SleepManagerService"] = None
    _lock = asyncio.Lock()

    def __init__(self, backend: SleepBackend) -> None:
        self._backend = backend
        self._current_state = SleepState.AWAKE
        self._state_since: Optional[datetime] = None
        self._idle_seconds: float = 0.0
        self._consecutive_idle_checks: int = 0
        self._paused_services: list[str] = []
        self._spun_down_disks: list[str] = []
        self._original_fan_modes: dict[str, str] = {}
        self._is_running = False
        self._idle_task: Optional[asyncio.Task] = None
        self._schedule_task: Optional[asyncio.Task] = None
        self._escalation_task: Optional[asyncio.Task] = None
        self._soft_sleep_entered_at: Optional[datetime] = None
        self._started_at: Optional[datetime] = None
        self._error_count: int = 0
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None

    @classmethod
    async def get_instance(cls, backend: Optional[SleepBackend] = None) -> "SleepManagerService":
        async with cls._lock:
            if cls._instance is None:
                if backend is None:
                    if settings.is_dev_mode or settings.nas_mode == "dev":
                        backend = DevSleepBackend()
                    else:
                        backend = LinuxSleepBackend()
                cls._instance = cls(backend)
            return cls._instance

    async def start(self) -> None:
        """Start the sleep manager background tasks."""
        if self._is_running:
            return
        self._is_running = True
        self._started_at = datetime.now(timezone.utc)
        self._state_since = datetime.now(timezone.utc)

        # Load config from DB
        config = self._load_config()

        # Start idle detection loop
        self._idle_task = asyncio.create_task(self._idle_detection_loop())

        # Start schedule check loop
        self._schedule_task = asyncio.create_task(self._schedule_check_loop())

        logger.info("Sleep manager started (auto_idle=%s, schedule=%s)",
                     config.auto_idle_enabled if config else False,
                     config.schedule_enabled if config else False)

    async def stop(self) -> None:
        """Stop the sleep manager and restore system to awake state."""
        self._is_running = False

        # Cancel background tasks
        for task in [self._idle_task, self._schedule_task, self._escalation_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # If in soft sleep, wake up before stopping
        if self._current_state == SleepState.SOFT_SLEEP:
            await self._exit_soft_sleep("service_shutdown")

        self._idle_task = None
        self._schedule_task = None
        self._escalation_task = None
        logger.info("Sleep manager stopped")

    def _load_config(self) -> Optional[SleepConfigModel]:
        """Load sleep config from DB (sync, used in background loops)."""
        try:
            db = SessionLocal()
            try:
                config = db.execute(
                    select(SleepConfigModel).where(SleepConfigModel.id == 1)
                ).scalar_one_or_none()
                return config
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to load sleep config: %s", e)
            return None

    def _log_state_change(
        self,
        previous: SleepState,
        new: SleepState,
        reason: str,
        triggered_by: SleepTrigger,
        details: Optional[dict] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Log a state transition to the database."""
        try:
            db = SessionLocal()
            try:
                log_entry = SleepStateLog(
                    previous_state=previous.value,
                    new_state=new.value,
                    reason=reason,
                    triggered_by=triggered_by.value,
                    details_json=json.dumps(details) if details else None,
                    duration_seconds=duration_seconds,
                )
                db.add(log_entry)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to log sleep state change: %s", e)

    def _get_activity_metrics(self) -> ActivityMetrics:
        """Collect current activity metrics from various services."""
        cpu_usage = 0.0
        disk_io = 0.0
        active_uploads = 0
        active_downloads = 0

        try:
            from app.services.telemetry import get_latest_cpu_usage
            cpu = get_latest_cpu_usage()
            if cpu is not None:
                cpu_usage = cpu
        except Exception:
            pass

        try:
            from app.services.disk_monitor import get_latest_io_stats
            io_stats = get_latest_io_stats()
            if io_stats:
                # Sum read + write MB/s across all devices
                for stats in io_stats.values():
                    disk_io += stats.get("read_mbps", 0.0) + stats.get("write_mbps", 0.0)
        except Exception:
            pass

        try:
            from app.services.upload_progress import get_upload_progress_manager
            mgr = get_upload_progress_manager()
            active_uploads = len(mgr.get_all_progress())
        except Exception:
            pass

        http_rpm = get_http_requests_per_minute()

        return ActivityMetrics(
            cpu_usage_avg=cpu_usage,
            disk_io_avg_mbps=disk_io,
            active_uploads=active_uploads,
            active_downloads=active_downloads,
            http_requests_per_minute=http_rpm,
        )

    def _is_system_idle(self, config: SleepConfigModel, metrics: ActivityMetrics) -> bool:
        """Check if system is idle based on thresholds."""
        if metrics.cpu_usage_avg > config.idle_cpu_threshold:
            return False
        if metrics.disk_io_avg_mbps > config.idle_disk_io_threshold:
            return False
        if metrics.active_uploads > 0:
            return False
        if metrics.http_requests_per_minute > config.idle_http_threshold:
            return False
        return True

    async def _idle_detection_loop(self) -> None:
        """Background loop that checks system idle status every 30 seconds."""
        check_interval = 30  # seconds
        while self._is_running:
            try:
                await asyncio.sleep(check_interval)
                if not self._is_running:
                    break

                config = self._load_config()
                if not config or not config.auto_idle_enabled:
                    self._consecutive_idle_checks = 0
                    self._idle_seconds = 0.0
                    continue

                # Only detect idle when AWAKE
                if self._current_state != SleepState.AWAKE:
                    continue

                metrics = self._get_activity_metrics()

                if self._is_system_idle(config, metrics):
                    self._consecutive_idle_checks += 1
                    self._idle_seconds = self._consecutive_idle_checks * check_interval
                    threshold_seconds = config.idle_timeout_minutes * 60

                    if self._idle_seconds >= threshold_seconds:
                        logger.info(
                            "Auto-idle threshold reached (%ds idle, threshold %ds). Entering soft sleep.",
                            self._idle_seconds, threshold_seconds
                        )
                        await self.enter_soft_sleep("auto_idle", SleepTrigger.AUTO_IDLE)
                        self._consecutive_idle_checks = 0
                else:
                    self._consecutive_idle_checks = 0
                    self._idle_seconds = 0.0

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                self._last_error_at = datetime.now(timezone.utc)
                logger.warning("Error in idle detection loop: %s", e)

    async def _schedule_check_loop(self) -> None:
        """Background loop that checks sleep schedule every 60 seconds."""
        while self._is_running:
            try:
                await asyncio.sleep(60)
                if not self._is_running:
                    break

                config = self._load_config()
                if not config or not config.schedule_enabled:
                    continue

                now = datetime.now()
                current_time = now.strftime("%H:%M")

                # Check if it's time to sleep
                if self._current_state == SleepState.AWAKE:
                    if self._time_matches(current_time, config.schedule_sleep_time):
                        mode = config.schedule_mode
                        if mode == "suspend":
                            # Schedule RTC wake first
                            wake_dt = self._next_occurrence(config.schedule_wake_time)
                            await self.enter_true_suspend(
                                "scheduled_suspend",
                                SleepTrigger.SCHEDULE,
                                wake_at=wake_dt,
                            )
                        else:
                            await self.enter_soft_sleep("scheduled_sleep", SleepTrigger.SCHEDULE)

                # Check if it's time to wake
                elif self._current_state == SleepState.SOFT_SLEEP:
                    if self._time_matches(current_time, config.schedule_wake_time):
                        await self.exit_soft_sleep("scheduled_wake")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                self._last_error_at = datetime.now(timezone.utc)
                logger.warning("Error in schedule check loop: %s", e)

    async def _escalation_monitor(self) -> None:
        """Monitor soft sleep duration and escalate to suspend if configured."""
        try:
            config = self._load_config()
            if not config or not config.auto_escalation_enabled:
                return

            wait_seconds = config.escalation_after_minutes * 60
            await asyncio.sleep(wait_seconds)

            if self._current_state == SleepState.SOFT_SLEEP and self._is_running:
                logger.info("Auto-escalation: soft sleep -> true suspend after %d minutes",
                            config.escalation_after_minutes)
                await self.enter_true_suspend(
                    "auto_escalation",
                    SleepTrigger.AUTO_ESCALATION,
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error in escalation monitor: %s", e)

    @staticmethod
    def _time_matches(current: str, target: str) -> bool:
        """Check if current HH:MM matches target HH:MM."""
        return current == target

    @staticmethod
    def _next_occurrence(time_str: str) -> datetime:
        """Get the next datetime for a given HH:MM time string."""
        now = datetime.now()
        hour, minute = map(int, time_str.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # --- Public API ---

    async def enter_soft_sleep(
        self,
        reason: str,
        trigger: SleepTrigger = SleepTrigger.MANUAL,
    ) -> bool:
        """
        Enter soft sleep mode.

        Sequence:
        1. Lock CPU to IDLE profile
        2. Pause configured services
        3. Set fans to silent
        4. Spin down data disks
        5. Log state change
        """
        if self._current_state != SleepState.AWAKE:
            logger.warning("Cannot enter soft sleep from state %s", self._current_state)
            return False

        prev_state = self._current_state
        self._current_state = SleepState.ENTERING_SOFT_SLEEP
        config = self._load_config()

        try:
            # 1. Lock CPU to IDLE profile
            try:
                from app.services.power.manager import get_power_manager
                from app.schemas.power import PowerProfile
                manager = get_power_manager()
                if manager:
                    await manager.register_demand(
                        source="sleep_mode",
                        level=PowerProfile.IDLE,
                        description="System in sleep mode",
                    )
                    logger.info("CPU locked to IDLE profile for sleep mode")
            except Exception as e:
                logger.warning("Could not lock CPU to IDLE: %s", e)

            # 2. Pause services
            paused = []
            if config and config.pause_monitoring:
                try:
                    from app.services.monitoring.orchestrator import stop_monitoring
                    await stop_monitoring()
                    paused.append("monitoring_orchestrator")
                    logger.info("Paused monitoring orchestrator for sleep mode")
                except Exception as e:
                    logger.warning("Could not pause monitoring: %s", e)

            if config and config.pause_disk_io:
                try:
                    from app.services import disk_monitor
                    disk_monitor.stop_monitoring()
                    paused.append("disk_io_monitor")
                    logger.info("Paused disk I/O monitor for sleep mode")
                except Exception as e:
                    logger.warning("Could not pause disk I/O monitor: %s", e)

            # Reduce telemetry interval
            if config:
                try:
                    from app.services import telemetry
                    await telemetry.stop_telemetry_monitor()
                    await telemetry.start_telemetry_monitor(
                        interval_seconds=config.reduced_telemetry_interval
                    )
                    logger.info("Telemetry interval reduced to %ss", config.reduced_telemetry_interval)
                except Exception as e:
                    logger.warning("Could not adjust telemetry interval: %s", e)

            self._paused_services = paused

            # 3. Set fans to silent
            try:
                from app.services.power.fan_control import get_fan_control_service
                fan_service = get_fan_control_service()
                if fan_service and fan_service._is_running:
                    for fan_id, fan_data in fan_service._fans.items():
                        self._original_fan_modes[fan_id] = fan_data.mode
                        await fan_service.apply_preset(fan_id, "silent")
                    logger.info("Fans set to silent for sleep mode")
            except Exception as e:
                logger.warning("Could not set fans to silent: %s", e)

            # 4. Spin down data disks
            if config and config.disk_spindown_enabled:
                try:
                    devices = await self._backend.get_data_disk_devices()
                    if devices:
                        self._spun_down_disks = await self._backend.spindown_disks(devices)
                        logger.info("Spun down %d data disks", len(self._spun_down_disks))
                except Exception as e:
                    logger.warning("Could not spin down disks: %s", e)

            # 5. Finalize state
            self._current_state = SleepState.SOFT_SLEEP
            self._state_since = datetime.now(timezone.utc)
            self._soft_sleep_entered_at = datetime.now(timezone.utc)

            self._log_state_change(
                prev_state, SleepState.SOFT_SLEEP, reason, trigger,
                details={
                    "paused_services": paused,
                    "spun_down_disks": self._spun_down_disks,
                },
            )

            # Start escalation monitor if configured
            if config and config.auto_escalation_enabled:
                self._escalation_task = asyncio.create_task(self._escalation_monitor())

            logger.info("Entered soft sleep (reason=%s, trigger=%s)", reason, trigger.value)
            return True

        except Exception as e:
            self._current_state = SleepState.AWAKE
            self._error_count += 1
            self._last_error = str(e)
            self._last_error_at = datetime.now(timezone.utc)
            logger.error("Failed to enter soft sleep: %s", e)
            return False

    async def exit_soft_sleep(self, reason: str) -> bool:
        """Exit soft sleep and return to awake state (public wrapper)."""
        return await self._exit_soft_sleep(reason)

    async def _exit_soft_sleep(self, reason: str) -> bool:
        """
        Exit soft sleep mode.

        Reverse sequence: spin up disks, resume services, restore telemetry,
        restore fans, remove IDLE lock.
        """
        if self._current_state not in (SleepState.SOFT_SLEEP, SleepState.ENTERING_SOFT_SLEEP):
            logger.warning("Cannot exit soft sleep from state %s", self._current_state)
            return False

        prev_state = self._current_state
        self._current_state = SleepState.WAKING
        config = self._load_config()

        # Cancel escalation monitor
        if self._escalation_task and not self._escalation_task.done():
            self._escalation_task.cancel()
            try:
                await self._escalation_task
            except asyncio.CancelledError:
                pass

        duration = None
        if self._soft_sleep_entered_at:
            duration = (datetime.now(timezone.utc) - self._soft_sleep_entered_at).total_seconds()

        try:
            # 1. Spin up disks
            if self._spun_down_disks:
                try:
                    await self._backend.spinup_disks(self._spun_down_disks)
                    logger.info("Spun up %d data disks", len(self._spun_down_disks))
                except Exception as e:
                    logger.warning("Could not spin up disks: %s", e)
                self._spun_down_disks = []

            # 2. Restore fans
            try:
                from app.services.power.fan_control import get_fan_control_service
                fan_service = get_fan_control_service()
                if fan_service and fan_service._is_running and self._original_fan_modes:
                    for fan_id, original_mode in self._original_fan_modes.items():
                        if original_mode == "auto":
                            await fan_service.set_fan_mode(fan_id, "auto")
                    logger.info("Fan modes restored")
            except Exception as e:
                logger.warning("Could not restore fan modes: %s", e)
            self._original_fan_modes = {}

            # 3. Restore telemetry interval
            if config:
                try:
                    from app.services import telemetry
                    await telemetry.stop_telemetry_monitor()
                    await telemetry.start_telemetry_monitor()  # uses default interval
                    logger.info("Telemetry interval restored")
                except Exception as e:
                    logger.warning("Could not restore telemetry interval: %s", e)

            # 4. Resume services
            if "disk_io_monitor" in self._paused_services:
                try:
                    from app.services import disk_monitor
                    disk_monitor.start_monitoring()
                    logger.info("Resumed disk I/O monitor")
                except Exception as e:
                    logger.warning("Could not resume disk I/O monitor: %s", e)

            if "monitoring_orchestrator" in self._paused_services:
                try:
                    from app.services.monitoring.orchestrator import start_monitoring
                    from app.core.database import get_db
                    await start_monitoring(get_db)
                    logger.info("Resumed monitoring orchestrator")
                except Exception as e:
                    logger.warning("Could not resume monitoring: %s", e)

            self._paused_services = []

            # 5. Remove IDLE lock
            try:
                from app.services.power.manager import get_power_manager
                manager = get_power_manager()
                if manager:
                    await manager.unregister_demand("sleep_mode")
                    logger.info("CPU IDLE lock removed")
            except Exception as e:
                logger.warning("Could not remove CPU IDLE lock: %s", e)

            # Finalize state
            self._current_state = SleepState.AWAKE
            self._state_since = datetime.now(timezone.utc)
            self._soft_sleep_entered_at = None
            self._consecutive_idle_checks = 0
            self._idle_seconds = 0.0

            self._log_state_change(
                prev_state, SleepState.AWAKE, reason, SleepTrigger.AUTO_WAKE,
                duration_seconds=duration,
            )

            logger.info("Exited soft sleep (reason=%s, duration=%ss)", reason, duration)
            return True

        except Exception as e:
            self._current_state = SleepState.AWAKE
            self._error_count += 1
            self._last_error = str(e)
            self._last_error_at = datetime.now(timezone.utc)
            logger.error("Error exiting soft sleep: %s", e)
            return False

    async def enter_true_suspend(
        self,
        reason: str,
        trigger: SleepTrigger = SleepTrigger.MANUAL,
        wake_at: Optional[datetime] = None,
    ) -> bool:
        """
        Enter true suspend (systemctl suspend).

        If currently in soft sleep, stays there.
        If awake, enters soft sleep first.
        Then suspends the system.
        """
        prev_state = self._current_state

        # Enter soft sleep first if awake
        if self._current_state == SleepState.AWAKE:
            ok = await self.enter_soft_sleep(reason, trigger)
            if not ok:
                return False

        self._current_state = SleepState.ENTERING_SUSPEND

        # Schedule RTC wake if requested
        if wake_at:
            try:
                await self._backend.schedule_rtc_wake(wake_at)
                logger.info("RTC wake scheduled for %s", wake_at.isoformat())
            except Exception as e:
                logger.warning("Could not schedule RTC wake: %s", e)

        self._log_state_change(
            SleepState.SOFT_SLEEP, SleepState.TRUE_SUSPEND, reason, trigger,
            details={"wake_at": wake_at.isoformat() if wake_at else None},
        )

        self._current_state = SleepState.TRUE_SUSPEND
        self._state_since = datetime.now(timezone.utc)

        # Actually suspend
        ok = await self._backend.suspend_system()

        # When system resumes, we'll be back here
        if ok:
            logger.info("System resumed from suspend")
            await self._exit_soft_sleep("resume_from_suspend")

        return ok

    async def send_wol(
        self,
        mac_address: Optional[str] = None,
        broadcast_address: Optional[str] = None,
    ) -> bool:
        """Send a Wake-on-LAN magic packet."""
        config = self._load_config()

        mac = mac_address or (config.wol_mac_address if config else None)
        broadcast = broadcast_address or (config.wol_broadcast_address if config else None) or "255.255.255.255"

        if not mac:
            logger.warning("No MAC address configured for WoL")
            return False

        return await self._backend.send_wol_packet(mac, broadcast)

    def get_status(self) -> SleepStatusResponse:
        """Get current sleep mode status."""
        config = self._load_config()
        metrics = self._get_activity_metrics()

        idle_threshold = 0.0
        if config:
            idle_threshold = config.idle_timeout_minutes * 60

        return SleepStatusResponse(
            current_state=self._current_state,
            state_since=self._state_since,
            idle_seconds=self._idle_seconds,
            idle_threshold_seconds=idle_threshold,
            activity_metrics=metrics,
            paused_services=self._paused_services,
            spun_down_disks=self._spun_down_disks,
            auto_idle_enabled=config.auto_idle_enabled if config else False,
            schedule_enabled=config.schedule_enabled if config else False,
            escalation_enabled=config.auto_escalation_enabled if config else False,
        )

    def get_config(self) -> SleepConfigResponse:
        """Get sleep mode configuration."""
        config = self._load_config()
        if not config:
            return SleepConfigResponse()

        return SleepConfigResponse(
            auto_idle_enabled=config.auto_idle_enabled,
            idle_timeout_minutes=config.idle_timeout_minutes,
            idle_cpu_threshold=config.idle_cpu_threshold,
            idle_disk_io_threshold=config.idle_disk_io_threshold,
            idle_http_threshold=config.idle_http_threshold,
            auto_escalation_enabled=config.auto_escalation_enabled,
            escalation_after_minutes=config.escalation_after_minutes,
            schedule_enabled=config.schedule_enabled,
            schedule_sleep_time=config.schedule_sleep_time,
            schedule_wake_time=config.schedule_wake_time,
            schedule_mode=ScheduleMode(config.schedule_mode),
            wol_mac_address=config.wol_mac_address,
            wol_broadcast_address=config.wol_broadcast_address,
            pause_monitoring=config.pause_monitoring,
            pause_disk_io=config.pause_disk_io,
            reduced_telemetry_interval=config.reduced_telemetry_interval,
            disk_spindown_enabled=config.disk_spindown_enabled,
        )

    def update_config(self, update: SleepConfigUpdate) -> SleepConfigResponse:
        """Update sleep mode configuration."""
        try:
            db = SessionLocal()
            try:
                config = db.execute(
                    select(SleepConfigModel).where(SleepConfigModel.id == 1)
                ).scalar_one_or_none()

                if not config:
                    # Create default config
                    config = SleepConfigModel(id=1)
                    db.add(config)

                # Apply partial update
                update_data = update.model_dump(exclude_unset=True)
                for field, value in update_data.items():
                    if value is not None:
                        setattr(config, field, value.value if hasattr(value, 'value') else value)

                db.commit()
                db.refresh(config)
                logger.info("Sleep config updated: %s", list(update_data.keys()))
            finally:
                db.close()
        except Exception as e:
            logger.error("Failed to update sleep config: %s", e)
            raise

        return self.get_config()

    def get_history(self, limit: int = 50, offset: int = 0) -> SleepHistoryResponse:
        """Get sleep state change history."""
        try:
            db = SessionLocal()
            try:
                total = db.execute(
                    select(sa_func.count(SleepStateLog.id))
                ).scalar() or 0

                rows = db.execute(
                    select(SleepStateLog)
                    .order_by(desc(SleepStateLog.timestamp))
                    .limit(limit)
                    .offset(offset)
                ).scalars().all()

                entries = []
                for row in rows:
                    details = None
                    if row.details_json:
                        try:
                            details = json.loads(row.details_json)
                        except json.JSONDecodeError:
                            pass

                    entries.append(SleepHistoryEntry(
                        id=row.id,
                        timestamp=row.timestamp,
                        previous_state=SleepState(row.previous_state),
                        new_state=SleepState(row.new_state),
                        reason=row.reason,
                        triggered_by=SleepTrigger(row.triggered_by),
                        details=details,
                        duration_seconds=row.duration_seconds,
                    ))

                return SleepHistoryResponse(entries=entries, total=total)
            finally:
                db.close()
        except Exception as e:
            logger.error("Failed to get sleep history: %s", e)
            return SleepHistoryResponse()

    async def get_capabilities(self) -> SleepCapabilities:
        """Check system capabilities for sleep features."""
        hdparm = await self._backend.check_tool_available("hdparm")
        rtcwake = await self._backend.check_tool_available("rtcwake")
        systemctl = await self._backend.check_tool_available("systemctl")
        wol_interfaces = await self._backend.get_wol_capability()
        data_disks = await self._backend.get_data_disk_devices()

        can_suspend = systemctl
        if not settings.is_dev_mode:
            # Check if suspend is actually supported
            try:
                import subprocess
                result = subprocess.run(
                    ["systemctl", "can-suspend"],
                    capture_output=True, text=True, timeout=5,
                )
                can_suspend = result.returncode == 0 and "yes" in result.stdout.lower()
            except Exception:
                can_suspend = False

        return SleepCapabilities(
            hdparm_available=hdparm,
            rtcwake_available=rtcwake,
            systemctl_available=systemctl,
            can_suspend=can_suspend,
            wol_interfaces=wol_interfaces,
            data_disk_devices=data_disks,
        )


# ---------------------------------------------------------------------------
# Module-level functions (for main.py wiring)
# ---------------------------------------------------------------------------

_service: Optional[SleepManagerService] = None


def get_sleep_manager() -> Optional[SleepManagerService]:
    """Get the global sleep manager instance."""
    return _service


async def start_sleep_manager() -> None:
    """Initialize and start the sleep manager service."""
    global _service
    _service = await SleepManagerService.get_instance()
    await _service.start()


async def stop_sleep_manager() -> None:
    """Stop the sleep manager service."""
    global _service
    if _service:
        await _service.stop()
        _service = None
        SleepManagerService._instance = None


def get_service_status() -> dict:
    """Get service status for the service registry."""
    if _service is None:
        return {"is_running": False}

    return {
        "is_running": _service._is_running,
        "started_at": _service._started_at.isoformat() if _service._started_at else None,
        "uptime_seconds": (
            (datetime.now(timezone.utc) - _service._started_at).total_seconds()
            if _service._started_at else None
        ),
        "sample_count": 0,
        "error_count": _service._error_count,
        "last_error": _service._last_error,
        "last_error_at": _service._last_error_at.isoformat() if _service._last_error_at else None,
        "interval_seconds": 30.0,
        "current_state": _service._current_state.value,
    }
