"""Der Sleep-Zustand des Primary ist fuer jeden API-Prozess lesbar (#823).

Produktion laeuft mit sechs API-Prozessen, genau einer ("Primary") betreibt
Idle- und Schedule-Loop. Ging er in den Soft-Sleep, hielten die anderen fuenf
die Box fuer wach: Sync-Sperre, Sync-Preflight und `GET /api/sleep/status`
antworteten je nach Worker verschieden.

Die Tests bauen zwei echte Service-Instanzen auf DERSELBEN Datenbank:
"Primary" (gestartet mit monitoring=True) und "Follower" (monitoring=False).
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ServiceUnavailableError
from app.models.base import Base
from app.schemas.sleep import SleepState, SleepTrigger
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


def _published(factory):
    db = factory()
    try:
        return store.read_state(db)
    finally:
        db.close()


def _publish(factory, state: SleepState, since=None) -> None:
    db = factory()
    try:
        assert store.publish_state(db, state, since)
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


async def _stop(svc: SleepManagerService) -> None:
    with patch.object(svc._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await svc.stop()


# ─── Veroeffentlichen ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_publishes_every_state_change(session_factory):
    primary = await _started(primary=True)

    primary._current_state = SleepState.SOFT_SLEEP

    state, since = _published(session_factory)
    assert state is SleepState.SOFT_SLEEP
    assert since is not None


@pytest.mark.asyncio
async def test_primary_publishes_through_the_real_soft_sleep_path(session_factory):
    primary = await _started(primary=True)

    assert await primary.enter_soft_sleep("test", SleepTrigger.MANUAL) is True

    assert _published(session_factory)[0] is SleepState.SOFT_SLEEP


@pytest.mark.asyncio
async def test_follower_never_publishes(session_factory):
    follower = await _started(primary=False)

    follower._current_state = SleepState.SOFT_SLEEP

    assert _published(session_factory) is None


def test_unstarted_instance_needs_no_database(monkeypatch):
    """Tests und Hilfscode weisen den Zustand direkt zu -- ohne DB."""
    exploding = MagicMock(side_effect=AssertionError("DB touched"))
    monkeypatch.setattr(sleep_mode, "SessionLocal", exploding)
    svc = _new_service()

    svc._current_state = SleepState.SOFT_SLEEP

    assert svc._current_state is SleepState.SOFT_SLEEP
    exploding.assert_not_called()


@pytest.mark.asyncio
async def test_primary_start_overwrites_a_stale_state(session_factory):
    """Ein Stand aus der Zeit vor dem Neustart darf nicht stehen bleiben."""
    _publish(session_factory, SleepState.SOFT_SLEEP, datetime(2026, 1, 1, tzinfo=timezone.utc))

    await _started(primary=True)

    assert _published(session_factory)[0] is SleepState.AWAKE


@pytest.mark.asyncio
async def test_follower_start_leaves_the_published_state_alone(session_factory):
    _publish(session_factory, SleepState.SOFT_SLEEP)

    await _started(primary=False)

    assert _published(session_factory)[0] is SleepState.SOFT_SLEEP


@pytest.mark.asyncio
async def test_failed_publish_does_not_disturb_the_state_machine(session_factory):
    primary = await _started(primary=True)

    with patch.object(store, "publish_state", side_effect=RuntimeError("db down")):
        primary._current_state = SleepState.SOFT_SLEEP

    assert primary._current_state is SleepState.SOFT_SLEEP
    assert _published(session_factory)[0] is SleepState.AWAKE  # Stand vom Start


@pytest.mark.asyncio
async def test_failed_publish_is_retried_on_the_next_schedule_tick(session_factory):
    primary = await _started(primary=True)
    with patch.object(store, "publish_state", return_value=False):
        primary._current_state = SleepState.SOFT_SLEEP
    assert _published(session_factory)[0] is SleepState.AWAKE

    primary._is_running = True

    async def one_tick(*_a, **_k):
        if getattr(one_tick, "done", False):
            primary._is_running = False
        one_tick.done = True

    with patch.object(primary, "_load_config", return_value=None), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch.object(primary, "_is_gaming_active", return_value=False), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=one_tick):
        await primary._schedule_check_loop()

    assert _published(session_factory)[0] is SleepState.SOFT_SLEEP


@pytest.mark.asyncio
async def test_successful_retry_clears_the_dirty_flag(session_factory):
    primary = await _started(primary=True)
    with patch.object(store, "publish_state", return_value=False):
        primary._current_state = SleepState.SOFT_SLEEP

    primary._retry_state_publish()
    calls = MagicMock(wraps=store.publish_state)
    with patch.object(store, "publish_state", calls):
        primary._retry_state_publish()

    calls.assert_not_called()


@pytest.mark.asyncio
async def test_primary_stop_leaves_awake_published(session_factory):
    primary = await _started(primary=True)
    primary._current_state = SleepState.SOFT_SLEEP

    await _stop(primary)

    assert _published(session_factory)[0] is SleepState.AWAKE


@pytest.mark.asyncio
async def test_primary_stop_mid_transition_still_leaves_awake_published(session_factory):
    """`_exit_soft_sleep` lehnt ENTERING_SUSPEND ab -- trotzdem darf kein
    Nicht-AWAKE-Stand stehen bleiben, den kein Loop mehr korrigiert."""
    primary = await _started(primary=True)
    primary._current_state = SleepState.ENTERING_SUSPEND

    await _stop(primary)

    assert _published(session_factory)[0] is SleepState.AWAKE


@pytest.mark.asyncio
async def test_stopped_primary_no_longer_publishes(session_factory):
    primary = await _started(primary=True)
    await _stop(primary)

    primary._current_state = SleepState.SOFT_SLEEP

    assert _published(session_factory)[0] is SleepState.AWAKE


# ─── effective_state() ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_effective_state_of_the_primary_is_local(session_factory):
    primary = await _started(primary=True)
    _publish(session_factory, SleepState.SOFT_SLEEP)  # fremder Stand

    state, since = primary.effective_state()

    assert state is SleepState.AWAKE
    assert since == primary._state_since


@pytest.mark.asyncio
async def test_follower_reads_the_published_state(session_factory):
    follower = await _started(primary=False)
    since = datetime(2026, 11, 12, 23, 0, tzinfo=timezone.utc)
    _publish(session_factory, SleepState.SOFT_SLEEP, since)

    assert follower.effective_state() == (SleepState.SOFT_SLEEP, since)


@pytest.mark.asyncio
async def test_follower_caches_the_published_state_for_two_seconds(session_factory):
    follower = await _started(primary=False)
    now = [1000.0]
    follower._clock = lambda: now[0]
    _publish(session_factory, SleepState.SOFT_SLEEP)
    assert follower.effective_state()[0] is SleepState.SOFT_SLEEP

    _publish(session_factory, SleepState.AWAKE)
    now[0] += 1.9
    assert follower.effective_state()[0] is SleepState.SOFT_SLEEP

    now[0] += 0.2
    assert follower.effective_state()[0] is SleepState.AWAKE


@pytest.mark.asyncio
async def test_follower_falls_back_to_local_when_nothing_is_published(session_factory):
    follower = await _started(primary=False)

    state, since = follower.effective_state()

    assert state is SleepState.AWAKE
    assert since == follower._state_since


@pytest.mark.asyncio
async def test_follower_falls_back_to_local_when_the_database_fails(monkeypatch):
    follower = _new_service()
    monkeypatch.setattr(sleep_mode, "SessionLocal", MagicMock(side_effect=RuntimeError("down")))

    assert follower.effective_state()[0] is SleepState.AWAKE


@pytest.mark.asyncio
async def test_local_non_awake_state_of_a_follower_wins(session_factory):
    """Eine manuelle Aktion, die auf diesem Worker gelandet ist, bleibt bis
    zum zweiten PR sichtbar (#823)."""
    follower = await _started(primary=False)
    _publish(session_factory, SleepState.AWAKE)
    follower._current_state = SleepState.SOFT_SLEEP

    assert follower.effective_state()[0] is SleepState.SOFT_SLEEP


# ─── Leser auf einem Follower, waehrend der Primary schlaeft ─────────


async def _primary_asleep_and_follower():
    primary = await _started(primary=True)
    primary._current_state = SleepState.SOFT_SLEEP
    follower = await _started(primary=False)
    return primary, follower


@pytest.mark.asyncio
async def test_follower_status_shows_the_primary_soft_sleep(session_factory):
    primary, follower = await _primary_asleep_and_follower()

    with patch.object(follower, "_foreign_inhibitor", return_value=None):
        status = follower.get_status()

    assert status.current_state is SleepState.SOFT_SLEEP
    assert status.state_since is not None


@pytest.mark.asyncio
async def test_follower_service_status_shows_the_primary_soft_sleep(
    session_factory, monkeypatch
):
    _primary, follower = await _primary_asleep_and_follower()
    monkeypatch.setattr(sleep_mode, "_service", follower)

    assert sleep_mode.get_service_status()["current_state"] == "soft_sleep"


@pytest.mark.asyncio
async def test_follower_sync_guard_blocks_auto_sync(session_factory):
    from app.api.deps import require_sync_allowed

    _primary, follower = await _primary_asleep_and_follower()
    request = SimpleNamespace(headers={"X-Sync-Trigger": "auto"})

    with patch("app.services.power.sleep.get_sleep_manager", return_value=follower), \
         pytest.raises(ServiceUnavailableError) as exc:
        await require_sync_allowed(request)

    assert exc.value.public_detail["sleep_state"] == "soft_sleep"


@pytest.mark.asyncio
async def test_follower_preflight_reports_the_primary_soft_sleep(session_factory):
    from app.api.routes import sync as sync_routes

    _primary, follower = await _primary_asleep_and_follower()

    with patch.object(sync_routes, "get_sleep_manager", return_value=follower):
        result = await sync_routes.sync_preflight.__wrapped__(
            request=MagicMock(), response=Response(), current_user=MagicMock(),
        )

    assert result.sync_allowed is False
    assert result.current_sleep_state == "soft_sleep"
    assert result.block_reason == "sleep_active"


@pytest.mark.asyncio
async def test_follower_auto_wake_does_not_exit_soft_sleep_for_the_primary(session_factory):
    """Ein Follower kann den Primary noch nicht wecken. Fuehrte er
    exit_soft_sleep() lokal aus, setzte er Dienste fort und naehme den
    IDLE-Demand weg, waehrend der Primary weiter soft_sleep veroeffentlicht."""
    from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware

    _primary, follower = await _primary_asleep_and_follower()
    app = FastAPI()
    app.add_middleware(SleepAutoWakeMiddleware)

    @app.post("/api/files/upload")
    async def upload_stub():
        return {"ok": True}

    with patch("app.services.power.sleep.get_sleep_manager", return_value=follower), \
         patch.object(follower, "exit_soft_sleep", new=AsyncMock()) as exit_mock:
        TestClient(app).post("/api/files/upload")

    exit_mock.assert_not_called()
