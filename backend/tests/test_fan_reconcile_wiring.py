"""Vorbedingungen und Gate des Identitaets-Abgleichs (#532)."""
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import FanCurvePoint, FanMode
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData


class _FakeLinuxBackend:
    """Schlankes Double fuer LinuxFanControlBackend, mit echten dict-Attributen
    statt Mock-Kindern -- fuer die beiden Tests unten, die eine echte
    SQLite-Session gegen die tatsaechliche Transaktionsreihenfolge pruefen.
    """

    def __init__(self, fan_cache, temp_paths, fans, cpu_sensor_id=None):
        self._fan_cache = fan_cache
        self._temp_paths = temp_paths
        self._fans = fans
        self._cpu_sensor_id = cpu_sensor_id

    async def get_fans(self):
        return self._fans

    async def get_available_temp_sensors(self):
        if self._cpu_sensor_id is None:
            return []
        from app.services.power.fan_control import TempSensorData
        return [TempSensorData(
            sensor_id=self._cpu_sensor_id,
            device_name="k10temp",
            label="Tctl",
            is_cpu_sensor=True,
            current_temp=50.0,
        )]


def _service(monkeypatch, *, primary: bool, linux: bool):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, MagicMock())
    service._use_linux_backend = linux
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_skips_when_not_primary_worker(monkeypatch):
    service = _service(monkeypatch, primary=False, linux=True)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_on_dev_backend(monkeypatch):
    # is_available() faellt bei 0 gefundenen Lueftern auch in Produktion auf
    # das Dev-Backend zurueck. Liefe der Abgleich dann, deaktivierte er in
    # einem Rutsch alle hwmon-Zeilen.
    service = _service(monkeypatch, primary=True, linux=False)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_when_scan_found_no_chip(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=0) is False


def test_runs_when_all_preconditions_hold(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=3) is True


@pytest.mark.asyncio
async def test_reconcile_failure_does_not_create_configs(monkeypatch, caplog):
    """Wirft reconcile_fan_identities, darf die Anlage-Schleife NICHT laufen.

    Sonst legte sie eine frische Default-Config unter der bereits neuen
    Scan-ID an, deren updated_at "jetzt" ist -- die schluege beim naechsten
    Abgleich jede echte Nutzerkurve. Genau das soll dieser Abgleich
    verhindern; ihn bei einem eigenen Fehler trotzdem durchlaufen zu lassen,
    waere derselbe Datenverlust auf einem Umweg.
    """
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False

    service = FanControlService(config, MagicMock())
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    fan = FanData(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        rpm=900,
        pwm_percent=40,
        temperature_celsius=None,
        mode=FanMode.AUTO,
        min_pwm_percent=0,
        max_pwm_percent=100,
        emergency_temp_celsius=85.0,
        temp_sensor_id=None,
        curve_points=[FanCurvePoint(temp=35, pwm=30)],
        is_active=True,
    )

    backend = AsyncMock()
    backend.get_fans.return_value = [fan]
    backend.get_available_temp_sensors.return_value = []
    backend._fan_cache = {
        "nct6798-isa-0290:pwm1": {
            "identity_stable": True,
            "device_driver": "nct6798",
        },
    }
    backend._temp_paths = {}
    service._backend = backend

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # keine Altzeile vorhanden
    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    service.db_session_factory = mock_session_factory

    def _boom(*args, **kwargs):
        raise RuntimeError("Abgleich kaputt")

    monkeypatch.setattr(fan_control_module, "reconcile_fan_identities", _boom)

    with caplog.at_level(logging.ERROR, logger="app.services.power.fan_control"):
        await service._load_fan_configs()  # darf NICHT werfen

    assert mock_db.add.call_count == 0, "Anlage-Schleife durfte nicht laufen"
    assert mock_db.commit.call_count == 0, "kein Commit nach fehlgeschlagenem Abgleich"
    assert any(r.levelno == logging.ERROR for r in caplog.records), (
        "Fehlschlag muss als ERROR mit Traceback geloggt werden"
    )


