"""Integration tests: SleepManagerService respects always-awake override."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.models.sleep import SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import ActivityMetrics, SleepState, SleepTrigger


def _build_service():
    SleepManagerService._instance = None
    return SleepManagerService(DevSleepBackend())


def _config(
    *,
    always_awake_enabled: bool = False,
    always_awake_until: datetime | None = None,
    auto_idle_enabled: bool = True,
    idle_timeout_minutes: int = 1,
    auto_escalation_enabled: bool = False,
    schedule_enabled: bool = False,
    core_uptime_enabled: bool = False,
):
    return SleepConfig(
        id=1,
        auto_idle_enabled=auto_idle_enabled,
        idle_timeout_minutes=idle_timeout_minutes,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=auto_escalation_enabled,
        escalation_after_minutes=1,
        schedule_enabled=schedule_enabled,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=core_uptime_enabled,
        always_awake_enabled=always_awake_enabled,
        always_awake_until=always_awake_until,
    )


def test_is_always_awake_disabled_returns_false():
    svc = _build_service()
    cfg = _config(always_awake_enabled=False, always_awake_until=None)
    assert svc._is_always_awake(cfg) is False


def test_is_always_awake_enabled_no_expiry_returns_true():
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)
    assert svc._is_always_awake(cfg) is True


def test_is_always_awake_future_expiry_returns_true():
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert svc._is_always_awake(cfg) is True


def test_is_always_awake_past_expiry_returns_false():
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert svc._is_always_awake(cfg) is False


def test_is_always_awake_naive_until_treated_as_utc():
    """Regression: legacy DB rows may store naive datetimes; comparison must not crash."""
    svc = _build_service()
    naive_future = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    cfg = _config(always_awake_enabled=True, always_awake_until=naive_future)
    assert svc._is_always_awake(cfg) is True


def test_clear_always_awake_resets_columns_and_audits():
    """_clear_always_awake must zero both fields and emit an audit-log event."""
    svc = _build_service()
    fake_row = SleepConfig(
        id=1, auto_idle_enabled=False, idle_timeout_minutes=15,
        idle_cpu_threshold=5.0, idle_disk_io_threshold=0.5, idle_http_threshold=5.0,
        auto_escalation_enabled=False, escalation_after_minutes=60,
        schedule_enabled=False, schedule_sleep_time="23:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False, core_uptime_enabled=False,
        always_awake_enabled=True,
        always_awake_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    fake_session = MagicMock()
    fake_session.execute.return_value.scalar_one_or_none.return_value = fake_row
    fake_audit = MagicMock()

    with patch("app.services.power.sleep.SessionLocal", return_value=fake_session), \
         patch("app.services.power.sleep.get_audit_logger_db", return_value=fake_audit):
        svc._clear_always_awake(reason="always_awake_expired")

    assert fake_row.always_awake_enabled is False
    assert fake_row.always_awake_until is None
    fake_session.commit.assert_called_once()
    fake_audit.log_security_event.assert_called_once()
    args = fake_audit.log_security_event.call_args
    assert args.kwargs["action"] == "always_awake_expired"


@pytest.mark.asyncio
async def test_idle_detection_skips_when_always_awake():
    """While always-awake is on, idle counter must not advance and no auto-sleep is triggered."""
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=None,
        auto_idle_enabled=True,
        idle_timeout_minutes=1,
    )

    enter_called = []

    async def fake_enter_soft_sleep(*a, **k):
        enter_called.append(a)
        return True

    svc.enter_soft_sleep = fake_enter_soft_sleep
    svc._is_running = True
    svc._current_state = SleepState.AWAKE
    svc._consecutive_idle_checks = 5
    svc._idle_seconds = 150.0

    # Counter pattern: first call lets the loop body run; second call stops the loop.
    call_count = [0]

    async def fake_sleep(*_a, **_k):
        call_count[0] += 1
        if call_count[0] >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_system_idle", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._idle_detection_loop()

    # Body ran exactly once. With the guard, the always-awake branch resets
    # _consecutive_idle_checks and _idle_seconds, and continues — so no
    # enter_soft_sleep is called.
    assert enter_called == []
    assert svc._consecutive_idle_checks == 0
    assert svc._idle_seconds == 0.0


@pytest.mark.asyncio
async def test_schedule_loop_skips_sleep_when_always_awake():
    """Scheduled sleep_time match must NOT trigger sleep when always-awake is on."""
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=None,
        auto_idle_enabled=False,
        schedule_enabled=True,
    )
    cfg.schedule_sleep_time = "12:00"

    enter_called = []

    async def fake_enter(*a, **k):
        enter_called.append(a)
        return True

    svc.enter_soft_sleep = fake_enter
    svc.enter_true_suspend = fake_enter
    svc._is_running = True
    svc._current_state = SleepState.AWAKE

    # Counter pattern: first call lets body run; second stops the loop.
    call_count = [0]

    async def fake_sleep(*_a, **_k):
        call_count[0] += 1
        if call_count[0] >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.sleep.datetime") as mock_dt:
        # Make datetime.now() return 12:00 so the schedule_sleep_time matches.
        mock_dt.now.return_value = datetime(2026, 5, 7, 12, 0)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        with patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
            await svc._schedule_check_loop()

    assert enter_called == []


@pytest.mark.asyncio
async def test_schedule_loop_clears_expired_always_awake():
    """When until < now and enabled, the loop must call _clear_always_awake('always_awake_expired')."""
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    cleared = []

    def fake_clear(reason):
        cleared.append(reason)

    svc._clear_always_awake = fake_clear
    svc._is_running = True
    svc._current_state = SleepState.AWAKE

    call_count = [0]

    async def fake_sleep(*_a, **_k):
        call_count[0] += 1
        if call_count[0] >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._schedule_check_loop()

    assert cleared == ["always_awake_expired"]


@pytest.mark.asyncio
async def test_escalation_skipped_when_always_awake():
    """_escalation_monitor must return without escalating if always-awake is on."""
    svc = _build_service()
    cfg = _config(
        always_awake_enabled=True,
        always_awake_until=None,
        auto_escalation_enabled=True,
    )

    suspend_called = []

    async def fake_suspend(*a, **k):
        suspend_called.append(a)
        return True

    svc.enter_true_suspend = fake_suspend
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    # Don't actually wait the configured 60s
    async def instant_sleep(*_a, **_k):
        return None

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=instant_sleep):
        await svc._escalation_monitor()

    assert suspend_called == []


@pytest.mark.asyncio
async def test_enter_soft_sleep_clears_always_awake():
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    cleared = []

    def fake_clear(reason):
        cleared.append(reason)

    svc._clear_always_awake = fake_clear
    svc._current_state = SleepState.AWAKE

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_log_state_change", new=MagicMock()):
        await svc.enter_soft_sleep("test", SleepTrigger.MANUAL)

    assert cleared == ["always_awake_cleared_by_sleep"]


@pytest.mark.asyncio
async def test_enter_true_suspend_clears_always_awake():
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    cleared = []

    def fake_clear(reason):
        cleared.append(reason)

    svc._clear_always_awake = fake_clear
    # Start in SOFT_SLEEP so enter_true_suspend does not recurse into
    # enter_soft_sleep (which has its own clear hook tested separately).
    svc._current_state = SleepState.SOFT_SLEEP

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_log_state_change", new=MagicMock()), \
         patch.object(svc._backend, "suspend_system", new=AsyncMock(return_value=True)):
        await svc.enter_true_suspend("test", SleepTrigger.MANUAL)

    assert cleared == ["always_awake_cleared_by_sleep"]


def test_get_status_includes_always_awake_block():
    svc = _build_service()
    until = datetime.now(timezone.utc) + timedelta(hours=2)
    cfg = _config(always_awake_enabled=True, always_awake_until=until)

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_get_activity_metrics", return_value=ActivityMetrics()):
        status = svc.get_status()

    assert status.always_awake.enabled is True
    assert status.always_awake.until == until
    assert status.always_awake.expires_in_seconds is not None
    assert status.always_awake.expires_in_seconds > 0


def test_get_status_always_awake_off_returns_default_block():
    svc = _build_service()
    cfg = _config(always_awake_enabled=False, always_awake_until=None)

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_get_activity_metrics", return_value=ActivityMetrics()):
        status = svc.get_status()

    assert status.always_awake.enabled is False
    assert status.always_awake.until is None
    assert status.always_awake.expires_in_seconds is None


def test_get_config_returns_always_awake_fields():
    svc = _build_service()
    until = datetime.now(timezone.utc) + timedelta(hours=1)
    cfg = _config(always_awake_enabled=True, always_awake_until=until)

    with patch.object(svc, "_load_config", return_value=cfg):
        resp = svc.get_config()

    assert resp.always_awake_enabled is True
    assert resp.always_awake_until == until
