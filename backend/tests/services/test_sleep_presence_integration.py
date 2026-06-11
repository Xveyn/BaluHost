"""Integration tests: SleepManagerService respects user presence (issue #214)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sleep import SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepState, SleepTrigger


def _build_service():
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _config(
    presence_enabled: bool = True,
    presence_timeout_minutes: int = 3,
    auto_escalation_enabled: bool = True,
    schedule_enabled: bool = False,
    schedule_mode: str = "suspend",
):
    return SleepConfig(
        id=1,
        auto_idle_enabled=False,
        idle_timeout_minutes=15,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=auto_escalation_enabled,
        escalation_after_minutes=1,
        schedule_enabled=schedule_enabled,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode=schedule_mode,
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=False,
        always_awake_enabled=False,
        always_awake_until=None,
        presence_enabled=presence_enabled,
        presence_mode="active",
        presence_timeout_minutes=presence_timeout_minutes,
    )


class TestIsUserPresent:
    def test_false_when_config_none(self):
        svc = _build_service()
        assert svc._is_user_present(None) is False

    def test_false_when_disabled_even_if_sessions_exist(self):
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", return_value=True):
            assert svc._is_user_present(_config(presence_enabled=False)) is False

    def test_true_when_enabled_and_session_fresh(self):
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", return_value=True) as m:
            assert svc._is_user_present(_config()) is True
        m.assert_called_once_with(3)

    def test_false_on_db_error(self):
        """Fail toward energy saving: a DB outage must not block suspend forever."""
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", side_effect=RuntimeError("db down")):
            assert svc._is_user_present(_config()) is False


@pytest.mark.asyncio
async def test_escalation_skipped_while_user_present():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_escalation_proceeds_when_nobody_present():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=False), \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_suspend_suppressed_while_user_present():
    svc = _build_service()
    cfg = _config(schedule_enabled=True, schedule_mode="suspend")
    svc._current_state = SleepState.AWAKE
    svc._is_running = True

    call_count = 0

    async def fake_sleep(*_a, **_k):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_reconcile_sleep_inhibitor"), \
         patch.object(svc, "_time_matches", return_value=True), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._schedule_check_loop()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_soft_sleep_proceeds_while_user_present():
    """Presence blocks true suspend ONLY — scheduled soft sleep must still fire."""
    svc = _build_service()
    cfg = _config(schedule_enabled=True, schedule_mode="soft")
    svc._current_state = SleepState.AWAKE
    svc._is_running = True

    call_count = 0

    async def fake_sleep(*_a, **_k):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_reconcile_sleep_inhibitor"), \
         patch.object(svc, "_time_matches", return_value=True), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._schedule_check_loop()

    mock_soft.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_IDLE,
    SleepTrigger.AUTO_ESCALATION,
])
async def test_enter_true_suspend_blocks_non_manual_while_present(trigger):
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.SOFT_SLEEP

    suspend_called: list = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.SessionLocal"):
        ok = await svc.enter_true_suspend("auto", trigger)

    assert ok is False
    assert suspend_called == []


@pytest.mark.asyncio
async def test_enter_true_suspend_manual_proceeds_while_present():
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.SOFT_SLEEP

    suspend_called: list = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("manual by admin", SleepTrigger.MANUAL)

    assert ok is True
    assert len(suspend_called) == 1


class TestInhibitorReconcile:
    def test_presence_holds_inhibitor(self):
        svc = _build_service()
        cfg = _config()
        with patch("app.services.power.presence.is_anyone_present", return_value=True), \
             patch.object(svc._core_uptime_inhibitor, "is_held", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire:
            svc._reconcile_sleep_inhibitor(cfg, in_core=False)
        mock_acquire.assert_called_once_with("user_present_active")

    def test_presence_expiry_releases_inhibitor(self):
        svc = _build_service()
        cfg = _config()
        with patch("app.services.power.presence.is_anyone_present", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "is_held", return_value=True), \
             patch.object(svc._core_uptime_inhibitor, "release") as mock_release:
            svc._reconcile_sleep_inhibitor(cfg, in_core=False)
        mock_release.assert_called_once()

    def test_existing_core_uptime_reason_unchanged(self):
        """Reason strings for pre-existing conditions must stay stable."""
        svc = _build_service()
        cfg = _config(presence_enabled=False)
        with patch.object(svc._core_uptime_inhibitor, "is_held", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire:
            svc._reconcile_sleep_inhibitor(cfg, in_core=True)
        mock_acquire.assert_called_once_with("core_uptime_active")


def test_get_status_includes_presence_block():
    svc = _build_service()
    cfg = _config()
    fake_session = MagicMock(client_id="tab-1")
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.presence.get_present_sessions", return_value=[fake_session]):
        status = svc.get_status()
    assert status.presence.enabled is True
    assert status.presence.anyone_present is True
    assert status.presence.active_session_count == 1
    assert status.presence.suppressing_suspend is True


def test_get_status_presence_disabled():
    svc = _build_service()
    cfg = _config(presence_enabled=False)
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])):
        status = svc.get_status()
    assert status.presence.enabled is False
    assert status.presence.suppressing_suspend is False
