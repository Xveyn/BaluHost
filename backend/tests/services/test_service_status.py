"""
Tests for service status collector service.

Tests:
- Service registration and state tracking
- Health checks and dependencies
- Service control (start/stop/restart)
"""
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.service_status import (
    ServiceStateEnum,
    ServiceStatusResponse,
    ServiceRestartResponse,
    ServiceStopResponse,
    ServiceStartResponse,
)
from app.services.service_status import (
    ServiceStatusCollector,
    register_service,
    unregister_service,
    set_server_start_time,
    get_server_uptime,
    _service_registry,
)


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear service registry before and after each test."""
    _service_registry.clear()
    yield
    _service_registry.clear()


@pytest.fixture
def collector():
    """Create a ServiceStatusCollector instance."""
    return ServiceStatusCollector()


class TestServerUptime:
    """Tests for server uptime functions."""

    def test_set_server_start_time(self):
        """Test setting server start time."""
        set_server_start_time()
        uptime = get_server_uptime()

        # Should be very small (just started)
        assert 0 <= uptime < 1.0

    def test_get_server_uptime_increases(self):
        """Test that uptime increases over time."""
        import time
        set_server_start_time()

        uptime1 = get_server_uptime()
        time.sleep(0.1)
        uptime2 = get_server_uptime()

        assert uptime2 > uptime1


class TestServiceRegistration:
    """Tests for service registration functions."""

    def test_register_service_basic(self):
        """Test basic service registration."""
        status_fn = lambda: {"is_running": True}

        register_service(
            name="test_service",
            display_name="Test Service",
            get_status_fn=status_fn,
        )

        assert "test_service" in _service_registry
        assert _service_registry["test_service"]["display_name"] == "Test Service"

    def test_register_service_with_restart(self):
        """Test service registration with restart function."""
        register_service(
            name="restartable",
            display_name="Restartable Service",
            get_status_fn=lambda: {"is_running": True},
            restart_fn=lambda: None,
        )

        assert _service_registry["restartable"]["restart"] is not None

    def test_register_service_with_stop_start(self):
        """Test service registration with stop and start functions."""
        register_service(
            name="controllable",
            display_name="Controllable Service",
            get_status_fn=lambda: {"is_running": True},
            stop_fn=lambda: None,
            start_fn=lambda: None,
        )

        assert _service_registry["controllable"]["stop"] is not None
        assert _service_registry["controllable"]["start"] is not None

    def test_unregister_service(self):
        """Test service unregistration."""
        register_service(
            name="to_remove",
            display_name="Temporary",
            get_status_fn=lambda: {},
        )

        unregister_service("to_remove")

        assert "to_remove" not in _service_registry

    def test_unregister_nonexistent_service(self):
        """Test unregistering non-existent service doesn't raise."""
        # Should not raise
        unregister_service("nonexistent")


class TestServiceStatusCollector:
    """Tests for ServiceStatusCollector class."""

    def test_get_all_services_empty(self, collector):
        """Test getting services when none registered."""
        services = collector.get_all_services()

        assert services == []

    def test_get_all_services_running(self, collector):
        """Test getting running services."""
        register_service(
            name="running_service",
            display_name="Running Service",
            get_status_fn=lambda: {"is_running": True, "uptime_seconds": 100},
        )

        services = collector.get_all_services()

        assert len(services) == 1
        assert services[0].name == "running_service"
        assert services[0].state == ServiceStateEnum.RUNNING
        assert services[0].uptime_seconds == 100

    def test_get_all_services_stopped(self, collector):
        """Test getting stopped services."""
        register_service(
            name="stopped_service",
            display_name="Stopped Service",
            get_status_fn=lambda: {"is_running": False},
        )

        services = collector.get_all_services()

        assert len(services) == 1
        assert services[0].state == ServiceStateEnum.STOPPED

    def test_get_all_services_error(self, collector):
        """Test getting services with errors."""
        register_service(
            name="error_service",
            display_name="Error Service",
            get_status_fn=lambda: {"is_running": True, "has_error": True, "last_error": "Test error"},
        )

        services = collector.get_all_services()

        assert len(services) == 1
        assert services[0].state == ServiceStateEnum.ERROR

    def test_get_all_services_disabled(self, collector):
        """Test getting disabled services."""
        register_service(
            name="disabled_service",
            display_name="Disabled Service",
            get_status_fn=lambda: {"is_running": False},
            config_enabled_fn=lambda: False,
        )

        services = collector.get_all_services()

        assert len(services) == 1
        assert services[0].state == ServiceStateEnum.DISABLED
        assert services[0].config_enabled is False

    def test_get_all_services_handles_exceptions(self, collector):
        """Test that exceptions in status functions are handled."""
        def failing_status():
            raise RuntimeError("Status check failed")

        register_service(
            name="failing_service",
            display_name="Failing Service",
            get_status_fn=failing_status,
        )

        services = collector.get_all_services()

        assert len(services) == 1
        assert services[0].state == ServiceStateEnum.ERROR
        assert "Status check failed" in services[0].last_error

    def test_get_service_found(self, collector):
        """Test getting a specific service."""
        register_service(
            name="specific",
            display_name="Specific Service",
            get_status_fn=lambda: {"is_running": True},
        )

        service = collector.get_service("specific")

        assert service is not None
        assert service.name == "specific"

    def test_get_service_not_found(self, collector):
        """Test getting a non-existent service."""
        service = collector.get_service("nonexistent")

        assert service is None


