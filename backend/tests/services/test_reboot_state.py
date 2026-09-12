"""Zustands- und Konfigurationszugriff für den geplanten Systemneustart."""
import json
from datetime import datetime, timedelta, timezone

from app.models.scheduler_history import SchedulerConfig
from app.services.power import reboot_state
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_IDLE,
    get_state,
    load_enabled_config,
    next_reboot_due,
    to_local,
    to_utc,
)


def _write_config(db, *, enabled: bool, extra: dict | None = None) -> None:
    row = SchedulerConfig(
        scheduler_name="system_reboot",
        is_enabled=enabled,
        interval_seconds=604800,
        extra_config=json.dumps(extra) if extra is not None else None,
    )
    db.add(row)
    db.commit()


def test_get_state_creates_singleton(db_session):
    state = get_state(db_session)
    assert state.id == 1
    assert state.phase == PHASE_IDLE
    assert state.woke_for_reboot is False
    # Zweiter Aufruf legt keine zweite Zeile an.
    again = get_state(db_session)
    assert again.id == 1


def test_get_state_persists_changes(db_session):
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    db_session.commit()
    assert get_state(db_session).phase == PHASE_ARMED


def test_load_enabled_config_none_without_row(db_session):
    assert load_enabled_config(db_session) is None


def test_load_enabled_config_none_when_disabled(db_session):
    _write_config(db_session, enabled=False, extra={"weekday": 6, "time": "04:00"})
    assert load_enabled_config(db_session) is None


def test_load_enabled_config_returns_defaults_for_empty_extra(db_session):
    _write_config(db_session, enabled=True, extra=None)
    cfg = load_enabled_config(db_session)
    assert cfg is not None
    assert cfg.weekday == 6
    assert cfg.time == "04:00"
    assert cfg.retry_window_hours == 6
    assert cfg.warning_lead_minutes == 10


def test_load_enabled_config_reads_values(db_session):
    _write_config(
        db_session,
        enabled=True,
        extra={"weekday": 2, "time": "03:30", "retry_window_hours": 2,
               "warning_lead_minutes": 0},
    )
    cfg = load_enabled_config(db_session)
    assert (cfg.weekday, cfg.time, cfg.retry_window_hours, cfg.warning_lead_minutes) == (
        2, "03:30", 2, 0
    )


def test_load_enabled_config_survives_corrupt_json(db_session):
    row = SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config="{nicht json",
    )
    db_session.add(row)
    db_session.commit()
    cfg = load_enabled_config(db_session)
    assert cfg is not None and cfg.time == "04:00"  # Defaults statt Absturz


def test_next_reboot_due_none_when_disabled(db_session):
    assert next_reboot_due(db_session, datetime(2026, 9, 13, 1, 0)) is None


def test_next_reboot_due_uses_config(db_session):
    _write_config(db_session, enabled=True, extra={"weekday": 6, "time": "04:00"})
    due = next_reboot_due(db_session, datetime(2026, 9, 13, 1, 0))
    assert due == datetime(2026, 9, 13, 4, 0)


def test_utc_roundtrip_keeps_wall_clock():
    naive_local = datetime(2026, 9, 13, 4, 0)
    aware = to_utc(naive_local)
    assert aware.tzinfo is not None
    assert to_local(aware) == naive_local


def test_to_local_accepts_naive_as_utc():
    """Spiegelt `_is_always_awake`: naive Werte aus SQLite gelten als UTC."""
    aware = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    naive_from_db = aware.replace(tzinfo=None)
    assert to_local(naive_from_db) == to_local(aware)


def test_load_enabled_config_survives_non_dict_json(db_session):
    row = SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config="[1, 2, 3]",
    )
    db_session.add(row)
    db_session.commit()
    cfg = load_enabled_config(db_session)
    assert cfg is not None and cfg.time == "04:00"  # Defaults statt Absturz


def test_reset_to_idle_clears_all_date_bound_fields(db_session):
    from app.services.power.reboot_state import PHASE_ARMED, reset_to_idle

    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    state.deadline_at = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    state.execution_id = 42
    state.woke_for_reboot = True
    state.resuspend_wake_at = datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc)
    state.warned_for_due_at = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    db_session.commit()

    reset_to_idle(db_session, state)

    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert state.due_at is None
    assert state.deadline_at is None
    assert state.execution_id is None
    assert state.woke_for_reboot is False
    assert state.resuspend_wake_at is None
    assert state.warned_for_due_at is None
    assert state.phase_entered_at is not None


def test_reset_to_idle_sets_the_repeat_lock_when_given_one(db_session):
    """Ohne diese Sperre startet die Box nach dem Neustart in einer Schleife neu."""
    from app.services.power.reboot_state import reset_to_idle

    due = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    state = get_state(db_session)
    reset_to_idle(db_session, state, completed_due_at=due)
    # SQLite gibt timestamptz naiv zurück (dieselbe Annahme wie in `to_local`);
    # der Vergleich erfolgt deshalb naiv statt gegen den aware Ausgangswert.
    assert get_state(db_session).last_completed_due_at == due.replace(tzinfo=None)


def test_reset_to_idle_leaves_the_repeat_lock_alone_without_a_value(db_session):
    from app.services.power.reboot_state import reset_to_idle

    earlier = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
    state = get_state(db_session)
    state.last_completed_due_at = earlier
    db_session.commit()

    reset_to_idle(db_session, get_state(db_session))
    # SQLite gibt timestamptz naiv zurück (dieselbe Annahme wie in `to_local`);
    # der Vergleich erfolgt deshalb naiv statt gegen den aware Ausgangswert.
    assert get_state(db_session).last_completed_due_at == earlier.replace(tzinfo=None)


def test_same_instant_compares_moments_not_wall_clock():
    """Zwei Darstellungen desselben Moments mit verschiedenem Offset sind gleich."""
    from datetime import datetime, timedelta, timezone
    from app.services.power.reboot_state import same_instant

    plus_two = datetime(2026, 9, 13, 4, 0, tzinfo=timezone(timedelta(hours=2)))
    in_utc = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    assert same_instant(plus_two, in_utc) is True


def test_same_instant_treats_naive_stored_values_as_utc():
    """SQLite gibt timestamptz naiv zurück — sonst schlägt die Sperre dort fehl."""
    from datetime import datetime, timezone
    from app.services.power.reboot_state import same_instant

    aware = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    assert same_instant(aware.replace(tzinfo=None), aware) is True


def test_same_instant_is_false_for_none_and_for_other_moments():
    from datetime import datetime, timedelta, timezone
    from app.services.power.reboot_state import same_instant

    aware = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    assert same_instant(None, aware) is False
    assert same_instant(aware + timedelta(minutes=1), aware) is False
