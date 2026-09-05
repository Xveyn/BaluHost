"""Zuordnung der Altzeilen auf stabile Kennungen (#532).

Das Fixture ist die auf BaluNode gemessene Datenlage: 16 Zeilen, davon 13
hwmon-indiziert in vier Generationen fuer 5 physische Luefter, plus 3 dev_*.
"""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import CompositeTempSensor, FanConfig, TempSensorLabel
from app.services.power.fan_reconcile import (
    ChipFacts,
    ReconcileReport,
    _map_sensor,
    reconcile_fan_identities,
)

NCT = ChipFacts(key="nct6798-isa-0290",
                pwm_channels=frozenset({1, 2, 3, 7}), ambiguous=False)
AMD = ChipFacts(key="amdgpu-pci-0300",
                pwm_channels=frozenset({1}), ambiguous=False)
CHIPS = {"nct6798": NCT, "amdgpu": AMD}

SENSOR_MAP = {
    "hwmon4_temp1": "hwmon:k10temp-pci-00c3:temp1",
    "hwmon3_temp1": "hwmon:nct6798-isa-0290:temp1",
}
CPU_DEFAULT = "hwmon:k10temp-pci-00c3:temp1"


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


ROWS = [
    # (fan_id, name, temp_sensor_id, updated_at)
    ("hwmon5_pwm1", "nct6798 PWM1", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm2", "nct6798 PWM2", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm3", "nct6798 PWM3", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("hwmon5_pwm7", "nct6798 PWM7", "hwmon5_temp6", "2026-01-25T22:51:59"),
    ("dev_case_fan_1", "Case Fan 1 (Simulated)", "dev_package_temp", "2026-01-27T22:48:27"),
    ("dev_cpu_fan", "CPU Fan (Simulated)", "dev_cpu_temp", "2026-02-17T21:48:42"),
    ("dev_case_fan_2", "Case Fan 2 (Simulated)", "dev_cpu_temp", "2026-02-25T19:57:42"),
    ("hwmon1_pwm1", "amdgpu PWM1", "hwmon3_temp1", "2026-07-06T23:38:15"),
    ("hwmon2_pwm1", "nct6798 PWM1", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm2", "nct6798 PWM2", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm3", "nct6798 PWM3", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon2_pwm7", "nct6798 PWM7", "hwmon3_temp1", "2026-07-20T22:59:55"),
    ("hwmon3_pwm1", "nct6798 PWM1", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm2", "nct6798 PWM2", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm3", "nct6798 PWM3", "hwmon4_temp1", "2026-08-07T00:32:04"),
    ("hwmon3_pwm7", "nct6798 PWM7", "hwmon4_temp1", "2026-08-07T00:32:04"),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for fan_id, name, sensor, updated in ROWS:
        session.add(FanConfig(fan_id=fan_id, name=name, mode="auto",
                              temp_sensor_id=sensor, is_active=True,
                              updated_at=_dt(updated)))
    session.commit()
    yield session
    session.close()


def _active(db):
    return {r.fan_id for r in db.execute(
        select(FanConfig).where(FanConfig.is_active.is_(True))).scalars()}


def test_newest_generation_wins_and_nothing_is_deleted(db):
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert _active(db) == {
        "nct6798-isa-0290:pwm1", "nct6798-isa-0290:pwm2",
        "nct6798-isa-0290:pwm3", "nct6798-isa-0290:pwm7",
        "amdgpu-pci-0300:pwm1",
        "dev_case_fan_1", "dev_cpu_fan", "dev_case_fan_2",
    }
    assert db.query(FanConfig).count() == 16   # nichts geloescht


def test_july_row_named_nct6798_does_not_become_the_gpu(db):
    """Die Falle: hwmon2 ist heute die GPU, war im Juli aber der nct6798."""
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    gpu = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "amdgpu-pci-0300:pwm1")).scalar_one()
    assert gpu.legacy_fan_id == "hwmon1_pwm1"
    assert gpu.name == "amdgpu PWM1"


def test_absent_chip_is_never_deactivated(db):
    """Treiber beim Start noch nicht geladen -- Kurven muessen bleiben."""
    reconcile_fan_identities(db, chips={"amdgpu": AMD}, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    for fan_id in ("hwmon3_pwm1", "hwmon2_pwm1", "hwmon5_pwm1"):
        row = db.execute(select(FanConfig).where(
            FanConfig.fan_id == fan_id)).scalar_one()
        assert row.is_active is True


def test_second_run_is_a_noop(db):
    first = reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                                     cpu_sensor_id=CPU_DEFAULT)
    db.commit()
    second = reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                                      cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert len(first.renamed) == 5
    assert second.renamed == []
    assert second.deactivated == []


def test_resumes_after_abort_between_rename_and_deactivate(db):
    """Gewinner schon umbenannt, Verlierer noch aktiv -- kein Unique-Fehler."""
    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon3_pwm1")).scalar_one()
    row.fan_id = "nct6798-isa-0290:pwm1"
    row.legacy_fan_id = "hwmon3_pwm1"
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert "hwmon2_pwm1" not in _active(db)
    assert "nct6798-isa-0290:pwm1" in _active(db)


def test_losing_incumbent_frees_its_id_for_the_winner(db):
    """I-2: Traegt der Inkumbent (bereits in Neuform) das AELTERE updated_at
    und eine Altzeile das juengere, verliert der Inkumbent den Rangvergleich.
    Ohne Freimachen wuerde die anschliessende Umbenennung des Gewinners auf
    denselben fan_id-Wert den Unique-Index verletzen -- reproduzierbar ueber
    Rollback+Roll-forward (siehe Review)."""
    incumbent = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon3_pwm1")).scalar_one()
    incumbent.fan_id = "nct6798-isa-0290:pwm1"
    incumbent.legacy_fan_id = "hwmon3_pwm1"
    incumbent.updated_at = _dt("2026-01-01T00:00:00")   # aelter als alle Rivalen
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()   # darf keinen IntegrityError werfen

    winner = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert winner.legacy_fan_id == "hwmon2_pwm1"        # juengste Altzeile gewinnt

    incumbent_after = db.execute(select(FanConfig).where(
        FanConfig.id == incumbent.id)).scalar_one()
    assert incumbent_after.is_active is False
    assert incumbent_after.fan_id != "nct6798-isa-0290:pwm1"

    assert db.query(FanConfig).count() == 16            # nichts geloescht


def test_losing_incumbent_does_not_reuse_an_id_the_winner_still_holds(db):
    """Der Rollback+Roll-forward-Fall: die Altform, die der Inkumbent als
    legacy_fan_id fuehrt, ist von der Gewinnerin noch belegt.

    Nach einem Rollback auf Code vor #532 legt die alte Anlage-Schleife eine
    Zeile unter genau dieser Altform an; beim Roll-forward gewinnt sie, weil
    sie juenger ist. Wuerde legacy_fan_id als Ersatz-ID wiederverwendet, traefe
    derselbe Unique-Verstoss eine Zeile weiter -- und der Dienst kaeme bei
    JEDEM folgenden Start ohne Luefter-Configs hoch.
    """
    incumbent = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon3_pwm1")).scalar_one()
    incumbent.fan_id = "nct6798-isa-0290:pwm1"
    incumbent.legacy_fan_id = "hwmon2_pwm1"   # genau die ID der spaeteren Gewinnerin
    incumbent.updated_at = _dt("2026-01-01T00:00:00")
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()   # darf keinen IntegrityError werfen

    winner = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert winner.legacy_fan_id == "hwmon2_pwm1"

    incumbent_after = db.execute(select(FanConfig).where(
        FanConfig.id == incumbent.id)).scalar_one()
    assert incumbent_after.is_active is False
    # Ersatz-ID aus dem Primaerschluessel, nicht aus legacy_fan_id
    assert incumbent_after.fan_id == f"nct6798-isa-0290:pwm1#legacy{incumbent.id}"
    assert incumbent_after.legacy_fan_id == "hwmon2_pwm1"   # Herkunft bleibt

    assert db.query(FanConfig).count() == 16


def test_unknown_name_is_neither_candidate_nor_deactivated(db):
    db.add(FanConfig(fan_id="hwmon9_pwm1", name="Unknown PWM1", mode="auto",
                     temp_sensor_id=None, is_active=True,
                     updated_at=_dt("2026-08-08T00:00:00")))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon9_pwm1")).scalar_one()
    assert row.is_active is True


def test_ambiguous_chip_name_is_no_candidate(db):
    chips = {"nct6798": ChipFacts(key="nct6798-isa-0290",
                                  pwm_channels=frozenset({1, 2, 3, 7}),
                                  ambiguous=True),
             "amdgpu": AMD}
    reconcile_fan_identities(db, chips=chips, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    assert "hwmon3_pwm1" in _active(db)


def test_winner_sensor_is_rewritten_prefixed(db):
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert row.temp_sensor_id == "hwmon:k10temp-pci-00c3:temp1"


def test_unresolvable_sensor_falls_back_to_cpu_default(db):
    report = reconcile_fan_identities(db, chips=CHIPS, sensor_map={},
                                      cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "nct6798-isa-0290:pwm1")).scalar_one()
    assert row.temp_sensor_id == CPU_DEFAULT
    assert "hwmon4_temp1" in report.unresolved_sensors


def test_sensor_label_is_rekeyed_and_keeps_provenance(db):
    """I-1: real gespeicherte Label-sensor_id traegt IMMER das 'hwmon:'-Praefix
    (die Route persistiert die Registry-Kennung, siehe HwmonTempSource.id).
    Ohne Praefix-Abstreifen vor dem Regex-Test traf die Migration keine
    einzige echte Zeile."""
    db.add(TempSensorLabel(sensor_id="hwmon:hwmon4_temp1", custom_label="RAID-Platten"))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    labels = {row.sensor_id: row for row in db.query(TempSensorLabel).all()}
    assert "hwmon:k10temp-pci-00c3:temp1" in labels
    assert labels["hwmon:k10temp-pci-00c3:temp1"].custom_label == "RAID-Platten"
    assert labels["hwmon:k10temp-pci-00c3:temp1"].legacy_sensor_id == "hwmon:hwmon4_temp1"


def test_sensor_label_collision_keeps_older_row_under_its_own_key(db):
    """Zwei Altzeilen zielen auf denselben neuen Schluessel -- die juengere
    gewinnt und traegt ihn, die aeltere bleibt unter ihrem alten Schluessel
    liegen (kein Loeschen, kein Primaerschluessel-Konflikt)."""
    older = TempSensorLabel(sensor_id="hwmon:hwmon4_temp1", custom_label="Alt",
                            updated_at=_dt("2026-01-01T00:00:00"))
    newer = TempSensorLabel(sensor_id="hwmon:hwmon6_temp1", custom_label="Neu",
                            updated_at=_dt("2026-08-01T00:00:00"))
    db.add(older)
    db.add(newer)
    db.commit()

    sensor_map = dict(SENSOR_MAP)
    sensor_map["hwmon6_temp1"] = "hwmon:k10temp-pci-00c3:temp1"

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=sensor_map,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()   # darf keinen Primaerschluessel-Konflikt werfen

    labels = {row.sensor_id: row for row in db.query(TempSensorLabel).all()}
    assert "hwmon:k10temp-pci-00c3:temp1" in labels
    assert labels["hwmon:k10temp-pci-00c3:temp1"].custom_label == "Neu"
    assert "hwmon:hwmon4_temp1" in labels           # aeltere bleibt liegen
    assert labels["hwmon:hwmon4_temp1"].custom_label == "Alt"
    assert len(labels) == 2


def test_composite_sources_are_rewritten(db):
    db.add(CompositeTempSensor(
        id="mix:abc", name="CPU und Board", function="max",
        source_ids_json='["hwmon:hwmon4_temp1", "hwmon3_temp1"]',
    ))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    composite = db.query(CompositeTempSensor).one()
    assert json.loads(composite.source_ids_json) == [
        "hwmon:k10temp-pci-00c3:temp1",
        "hwmon:nct6798-isa-0290:temp1",
    ]


def test_unmappable_composite_source_is_left_alone(db):
    db.add(CompositeTempSensor(
        id="mix:def", name="Mit Luecke", function="max",
        source_ids_json='["gpu:junction", "hwmon9_temp1"]',
    ))
    db.commit()

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    composite = db.query(CompositeTempSensor).one()
    assert json.loads(composite.source_ids_json) == ["gpu:junction", "hwmon9_temp1"]


def test_map_sensor_leaves_already_stable_id_untouched():
    """R2: eine bereits migrierte Sensor-ID wird nicht erneut abgebildet
    und erzeugt keinen Fehlalarm."""
    report = ReconcileReport()
    result = _map_sensor("hwmon:k10temp-pci-00c3:temp1", SENSOR_MAP,
                         CPU_DEFAULT, report)
    assert result == "hwmon:k10temp-pci-00c3:temp1"
    assert report.unresolved_sensors == []


def test_map_sensor_leaves_unknown_form_untouched():
    """R2: was nicht wie eine Alt-ID aussieht, wird nicht angefasst."""
    report = ReconcileReport()
    result = _map_sensor("gpu:junction", SENSOR_MAP, CPU_DEFAULT, report)
    assert result == "gpu:junction"
    assert report.unresolved_sensors == []


def test_tie_break_on_identical_updated_at_is_deterministic(db):
    """F2: bei exakt gleichem updated_at entscheidet die hoehere id (die
    zuletzt angelegte, also aktuellere Zeile) -- nicht die Query-Reihenfolge.
    """
    same_ts = _dt("2026-07-06T23:38:15")
    db.add(FanConfig(fan_id="hwmon6_pwm1", name="amdgpu PWM1", mode="auto",
                     temp_sensor_id="hwmon3_temp1", is_active=True,
                     updated_at=same_ts))
    db.commit()

    newer_row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon6_pwm1")).scalar_one()
    older_row = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "hwmon1_pwm1")).scalar_one()
    assert newer_row.updated_at == older_row.updated_at   # echter Gleichstand
    assert newer_row.id > older_row.id

    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    winner = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "amdgpu-pci-0300:pwm1")).scalar_one()
    assert winner.legacy_fan_id == "hwmon6_pwm1"

    # Wiederholter Lauf liefert dasselbe Ergebnis -- kein Ranggleichstands-Flackern.
    reconcile_fan_identities(db, chips=CHIPS, sensor_map=SENSOR_MAP,
                             cpu_sensor_id=CPU_DEFAULT)
    db.commit()

    winner_again = db.execute(select(FanConfig).where(
        FanConfig.fan_id == "amdgpu-pci-0300:pwm1")).scalar_one()
    assert winner_again.legacy_fan_id == "hwmon6_pwm1"
