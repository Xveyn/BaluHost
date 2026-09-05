"""Ueberfuehrt hwmon-indizierte fan_configs auf stabile Kennungen (#532).

Reines Modul: es bekommt die Scan-Fakten uebergeben und fasst kein sysfs an.
Der Aufrufer haelt die Transaktion.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fans import (
    CompositeTempSensor,
    FanConfig,
    FanScheduleEntry,
    TempSensorLabel,
)

logger = logging.getLogger(__name__)

_LEGACY_FAN_ID = re.compile(r"^hwmon(\d+)_pwm(\d+)$")
_LEGACY_SENSOR_ID = re.compile(r"^hwmon(\d+)_temp(\d+)$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ChipFacts:
    """Was der Scan ueber einen heute vorhandenen Chip weiss."""
    key: str
    pwm_channels: frozenset
    ambiguous: bool


@dataclass
class ReconcileReport:
    renamed: List[Tuple[str, str]] = field(default_factory=list)
    deactivated: List[str] = field(default_factory=list)
    skipped_absent: List[str] = field(default_factory=list)
    unresolved_sensors: List[str] = field(default_factory=list)


def _chip_from_name(name: Optional[str]) -> Optional[str]:
    """"nct6798 PWM1" -> "nct6798". Ohne " PWM" kein Kandidat.

    Der Dev-Backend erzeugt Namen wie "CPU Fan (Simulated)"; ein naives
    rsplit gaebe dort den ganzen Namen als Chip-Namen zurueck.
    """
    if not name:
        return None
    index = name.rfind(" PWM")
    if index <= 0:
        return None
    return name[:index]


def _map_sensor(sensor_id: Optional[str], sensor_map: Dict[str, str],
                cpu_sensor_id: Optional[str],
                report: ReconcileReport) -> Optional[str]:
    """Bildet eine Alt-Sensor-ID ueber sensor_map auf die stabile Form ab.

    Regel R2: nur die nackte Alt-Form (nach optionalem "hwmon:"-Praefix)
    im Muster "hwmonX_tempY" ist ueberhaupt ein Abbildungskandidat. Ohne
    diese Einschraenkung wuerde ein zweiter Lauf jede bereits stabile ID
    (z. B. "hwmon:k10temp-pci-00c3:temp1") erneut durch die Map schicken,
    dort nicht finden und faelschlich als unaufloesbar melden -- bei
    jedem Dienststart eine WARNING, obwohl nichts falsch ist.
    """
    if not sensor_id:
        return cpu_sensor_id
    bare = sensor_id[len("hwmon:"):] if sensor_id.startswith("hwmon:") else sensor_id
    if not _LEGACY_SENSOR_ID.match(bare):
        return sensor_id                               # bereits stabil oder unbekanntes Format
    mapped = sensor_map.get(bare)
    if mapped:
        return mapped
    report.unresolved_sensors.append(bare)
    logger.warning(
        "Sensor %s nicht aufloesbar, Rueckfall auf den CPU-Default %s",
        sensor_id, cpu_sensor_id,
    )
    return cpu_sensor_id


def reconcile_fan_identities(
    db: Session,
    *,
    chips: Dict[str, ChipFacts],
    sensor_map: Dict[str, str],
    cpu_sensor_id: Optional[str],
) -> ReconcileReport:
    """Ordnet Altzeilen stabilen Kennungen zu. Committet NICHT."""
    report = ReconcileReport()
    rows = list(db.execute(select(FanConfig)).scalars())

    # Rangfolge VOR dem ersten Schreibzugriff festhalten: updated_at traegt
    # ein onupdate=func.now() und aendert sich sonst waehrend des Laufs.
    order = {row.id: row.updated_at for row in rows}

    candidates: Dict[str, List[FanConfig]] = {}
    for row in rows:
        match = _LEGACY_FAN_ID.match(row.fan_id or "")
        if not match:
            continue                                   # Regel 1
        if not row.is_active:
            # Bereits in einem frueheren Lauf final entschieden (verloren
            # oder wegen fehlendem Kanal deaktiviert). Ohne diese Sperre
            # traete die Zeile bei jedem weiteren Lauf erneut gegen den
            # laengst gekuerten Gewinner an -- mit demselben fan_id-Wert
            # wie zuvor, also ohne neue Information, aber mit der Chance,
            # den Wettbewerb per Ranggleichstand zu gewinnen und so den
            # Unique-Index auf fan_id zu verletzen.
            continue
        chip = _chip_from_name(row.name)
        if chip is None:
            continue                                   # kein " PWM" im Namen
        facts = chips.get(chip)
        if facts is None:                              # Regel 4: Chip abwesend
            report.skipped_absent.append(row.fan_id)
            continue
        if facts.ambiguous:
            continue                                   # Regel 2
        channel = int(match.group(2))
        if channel not in facts.pwm_channels:
            row.is_active = False                      # Chip da, Kanal weg
            report.deactivated.append(row.fan_id)
            continue
        candidates.setdefault(f"{facts.key}:pwm{channel}", []).append(row)

    # Bereits in Neuform vorliegende Zeilen treten mit an, sonst laeuft ein
    # nach einem Abbruch wiederholter Lauf in den Unique-Index.
    existing = {row.fan_id: row for row in rows}
    for new_id, group in candidates.items():
        incumbent = existing.get(new_id)
        if incumbent is not None and incumbent not in group:
            group.append(incumbent)

        # Kein None in den Sortierschluessel: zwei Zeilen ohne updated_at
        # liefen sonst in einen TypeError beim Vergleich None < None.
        winner = max(group, key=lambda r: order.get(r.id) or _EPOCH)
        for row in group:
            if row is winner:
                continue
            if row.is_active:
                row.is_active = False
                report.deactivated.append(row.fan_id)

        if winner.fan_id != new_id:
            old_id = winner.fan_id
            winner.legacy_fan_id = old_id
            winner.fan_id = new_id
            report.renamed.append((old_id, new_id))
            logger.info("Fan-Identitaet: %s -> %s", old_id, new_id)
            _rewrite_references(db, old_id, new_id)

        winner.temp_sensor_id = _map_sensor(
            winner.temp_sensor_id, sensor_map, cpu_sensor_id, report
        )

    _reconcile_sensor_labels(db, sensor_map, report)
    _reconcile_composites(db, sensor_map)

    logger.info(
        "Identitaets-Abgleich: %d uebernommen, %d deaktiviert, %d ohne Chip",
        len(report.renamed), len(report.deactivated), len(report.skipped_absent),
    )
    return report


def _rewrite_references(db: Session, old_id: str, new_id: str) -> None:
    """sync_fan_id und Zeitplaneintraege ziehen mit."""
    for row in db.execute(
        select(FanConfig).where(FanConfig.sync_fan_id == old_id)
    ).scalars():
        row.sync_fan_id = new_id
    for entry in db.execute(
        select(FanScheduleEntry).where(FanScheduleEntry.fan_id == old_id)
    ).scalars():
        entry.fan_id = new_id


def _reconcile_sensor_labels(db: Session, sensor_map: Dict[str, str],
                             report: ReconcileReport) -> None:
    """Nutzer-Labels auf die neuen Sensor-Kennungen umschluesseln.

    sensor_id ist Primaerschluessel und die Tabelle hat kein is_active. Bei
    einer Kollision gewinnt die juengste Zeile; die verworfene BLEIBT unter
    ihrem alten Schluessel liegen und wird ignoriert. Kein Loeschen -- das
    ist ein ausdrueckliches Nicht-Ziel der Spec.
    """
    rows = list(db.execute(select(TempSensorLabel)).scalars())
    existing = {row.sensor_id for row in rows}
    claimed: Dict[str, TempSensorLabel] = {}

    for row in rows:
        if not _LEGACY_SENSOR_ID.match(row.sensor_id or ""):
            continue
        new_id = sensor_map.get(row.sensor_id)
        if not new_id:
            report.unresolved_sensors.append(row.sensor_id)
            continue
        bare_new = new_id[len("hwmon:"):] if new_id.startswith("hwmon:") else new_id
        if bare_new in existing:
            continue
        rival = claimed.get(bare_new)
        if rival is not None:
            loser = min((rival, row), key=lambda r: r.updated_at or _EPOCH)
            logger.warning(
                "Sensor-Label %s verworfen: %s ist bereits vergeben",
                loser.sensor_id, bare_new,
            )
            if loser is row:
                continue
        claimed[bare_new] = row

    for bare_new, row in claimed.items():
        row.legacy_sensor_id = row.sensor_id
        row.sensor_id = bare_new
        logger.info("Sensor-Label: %s -> %s", row.legacy_sensor_id, bare_new)


def _reconcile_composites(db: Session, sensor_map: Dict[str, str]) -> None:
    """Quell-IDs in composite_temp_sensors mit derselben Abbildung umschreiben."""
    for composite in db.execute(select(CompositeTempSensor)).scalars():
        try:
            sources = json.loads(composite.source_ids_json)
        except (TypeError, ValueError):
            logger.warning("Composite %s: source_ids_json unlesbar", composite.id)
            continue
        if not isinstance(sources, list):
            continue

        changed = False
        rewritten = []
        for source in sources:
            bare = source[len("hwmon:"):] if isinstance(source, str) and source.startswith("hwmon:") else source
            mapped = sensor_map.get(bare) if isinstance(bare, str) else None
            if mapped:
                rewritten.append(mapped)
                changed = True
            else:
                rewritten.append(source)
        if changed:
            composite.source_ids_json = json.dumps(rewritten)
            logger.info("Composite %s: Quell-IDs umgeschrieben", composite.id)
