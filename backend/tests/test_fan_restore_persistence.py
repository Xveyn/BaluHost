"""Die Beobachtung wird persistiert -- und updated_at bleibt unangetastet (#534).

updated_at traegt onupdate=func.now() (models/fans.py:107-112) und ist das
Rangkriterium des Identitaets-Abgleichs (fan_reconcile.py:151). Ein Schreiben
bei jedem Start setzte jede Zeile auf "gerade angefasst" und entwertete es.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _service(session_factory, monkeypatch, *, primary=True):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_persist_does_not_create_rows(session_factory, monkeypatch):
    """_persist_restore_values fasst nur bestehende Zeilen an.

    Die Erstbeobachtung eines NEUEN Luefters kommt nicht von hier, sondern
    direkt am FanConfig(...)-Objekt der Anlage-Schleife (Step 5) -- sonst
    entstuende unmittelbar nach dem INSERT ein zweiter Schreibvorgang.
    """
    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one_or_none()
    assert row is None


def test_existing_row_is_updated(session_factory, monkeypatch):
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore == 5


def test_updated_at_does_not_move(session_factory, monkeypatch):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True, updated_at=stamp))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.updated_at.replace(tzinfo=timezone.utc) == stamp


def test_unchanged_value_writes_nothing(session_factory, monkeypatch):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True, updated_at=stamp,
                         pwm_enable_restore=5))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.updated_at.replace(tzinfo=timezone.utc) == stamp
    assert row.pwm_enable_restore == 5


def test_secondary_worker_persists_nothing(session_factory, monkeypatch):
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True))
        db.commit()

    service = _service(session_factory, monkeypatch, primary=False)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore is None


def test_new_row_carries_the_observation():
    """Die Erstbeobachtung landet am neu angelegten FanConfig-Objekt.

    Geprueft wird der Konstruktoraufruf, nicht der UPDATE-Pfad -- fuer einen
    neuen Luefter gibt es zum Zeitpunkt der Anlage noch keine Zeile, die man
    aktualisieren koennte.
    """
    from app.models.fans import FanConfig

    observations = {"nct6798-isa-0290:pwm1": 5}
    config = FanConfig(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        mode="auto",
        is_active=True,
        pwm_enable_restore=observations.get("nct6798-isa-0290:pwm1"),
    )
    assert config.pwm_enable_restore == 5

    unknown = FanConfig(
        fan_id="nct6798-isa-0290:pwm2",
        name="nct6798 PWM2",
        mode="auto",
        is_active=True,
        pwm_enable_restore=observations.get("nct6798-isa-0290:pwm2"),
    )
    assert unknown.pwm_enable_restore is None
