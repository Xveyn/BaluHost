"""Die Statusdetails des Primary sind fuer jeden API-Prozess lesbar (#834).

`idle_seconds`, `paused_services` und `spun_down_disks` kennt nur der Prozess,
der die Zustandsmaschine betreibt. `GET /api/system/sleep/status` zeigte sie
deshalb nur, wenn die Anfrage zufaellig den Primary traf; jeder andere Worker
antwortete mit 0 und leeren Listen. Der Primary veroeffentlicht sie jetzt
zusammen mit dem Zustand in `sleep_runtime_state`.

Aufbau wie in `test_sleep_state_shared.py`: zwei echte Service-Instanzen auf
derselben Datenbank.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.sleep import SleepConfig, SleepRuntimeState
from app.schemas.sleep import SleepState
from app.services.power import sleep as sleep_mode
from app.services.power import sleep_runtime_store as store
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(sleep_mode, "SessionLocal", factory)
    return factory


@pytest.fixture(autouse=True)
def _reset_singleton():
    SleepManagerService._instance = None
    yield
    SleepManagerService._instance = None


def _snapshot(factory):
    db = factory()
    try:
        return store.read_snapshot(db)
    finally:
        db.close()


def _new_service() -> SleepManagerService:
    svc = SleepManagerService(DevSleepBackend())
    inhibitor = MagicMock()
    inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = inhibitor
    return svc


async def _started(*, primary: bool) -> SleepManagerService:
    """Eine Instanz in der gewuenschten Rolle, ohne Loops und ohne logind."""
    svc = _new_service()
    with patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch("app.services.power.sleep.asyncio.create_task",
               side_effect=lambda coro: coro.close() or None):
        await svc.start(monitoring=primary)
    return svc


def _status(svc: SleepManagerService):
    with patch.object(svc, "_foreign_inhibitor", return_value=None):
        return svc.get_status()


def _config(**overrides) -> SleepConfig:
    values = dict(
        id=1,
        auto_idle_enabled=True,
        idle_timeout_minutes=60,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=False,
        escalation_after_minutes=60,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=True,
        core_uptime_enabled=False,
        core_uptime_suspend_on_exit=False,
    )
    values.update(overrides)
    return SleepConfig(**values)


# ─── Veroeffentlichen ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_change_publishes_the_details_with_it(session_factory):
    primary = await _started(primary=True)
    primary._paused_services = ["monitoring_orchestrator"]
    primary._spun_down_disks = ["/dev/sda", "/dev/sdb"]
    primary._idle_seconds = 900.0

    primary._current_state = SleepState.SOFT_SLEEP

    snap = _snapshot(session_factory)
    assert snap.state is SleepState.SOFT_SLEEP
    assert snap.paused_services == ["monitoring_orchestrator"]
    assert snap.spun_down_disks == ["/dev/sda", "/dev/sdb"]
    assert snap.idle_seconds == 900.0


@pytest.mark.asyncio
async def test_real_soft_sleep_and_wake_publish_what_they_did(session_factory):
    primary = await _started(primary=True)
    primary._idle_seconds = 600.0
    with patch.object(primary, "_load_config", return_value=_config()), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.manager.get_power_manager", return_value=None), \
         patch("app.services.power.fan_control.get_fan_control_service", return_value=None), \
         patch("app.services.telemetry.stop_telemetry_monitor", new=AsyncMock()), \
         patch("app.services.telemetry.start_telemetry_monitor", new=AsyncMock()):
        assert await primary.enter_soft_sleep("test") is True
        asleep = _snapshot(session_factory)

        assert await primary.exit_soft_sleep("test") is True
        awake = _snapshot(session_factory)

    assert asleep.state is SleepState.SOFT_SLEEP
    assert asleep.spun_down_disks == ["/dev/sda", "/dev/sdb"]
    assert awake.state is SleepState.AWAKE
    assert awake.spun_down_disks == []
    assert awake.paused_services == []
    # Der Zaehler wird beim Aufwachen zurueckgesetzt -- das muss auch der
    # veroeffentlichte Stand zeigen, nicht erst der naechste Idle-Tick.
    assert awake.idle_seconds == 0.0


@pytest.mark.asyncio
async def test_idle_counter_is_published_without_a_state_change(session_factory):
    primary = await _started(primary=True)

    primary._idle_seconds = 90.0
    primary._publish_details_if_changed()

    snap = _snapshot(session_factory)
    assert snap.state is SleepState.AWAKE
    assert snap.idle_seconds == 90.0


@pytest.mark.asyncio
async def test_unchanged_details_are_not_written_again(session_factory):
    primary = await _started(primary=True)
    primary._idle_seconds = 90.0
    primary._publish_details_if_changed()

    with patch.object(store, "publish_state", wraps=store.publish_state) as publish:
        primary._publish_details_if_changed()
        primary._publish_details_if_changed()

    publish.assert_not_called()


@pytest.mark.asyncio
async def test_failed_details_publish_is_tried_again(session_factory):
    primary = await _started(primary=True)
    primary._idle_seconds = 90.0
    with patch.object(store, "publish_state", return_value=False):
        primary._publish_details_if_changed()

    primary._publish_details_if_changed()

    assert _snapshot(session_factory).idle_seconds == 90.0


@pytest.mark.asyncio
async def test_details_publish_keeps_the_published_since(session_factory):
    """Ein Detail-Update darf `state_since` nicht auf "jetzt" ziehen."""
    primary = await _started(primary=True)
    primary._current_state = SleepState.SOFT_SLEEP
    since_before = _snapshot(session_factory).since

    primary._idle_seconds = 30.0
    primary._publish_details_if_changed()

    after = _snapshot(session_factory)
    assert after.state is SleepState.SOFT_SLEEP
    assert after.since == since_before


@pytest.mark.asyncio
async def test_follower_never_publishes_details(session_factory):
    follower = await _started(primary=False)

    follower._idle_seconds = 90.0
    follower._publish_details_if_changed()

    assert _snapshot(session_factory) is None


@pytest.mark.asyncio
async def test_idle_loop_publishes_the_counter_each_tick(session_factory):
    primary = await _started(primary=True)
    primary._is_running = True
    ticks = [0]

    async def one_tick(*_a, **_k):
        ticks[0] += 1
        if ticks[0] >= 2:
            primary._is_running = False

    with patch.object(primary, "_load_config", return_value=_config()), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch.object(primary, "_is_gaming_active", return_value=False), \
         patch.object(primary, "_foreign_inhibitor", return_value=None), \
         patch.object(primary, "_is_system_idle", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=one_tick):
        await primary._idle_detection_loop()

    assert primary._idle_seconds == 30.0
    assert _snapshot(session_factory).idle_seconds == 30.0


@pytest.mark.asyncio
async def test_idle_loop_publishes_the_reset_when_activity_returns(session_factory):
    primary = await _started(primary=True)
    primary._idle_seconds = 300.0
    primary._consecutive_idle_checks = 10
    primary._publish_details_if_changed()
    primary._is_running = True
    ticks = [0]

    async def one_tick(*_a, **_k):
        ticks[0] += 1
        if ticks[0] >= 2:
            primary._is_running = False

    with patch.object(primary, "_load_config", return_value=_config()), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch.object(primary, "_is_gaming_active", return_value=False), \
         patch.object(primary, "_foreign_inhibitor", return_value=None), \
         patch.object(primary, "_is_system_idle", return_value=False), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=one_tick):
        await primary._idle_detection_loop()

    assert _snapshot(session_factory).idle_seconds == 0.0


# ─── Lesen ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_follower_status_shows_the_primary_details(session_factory):
    primary = await _started(primary=True)
    follower = await _started(primary=False)
    primary._paused_services = ["disk_io_monitor"]
    primary._spun_down_disks = ["/dev/sda"]
    primary._idle_seconds = 1200.0
    primary._current_state = SleepState.SOFT_SLEEP

    status = _status(follower)

    assert status.current_state is SleepState.SOFT_SLEEP
    assert status.paused_services == ["disk_io_monitor"]
    assert status.spun_down_disks == ["/dev/sda"]
    assert status.idle_seconds == 1200.0


@pytest.mark.asyncio
async def test_primary_status_stays_local(session_factory):
    primary = await _started(primary=True)
    primary._idle_seconds = 60.0
    db = session_factory()
    try:
        store.publish_state(
            db, SleepState.AWAKE, None,
            store.SleepRuntimeDetails(idle_seconds=999.0, paused_services=["x"]),
        )
    finally:
        db.close()

    status = _status(primary)

    assert status.idle_seconds == 60.0
    assert status.paused_services == []


@pytest.mark.asyncio
async def test_follower_status_falls_back_to_local_when_nothing_is_published(session_factory):
    follower = await _started(primary=False)

    status = _status(follower)

    assert status.idle_seconds == 0.0
    assert status.paused_services == []
    assert status.spun_down_disks == []


@pytest.mark.asyncio
async def test_follower_status_survives_unreadable_details(session_factory):
    """Ein kaputter Detailwert kostet die Details, nicht den Zustand."""
    primary = await _started(primary=True)
    follower = await _started(primary=False)
    primary._current_state = SleepState.SOFT_SLEEP
    db = session_factory()
    try:
        db.get(SleepRuntimeState, 1).details_json = "{not json"
        db.commit()
    finally:
        db.close()

    status = _status(follower)

    assert status.current_state is SleepState.SOFT_SLEEP
    assert status.idle_seconds == 0.0
    assert status.paused_services == []
    assert status.spun_down_disks == []
