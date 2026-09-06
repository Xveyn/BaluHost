"""Persistenz des AMD-Manual-Mode-Vorzustands ueber Worker-Grenzen (#411).

Der Vorzustand lag in einem modulweiten Dict in routes/fans.py und war damit
pro Uvicorn-Worker getrennt. Bei vier Workern bedient statistisch ein anderer
Prozess das Ausschalten als das Einschalten; dort fand `pop()` nichts, und
zurueckgeschrieben wurde ein GERATENER Vorzustand (`auto` / `2`).

Auf BaluNode steht `power_dpm_force_performance_level` auf `low`. Das Raten
haette dort eine bewusst gesetzte Stromspar-Einstellung ueberschrieben --
und zwar im Regelfall, nicht im Ausnahmefall.

Abgelegt wird an der Luefterzeile in `fan_configs`, wie schon der
Rueckgabewert aus #534. Anders als dort wird `updated_at` hier bewusst
mitgefuehrt: geschrieben wird nur auf eine ausdrueckliche Nutzeraktion hin,
nicht bei jedem Start -- die Zeile wurde also tatsaechlich angefasst, und das
Rangkriterium des Identitaets-Abgleichs bleibt aussagekraeftig.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.models.fans import FanConfig
from app.services.power.fan_gpu_manual import AmdManualState

logger = logging.getLogger(__name__)


def remember_manual_state(db, fan_id: str, state: AmdManualState) -> bool:
    """Vorzustand an der Luefterzeile ablegen.

    Returns:
        False, wenn es zu diesem Luefter keine Konfigurationszeile gibt --
        dann existiert kein Ablageort und der Aufrufer muss das wissen.
    """
    row = db.execute(
        select(FanConfig).where(FanConfig.fan_id == fan_id)
    ).scalar_one_or_none()
    if row is None:
        logger.warning(
            "Kein fan_configs-Eintrag fuer %s -- Manual-Mode-Vorzustand nicht "
            "gespeichert. Das Abschalten kann ihn spaeter nicht zurueckgeben.",
            fan_id,
        )
        return False

    row.gpu_manual_prev_level = state.previous_level
    row.gpu_manual_prev_pwm_enable = state.previous_pwm_enable
    db.commit()
    logger.info(
        "Manual-Mode-Vorzustand fuer %s gespeichert (level=%s, pwm_enable=%s)",
        fan_id, state.previous_level, state.previous_pwm_enable,
    )
    return True


def take_manual_state(db, fan_id: str) -> Optional[AmdManualState]:
    """Vorzustand lesen und dabei entfernen.

    Das Entfernen ist die eigentliche Zusage: bliebe der Wert stehen, gaebe
    ein zweites Abschalten ihn ein zweites Mal zurueck -- obwohl inzwischen
    jemand anderes den Zustand gesetzt haben kann.

    Returns:
        None, wenn nichts oder nur eine der beiden Spalten hinterlegt ist.
        Was dann geschieht, entscheidet der Aufrufer; hier wird nicht geraten.
    """
    row = db.execute(
        select(FanConfig).where(FanConfig.fan_id == fan_id)
    ).scalar_one_or_none()
    if row is None:
        return None

    level = row.gpu_manual_prev_level
    pwm_enable = row.gpu_manual_prev_pwm_enable
    if level is None or pwm_enable is None:
        # Halb gefuellt zaehlt als nicht gefuellt: ein Vorzustand aus nur
        # einer der beiden Groessen laesst sich nicht zurueckschreiben.
        return None

    row.gpu_manual_prev_level = None
    row.gpu_manual_prev_pwm_enable = None
    db.commit()
    return AmdManualState(previous_level=level, previous_pwm_enable=pwm_enable)
