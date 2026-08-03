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


def test_update_config_can_clear_until():
    """Sending always_awake_until=null must clear the column."""
    from app.schemas.sleep import SleepConfigUpdate
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

    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=None)
    payload = update.model_dump(exclude_unset=True)
    assert "always_awake_until" in payload
    assert payload["always_awake_until"] is None

    with patch("app.services.power.sleep.SessionLocal", return_value=fake_session), \
         patch.object(svc, "get_config", return_value=MagicMock()):
        svc.update_config(update)

    assert fake_row.always_awake_until is None


def test_update_config_disabling_normalizes_until():
    """Setting enabled=False must also reset until to None."""
    from app.schemas.sleep import SleepConfigUpdate
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

    update = SleepConfigUpdate(always_awake_enabled=False)

    with patch("app.services.power.sleep.SessionLocal", return_value=fake_session), \
         patch.object(svc, "get_config", return_value=MagicMock()):
        svc.update_config(update)

    assert fake_row.always_awake_enabled is False
    assert fake_row.always_awake_until is None


def test_reconcile_inhibitor_acquires_for_always_awake_only():
    """When only Always-Awake is active (no core uptime), the sleep inhibitor must be acquired."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = fake_inhibitor

    svc._reconcile_sleep_inhibitor(cfg, in_core=False)

    fake_inhibitor.acquire.assert_called_once_with("always_awake_active")
    fake_inhibitor.release.assert_not_called()


def test_reconcile_inhibitor_releases_when_nothing_active():
    """When neither core-uptime nor always-awake is active, an held inhibitor must be released."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=False, always_awake_until=None)

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = True
    svc._core_uptime_inhibitor = fake_inhibitor

    svc._reconcile_sleep_inhibitor(cfg, in_core=False)

    fake_inhibitor.release.assert_called_once_with()
    fake_inhibitor.acquire.assert_not_called()


def test_reconcile_inhibitor_keeps_held_when_one_of_two_remains_active():
    """Releasing only one of (core_uptime, always_awake) while the other stays active must NOT release."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = True
    svc._core_uptime_inhibitor = fake_inhibitor

    # core uptime has ended (in_core=False) but always-awake is still on
    svc._reconcile_sleep_inhibitor(cfg, in_core=False)

    fake_inhibitor.release.assert_not_called()
    # already held; reconcile should not re-acquire either
    fake_inhibitor.acquire.assert_not_called()


def test_reconcile_inhibitor_reason_when_both_active():
    """If both core-uptime and always-awake are active, the acquire reason must reflect both."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None, core_uptime_enabled=True)

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = fake_inhibitor

    svc._reconcile_sleep_inhibitor(cfg, in_core=True)

    fake_inhibitor.acquire.assert_called_once_with("core_uptime_and_always_awake_active")


@pytest.mark.asyncio
async def test_schedule_loop_calls_reconcile_inhibitor_each_tick():
    """Every schedule-loop tick must call _reconcile_sleep_inhibitor with the current (config, in_core)."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    reconcile_calls = []

    def fake_reconcile(c, in_core):
        reconcile_calls.append((c, in_core))

    svc._reconcile_sleep_inhibitor = fake_reconcile
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

    assert len(reconcile_calls) == 1
    assert reconcile_calls[0][0] is cfg
    assert reconcile_calls[0][1] is False


@pytest.mark.asyncio
async def test_start_acquires_inhibitor_when_always_awake_active():
    """If the service starts while Always-Awake is on, the inhibitor must be acquired at startup."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = fake_inhibitor

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch("app.services.power.sleep.asyncio.create_task", side_effect=lambda coro: coro.close() or None):
        await svc.start(monitoring=True)

    fake_inhibitor.acquire.assert_called_once_with("always_awake_active")


