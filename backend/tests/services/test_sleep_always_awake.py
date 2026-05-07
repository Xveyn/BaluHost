"""Integration tests: SleepManagerService respects always-awake override."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.models.sleep import SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepState, SleepTrigger


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
    import asyncio
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

    async def stop_after_one(*_a, **_k):
        svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_system_idle", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one):
        await svc._idle_detection_loop()

    assert enter_called == []
    assert svc._idle_seconds == 0.0
