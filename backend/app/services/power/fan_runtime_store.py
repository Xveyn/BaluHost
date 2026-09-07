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

import json
import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fans import FanRuntimeState

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def read_write_permission(db: Session) -> Optional[bool]:
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


def read_denied_fans(db: Session) -> Optional[set]:
    """Die vom Primary gemeldeten Kanaele ohne Schreibrecht (#568 Punkt 2).

    Returns:
        None, wenn nichts veroeffentlicht wurde -- das ist ausdruecklich NICHT
        dasselbe wie "kein Kanal betroffen". Der Aufrufer soll dann seine
        eigene Sicht behalten statt eine leere Menge als Tatsache zu nehmen.
    """
    try:
        row = db.execute(
            select(FanRuntimeState).where(FanRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
    except Exception as exc:
        logger.debug("fan_runtime_state nicht lesbar: %s", exc)
        return None
    if row is None or not row.denied_fan_ids:
        return None
    try:
        werte = json.loads(row.denied_fan_ids)
    except (ValueError, TypeError) as exc:
        logger.debug("denied_fan_ids nicht lesbar: %s", exc)
        return None
    return set(werte) if isinstance(werte, list) else None


def read_released_fans(db: Session) -> dict:
    """Die freigegebenen Kanaele mit ihrem Zustand (#534).

    Returns:
        `{fan_id: "released" | "abandoned"}`. Eine leere Abbildung heisst
        "kein Kanal freigegeben" -- anders als bei read_denied_fans gibt es
        hier kein None, weil der Besitzzustand ausschliesslich hier lebt und
        nicht mit einer prozesslokalen Sicht zusammengefuehrt wird.
    """
    try:
        row = db.execute(
            select(FanRuntimeState).where(FanRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
    except Exception as exc:
        logger.debug("fan_runtime_state nicht lesbar: %s", exc)
        return {}
    if row is None or not row.released_fans:
        return {}
    try:
        werte = json.loads(row.released_fans)
    except (ValueError, TypeError) as exc:
        logger.debug("released_fans nicht lesbar: %s", exc)
        return {}
    if not isinstance(werte, dict):
        return {}

    # Zwei Formen werden gelesen: der blosse Zustand als Zeichenkette (die
    # Form, mit der #534 Punkt 1 ausgeliefert wurde) und das Objekt mit
    # Zustand UND Grund (seit Punkt 2). Ohne diese Nachsicht saehe der erste
    # Zyklus nach dem Deploy die alte Zeile als unlesbar an und verloere den
    # Freigabe-Zustand still.
    vereinheitlicht = {}
    for fan_id, wert in werte.items():
        if isinstance(wert, str):
            vereinheitlicht[fan_id] = {"state": wert, "reason": None}
        elif isinstance(wert, dict) and "state" in wert:
            vereinheitlicht[fan_id] = {
                "state": wert["state"],
                "reason": wert.get("reason"),
            }
    return vereinheitlicht


def publish_released_fans(db: Session, released: dict) -> bool:
    """Die freigegebenen Kanaele hinterlegen. Nur der Primary schreibt.

    Returns:
        False bei einem Datenbankfehler -- der Aufrufer soll seinen Stand dann
        NICHT als veroeffentlicht verbuchen.
    """
    try:
        row = db.execute(
            select(FanRuntimeState).where(FanRuntimeState.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None:
            row = FanRuntimeState(id=_SINGLETON_ID)
            db.add(row)
        row.released_fans = json.dumps(released, sort_keys=True)
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("released_fans nicht schreibbar: %s", exc)
        return False


def publish_write_permission(db: Session, may_write: bool,
                             denied_fan_ids: Optional[set] = None) -> bool:
    """Den eigenen Stand hinterlegen. Legt die Zeile an, falls noetig.

    Args:
        denied_fan_ids: die Kanaele, auf denen ein EACCES beobachtet wurde.
            None laesst die gespeicherte Liste unberuehrt -- so bleibt der
            Aufrufer, der nur das Flag kennt, rueckwaertskompatibel.

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
        if denied_fan_ids is not None:
            row.denied_fan_ids = json.dumps(sorted(denied_fan_ids))
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("fan_runtime_state nicht schreibbar: %s", exc)
        return False
