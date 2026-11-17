"""Der Sleep-Zustand des Primary ueber Prozessgrenzen hinweg (#823).

`SleepManagerService._current_state` lebt im Speicher eines Prozesses.
Produktiv laufen sechs API-Prozesse; nur der Primary betreibt Idle- und
Schedule-Loop und geht damit automatisch in den Soft-Sleep. Die anderen fuenf
hielten die Box danach weiter fuer wach -- Sync-Sperre, Preflight und Status
antworteten je nach Worker verschieden.

Der Primary veroeffentlicht seinen Zustand deshalb in einer Singleton-Zeile,
alle anderen lesen ihn von dort. Gleiches Muster wie `fan_runtime_store`.

Mit dem Zustand reist, was sonst nur der Primary weiss (#834): der
Idle-Zaehler, die pausierten Dienste und die heruntergefahrenen Platten.
Jede Veroeffentlichung ist der ganze Stand; ein kaputter Detailwert kostet
beim Lesen die Details, nicht den Zustand.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sleep import SleepRuntimeState
from app.schemas.sleep import SleepState

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


@dataclass(frozen=True)
class SleepRuntimeDetails:
    """Was der Primary ausser dem Zustand veroeffentlicht (#834)."""
    idle_seconds: float = 0.0
    paused_services: list[str] = field(default_factory=list)
    spun_down_disks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SleepRuntimeSnapshot:
    """Der veroeffentlichte Stand: Zustand, Zeitpunkt und Details."""
    state: SleepState
    since: Optional[datetime]
    idle_seconds: float = 0.0
    paused_services: list[str] = field(default_factory=list)
    spun_down_disks: list[str] = field(default_factory=list)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _parse_details(raw: Optional[str]) -> SleepRuntimeDetails:
    """Die Details aus der Spalte; alles Unlesbare wird zu "keine Details"."""
    if not raw:
        return SleepRuntimeDetails()
    try:
        data = json.loads(raw)
    except ValueError:
        logger.debug("sleep_runtime_state: details_json nicht lesbar")
        return SleepRuntimeDetails()
    if not isinstance(data, dict):
        return SleepRuntimeDetails()
    idle = data.get("idle_seconds")
    if isinstance(idle, bool) or not isinstance(idle, (int, float)) \
            or not math.isfinite(idle) or idle < 0:
        idle = 0.0
    return SleepRuntimeDetails(
        idle_seconds=float(idle),
        paused_services=_string_list(data.get("paused_services")),
        spun_down_disks=_string_list(data.get("spun_down_disks")),
    )


def publish_state(
    db: Session,
    state: SleepState,
    since: Optional[datetime],
    details: Optional[SleepRuntimeDetails] = None,
) -> bool:
    """Den Stand des Primary hinterlegen. Legt die Zeile an, falls noetig.

    Schreibt immer den ganzen Stand: ohne `details` stehen danach keine in
    der Zeile, auch wenn vorher welche da waren.

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
        row.details_json = (
            json.dumps({
                "idle_seconds": details.idle_seconds,
                "paused_services": list(details.paused_services),
                "spun_down_disks": list(details.spun_down_disks),
            })
            if details is not None else None
        )
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
    """Der veroeffentlichte Zustand samt Zeitpunkt; None wie `read_snapshot`."""
    snapshot = read_snapshot(db)
    if snapshot is None:
        return None
    return snapshot.state, snapshot.since


def read_snapshot(db: Session) -> Optional[SleepRuntimeSnapshot]:
    """Der veroeffentlichte Stand: Zustand, Zeitpunkt und Details.

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
    details = _parse_details(row.details_json)
    return SleepRuntimeSnapshot(
        state=state,
        since=since,
        idle_seconds=details.idle_seconds,
        paused_services=details.paused_services,
        spun_down_disks=details.spun_down_disks,
    )
