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
