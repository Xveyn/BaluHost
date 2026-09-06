"""Persistenz der GPU-Akustik-Konfiguration (#516)."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
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


def test_corrupt_json_falls_back_to_defaults(session_factory):
    """Eine von Hand verunstaltete Zeile darf den Start nicht verhindern."""
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature is None
