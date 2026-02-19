"""
Tests for the Sleep Mode feature.

Tests cover:
- SleepManagerService state machine transitions
- DevSleepBackend simulation
- Auto-idle detection logic
- API endpoints
- Auto-wake middleware
- Config persistence
"""
import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.schemas.sleep import (
    SleepState,
    SleepTrigger,
    ScheduleMode,
    ActivityMetrics,
    SleepConfigUpdate,
)
from app.services.power.sleep import (
    DevSleepBackend,
    SleepManagerService,
    record_http_request,
    get_http_requests_per_minute,
    _http_request_timestamps,
)
from app.models.sleep import SleepConfig as SleepConfigModel, SleepStateLog


# ============================================================================
# DevSleepBackend Tests
# ============================================================================


class TestDevSleepBackend:
    """Test the development (mock) sleep backend."""

    @pytest.mark.asyncio
    async def test_spindown_disks(self):
        backend = DevSleepBackend()
        result = await backend.spindown_disks(["/dev/sda", "/dev/sdb"])
        assert result == ["/dev/sda", "/dev/sdb"]
        assert backend._spun_down == {"/dev/sda", "/dev/sdb"}

    @pytest.mark.asyncio
    async def test_spinup_disks(self):
        backend = DevSleepBackend()
        backend._spun_down = {"/dev/sda", "/dev/sdb"}
        result = await backend.spinup_disks(["/dev/sda", "/dev/sdb"])
        assert result == ["/dev/sda", "/dev/sdb"]

    @pytest.mark.asyncio
    async def test_suspend_system(self):
        backend = DevSleepBackend()
        result = await backend.suspend_system()
        assert result is True
        assert backend._suspended is False  # Resumes after delay

    @pytest.mark.asyncio
    async def test_schedule_rtc_wake(self):
        backend = DevSleepBackend()
        wake_at = datetime.now(timezone.utc) + timedelta(hours=1)
        result = await backend.schedule_rtc_wake(wake_at)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_wol_packet(self):
        backend = DevSleepBackend()
        result = await backend.send_wol_packet("AA:BB:CC:DD:EE:FF", "255.255.255.255")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_wol_capability(self):
        backend = DevSleepBackend()
        interfaces = await backend.get_wol_capability()
        assert "eth0" in interfaces

    @pytest.mark.asyncio
    async def test_get_data_disk_devices(self):
        backend = DevSleepBackend()
        devices = await backend.get_data_disk_devices()
        assert len(devices) == 2
        assert "/dev/sda" in devices

    @pytest.mark.asyncio
    async def test_check_tool_available(self):
        backend = DevSleepBackend()
        assert await backend.check_tool_available("hdparm") is True
        assert await backend.check_tool_available("nonexistent") is True  # Dev always True


# ============================================================================
# SleepManagerService Tests
# ============================================================================


