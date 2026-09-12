"""Zustands- und Konfigurationszugriff für den geplanten Systemneustart.

Hier — und nur hier — liegt die Grenze zwischen der naiv-lokalen Rechnung in
`reboot_schedule.py` und der UTC-aware Persistenz in der Datenbank.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.scheduled_reboot import ScheduledRebootState
from app.models.scheduler_history import SchedulerConfig
from app.schemas.scheduler import RebootScheduleConfig
from app.services.power.reboot_schedule import next_weekday_occurrence

logger = logging.getLogger(__name__)

SCHEDULER_NAME = "system_reboot"

PHASE_IDLE = "idle"
PHASE_ARMED = "armed"
PHASE_EXECUTING = "executing"
PHASE_RESUSPEND_PENDING = "resuspend_pending"


def to_utc(naive_local: datetime) -> datetime:
    """Naive server-lokale Zeit -> UTC-aware.

    `astimezone()` auf einem naiven Wert liest ihn als lokale Zeit — genau das
    ist hier gewollt (dasselbe Vorgehen wie in `core_uptime.clamp_to_core_uptime_start`).
    """
    return naive_local.astimezone(timezone.utc)


def to_local(value: datetime) -> datetime:
    """DB-Wert -> naive server-lokale Zeit.

    Naive Werte gelten als UTC (SQLite liefert timestamptz naiv zurück) —
    dieselbe Annahme wie in `SleepManagerService._is_always_awake`.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().replace(tzinfo=None)


def get_state(db: Session) -> ScheduledRebootState:
    """Die Singleton-Zeile, bei Bedarf angelegt."""
    state = db.query(ScheduledRebootState).filter(ScheduledRebootState.id == 1).first()
    if state is None:
        state = ScheduledRebootState(id=1, phase=PHASE_IDLE, woke_for_reboot=False)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def load_enabled_config(db: Session) -> Optional[RebootScheduleConfig]:
    """Die Konfiguration, oder `None` wenn das Feature aus ist.

    Kein Row = aus. Unlesbares JSON fällt auf die Defaults zurück statt zu
    werfen: ein kaputtes Konfigurationsfeld darf den Sleep-Tick nicht abreißen.
    """
    row = (
        db.query(SchedulerConfig)
        .filter(SchedulerConfig.scheduler_name == SCHEDULER_NAME)
        .first()
    )
    if row is None or not row.is_enabled:
        return None

    raw: dict = {}
    if row.extra_config:
        try:
            parsed = json.loads(row.extra_config)
            if isinstance(parsed, dict):
                raw = parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("system_reboot: extra_config unlesbar — nutze Defaults")

    try:
        return RebootScheduleConfig(**raw)
    except Exception as exc:
        logger.warning("system_reboot: extra_config ungültig (%s) — nutze Defaults", exc)
        return RebootScheduleConfig()


def next_reboot_due(db: Session, now_local: datetime) -> Optional[datetime]:
    """Nächster Neustart-Termin als naive lokale Zeit, oder `None`."""
    config = load_enabled_config(db)
    if config is None:
        return None
    try:
        return next_weekday_occurrence(now_local, config.weekday, config.time)
    except ValueError as exc:
        logger.warning("system_reboot: Termin nicht berechenbar (%s)", exc)
        return None


def reset_to_idle(
    db: Session,
    state: ScheduledRebootState,
    *,
    completed_due_at: Optional[datetime] = None,
) -> None:
    """Zurück auf `idle` und alle Termin-gebundenen Felder räumen.

    `completed_due_at` setzt die Wiederholungssperre. Sie MUSS auf jedem Weg
    aus `armed` heraus gesetzt werden — Erfolg, Fristablauf, Ausführungsfehler
    und Rücksetzen vor einem Suspend. Fehlt einer davon, erkennt der Automat
    denselben Termin erneut als fällig und startet in einer Schleife neu.
    """
    if completed_due_at is not None:
        state.last_completed_due_at = completed_due_at
    state.phase = PHASE_IDLE
    state.due_at = None
    state.deadline_at = None
    state.execution_id = None
    state.woke_for_reboot = False
    state.resuspend_wake_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()
