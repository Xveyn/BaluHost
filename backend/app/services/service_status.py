"""
Service Status Collector.

Aggregates status information from all background services for the admin
debugging dashboard. Provides unified access to service health, dependencies,
and application metrics.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any

import psutil

from app.core.config import settings
from app.schemas.service_status import (
    ServiceStateEnum,
    ServiceStatusResponse,
    DependencyStatusResponse,
    ApplicationMetricsResponse,
    AdminDebugResponse,
    DbPoolStatus,
    CacheStatsResponse,
    ServiceRestartResponse,
    ServiceStopResponse,
    ServiceStartResponse,
)

logger = logging.getLogger(__name__)

# Server start time for uptime calculation
_SERVER_START_TIME: Optional[float] = None


def set_server_start_time() -> None:
    """Set the server start time. Call this during app startup."""
    global _SERVER_START_TIME
    _SERVER_START_TIME = time.time()


def get_server_uptime() -> float:
    """Get server uptime in seconds."""
    if _SERVER_START_TIME is None:
        return 0.0
    return time.time() - _SERVER_START_TIME


# Service registry - maps service name to status getter and restart functions
_service_registry: Dict[str, Dict[str, Any]] = {}


def register_service(
    name: str,
    display_name: str,
    get_status_fn: Callable[[], Dict[str, Any]],
    restart_fn: Optional[Callable[[], Any]] = None,
    stop_fn: Optional[Callable[[], Any]] = None,
    start_fn: Optional[Callable[[], Any]] = None,
    config_enabled_fn: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Register a service for status monitoring.

    Args:
        name: Service identifier (e.g., 'telemetry_monitor')
        display_name: Human-readable name (e.g., 'Telemetry Monitor')
        get_status_fn: Function that returns service status dict
        restart_fn: Optional function to restart the service
        stop_fn: Optional function to stop the service
        start_fn: Optional function to start the service
        config_enabled_fn: Optional function to check if service is enabled in config
    """
    _service_registry[name] = {
        "display_name": display_name,
        "get_status": get_status_fn,
        "restart": restart_fn,
        "stop": stop_fn,
        "start": start_fn,
        "config_enabled": config_enabled_fn,
    }
    logger.debug(f"Registered service: {name}")


def unregister_service(name: str) -> None:
    """Unregister a service from monitoring."""
    if name in _service_registry:
        del _service_registry[name]
        logger.debug(f"Unregistered service: {name}")