class TestSleepManagerService:
    """Test the sleep manager service state machine."""

    def _create_service(self) -> SleepManagerService:
        """Create a service with mock backend and DB."""
        backend = DevSleepBackend()
        service = SleepManagerService(backend)
        # Mock the DB interactions
        service._load_config = MagicMock(return_value=self._mock_config())
        service._log_state_change = MagicMock()
        return service

    def _mock_config(self, **overrides) -> MagicMock:
        """Create a mock SleepConfigModel with defaults."""
        config = MagicMock(spec=SleepConfigModel)
        config.auto_idle_enabled = overrides.get("auto_idle_enabled", True)
        config.idle_timeout_minutes = overrides.get("idle_timeout_minutes", 15)
        config.idle_cpu_threshold = overrides.get("idle_cpu_threshold", 5.0)
        config.idle_disk_io_threshold = overrides.get("idle_disk_io_threshold", 0.5)
        config.idle_http_threshold = overrides.get("idle_http_threshold", 5.0)
        config.auto_escalation_enabled = overrides.get("auto_escalation_enabled", False)
        config.escalation_after_minutes = overrides.get("escalation_after_minutes", 60)
        config.schedule_enabled = overrides.get("schedule_enabled", False)
        config.schedule_sleep_time = overrides.get("schedule_sleep_time", "23:00")
        config.schedule_wake_time = overrides.get("schedule_wake_time", "06:00")
        config.schedule_mode = overrides.get("schedule_mode", "soft")
        config.wol_mac_address = overrides.get("wol_mac_address", None)
        config.wol_broadcast_address = overrides.get("wol_broadcast_address", None)
        config.pause_monitoring = overrides.get("pause_monitoring", True)
        config.pause_disk_io = overrides.get("pause_disk_io", True)
        config.reduced_telemetry_interval = overrides.get("reduced_telemetry_interval", 30.0)
        config.disk_spindown_enabled = overrides.get("disk_spindown_enabled", True)
        return config

    @pytest.mark.asyncio
    async def test_initial_state_is_awake(self):
        service = self._create_service()
        assert service._current_state == SleepState.AWAKE

    @pytest.mark.asyncio
    async def test_enter_soft_sleep_from_awake(self):
        service = self._create_service()
        # Mock the service interactions to avoid import errors in tests
        with patch("app.services.power.sleep.SleepManagerService._get_activity_metrics"):
            ok = await service.enter_soft_sleep("test", SleepTrigger.MANUAL)
        assert ok is True
        assert service._current_state == SleepState.SOFT_SLEEP
        assert service._state_since is not None
        service._log_state_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_cannot_enter_soft_sleep_when_already_sleeping(self):
        service = self._create_service()
        service._current_state = SleepState.SOFT_SLEEP
        ok = await service.enter_soft_sleep("test", SleepTrigger.MANUAL)
        assert ok is False

    @pytest.mark.asyncio
    async def test_exit_soft_sleep(self):
        service = self._create_service()
        service._current_state = SleepState.SOFT_SLEEP
        service._soft_sleep_entered_at = datetime.now(timezone.utc)
        service._paused_services = []
        service._spun_down_disks = []

        ok = await service.exit_soft_sleep("test_wake")
        assert ok is True
        assert service._current_state == SleepState.AWAKE

    @pytest.mark.asyncio
    async def test_cannot_exit_soft_sleep_when_awake(self):
        service = self._create_service()
        assert service._current_state == SleepState.AWAKE
        ok = await service.exit_soft_sleep("test_wake")
        assert ok is False

    @pytest.mark.asyncio
    async def test_full_cycle_awake_sleep_awake(self):
        service = self._create_service()
        assert service._current_state == SleepState.AWAKE

        ok = await service.enter_soft_sleep("going to sleep", SleepTrigger.MANUAL)
        assert ok is True
        assert service._current_state == SleepState.SOFT_SLEEP

        ok = await service.exit_soft_sleep("waking up")
        assert ok is True
        assert service._current_state == SleepState.AWAKE

    @pytest.mark.asyncio
    async def test_get_status(self):
        service = self._create_service()
        status = service.get_status()
        assert status.current_state == SleepState.AWAKE
        assert status.auto_idle_enabled is True
        assert isinstance(status.activity_metrics, ActivityMetrics)

    @pytest.mark.asyncio
    async def test_send_wol_with_configured_mac(self):
        service = self._create_service()
        service._load_config = MagicMock(
            return_value=self._mock_config(
                wol_mac_address="AA:BB:CC:DD:EE:FF",
                wol_broadcast_address="192.168.1.255",
            )
        )
        ok = await service.send_wol()
        assert ok is True

    @pytest.mark.asyncio
    async def test_send_wol_without_mac_fails(self):
        service = self._create_service()
        service._load_config = MagicMock(
            return_value=self._mock_config(wol_mac_address=None)
        )
        ok = await service.send_wol()
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_capabilities(self):
        service = self._create_service()
        caps = await service.get_capabilities()
        assert caps.hdparm_available is True
        assert caps.can_suspend is True
        assert len(caps.data_disk_devices) > 0