@pytest.mark.asyncio
async def test_secondary_worker_creates_no_configs(monkeypatch):
    """C1: der Sekundaer-Worker darf die Anlage-Schleife nicht ausfuehren.

    Legte er hier eine Default-Config unter der (bereits neuen) Scan-ID an,
    truege sie updated_at="jetzt" und gewaenne beim spaeteren Abgleich des
    Primary gegen die echte Nutzerkurve -- der Datenverlust, den der
    Abgleich verhindern soll, nur ueber den Sekundaer-Worker eingeschleust.
    Echte In-Memory-SQLite-Session, kein MagicMock: die Zeilenzahl wird
    tatsaechlich gezaehlt, nicht an einem Call-Count abgelesen.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False

    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        False, raising=False)

    fan = FanData(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        rpm=900,
        pwm_percent=40,
        temperature_celsius=None,
        mode=FanMode.AUTO,
        min_pwm_percent=0,
        max_pwm_percent=100,
        emergency_temp_celsius=85.0,
        temp_sensor_id=None,
        curve_points=[FanCurvePoint(temp=35, pwm=30)],
        is_active=True,
    )
    service._backend = _FakeLinuxBackend(fan_cache={}, temp_paths={}, fans=[fan])

    await service._load_fan_configs()

    with session_factory() as check:
        assert check.execute(select(FanConfig)).scalars().all() == [], (
            "Sekundaer-Worker hat eine Config angelegt -- C1-Regression"
        )


@pytest.mark.asyncio
async def test_reconcile_runs_before_anlage_and_no_duplicate_row(monkeypatch):
    """Reihenfolge: Abgleich vor Anlage-Schleife, keine zusaetzliche Zeile.

    Eine Altzeile liegt unter der frueheren hwmon-indizierten ID in der DB.
    Der Scan liefert dieselbe physische PWM-Leitung bereits unter der neuen,
    stabilen ID. Lief der Abgleich VOR der Anlage-Schleife (wie vorgesehen),
    traegt die migrierte Zeile danach die neue ID plus legacy_fan_id, und
    die Anlage-Schleife findet unter der neuen ID bereits eine "existing"
    Zeile vor -- es entsteht KEINE zweite, zusaetzliche Default-Zeile. Liefe
    der Abgleich stattdessen nach der Anlage-Schleife (die Regression, die
    R4 verhindern soll), gaebe es zwei Zeilen: die frische Default-Zeile
    unter der neuen ID und die unveraenderte Altzeile.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as seed:
        seed.add(FanConfig(
            fan_id="hwmon5_pwm1",
            name="nct6798 PWM1",
            mode="auto",
            temp_sensor_id="hwmon5_temp6",
            is_active=True,
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        seed.commit()

    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False

    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    fan = FanData(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        rpm=900,
        pwm_percent=40,
        temperature_celsius=None,
        mode=FanMode.AUTO,
        min_pwm_percent=0,
        max_pwm_percent=100,
        emergency_temp_celsius=85.0,
        temp_sensor_id=None,
        curve_points=[FanCurvePoint(temp=35, pwm=30)],
        is_active=True,
    )
    service._backend = _FakeLinuxBackend(
        fan_cache={
            "nct6798-isa-0290:pwm1": {
                "identity_stable": True,
                "device_driver": "nct6798",
            },
        },
        temp_paths={},
        fans=[fan],
    )

    await service._load_fan_configs()

    with session_factory() as check:
        rows = list(check.execute(select(FanConfig)).scalars())
        assert len(rows) == 1, (
            f"erwartet genau eine Zeile (migriert, keine zusaetzliche "
            f"Default-Zeile), gefunden: {[r.fan_id for r in rows]}"
        )
        row = rows[0]
        assert row.fan_id == "nct6798-isa-0290:pwm1"
        assert row.legacy_fan_id == "hwmon5_pwm1"
