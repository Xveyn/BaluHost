"""Wechselwirkung zwischen Neustart-Automat und Sleep-Manager."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.scheduler_history import SchedulerConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power import reboot_state
from app.services.power.reboot_state import claim_wakeup, get_state, to_utc
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)
SUNDAY_0800 = datetime(2026, 9, 13, 8, 0)


def _enable(db):
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True, interval_seconds=604800,
        extra_config=json.dumps({"weekday": 6, "time": "04:00"}),
    ))
    db.commit()


def test_trigger_value_exists():
    assert SleepTrigger.SCHEDULED_REBOOT.value == "scheduled_reboot"


def test_claim_wakeup_takes_the_earlier_reboot_and_remembers_the_regular(db_session):
    _enable(db_session)
    regular = to_utc(SUNDAY_0800)
    claimed = claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0))
    assert claimed == to_utc(SUNDAY_0400)
    state = get_state(db_session)
    assert state.woke_for_reboot is True
    # SQLite gibt timestamptz naiv zurück (dieselbe Annahme wie in `to_local`);
    # der Vergleich erfolgt deshalb naiv statt gegen den aware Ausgangswert.
    assert state.resuspend_wake_at == regular.replace(tzinfo=None)


def test_claim_wakeup_leaves_an_earlier_regular_alone(db_session):
    _enable(db_session)
    regular = to_utc(datetime(2026, 9, 13, 2, 0))  # vor dem Termin
    claimed = claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0))
    assert claimed == regular
    assert get_state(db_session).woke_for_reboot is False


def test_claim_wakeup_with_no_regular_wake_time(db_session):
    """Keine Kernbetriebszeit konfiguriert -> resuspend_wake_at bleibt None."""
    _enable(db_session)
    claimed = claim_wakeup(db_session, None, datetime(2026, 9, 13, 1, 0))
    assert claimed == to_utc(SUNDAY_0400)
    state = get_state(db_session)
    assert state.woke_for_reboot is True
    assert state.resuspend_wake_at is None


def test_claim_wakeup_without_the_feature_is_a_no_op(db_session):
    regular = to_utc(SUNDAY_0800)
    assert claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0)) == regular
    assert get_state(db_session).woke_for_reboot is False


def test_claim_wakeup_refuses_a_naive_regular_wake_time(db_session):
    """Naiv heißt server-lokal. Das als UTC zu deuten war der Fehler: die
    Klemm-Entscheidung läge um den UTC-Offset daneben und `resuspend_wake_at`
    bekäme eine Ortszeit in eine UTC-Spalte. Also lieber laut scheitern."""
    _enable(db_session)
    with pytest.raises(ValueError):
        claim_wakeup(db_session, SUNDAY_0800, datetime(2026, 9, 13, 1, 0))
    assert get_state(db_session).woke_for_reboot is False


@pytest.mark.asyncio
async def test_suspend_path_converts_the_local_wake_time_before_claiming(db_session):
    """Der Suspend-Pfad muss die naiv-LOKALE Weckzeit nach UTC wandeln.

    Reicht er sie roh durch, deutet `claim_wakeup` sie als UTC — eine reguläre
    Weckzeit, die vor dem Neustart-Termin liegt, sähe dann später aus und würde
    fälschlich geklemmt. Geprüft wird deshalb beides: die Form, in der die
    Weckzeit ankommt (aware UTC — das ist zeitzonenunabhängig und fällt auch in
    der UTC-CI auf), und die Wirkung (kein Klemmen, Rückgabe wieder naiv-lokal).
    """
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.SOFT_SLEEP
    _enable(db_session)

    # Frische Session pro Aufruf: `enter_true_suspend` schließt jede, die es
    # öffnet — die Fixture-Session selbst darf davon nicht getroffen werden.
    factory = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )

    due_local = reboot_state.next_reboot_due(db_session, datetime.now())
    assert due_local is not None
    regular_local = due_local - timedelta(hours=1)  # naiv-lokal, VOR dem Termin

    seen: list = []
    backend_called: list = []
    real_claim = reboot_state.claim_wakeup

    def _spy_claim(db, regular_utc, now_local):
        seen.append(regular_utc)
        return real_claim(db, regular_utc, now_local)

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=False), \
         patch("app.services.power.sleep.scheduled_reboot.reset_before_suspend"), \
         patch("app.services.power.sleep.reboot_state.claim_wakeup",
               side_effect=_spy_claim), \
         patch("app.services.power.sleep.SessionLocal", factory), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend(
            "idle", SleepTrigger.AUTO_IDLE, wake_at=regular_local,
        )

    assert ok is True
    assert len(seen) == 1
    assert seen[0].tzinfo is not None, "claim_wakeup bekam einen naiven Wert"
    assert seen[0] == regular_local.astimezone(timezone.utc)
    # Nicht geklemmt — und in der Form, die das Backend erwartet (naiv-lokal).
    assert backend_called == [regular_local]
    assert get_state(db_session).woke_for_reboot is False


@pytest.mark.asyncio
async def test_auto_suspend_is_refused_while_a_reboot_is_armed():
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.AWAKE
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()):
        ok = await svc.enter_true_suspend("test", SleepTrigger.AUTO_IDLE, wake_at=None)

    assert ok is False
    assert backend_called == []


@pytest.mark.asyncio
async def test_manual_suspend_is_never_refused():
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.SOFT_SLEEP
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=None)

    assert ok is True
    assert len(backend_called) == 1


@pytest.mark.asyncio
async def test_blocked_reboot_does_not_prevent_a_normal_suspend():
    """Gates zu -> kein Aufschub, sonst hält ein blockierter Termin die Box wach."""
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.SOFT_SLEEP
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=False), \
         patch("app.services.power.sleep.scheduled_reboot.reset_before_suspend"), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("idle", SleepTrigger.AUTO_IDLE, wake_at=None)

    assert ok is True
    assert len(backend_called) == 1