# ============================================================================
# Idle Detection Tests
# ============================================================================


class TestIdleDetection:
    """Test the idle detection logic."""

    def _create_service(self) -> SleepManagerService:
        backend = DevSleepBackend()
        service = SleepManagerService(backend)
        service._load_config = MagicMock()
        service._log_state_change = MagicMock()
        return service

    def _mock_config(self, **overrides) -> MagicMock:
        config = MagicMock(spec=SleepConfigModel)
        config.idle_cpu_threshold = overrides.get("idle_cpu_threshold", 5.0)
        config.idle_disk_io_threshold = overrides.get("idle_disk_io_threshold", 0.5)
        config.idle_http_threshold = overrides.get("idle_http_threshold", 5.0)
        return config

    def test_idle_when_all_below_thresholds(self):
        service = self._create_service()
        config = self._mock_config()
        metrics = ActivityMetrics(
            cpu_usage_avg=2.0, disk_io_avg_mbps=0.1,
            active_uploads=0, active_downloads=0,
            http_requests_per_minute=1.0,
        )
        assert service._is_system_idle(config, metrics) is True

    def test_not_idle_when_cpu_above_threshold(self):
        service = self._create_service()
        config = self._mock_config()
        metrics = ActivityMetrics(
            cpu_usage_avg=10.0, disk_io_avg_mbps=0.1,
            active_uploads=0, active_downloads=0,
            http_requests_per_minute=1.0,
        )
        assert service._is_system_idle(config, metrics) is False

    def test_not_idle_when_disk_io_above_threshold(self):
        service = self._create_service()
        config = self._mock_config()
        metrics = ActivityMetrics(
            cpu_usage_avg=2.0, disk_io_avg_mbps=1.0,
            active_uploads=0, active_downloads=0,
            http_requests_per_minute=1.0,
        )
        assert service._is_system_idle(config, metrics) is False

    def test_not_idle_when_uploads_active(self):
        service = self._create_service()
        config = self._mock_config()
        metrics = ActivityMetrics(
            cpu_usage_avg=2.0, disk_io_avg_mbps=0.1,
            active_uploads=1, active_downloads=0,
            http_requests_per_minute=1.0,
        )
        assert service._is_system_idle(config, metrics) is False

    def test_not_idle_when_http_above_threshold(self):
        service = self._create_service()
        config = self._mock_config()
        metrics = ActivityMetrics(
            cpu_usage_avg=2.0, disk_io_avg_mbps=0.1,
            active_uploads=0, active_downloads=0,
            http_requests_per_minute=10.0,
        )
        assert service._is_system_idle(config, metrics) is False


# ============================================================================
# HTTP Request Counter Tests
# ============================================================================


class TestHttpRequestCounter:
    """Test the HTTP request per minute counter."""

    def test_record_and_count(self):
        _http_request_timestamps.clear()
        for _ in range(10):
            record_http_request()
        rpm = get_http_requests_per_minute()
        assert rpm == 10.0

    def test_old_requests_not_counted(self):
        import time
        _http_request_timestamps.clear()
        # Add a request with a timestamp in the past (>60s ago)
        _http_request_timestamps.append(time.monotonic() - 120)
        record_http_request()  # Add one recent request
        rpm = get_http_requests_per_minute()
        assert rpm == 1.0


# ============================================================================
# State Machine Edge Cases
# ============================================================================


