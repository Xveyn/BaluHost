"""Persistenz der GPU-Akustik-Konfiguration (#516)."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics_store import (
    AcousticsConfigUnreadable,
    capture_baseline,
    load_acoustics_config,
    load_acoustics_config_fail_soft,
    save_acoustics_config,
    store_desired,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_loading_without_a_row_gives_empty_defaults(session_factory):
    """Frisch migriert heisst: BaluHost verwaltet nichts."""
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature is None
    assert config.baseline.fan_target_temperature is None


def test_round_trip(session_factory):
    config = GpuFanAcousticsConfig(
        desired=GpuFanAcousticsValues(fan_target_temperature=75),
        baseline=GpuFanAcousticsValues(fan_target_temperature=95),
    )
    with session_factory() as db:
        assert save_acoustics_config(db, config) is True
    with session_factory() as db:
        loaded = load_acoustics_config(db)
    assert loaded.desired.fan_target_temperature == 75
    assert loaded.baseline.fan_target_temperature == 95


def test_saving_twice_keeps_a_single_row(session_factory):
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig())
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_minimum_pwm=40)))
    with session_factory() as db:
        rows = list(db.execute(select(GpuFanAcousticsConfigDb)).scalars())
    assert len(rows) == 1
    stored = GpuFanAcousticsConfig.model_validate_json(rows[0].config_json)
    assert stored.desired.fan_minimum_pwm == 40


def test_corrupt_json_falls_back_to_defaults_on_the_fail_soft_path(session_factory):
    """Eine von Hand verunstaltete Zeile darf den Start nicht verhindern.

    Das war frueher das Verhalten von load_acoustics_config selbst. Es ist
    jetzt eine eigene Funktion, weil ein SCHREIBPFAD auf einem
    fehlgeschlagenen Load nicht aufbauen darf: er legte leere Vorgaben ueber
    die echte Zeile und loeschte die beobachtete Baseline (#516).
    """
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()
    with session_factory() as db:
        config = load_acoustics_config_fail_soft(db)
    assert config.desired.fan_target_temperature is None


def test_corrupt_json_is_an_error_for_a_writer(session_factory):
    """'Keine Zeile' und 'Lesen fehlgeschlagen' sind verschiedene Faelle."""
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()
    with session_factory() as db:
        with pytest.raises(AcousticsConfigUnreadable):
            load_acoustics_config(db)


def test_a_missing_row_is_not_an_error(session_factory):
    """Frisch migriert ist ein gueltiger Zustand, kein Lesefehler."""
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature is None


def test_capture_baseline_only_fills_empty_fields(session_factory):
    """Der Kern gegen die Kontamination: eine erfasste Baseline bleibt.

    Sonst schriebe ein Aufrufer mit veraltetem Snapshot BaluHosts eigenen
    Eingriff als 'wie es vorher war' hinein.
    """
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))
    with session_factory() as db:
        capture_baseline(db, {"fan_target_temperature": 75,
                              "fan_minimum_pwm": 23})
    with session_factory() as db:
        baseline = load_acoustics_config(db).baseline
    assert baseline.fan_target_temperature == 95
    assert baseline.fan_minimum_pwm == 23


def test_capture_baseline_leaves_desired_alone(session_factory):
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))
    with session_factory() as db:
        capture_baseline(db, {"fan_target_temperature": 95})
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature == 75
    assert config.baseline.fan_target_temperature == 95


def test_store_desired_writes_only_the_named_fields(session_factory):
    """Kein Lost Update: der PUT schrieb frueher das ganze Objekt zurueck."""
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_minimum_pwm=40),
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))
    with session_factory() as db:
        store_desired(db, {"fan_target_temperature": 75})
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature == 75
    assert config.desired.fan_minimum_pwm == 40, "fremdes Feld verloren"
    assert config.baseline.fan_target_temperature == 95, "Baseline verloren"


def test_a_writer_refuses_to_touch_an_unreadable_row(session_factory):
    """Statt sie zu ueberschreiben -- die Baseline waere sonst weg."""
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()
    with session_factory() as db:
        with pytest.raises(AcousticsConfigUnreadable):
            store_desired(db, {"fan_target_temperature": 75})
    with session_factory() as db:
        row = db.execute(select(GpuFanAcousticsConfigDb)).scalar_one()
    assert row.config_json == "{kaputt"
