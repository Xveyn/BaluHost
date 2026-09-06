"""Wortlaut des Schreibrechts ueber Worker-Grenzen hinweg (#552).

`LinuxFanControlBackend._has_write_permission` ist ein Instanz-Attribut. Bei
vier Uvicorn-Workern gibt es damit vier Wahrheiten ueber denselben Zustand
derselben Hardware -- obwohl alle vier als derselbe Nutzer mit denselben
sudoers-Regeln laufen und die Antwort per Konstruktion identisch sein muesste.

Geheilt hat sich nur, wer schreibt: der Primary ueber den Regelkreis. Die drei
Follower blieben auf ihrem Startwert stehen.

Der Primary veroeffentlicht seinen Stand deshalb in einer Singleton-Zeile,
alle Worker lesen ihn von dort. Dasselbe Muster tragen `PowerRuntimeState`
und `GpuPowerRuntimeState` -- letztere fuehrt sogar dieselbe Spalte fuer
denselben Zweck.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy import select

from app.models.fans import FanRuntimeState

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def read_write_permission(db) -> Optional[bool]:
    """Der veroeffentlichte Stand.

    Returns:
        None, wenn noch nichts veroeffentlicht wurde. Das ist ausdruecklich
        NICHT dasselbe wie "kein Schreibrecht": eine frisch migrierte
        Datenbank meldete sonst readonly, obwohl niemand etwas gemessen hat.
        Der Aufrufer faellt dann auf seine eigene Messung zurueck.
    """
    try:
        row = db.execute(
            select(FanRuntimeState).where(FanRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
    except Exception as exc:
        # Der Rechtezustand ist eine Anzeige, kein Regelungseingang -- eine
        # klemmende Datenbank darf get_status() nicht mitreissen.
        logger.debug("fan_runtime_state nicht lesbar: %s", exc)
        return None
    return None if row is None else bool(row.has_write_permission)


def publish_write_permission(db, may_write: bool) -> bool:
    """Den eigenen Stand hinterlegen. Legt die Zeile an, falls noetig.

    Returns:
        False bei einem Datenbankfehler -- der Aufrufer soll dann seinen
        gemerkten Stand NICHT als veroeffentlicht verbuchen, sonst versucht
        er es nie wieder.
    """
    try:
        row = db.execute(
            select(FanRuntimeState).where(FanRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None:
            row = FanRuntimeState(id=_SINGLETON_ID)
            db.add(row)
        row.has_write_permission = bool(may_write)
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("fan_runtime_state nicht schreibbar: %s", exc)
        return False