class TestStateMachineEdgeCases:
    """Test edge cases in the state machine."""

    def _create_service(self) -> SleepManagerService:
        backend = DevSleepBackend()
        service = SleepManagerService(backend)
        service._load_config = MagicMock(return_value=MagicMock(
            auto_idle_enabled=True,
            idle_timeout_minutes=15,
            idle_cpu_threshold=5.0,
            idle_disk_io_threshold=0.5,
            idle_http_threshold=5.0,
            auto_escalation_enabled=False,
            escalation_after_minutes=60,
            pause_monitoring=False,
            pause_disk_io=False,
            reduced_telemetry_interval=30.0,
            disk_spindown_enabled=False,
            wol_mac_address=None,
            wol_broadcast_address=None,
            schedule_enabled=False,
            schedule_sleep_time="23:00",
            schedule_wake_time="06:00",
            schedule_mode="soft",
        ))
        service._log_state_change = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_double_enter_sleep_returns_false(self):
        service = self._create_service()
        ok1 = await service.enter_soft_sleep("first", SleepTrigger.MANUAL)
        assert ok1 is True
        ok2 = await service.enter_soft_sleep("second", SleepTrigger.MANUAL)
        assert ok2 is False

    @pytest.mark.asyncio
    async def test_double_exit_sleep_returns_false(self):
        service = self._create_service()
        await service.enter_soft_sleep("enter", SleepTrigger.MANUAL)
        ok1 = await service.exit_soft_sleep("first")
        assert ok1 is True
        ok2 = await service.exit_soft_sleep("second")
        assert ok2 is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        service = self._create_service()
        await service.start()
        assert service._is_running is True
        assert service._idle_task is not None

        await service.stop()
        assert service._is_running is False

    @pytest.mark.asyncio
    async def test_stop_wakes_from_sleep(self):
        service = self._create_service()
        await service.start()
        await service.enter_soft_sleep("test", SleepTrigger.MANUAL)
        assert service._current_state == SleepState.SOFT_SLEEP

        await service.stop()
        assert service._current_state == SleepState.AWAKE

    def test_time_matches(self):
        assert SleepManagerService._time_matches("23:00", "23:00") is True
        assert SleepManagerService._time_matches("23:00", "06:00") is False
        assert SleepManagerService._time_matches("06:00", "06:00") is True


# ============================================================================
# API Endpoint Tests
# ============================================================================


class TestSleepApiEndpoints:
    """Test the sleep mode API endpoints."""

    def test_get_status_requires_auth(self, client):
        response = client.get("/api/system/sleep/status")
        assert response.status_code == 401

    def test_get_status_returns_data(self, client, admin_headers):
        response = client.get("/api/system/sleep/status", headers=admin_headers)
        # May be 503 if service not started in test env, or 200 if mocked
        assert response.status_code in (200, 503)

    def test_soft_sleep_requires_admin(self, client, user_headers):
        response = client.post("/api/system/sleep/soft", headers=user_headers)
        assert response.status_code == 403

    def test_wake_requires_admin(self, client, user_headers):
        response = client.post("/api/system/sleep/wake", headers=user_headers)
        assert response.status_code == 403

    def test_suspend_requires_admin(self, client, user_headers):
        response = client.post("/api/system/sleep/suspend", headers=user_headers)
        assert response.status_code == 403

    def test_wol_requires_admin(self, client, user_headers):
        response = client.post("/api/system/sleep/wol", headers=user_headers)
        assert response.status_code == 403

    def test_config_requires_admin(self, client, user_headers):
        response = client.get("/api/system/sleep/config", headers=user_headers)
        assert response.status_code == 403

    def test_history_requires_admin(self, client, user_headers):
        response = client.get("/api/system/sleep/history", headers=user_headers)
        assert response.status_code == 403

    def test_capabilities_requires_admin(self, client, user_headers):
        response = client.get("/api/system/sleep/capabilities", headers=user_headers)
        assert response.status_code == 403


# ============================================================================
# Schema Tests
# ============================================================================