@pytest.mark.asyncio
async def test_enter_true_suspend_releases_inhibitor_before_backend_call():
    """Manual suspend while Always-Awake is on must release the inhibitor BEFORE backend.suspend_system runs,
    so logind doesn't refuse the suspend."""
    svc = _build_service()
    cfg = _config(always_awake_enabled=True, always_awake_until=None)

    # Track call order: inhibitor release vs backend suspend
    call_order: list[str] = []

    fake_inhibitor = MagicMock()
    fake_inhibitor.is_held.return_value = True
    fake_inhibitor.release.side_effect = lambda: call_order.append("release")
    svc._core_uptime_inhibitor = fake_inhibitor

    async def fake_suspend(*a, **k):
        call_order.append("suspend")
        return True

    svc._current_state = SleepState.SOFT_SLEEP

    # _is_always_awake: first call (outer guard) → True so the if-block runs and
    # _clear_always_awake is called; second call (inside _reconcile_sleep_inhibitor
    # after the clear) → False so reconcile decides to release the inhibitor.
    aa_responses = iter([True, False])

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_clear_always_awake", new=MagicMock()), \
         patch.object(svc, "_log_state_change", new=MagicMock()), \
         patch.object(svc, "_is_always_awake", side_effect=lambda _cfg: next(aa_responses)), \
         patch.object(svc._backend, "suspend_system", new=AsyncMock(side_effect=fake_suspend)):
        await svc.enter_true_suspend("test", SleepTrigger.MANUAL)

    assert call_order == ["release", "suspend"], (
        f"Expected release before suspend, got {call_order}"
    )


# ---------------------------------------------------------------------------
# Kuerzung von always_awake_until an Kernbetriebszeit-Fenstern
# ---------------------------------------------------------------------------

def _clamp_row(*, core_uptime_enabled: bool = True, until=None):
    """SleepConfig-Zeile fuer die Kuerzungstests."""
    return SleepConfig(
        id=1, auto_idle_enabled=False, idle_timeout_minutes=15,
        idle_cpu_threshold=5.0, idle_disk_io_threshold=0.5, idle_http_threshold=5.0,
        auto_escalation_enabled=False, escalation_after_minutes=60,
        schedule_enabled=False, schedule_sleep_time="23:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=core_uptime_enabled,
        always_awake_enabled=True,
        always_awake_until=until,
    )


def _window(start: str, end: str, weekdays: str = "0,1,2,3,4,5,6"):
    """Fake CoreUptimeWindow — duck-typed, wie in test_core_uptime_helpers."""
    from types import SimpleNamespace
    return SimpleNamespace(
        id=1, enabled=True, label=None,
        start_time=start, end_time=end, weekdays=weekdays,
    )


def _session_with(row, windows):
    """MagicMock-Session: scalar_one_or_none -> row, scalars().all() -> windows."""
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = row
    session.execute.return_value.scalars.return_value.all.return_value = windows
    return session


def _local_utc(local_naive):
    """Lokal-naiven Zeitpunkt in den entsprechenden UTC-aware Wert umrechnen."""
    return local_naive.astimezone(timezone.utc)


def test_update_config_clamps_until_into_future_window():
    """Ablauf im kuenftigen Fenster wird auf den Fensterbeginn gekuerzt."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row()

    # Anchor on local time (tomorrow at 12:00) — window times are local wall clock
    # Window must START AFTER now_local for clamping to apply
    now_local = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    # Window 16:00-22:00 starts 4 hours after now (12:00)
    window = _window("16:00", "22:00")

    # Until is 18:00 local (inside the future window 16:00-22:00)
    until_local = now_local.replace(hour=18)
    requested = until_local.astimezone(timezone.utc)

    # Expected: clamped to 16:00 local (window start)
    expected_local = now_local.replace(hour=16)
    expected_utc = expected_local.astimezone(timezone.utc)

    session = _session_with(row, [window])
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    assert row.always_awake_until == expected_utc


def test_update_config_leaves_until_past_window_end_untouched():
    """Ablauf hinter dem Fensterende bleibt unveraendert."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row()

    # Anchor on local time (tomorrow at 12:00) — window times are local wall clock
    # Never derive scenarios from UTC anchor when windows use local HH:MM strings
    now_local = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    # Window 16:00-22:00 starts after now (12:00)
    window = _window("16:00", "22:00")

    # Until is 23:00 local (past the window end at 22:00)
    until_local = now_local.replace(hour=23)
    requested = until_local.astimezone(timezone.utc)

    session = _session_with(row, [window])
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    # Should remain unchanged since requested is past window end
    assert row.always_awake_until == requested


