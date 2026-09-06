"""Die Beobachtung wird persistiert -- und updated_at bleibt unangetastet (#534).

updated_at traegt onupdate=func.now() (models/fans.py:107-112) und ist das
Rangkriterium des Identitaets-Abgleichs (fan_reconcile.py:151). Ein Schreiben
bei jedem Start setzte jede Zeile auf "gerade angefasst" und entwertete es.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_backend_linux import LinuxFanControlBackend
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


def _tree(tmp_path: Path, enable_value: str) -> Path:
    """nct6798 an platform/nct6775.656, doppelpunktfrei (Windows).

    Baummuster aus test_fan_scan_pwm_enable.py uebernommen (Fix-Brief zu #534,
    Fix 1) -- NTFS erlaubt keinen Doppelpunkt im Verzeichnisnamen, deshalb der
    Platform-Pfad statt eines PCI-Pfads.
    """
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text(enable_value + "\n")
    (hwmon / "fan1_input").write_text("900\n")
    (hwmon / "temp1_input").write_text("42000\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_load_fan_configs_wires_scan_observation_through_to_restore_values(
    tmp_path, session_factory, monkeypatch,
):
    """Schliesst die drei Naehte zwischen Scan und Persistenz gleichzeitig (#534).

    Ein geloeschter Aufruf an fan_control.py:457
    (observations = self._collect_pwm_enable_observations()), :580
    (pwm_enable_restore=observations.get(fan.fan_id) am neu angelegten
    FanConfig) oder :606 (self._persist_restore_values(observations)) liess
    zuvor alle Tests gruen -- dieser Test durchlaeuft _load_fan_configs() echt,
    mit einem echten LinuxFanControlBackend ueber einem tmp_path-sysfs-Baum und
    einer echten SQLite-Session.

    Gegenprobe beim Schreiben dieses Tests ergab: _persist_restore_values
    (naht :606) liest bei jedem Aufruf ALLE Zeilen neu und korrigiert jede mit
    derselben observations-Momentaufnahme -- auch die soeben erst angelegte.
    Ein blosses Entfernen von :580 aendert deshalb den *externen* Endzustand
    der Zeile nicht: :606 heilt ihn im selben Durchlauf nach, und eine
    Assertion allein auf dem finalen DB-Wert wuerde bei geloeschtem :580 gruen
    bleiben (geprueft und beobachtet). Deshalb wird _persist_restore_values
    hier durch einen Spy ersetzt, der die Beobachtungen nur aufzeichnet, aber
    NICHT mehr in die DB schreibt -- so bleibt :580 isoliert pruefbar, ohne
    Produktivcode zu aendern. Die Korrektheit von _persist_restore_values
    selbst (inkl. dem Befuellen von service._restore_values) ist bereits durch
    die uebrigen Tests dieser Datei direkt abgedeckt.
    """
    klass = _tree(tmp_path, "5")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()

    service = _service(session_factory, monkeypatch)
    service._backend = backend

    persist_calls = []
    monkeypatch.setattr(
        service, "_persist_restore_values",
        lambda observations: persist_calls.append(dict(observations)),
    )

    await service._load_fan_configs()

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    # Schliesst :457 und :580: der neu angelegte Datensatz traegt die
    # Scan-Beobachtung -- ohne Mithilfe des (hier stillgelegten) Persist-Aufrufs.
    assert row.pwm_enable_restore == 5

    # Schliesst :606: der Aufruf fand statt, und zwar mit genau dieser
    # Beobachtung.
    assert persist_calls == [{row.fan_id: 5}]