class TestServiceRestart:
    """Tests for service restart functionality."""

    @pytest.mark.asyncio
    async def test_restart_nonexistent_service(self, collector):
        """Test restarting non-existent service."""
        result = await collector.restart_service("nonexistent")

        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_restart_non_restartable_service(self, collector):
        """Test restarting service without restart function."""
        register_service(
            name="no_restart",
            display_name="No Restart",
            get_status_fn=lambda: {"is_running": True},
        )

        result = await collector.restart_service("no_restart")

        assert result.success is False
        assert "not restartable" in result.message

    @pytest.mark.asyncio
    async def test_restart_with_restart_fn(self, collector):
        """Test restarting with dedicated restart function."""
        restart_called = []

        register_service(
            name="with_restart",
            display_name="With Restart",
            get_status_fn=lambda: {"is_running": True},
            restart_fn=lambda: restart_called.append(True),
        )

        result = await collector.restart_service("with_restart")

        assert result.success is True
        assert len(restart_called) == 1

    @pytest.mark.asyncio
    async def test_restart_with_stop_start(self, collector):
        """Test restarting with stop/start functions."""
        calls = []

        register_service(
            name="stop_start",
            display_name="Stop Start",
            get_status_fn=lambda: {"is_running": True},
            stop_fn=lambda: calls.append("stop"),
            start_fn=lambda: calls.append("start"),
        )

        result = await collector.restart_service("stop_start")

        assert result.success is True
        assert "stop" in calls
        assert "start" in calls

    @pytest.mark.asyncio
    async def test_restart_handles_async_fn(self, collector):
        """Test restarting with async restart function."""
        async def async_restart():
            await asyncio.sleep(0.01)

        register_service(
            name="async_restart",
            display_name="Async Restart",
            get_status_fn=lambda: {"is_running": True},
            restart_fn=async_restart,
        )

        result = await collector.restart_service("async_restart")

        assert result.success is True


class TestServiceStop:
    """Tests for service stop functionality."""

    @pytest.mark.asyncio
    async def test_stop_nonexistent_service(self, collector):
        """Test stopping non-existent service."""
        result = await collector.stop_service("nonexistent")

        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_stop_non_stoppable_service(self, collector):
        """Test stopping service without stop function."""
        register_service(
            name="no_stop",
            display_name="No Stop",
            get_status_fn=lambda: {"is_running": True},
        )

        result = await collector.stop_service("no_stop")

        assert result.success is False
        assert "does not support stop" in result.message

    @pytest.mark.asyncio
    async def test_stop_service_success(self, collector):
        """Test successful service stop."""
        is_running = [True]

        def stop_fn():
            is_running[0] = False

        register_service(
            name="stoppable",
            display_name="Stoppable",
            get_status_fn=lambda: {"is_running": is_running[0]},
            stop_fn=stop_fn,
        )

        result = await collector.stop_service("stoppable")

        assert result.success is True
        assert is_running[0] is False


class TestServiceStart:
    """Tests for service start functionality."""

    @pytest.mark.asyncio
    async def test_start_nonexistent_service(self, collector):
        """Test starting non-existent service."""
        result = await collector.start_service("nonexistent")

        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_start_non_startable_service(self, collector):
        """Test starting service without start function."""
        register_service(
            name="no_start",
            display_name="No Start",
            get_status_fn=lambda: {"is_running": False},
        )

        result = await collector.start_service("no_start")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_start_service_success(self, collector):
        """Test successful service start."""
        is_running = [False]

        def start_fn():
            is_running[0] = True

        register_service(
            name="startable",
            display_name="Startable",
            get_status_fn=lambda: {"is_running": is_running[0]},
            start_fn=start_fn,
        )

        result = await collector.start_service("startable")

        assert result.success is True
        assert is_running[0] is True


class TestServiceRestartable:
    """Tests for restartable flag determination."""

    def test_service_with_restart_fn_is_restartable(self, collector):
        """Test that service with restart function is marked restartable."""
        register_service(
            name="has_restart",
            display_name="Has Restart",
            get_status_fn=lambda: {"is_running": True},
            restart_fn=lambda: None,
        )

        services = collector.get_all_services()

        assert services[0].restartable is True

    def test_service_with_stop_start_is_restartable(self, collector):
        """Test that service with stop+start functions is restartable."""
        register_service(
            name="has_stop_start",
            display_name="Has Stop Start",
            get_status_fn=lambda: {"is_running": True},
            stop_fn=lambda: None,
            start_fn=lambda: None,
        )

        services = collector.get_all_services()

        assert services[0].restartable is True

    def test_service_without_restart_not_restartable(self, collector):
        """Test that service without restart function is not restartable."""
        register_service(
            name="no_restart",
            display_name="No Restart",
            get_status_fn=lambda: {"is_running": True},
        )

        services = collector.get_all_services()

        assert services[0].restartable is False

    def test_service_with_only_stop_not_restartable(self, collector):
        """Test that service with only stop is not restartable."""
        register_service(
            name="only_stop",
            display_name="Only Stop",
            get_status_fn=lambda: {"is_running": True},
            stop_fn=lambda: None,
        )

        services = collector.get_all_services()

        assert services[0].restartable is False


class TestServiceLocking:
    """Tests for service operation locking."""

    def test_get_service_lock_creates_new(self, collector):
        """Test that get_service_lock creates new locks."""
        lock1 = collector._get_service_lock("service1")
        lock2 = collector._get_service_lock("service2")

        assert lock1 is not lock2

    def test_get_service_lock_returns_same(self, collector):
        """Test that get_service_lock returns same lock for same service."""
        lock1 = collector._get_service_lock("service1")
        lock2 = collector._get_service_lock("service1")

        assert lock1 is lock2


class TestDbEngine:
    """Tests for database engine setup."""

    def test_set_db_engine(self, collector):
        """Test setting database engine."""
        mock_engine = MagicMock()

        collector.set_db_engine(mock_engine)

        assert collector._db_engine is mock_engine