def test_update_config_does_not_clamp_when_core_uptime_disabled():
    """Hauptschalter aus -> keine Kuerzung (bis wird nicht geaendert)."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(core_uptime_enabled=False)

    # Anchor on local time (tomorrow at 12:00) — window times are local wall clock.
    # Never derive scenarios from a UTC anchor when windows use local HH:MM strings.
    now_local = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    # Window 16:00-22:00 starts 4 hours after now (12:00) — would clamp if enabled.
    window = _window("16:00", "22:00")

    # Until is 18:00 local (inside the window 16:00-22:00)
    until_local = now_local.replace(hour=18)
    requested = until_local.astimezone(timezone.utc)

    session = _session_with(row, [window])
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    # core_uptime_enabled=False -> should remain unchanged despite the window
    # containing the requested expiry.
    assert row.always_awake_until == requested


def test_update_config_ignores_pending_override_when_request_is_unrelated():
    """A write that only touches an unrelated field must not re-evaluate a
    pending always_awake_until, even though a containing future window exists.

    This is the case the SleepConfigPanel triggers in practice: it PUTs
    idle_timeout_minutes alone. Regression for the spec's explicit non-goal
    ("ein bereits gesetzter Override wird nicht neu bewertet").
    """
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()

    now_local = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    window = _window("16:00", "22:00")

    # Pending expiry already sits inside the future window — if the clamp were
    # to (wrongly) re-run here, it would shorten this to 16:00.
    pending_until = now_local.replace(hour=18).astimezone(timezone.utc)
    row = _clamp_row(until=pending_until)

    session = _session_with(row, [window])
    update = SleepConfigUpdate(idle_timeout_minutes=20)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    assert row.idle_timeout_minutes == 20
    assert row.always_awake_until == pending_until


def test_update_config_clamps_when_core_uptime_enabled_in_same_request():
    """core_uptime_enabled wird im selben Request eingeschaltet -> Kuerzung greift."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(core_uptime_enabled=False)

    # Anchor on local time (tomorrow at 12:00)
    # Window must START AFTER now_local for clamping to apply
    now_local = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    # Window 16:00-22:00 starts 4 hours after now (12:00)
    window = _window("16:00", "22:00")

    # Until is 18:00 local (inside the future window 16:00-22:00)
    until_local = now_local.replace(hour=18)
    requested = until_local.astimezone(timezone.utc)

    # Expected: clamped to 16:00 local (window start)
    expected_local = now_local.replace(hour=16)
    expected_utc = expected_local.astimezone(timezone.utc)

    session = _session_with(row, [window])

    # Enable core_uptime in the same request
    update = SleepConfigUpdate(
        always_awake_enabled=True,
        always_awake_until=requested,
        core_uptime_enabled=True,
    )

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    assert row.always_awake_until == expected_utc


def test_update_config_no_clamp_for_permanent_override():
    """until=None (dauerhaft) bleibt None — nichts zu kuerzen."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(until=_local_utc(datetime(2026, 8, 5, 21, 0)))
    session = _session_with(row, [_window("19:00", "23:30")])

    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=None)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 8, 5, 15, 0)
        svc.update_config(update)

    assert row.always_awake_until is None


def test_update_config_disabling_still_clears_until_with_windows_present():
    """enabled=False raeumt until ab — die Kuerzung darf da nichts wiederbeleben."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(until=_local_utc(datetime(2026, 8, 5, 21, 0)))
    session = _session_with(row, [_window("19:00", "23:30")])

    update = SleepConfigUpdate(always_awake_enabled=False)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 8, 5, 15, 0)
        svc.update_config(update)

    assert row.always_awake_enabled is False
    assert row.always_awake_until is None