class ServiceStatusCollector:
    """Aggregates status from all registered background services."""

    def __init__(self):
        self._db_engine = None
        self._service_locks: Dict[str, asyncio.Lock] = {}

    def set_db_engine(self, engine) -> None:
        """Set the database engine for connection pool monitoring."""
        self._db_engine = engine

    def _get_service_lock(self, service_name: str) -> asyncio.Lock:
        """
        Get or create a lock for a specific service.

        Ensures only one control operation (start/stop/restart) can run
        at a time for each service.
        """
        if service_name not in self._service_locks:
            self._service_locks[service_name] = asyncio.Lock()
        return self._service_locks[service_name]

    def get_all_services(self) -> List[ServiceStatusResponse]:
        """
        Get status for all registered services.

        Returns:
            List of ServiceStatusResponse objects
        """
        services = []

        for name, registry in _service_registry.items():
            try:
                status_fn = registry.get("get_status")
                if status_fn is None:
                    continue

                # Call the status function
                status_data = status_fn()

                # Determine state
                state = ServiceStateEnum.RUNNING
                if status_data.get("is_running") is False:
                    state = ServiceStateEnum.STOPPED
                elif status_data.get("has_error"):
                    state = ServiceStateEnum.ERROR

                # Check if service is enabled in config
                config_enabled = True
                config_enabled_fn = registry.get("config_enabled")
                if config_enabled_fn:
                    config_enabled = config_enabled_fn()

                if not config_enabled:
                    state = ServiceStateEnum.DISABLED

                # Build response
                service_response = ServiceStatusResponse(
                    name=name,
                    display_name=registry["display_name"],
                    state=state,
                    started_at=status_data.get("started_at"),
                    uptime_seconds=status_data.get("uptime_seconds"),
                    sample_count=status_data.get("sample_count"),
                    error_count=status_data.get("error_count", 0),
                    last_error=status_data.get("last_error"),
                    last_error_at=status_data.get("last_error_at"),
                    config_enabled=config_enabled,
                    interval_seconds=status_data.get("interval_seconds"),
                    restartable=registry.get("restart") is not None or (
                        registry.get("stop") is not None and registry.get("start") is not None
                    ),
                )
                services.append(service_response)

            except Exception as e:
                logger.error(f"Error getting status for service {name}: {e}")
                # Return error state for this service
                services.append(ServiceStatusResponse(
                    name=name,
                    display_name=registry.get("display_name", name),
                    state=ServiceStateEnum.ERROR,
                    error_count=1,
                    last_error=str(e),
                    last_error_at=datetime.utcnow(),
                    config_enabled=True,
                    restartable=False,
                ))

        return services

    def get_service(self, name: str) -> Optional[ServiceStatusResponse]:
        """
        Get status for a specific service.

        Args:
            name: Service identifier

        Returns:
            ServiceStatusResponse or None if service not found
        """
        if name not in _service_registry:
            return None

        services = self.get_all_services()
        for service in services:
            if service.name == name:
                return service
        return None

    async def restart_service(self, name: str, force: bool = False) -> ServiceRestartResponse:
        """
        Restart a specific service.

        Args:
            name: Service identifier
            force: Force restart even if service appears healthy

        Returns:
            ServiceRestartResponse with result
        """
        if name not in _service_registry:
            return ServiceRestartResponse(
                success=False,
                service_name=name,
                previous_state=ServiceStateEnum.STOPPED,
                current_state=ServiceStateEnum.STOPPED,
                message=f"Service '{name}' not found",
            )

        # Acquire lock to prevent concurrent operations on this service
        async with self._get_service_lock(name):
            registry = _service_registry[name]

            # Get current state
            current_service = self.get_service(name)
            previous_state = current_service.state if current_service else ServiceStateEnum.STOPPED

            # Check if restartable
            restart_fn = registry.get("restart")
            stop_fn = registry.get("stop")
            start_fn = registry.get("start")

            if restart_fn is None and (stop_fn is None or start_fn is None):
                return ServiceRestartResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=previous_state,
                    message=f"Service '{name}' is not restartable",
                )

            try:
                # Use dedicated restart function if available
                if restart_fn:
                    result = restart_fn()
                    if asyncio.iscoroutine(result):
                        await result
                else:
                    # Stop then start
                    if stop_fn:
                        result = stop_fn()
                        if asyncio.iscoroutine(result):
                            await result

                    # Small delay between stop and start
                    await asyncio.sleep(0.5)

                    if start_fn:
                        result = start_fn()
                        if asyncio.iscoroutine(result):
                            await result

                # Get new state
                await asyncio.sleep(0.5)  # Allow service to stabilize
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.STOPPED

                logger.info(f"Service '{name}' restarted: {previous_state} -> {new_state}")

                return ServiceRestartResponse(
                    success=True,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message="Service restarted successfully",
                )

            except Exception as e:
                logger.error(f"Error restarting service {name}: {e}")
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.ERROR

                return ServiceRestartResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message=str(e),
                )

    async def stop_service(self, name: str, force: bool = False) -> ServiceStopResponse:
        """
        Stop a specific service.

        Args:
            name: Service identifier
            force: Force stop even if service appears healthy

        Returns:
            ServiceStopResponse with result
        """
        if name not in _service_registry:
            return ServiceStopResponse(
                success=False,
                service_name=name,
                previous_state=ServiceStateEnum.STOPPED,
                current_state=ServiceStateEnum.STOPPED,
                message=f"Service '{name}' not found",
            )

        # Acquire lock to prevent concurrent operations on this service
        async with self._get_service_lock(name):
            registry = _service_registry[name]

            # Get current state
            current_service = self.get_service(name)
            previous_state = current_service.state if current_service else ServiceStateEnum.STOPPED

            # Check if stoppable
            stop_fn = registry.get("stop")
            if stop_fn is None:
                return ServiceStopResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=previous_state,
                    message=f"Service '{name}' does not support stop operation",
                )

            try:
                # Call stop function
                result = stop_fn()
                if asyncio.iscoroutine(result):
                    await result

                # Get new state
                await asyncio.sleep(0.5)  # Allow service to stabilize
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.STOPPED

                logger.info(f"Service '{name}' stopped: {previous_state} -> {new_state}")

                return ServiceStopResponse(
                    success=True,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message="Service stopped successfully",
                )

            except Exception as e:
                logger.error(f"Error stopping service {name}: {e}")
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.ERROR

                return ServiceStopResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message=str(e),
                )

    async def start_service(self, name: str, force: bool = False) -> ServiceStartResponse:
        """
        Start a specific service.

        Args:
            name: Service identifier
            force: Force start even if service appears running

        Returns:
            ServiceStartResponse with result
        """
        if name not in _service_registry:
            return ServiceStartResponse(
                success=False,
                service_name=name,
                previous_state=ServiceStateEnum.STOPPED,
                current_state=ServiceStateEnum.STOPPED,
                message=f"Service '{name}' not found",
            )

        # Acquire lock to prevent concurrent operations on this service
        async with self._get_service_lock(name):
            registry = _service_registry[name]

            # Get current state
            current_service = self.get_service(name)
            previous_state = current_service.state if current_service else ServiceStateEnum.STOPPED

            # Check if startable
            start_fn = registry.get("start")
            if start_fn is None:
                return ServiceStartResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=previous_state,
                    message=f"Service '{name}' does not support start operation",
                )

            try:
                # Call start function
                result = start_fn()
                if asyncio.iscoroutine(result):
                    await result

                # Get new state
                await asyncio.sleep(0.5)  # Allow service to stabilize
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.STOPPED

                logger.info(f"Service '{name}' started: {previous_state} -> {new_state}")

                return ServiceStartResponse(
                    success=True,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message="Service started successfully",
                )

            except Exception as e:
                logger.error(f"Error starting service {name}: {e}")
                new_service = self.get_service(name)
                new_state = new_service.state if new_service else ServiceStateEnum.ERROR

                return ServiceStartResponse(
                    success=False,
                    service_name=name,
                    previous_state=previous_state,
                    current_state=new_state,
                    message=str(e),
                )

    def get_dependencies(self) -> List[DependencyStatusResponse]:
        """
        Check availability of system dependencies.

        Returns:
            List of DependencyStatusResponse objects
        """
        dependencies = []

        # smartctl - SMART disk health
        smartctl_path = shutil.which("smartctl")
        dependencies.append(DependencyStatusResponse(
            name="smartctl",
            available=smartctl_path is not None,
            path=smartctl_path,
            version=self._get_tool_version(smartctl_path, ["--version"]) if smartctl_path else None,
            required_for=["SMART Disk Health", "Disk Monitoring"],
        ))

        # mdadm - RAID management
        mdadm_path = shutil.which("mdadm")
        dependencies.append(DependencyStatusResponse(
            name="mdadm",
            available=mdadm_path is not None,
            path=mdadm_path,
            version=self._get_tool_version(mdadm_path, ["--version"]) if mdadm_path else None,
            required_for=["RAID Management"],
        ))

        # wg (WireGuard) - VPN
        wg_path = shutil.which("wg")
        dependencies.append(DependencyStatusResponse(
            name="wg",
            available=wg_path is not None,
            path=wg_path,
            version=self._get_tool_version(wg_path, ["--version"]) if wg_path else None,
            required_for=["VPN Configuration"],
        ))

        # ipmitool - Fan control (optional)
        ipmitool_path = shutil.which("ipmitool")
        dependencies.append(DependencyStatusResponse(
            name="ipmitool",
            available=ipmitool_path is not None,
            path=ipmitool_path,
            version=self._get_tool_version(ipmitool_path, ["-V"]) if ipmitool_path else None,
            required_for=["IPMI Fan Control (optional)"],
        ))

        # hwmon/sysfs - Temperature sensors
        hwmon_available = Path("/sys/class/hwmon").exists()
        dependencies.append(DependencyStatusResponse(
            name="hwmon",
            available=hwmon_available,
            path="/sys/class/hwmon" if hwmon_available else None,
            version=None,
            required_for=["Temperature Sensors", "Fan Control"],
        ))

        # cpufreq - CPU frequency scaling
        cpufreq_available = Path("/sys/devices/system/cpu/cpu0/cpufreq").exists()
        dependencies.append(DependencyStatusResponse(
            name="cpufreq",
            available=cpufreq_available,
            path="/sys/devices/system/cpu/cpu0/cpufreq" if cpufreq_available else None,
            version=None,
            required_for=["CPU Power Management"],
        ))

        return dependencies

    def _get_tool_version(self, path: str, args: List[str]) -> Optional[str]:
        """Get version string for a tool."""
        if not path:
            return None

        import subprocess
        try:
            result = subprocess.run(
                [path] + args,
                capture_output=True,
                text=True,
                timeout=5
            )
            output = result.stdout or result.stderr
            # Extract first line which usually contains version
            if output:
                first_line = output.strip().split("\n")[0]
                return first_line[:100]  # Limit length
        except Exception:
            pass
        return None

    def get_app_metrics(self) -> ApplicationMetricsResponse:
        """
        Get application-level metrics.

        Returns:
            ApplicationMetricsResponse with current metrics
        """
        # Import error counter
        from app.middleware.error_counter import get_error_counts

        # Get error counts
        error_4xx, error_5xx = get_error_counts()

        # Get active asyncio tasks
        try:
            active_tasks = len(asyncio.all_tasks())
        except RuntimeError:
            active_tasks = 0

        # Get process memory
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_bytes = memory_info.rss
            memory_percent = process.memory_percent()
        except Exception:
            memory_bytes = 0
            memory_percent = 0.0

        # Get DB pool status
        db_pool_status = None
        if self._db_engine is not None:
            try:
                pool = self._db_engine.pool
                db_pool_status = DbPoolStatus(
                    pool_size=pool.size(),
                    checked_in=pool.checkedin(),
                    checked_out=pool.checkedout(),
                    overflow=pool.overflow(),
                )
            except Exception:
                pass

        # Collect cache stats from services that have them
        cache_stats = []
        # SMART cache
        try:
            from app.services import smart
            if hasattr(smart, 'get_cache_stats'):
                stats = smart.get_cache_stats()
                if stats:
                    cache_stats.append(CacheStatsResponse(
                        name="smart_cache",
                        hits=stats.get("hits", 0),
                        misses=stats.get("misses", 0),
                        size=stats.get("size", 0),
                        max_size=stats.get("max_size"),
                    ))
        except Exception:
            pass

        # RAID cache
        try:
            from app.services import raid
            if hasattr(raid, 'get_cache_stats'):
                stats = raid.get_cache_stats()
                if stats:
                    cache_stats.append(CacheStatsResponse(
                        name="raid_cache",
                        hits=stats.get("hits", 0),
                        misses=stats.get("misses", 0),
                        size=stats.get("size", 0),
                        max_size=stats.get("max_size"),
                    ))
        except Exception:
            pass

        return ApplicationMetricsResponse(
            server_uptime_seconds=get_server_uptime(),
            error_count_4xx=error_4xx,
            error_count_5xx=error_5xx,
            active_tasks=active_tasks,
            memory_bytes=memory_bytes,
            memory_percent=round(memory_percent, 2),
            db_pool_status=db_pool_status,
            cache_stats=cache_stats,
        )

    def get_debug_snapshot(self) -> AdminDebugResponse:
        """
        Get combined debug snapshot for admin dashboard.

        Returns:
            AdminDebugResponse with all status information
        """
        return AdminDebugResponse(
            timestamp=datetime.utcnow(),
            services=self.get_all_services(),
            dependencies=self.get_dependencies(),
            metrics=self.get_app_metrics(),
        )


# Singleton instance
_collector: Optional[ServiceStatusCollector] = None


def get_service_status_collector() -> ServiceStatusCollector:
    """Get the singleton ServiceStatusCollector instance."""
    global _collector
    if _collector is None:
        _collector = ServiceStatusCollector()
    return _collector
