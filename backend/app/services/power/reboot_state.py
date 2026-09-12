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


def same_instant(stored: Optional[datetime], candidate_utc: datetime) -> bool:
    """Ob ein DB-Zeitstempel denselben Moment meint wie `candidate_utc`.

    Naive Werte aus SQLite gelten als UTC — dieselbe Annahme wie in `to_local`.
    Der Vergleich läuft bewusst UTC-seitig: `to_local(to_utc(x))` ist an einem
    Sommerzeit-Umstellungstag keine Identität, und ein Vergleich in Ortszeit
    würde dort die Wiederholungssperre stillschweigend aushebeln.
    """
    if stored is None:
        return False
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    return stored == candidate_utc


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
            else:
                logger.warning(
                    "system_reboot: extra_config kein Objekt — nutze Defaults"
                )
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


def claim_wakeup(
    db: Session,
    regular_utc: Optional[datetime],
    now_local: datetime,
) -> Optional[datetime]:
    """Der Neustart-Termin stiehlt die Weckzeit — und legt die gestohlene daneben.

    Liegt der nächste Neustart-Termin vor `regular_utc`, wird er zurückgegeben,
    `woke_for_reboot` gesetzt und `regular_utc` als `resuspend_wake_at`
    hinterlegt. Genau das ist „bis zum regulären Aufwachzeitpunkt": nicht ein
    nach dem Neustart neu geratener Wert, sondern derselbe, der ohne den
    Neustart gegolten hätte. `regular_utc` darf `None` sein.

    Schreibt bewusst in die Datenbank — der Aufrufer steht unmittelbar vor dem
    Suspend, und danach gibt es keine Gelegenheit mehr dazu.
    """
    due_local = next_reboot_due(db, now_local)
    if due_local is None:
        return regular_utc

    due_utc = to_utc(due_local)
    if regular_utc is not None:
        regular_aware = regular_utc
        if regular_aware.tzinfo is None:
            regular_aware = regular_aware.replace(tzinfo=timezone.utc)
        if regular_aware <= due_utc:
            return regular_utc

    state = get_state(db)
    state.woke_for_reboot = True
    state.resuspend_wake_at = regular_utc
    db.commit()
    logger.info(
        "Weckzeit auf den Neustart-Termin %s vorgezogen (regulär war %s)",
        due_local, regular_utc,
    )
    return due_utc


def clear_wakeup_claim(db: Session) -> None:
    """Nach einem gescheiterten Suspend: das Flag wieder abräumen."""
    state = get_state(db)
    if state.woke_for_reboot:
        state.woke_for_reboot = False
        state.resuspend_wake_at = None
        db.commit()


def open_execution(db: Session) -> int:
    """Legt die `scheduler_executions`-Zeile für einen fälligen Termin an."""
    from app.models.scheduler_history import (
        SchedulerExecution,
        SchedulerStatus,
        TriggerType,
    )

    row = SchedulerExecution(
        scheduler_name=SCHEDULER_NAME,
        trigger_type=TriggerType.SCHEDULED.value,
        started_at=datetime.now(timezone.utc),
        status=SchedulerStatus.RUNNING.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def close_execution(
    db: Session,
    execution_id: Optional[int],
    status: str,
    *,
    error: Optional[str] = None,
    result: Optional[str] = None,
) -> None:
    """Schließt die Execution ab. Fehlt die Zeile, passiert nichts."""
    from app.models.scheduler_history import SchedulerExecution

    if execution_id is None:
        return
    row = db.query(SchedulerExecution).filter(
        SchedulerExecution.id == execution_id
    ).first()
    if row is None:
        return
    completed = datetime.now(timezone.utc)
    row.status = status
    row.completed_at = completed
    row.error_message = error
    row.result_summary = result
    started = row.started_at
    if started is not None:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        row.duration_ms = int((completed - started).total_seconds() * 1000)
    db.commit()


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
    state.warned_for_due_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()