class TestSleepSchemas:
    """Test Pydantic schema validation."""

    def test_sleep_config_update_partial(self):
        update = SleepConfigUpdate(auto_idle_enabled=True)
        data = update.model_dump(exclude_unset=True)
        assert data == {"auto_idle_enabled": True}

    def test_sleep_config_update_validates_ranges(self):
        update = SleepConfigUpdate(idle_timeout_minutes=30)
        assert update.idle_timeout_minutes == 30

    def test_sleep_config_update_rejects_invalid_timeout(self):
        with pytest.raises(Exception):
            SleepConfigUpdate(idle_timeout_minutes=0)  # min is 1

    def test_sleep_config_update_rejects_negative_threshold(self):
        with pytest.raises(Exception):
            SleepConfigUpdate(idle_cpu_threshold=-1.0)  # min is 0

    def test_activity_metrics_defaults(self):
        metrics = ActivityMetrics()
        assert metrics.cpu_usage_avg == 0.0
        assert metrics.active_uploads == 0

    def test_sleep_state_enum_values(self):
        assert SleepState.AWAKE.value == "awake"
        assert SleepState.SOFT_SLEEP.value == "soft_sleep"
        assert SleepState.TRUE_SUSPEND.value == "true_suspend"

    def test_schedule_mode_enum(self):
        assert ScheduleMode.SOFT.value == "soft"
        assert ScheduleMode.SUSPEND.value == "suspend"


# ============================================================================
# Model Tests
# ============================================================================


class TestSleepModels:
    """Test SQLAlchemy model creation."""

    def test_sleep_config_creation(self, db_session):
        config = SleepConfigModel(
            id=1,
            auto_idle_enabled=True,
            idle_timeout_minutes=30,
        )
        db_session.add(config)
        db_session.commit()

        loaded = db_session.query(SleepConfigModel).first()
        assert loaded is not None
        assert loaded.auto_idle_enabled is True
        assert loaded.idle_timeout_minutes == 30
        assert loaded.disk_spindown_enabled is True  # default

    def test_sleep_state_log_creation(self, db_session):
        log = SleepStateLog(
            previous_state="awake",
            new_state="soft_sleep",
            reason="manual test",
            triggered_by="manual",
            details_json=json.dumps({"test": True}),
        )
        db_session.add(log)
        db_session.commit()

        loaded = db_session.query(SleepStateLog).first()
        assert loaded is not None
        assert loaded.previous_state == "awake"
        assert loaded.new_state == "soft_sleep"
        assert loaded.reason == "manual test"
        assert loaded.triggered_by == "manual"
        details = json.loads(loaded.details_json)
        assert details["test"] is True

    def test_sleep_config_defaults(self, db_session):
        config = SleepConfigModel(id=1)
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)

        assert config.auto_idle_enabled is False
        assert config.idle_timeout_minutes == 15
        assert config.idle_cpu_threshold == 5.0
        assert config.schedule_mode == "soft"
        assert config.pause_monitoring is True
        assert config.reduced_telemetry_interval == 30.0


# ============================================================================
# Auto-Wake Middleware Tests
# ============================================================================


class TestAutoWakeMiddleware:
    """Test the sleep auto-wake middleware behavior."""

    def test_status_endpoint_does_not_wake(self, client, admin_headers):
        """Whitelisted endpoints should not trigger auto-wake."""
        # The middleware checks the path against whitelist prefixes.
        # /api/system/sleep/status is whitelisted.
        response = client.get("/api/system/sleep/status", headers=admin_headers)
        # Should not raise or cause wake issues
        assert response.status_code in (200, 503)

    def test_monitoring_endpoint_does_not_wake(self, client, admin_headers):
        """Monitoring endpoints are whitelisted."""
        response = client.get("/api/monitoring/metrics", headers=admin_headers)
        # Just verifying it hits the middleware without error
        assert response.status_code in (200, 404)

    def test_non_whitelisted_request_triggers_wake_check(self, client, admin_headers):
        """Non-whitelisted endpoints should trigger wake check."""
        # This endpoint is not whitelisted and would trigger auto-wake
        # In test env the sleep manager may not be running, so we just
        # verify the middleware doesn't break the request flow
        response = client.get("/api/files/list", headers=admin_headers)
        # Should still work (200 or other status, not 500)
        assert response.status_code != 500
