"""Zustandsautomat des geplanten Systemneustarts.

Der wichtigste Test hier ist `test_no_reboot_loop_after_boot`. Ohne die
Wiederholungssperre würde die Box sechs Stunden lang alle drei Minuten neu
starten.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.scheduler_history import SchedulerConfig, SchedulerExecution, SchedulerStatus
from app.services.power import scheduled_reboot
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_EXECUTING,
    PHASE_IDLE,
    PHASE_RESUSPEND_PENDING,
    get_state,
    same_instant,
    to_utc,
)

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)


def _enable(db, **overrides):
    extra = {"weekday": 6, "time": "04:00", "retry_window_hours": 6,
             "warning_lead_minutes": 10}
    extra.update(overrides)
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config=json.dumps(extra),
    ))
    db.commit()


def _sleep_service():
    svc = MagicMock()
    svc._load_config.return_value = SimpleNamespace(idle_cpu_threshold=5.0)
    svc._load_core_uptime.return_value = (False, [])
    svc._is_system_idle.return_value = True
    svc._get_activity_metrics.return_value = SimpleNamespace()
    return svc


@pytest.fixture(autouse=True)
def _gates_open_and_no_real_reboot(monkeypatch):
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: False)
    monkeypatch.setattr(scheduled_reboot, "run_reboot_command", lambda: (True, "test"))
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)


def _at(db, now, awake=True):
    with patch("app.services.power.scheduled_reboot._now_local", return_value=now):
        scheduled_reboot.tick(db, _sleep_service(), awake=awake)


# --- armen ---------------------------------------------------------------

def test_disabled_never_arms(db_session):
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_IDLE


def test_arms_and_executes_when_due_and_gates_open(db_session):
    _enable(db_session)
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_EXECUTING
    assert state.execution_id is not None


def test_does_not_arm_before_the_time(db_session):
    _enable(db_session)
    _at(db_session, SUNDAY_0400 - timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_IDLE


# --- Wiederholungssperre -------------------------------------------------

def test_no_reboot_loop_after_boot(db_session):
    """DER Test. Nach dem Boot liegt derselbe Termin noch in der Frist."""
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    with patch("app.services.power.scheduled_reboot._now_local",
               return_value=SUNDAY_0400 + timedelta(minutes=3)):
        assert scheduled_reboot.on_boot(db_session) == "completed"

    reboots = []
    with patch.object(scheduled_reboot, "run_reboot_command",
                      side_effect=lambda: reboots.append(1) or (True, "x")):
        for minute in (4, 10, 60, 300):
            _at(db_session, SUNDAY_0400 + timedelta(minutes=minute))

    assert reboots == []
    assert get_state(db_session).phase == PHASE_IDLE


def test_repeat_lock_set_on_deadline_expiry(db_session):
    _enable(db_session, retry_window_hours=1)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=1))
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(hours=1, minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    # Auf den Wert prüfen, nicht auf `is not None`: genau der Moment ist das
    # Sicherheitsmerkmal. Ein `to_utc(now)` käme durch eine Null-Prüfung durch
    # und würde den falschen Termin sperren.
    assert same_instant(state.last_completed_due_at, to_utc(SUNDAY_0400))


def test_repeat_lock_set_on_command_failure(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(
        scheduled_reboot, "run_reboot_command", lambda: (False, "sudo: no entry")
    )
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert same_instant(state.last_completed_due_at, to_utc(SUNDAY_0400))


def test_repeat_lock_survives_the_spring_forward_gap(db_session, monkeypatch):
    """02:30 existiert am Umstellungssonntag nicht — die Sperre muss halten.

    `to_local(to_utc(x))` ist dort keine Identität: derselbe Moment kommt eine
    Stunde später als Ortszeit zurück. Ein Vergleich in Ortszeit würde die
    Sperre aushebeln und die Box über die ganze Nachholfrist in einer Schleife
    neu starten. Die Verschiebung wird hier simuliert statt der echten
    Zeitzone überlassen, weil die CI in UTC läuft — dort gibt es gar keine
    Umstellung und der Test wäre wirkungslos.
    """
    gap_due = datetime(2026, 3, 29, 2, 30)  # Sonntag, in Europe/Berlin nicht existent
    stored_utc = to_utc(gap_due)
    _enable(db_session, time="02:30")

    state = get_state(db_session)
    state.last_completed_due_at = stored_utc
    db_session.commit()

    real_to_local = scheduled_reboot.to_local

    def _spring_forward(value):
        # Genau das, was Europe/Berlin an diesem Tag tut.
        if value == stored_utc:
            return gap_due + timedelta(hours=1)
        return real_to_local(value)

    monkeypatch.setattr(scheduled_reboot, "to_local", _spring_forward)

    reboots = []
    with patch.object(scheduled_reboot, "run_reboot_command",
                      side_effect=lambda: reboots.append(1) or (True, "x")):
        _at(db_session, gap_due + timedelta(minutes=3))

    assert reboots == []
    assert get_state(db_session).phase == PHASE_IDLE


def test_phase_is_committed_before_the_reboot_command(db_session):
    """Nach dem Neustart ist diese Zeile der einzige Beweis, dass er geplant war."""
    _enable(db_session)
    seen = []

    def _capture():
        seen.append(get_state(db_session).phase)
        return True, "test"

    with patch.object(scheduled_reboot, "run_reboot_command", side_effect=_capture):
        _at(db_session, SUNDAY_0400 + timedelta(minutes=1))

    assert seen == [PHASE_EXECUTING]


def test_failed_command_marks_execution_failed(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(
        scheduled_reboot, "run_reboot_command", lambda: (False, "sudo: no entry")
    )
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    row = db_session.query(SchedulerExecution).filter(
        SchedulerExecution.scheduler_name == "system_reboot"
    ).first()
    assert row.status == SchedulerStatus.FAILED.value
    assert "sudo: no entry" in (row.error_message or "")


# --- Gates und Nachholen -------------------------------------------------

def test_blocked_stays_armed_and_records_reason(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_ARMED
    assert state.last_skip_reason == scheduled_reboot.SKIP_DISPLAYS


def test_retries_when_gate_opens_within_the_window(db_session, monkeypatch):
    _enable(db_session)
    blocked = {"value": True}
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: blocked["value"])

    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_ARMED

    blocked["value"] = False
    _at(db_session, SUNDAY_0400 + timedelta(hours=2))
    assert get_state(db_session).phase == PHASE_EXECUTING


def test_disabling_the_schedule_closes_the_open_execution(db_session, monkeypatch):
    """Sonst bliebe die Zeile auf `running` und blockte Gate 3 dauerhaft.

    Gate 3 schließt nur die *eigene* Execution aus — eine Waise zählt dort als
    fremder Wartungsjob und verhindert jeden künftigen Neustart, bis ein
    Prozessneustart sie aufräumt.
    """
    _enable(db_session)
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_ARMED
    execution_id = state.execution_id
    assert execution_id is not None

    db_session.query(SchedulerConfig).filter(
        SchedulerConfig.scheduler_name == "system_reboot"
    ).update({"is_enabled": False})
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(minutes=2))

    assert get_state(db_session).phase == PHASE_IDLE
    row = db_session.query(SchedulerExecution).filter(
        SchedulerExecution.id == execution_id
    ).first()
    assert row.status == SchedulerStatus.CANCELLED.value
    assert row.completed_at is not None


# --- Korrupter Zustand ---------------------------------------------------

def test_armed_without_due_at_keeps_the_existing_lock(db_session):
    """Aufräumen ja, bestehende Sperre wegwerfen nein."""
    _enable(db_session)
    earlier = to_utc(SUNDAY_0400 - timedelta(days=7))
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = None
    state.deadline_at = None
    state.last_completed_due_at = earlier
    db_session.commit()

    _at(db_session, SUNDAY_0400 - timedelta(hours=2))

    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert same_instant(state.last_completed_due_at, earlier)


def test_on_boot_with_executing_but_no_due_at_keeps_the_existing_lock(db_session):
    """Ohne diesen Zweig schriebe `on_boot` die Sperre auf None — Schleife."""
    earlier = to_utc(SUNDAY_0400 - timedelta(days=7))
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = None
    state.woke_for_reboot = True
    state.last_completed_due_at = earlier
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "stale"
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert same_instant(state.last_completed_due_at, earlier)


# --- Vorwarnung ----------------------------------------------------------

def test_warning_sent_once_when_awake(db_session):
    _enable(db_session)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=5))
        _at(db_session, SUNDAY_0400 - timedelta(minutes=4))
    assert len(sent) == 1


def test_no_warning_when_suspended(db_session):
    _enable(db_session)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=5), awake=False)
    assert sent == []


def test_lead_zero_disables_the_warning(db_session):
    _enable(db_session, warning_lead_minutes=0)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=1))
    assert sent == []


# --- Boot-Übergabe -------------------------------------------------------

def test_on_boot_without_pending_reboot_returns_none(db_session):
    assert scheduled_reboot.on_boot(db_session) is None


def test_on_boot_schedules_resuspend_when_woken_for_reboot(db_session):
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = to_utc(datetime(2026, 9, 13, 8, 0))
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    state = get_state(db_session)
    assert state.phase == PHASE_RESUSPEND_PENDING
    # Weg 1a der Wiederholungssperre — der Produktionspfad. Dieser Zweig setzt
    # `last_completed_due_at` direkt statt über `reset_to_idle`, weil er nach
    # `resuspend_pending` wechselt; ohne diese Zusicherung wäre er ungetestet.
    assert same_instant(state.last_completed_due_at, to_utc(SUNDAY_0400))


def test_on_boot_resuspends_even_without_a_wake_time(db_session):
    """resuspend_wake_at=None ist gültig: Suspend ohne RTC-Alarm."""
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    assert get_state(db_session).phase == PHASE_RESUSPEND_PENDING


def test_on_boot_stays_awake_when_not_woken_for_reboot(db_session):
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = False
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    assert get_state(db_session).phase == PHASE_IDLE


def test_on_boot_treats_stale_executing_as_failure(db_session):
    """Kein Wieder-Suspend bei unklarem Ausgang — sonst kommt niemand mehr dran."""
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = to_utc(datetime(2026, 9, 13, 8, 0))
    state.phase_entered_at = datetime.now(timezone.utc) - timedelta(hours=5)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "stale"
    assert get_state(db_session).phase == PHASE_IDLE


# --- Suspend-Wechselwirkung ----------------------------------------------

def test_should_defer_suspend_only_when_gates_open(db_session):
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    db_session.commit()

    assert scheduled_reboot.should_defer_suspend(db_session, _sleep_service()) is True

    with patch.object(scheduled_reboot, "displays_block", return_value=True):
        assert scheduled_reboot.should_defer_suspend(db_session, _sleep_service()) is False


def test_reset_before_suspend_clears_armed_state(db_session):
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    db_session.commit()

    scheduled_reboot.reset_before_suspend(db_session)
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert same_instant(state.last_completed_due_at, to_utc(SUNDAY_0400))


# --- Wieder-Suspend nach dem Neustart (Schnittstelle zu Task 8) -----------

def test_resuspend_target_reports_the_wake_time(db_session):
    wake_at = to_utc(datetime(2026, 9, 13, 8, 0))
    state = get_state(db_session)
    state.phase = PHASE_RESUSPEND_PENDING
    state.resuspend_wake_at = wake_at
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    pending, reported = scheduled_reboot.resuspend_target(db_session)
    assert pending is True
    assert same_instant(reported, wake_at)


def test_resuspend_target_reports_none_without_a_wake_time(db_session):
    """Suspend ohne RTC-Alarm: `True` mit `None` ist gültig, nicht `False`."""
    state = get_state(db_session)
    state.phase = PHASE_RESUSPEND_PENDING
    state.resuspend_wake_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.resuspend_target(db_session) == (True, None)


def test_resuspend_target_is_silent_in_other_phases(db_session):
    assert scheduled_reboot.resuspend_target(db_session) == (False, None)


def test_resuspend_pending_holds_within_the_timeout(db_session):
    state = get_state(db_session)
    state.phase = PHASE_RESUSPEND_PENDING
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(minutes=10))
    assert get_state(db_session).phase == PHASE_RESUSPEND_PENDING


def test_resuspend_timeout_is_thirty_minutes():
    """Den Wert selbst festnageln.

    Der Timeout-Test unten rechnet bewusst absolut (31 Minuten) statt relativ
    zu dieser Konstante — sonst verschöbe eine Änderung der Konstante die
    eigene Messlatte mit und der Test könnte sie nie fangen.
    """
    assert scheduled_reboot.RESUSPEND_TIMEOUT == timedelta(minutes=30)


def test_resuspend_pending_gives_up_after_the_timeout(db_session):
    """Danach übernimmt die normale Auto-Idle-Mechanik."""
    state = get_state(db_session)
    state.phase = PHASE_RESUSPEND_PENDING
    state.phase_entered_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(minutes=10))
    assert get_state(db_session).phase == PHASE_IDLE


def test_resuspend_pending_without_phase_entered_at_resets(db_session):
    """Ohne Zeitstempel ist der Timeout nicht messbar — nicht ewig hängen bleiben."""
    state = get_state(db_session)
    state.phase = PHASE_RESUSPEND_PENDING
    state.phase_entered_at = None
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(minutes=10))
    assert get_state(db_session).phase == PHASE_IDLE
