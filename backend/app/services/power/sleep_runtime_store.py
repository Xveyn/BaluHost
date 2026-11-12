"""Der Sleep-Zustand des Primary ueber Prozessgrenzen hinweg (#823).

`SleepManagerService._current_state` lebt im Speicher eines Prozesses.
Produktiv laufen sechs API-Prozesse; nur der Primary betreibt Idle- und
Schedule-Loop und geht damit automatisch in den Soft-Sleep. Die anderen fuenf
hielten die Box danach weiter fuer wach -- Sync-Sperre, Preflight und Status
antworteten je nach Worker verschieden.

Der Primary veroeffentlicht seinen Zustand deshalb in einer Singleton-Zeile,
alle anderen lesen ihn von dort. Gleiches Muster wie `fan_runtime_store`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sleep import SleepRuntimeState
from app.schemas.sleep import SleepState

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def publish_state(db: Session, state: SleepState, since: Optional[datetime]) -> bool:
    """Den Zustand des Primary hinterlegen. Legt die Zeile an, falls noetig.

    Returns:
        False bei einem Datenbankfehler -- der Aufrufer soll den Stand dann
        NICHT als veroeffentlicht verbuchen, sonst versucht er es nie wieder.
    """
    try:
        row = db.execute(
            select(SleepRuntimeState).where(SleepRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None:
            row = SleepRuntimeState(id=_SINGLETON_ID)
            db.add(row)
        row.current_state = SleepState(state).value
        row.state_since = since
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("sleep_runtime_state nicht schreibbar: %s", exc)
        return False


def read_state(db: Session) -> Optional[tuple[SleepState, Optional[datetime]]]:
    """Der veroeffentlichte Zustand samt Zeitpunkt.

    Returns:
        None, wenn nichts veroeffentlicht wurde, die Datenbank nicht lesbar
        ist oder der Wert kein gueltiger `SleepState` ist. None heisst
        "unbekannt", ausdruecklich NICHT "wach" -- der Aufrufer faellt dann auf
        seinen eigenen Zustand zurueck.
    """
    try:
        row = db.execute(
            select(SleepRuntimeState).where(SleepRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
    except Exception as exc:
        logger.debug("sleep_runtime_state nicht lesbar: %s", exc)
        return None
    if row is None:
        return None
    try:
        state = SleepState(row.current_state)
    except ValueError:
        logger.debug("sleep_runtime_state: unbekannter Zustand %r", row.current_state)
        return None
    since = row.state_since
    # SQLite liefert DateTime(timezone=True) naiv zurueck; geschrieben wird UTC.
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return state, since
