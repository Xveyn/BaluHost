"""Persistenz der GPU-Akustik-Konfiguration (#516).

Singleton-Zeile, JSON-Feld -- gleiches Muster wie config_store.py fuer die
GPU-Power-Konfiguration.

Zwei Ladewege, weil 'keine Zeile' und 'Lesen fehlgeschlagen' verschiedene
Antworten verlangen: der Startpfad darf fail-soft weitermachen (ohne
Konfiguration verwaltet BaluHost eben nichts), ein Schreibpfad darf es nicht --
er wuerde sonst die beobachtete Baseline mit leeren Vorgaben ueberschreiben.

Die beiden mischenden Schreibfunktionen (capture_baseline, store_desired)
lesen die Zeile in ihrer EIGENEN Session frisch und aendern nur die Felder,
um die es geht. Damit kann ein veralteter Snapshot aus einem anderen Uvicorn
-Worker weder die Baseline kontaminieren noch ein desired-Feld verlieren.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


class AcousticsConfigError(RuntimeError):
    """Die Konfiguration liess sich nicht lesen oder nicht schreiben."""


class AcousticsConfigUnreadable(AcousticsConfigError):
    """Die gespeicherte Zeile war nicht lesbar.

    Ausdruecklich NICHT dasselbe wie 'es gibt noch keine Zeile': auf einem
    fehlgeschlagenen Load darf kein Schreibpfad aufbauen, sonst geht die
    beobachtete Baseline unwiederbringlich verloren (#516).
    """


def _read_row(db: Session) -> Optional[GpuFanAcousticsConfigDb]:
    return db.execute(
        select(GpuFanAcousticsConfigDb)
        .where(GpuFanAcousticsConfigDb.id == _SINGLETON_ID)
    ).scalar_one_or_none()


def load_acoustics_config(db: Session) -> GpuFanAcousticsConfig:
    """Die gespeicherte Konfiguration.

    Returns:
        Leere Vorgaben, wenn es noch keine Zeile gibt -- das ist der
        gueltige Zustand direkt nach der Migration.

    Raises:
        AcousticsConfigUnreadable: wenn die Zeile existiert, aber nicht
            gelesen werden konnte. Der Aufrufer entscheidet, ob er
            fail-soft weitermacht (Startpfad) oder abbricht (Schreibpfad).
    """
    try:
        row = _read_row(db)
    except Exception as exc:
        logger.warning("GPU-Akustik-Konfiguration nicht lesbar: %s", exc)
        raise AcousticsConfigUnreadable(str(exc)) from exc

    if row is None or not row.config_json:
        return GpuFanAcousticsConfig()

    try:
        return GpuFanAcousticsConfig.model_validate_json(row.config_json)
    except Exception as exc:
        logger.warning("GPU-Akustik-Konfiguration nicht lesbar: %s", exc)
        raise AcousticsConfigUnreadable(str(exc)) from exc


def load_acoustics_config_fail_soft(db: Session) -> GpuFanAcousticsConfig:
    """Wie load_acoustics_config, aber ein Lesefehler liefert leere Vorgaben.

    Fuer die Pfade, die nur lesen oder anwenden: ein Fehler darf den Start
    nicht verhindern, und ohne Konfiguration verwaltet BaluHost eben nichts.
    Ein Pfad, der die Zeile ANFASST, muss die harte Variante nehmen.
    """
    try:
        return load_acoustics_config(db)
    except AcousticsConfigUnreadable:
        return GpuFanAcousticsConfig()


def save_acoustics_config(db: Session, config: GpuFanAcousticsConfig) -> bool:
    """Die ganze Konfiguration ablegen. False bei einem Datenbankfehler.

    Ueberschreibt beide Bloecke. Fuer nebenlaeufige Pfade sind
    capture_baseline und store_desired die richtige Wahl -- sie mischen
    feldweise statt das Objekt zu ersetzen.
    """
    try:
        row = _read_row(db)
        if row is None:
            row = GpuFanAcousticsConfigDb(id=_SINGLETON_ID)
            db.add(row)
        row.config_json = config.model_dump_json()
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("GPU-Akustik-Konfiguration nicht schreibbar: %s", exc)
        return False


def _merge_and_store(db: Session, block: str,
                     values: Mapping[str, Optional[int]],
                     *, only_if_empty: bool) -> GpuFanAcousticsConfig:
    """Einen Block feldweise aendern -- Lesen und Schreiben in EINER Session.

    Raises:
        AcousticsConfigUnreadable: die vorhandene Zeile war nicht lesbar.
            Es wird dann nichts geschrieben; die Zeile bleibt, wie sie ist.
        AcousticsConfigError: der Schreibvorgang selbst schlug fehl.
    """
    config = load_acoustics_config(db)
    current = getattr(config, block).model_dump()

    changed = False
    for name, value in values.items():
        if name not in current:
            continue
        if only_if_empty and current[name] is not None:
            continue
        if current[name] == value:
            continue
        current[name] = value
        changed = True

    if not changed:
        return config

    setattr(config, block, type(getattr(config, block))(**current))
    if not save_acoustics_config(db, config):
        raise AcousticsConfigError(
            f"GPU-Akustik-Konfiguration ({block}) nicht schreibbar")
    return config


def capture_baseline(db: Session,
                     observed: Mapping[str, int]) -> GpuFanAcousticsConfig:
    """Beobachtete Ist-Werte als Baseline ablegen -- nur, wo noch nichts steht.

    Die Zeile wird in DIESER Session frisch gelesen. Ein Aufrufer mit einem
    veralteten Snapshot kann damit keine bereits erfasste Baseline
    ueberschreiben -- und genau das waere die Kontamination mit BaluHosts
    eigenem Eingriff, gegen die die Baseline gebaut ist (#516).
    """
    return _merge_and_store(db, "baseline", observed, only_if_empty=True)


def store_desired(db: Session,
                  desired: Mapping[str, Optional[int]]) -> GpuFanAcousticsConfig:
    """Nur die uebergebenen desired-Felder setzen, den Rest der Zeile lassen.

    Feldweise statt als ganzes Objekt: ein PUT, der das komplette Objekt
    zurueckschreibt, verliert die Aenderung eines nebenlaeufigen Workers.
    """
    return _merge_and_store(db, "desired", desired, only_if_empty=False)
