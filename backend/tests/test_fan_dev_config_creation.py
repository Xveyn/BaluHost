"""Simulierte Luefter gehoeren nicht in eine Produktionsdatenbank (#558).

Auf BaluNode standen drei `dev_*`-Zeilen mit `is_active=true` in `fan_configs`.
Sie entstehen ueber `POST /api/fans/backend`: der Wechsel auf das Dev-Backend
ruft `_load_fan_configs()`, und die Anlage-Schleife legte fuer jeden
gescannten -- also simulierten -- Luefter eine Zeile an.

Weg gehen sie von selbst nicht mehr: der Identitaets-Abgleich aus #532 fasst
sie nicht an, weil sie keine stabile Chip-Kennung tragen, und ein
Zurueckschalten auf das Linux-Backend entfernt sie nicht.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import FanCurvePoint, FanMode
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _fan(fan_id: str, name: str) -> FanData:
    return FanData(
        fan_id=fan_id,
        name=name,
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


def _service(session_factory, monkeypatch, *, linux: bool, dev_mode: bool,
             fans: list[FanData]):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = dev_mode
    service = FanControlService(config, session_factory)
    service._use_linux_backend = linux

    backend = AsyncMock()
    backend.get_fans.return_value = fans
    backend.get_available_temp_sensors.return_value = []
    backend._fan_cache = {
        fan.fan_id: {"identity_stable": linux, "device_driver": "nct6798"}
        for fan in fans
    }
    backend._temp_paths = {}
    service._backend = backend

    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)
    return service


DEV_FANS = [
    _fan("dev_cpu_fan", "CPU Fan (Simulated)"),
    _fan("dev_case_fan_1", "Case Fan 1 (Simulated)"),
]


def _fan_ids(session_factory) -> set[str]:
    with session_factory() as db:
        return {row.fan_id for row in db.execute(select(FanConfig)).scalars()}


@pytest.mark.asyncio
async def test_dev_backend_in_production_creates_no_configs(session_factory, monkeypatch):
    """Der Fall aus dem Issue: ein Klick auf "Dev-Backend" in der Produktions-UI."""
    service = _service(session_factory, monkeypatch,
                       linux=False, dev_mode=False, fans=DEV_FANS)

    await service._load_fan_configs()

    assert _fan_ids(session_factory) == set()


@pytest.mark.asyncio
async def test_dev_backend_in_dev_mode_still_creates_configs(session_factory, monkeypatch):
    """Im Dev-Modus sind die simulierten Luefter der Zweck der Uebung."""
    service = _service(session_factory, monkeypatch,
                       linux=False, dev_mode=True, fans=DEV_FANS)

    await service._load_fan_configs()

    assert _fan_ids(session_factory) == {"dev_cpu_fan", "dev_case_fan_1"}


@pytest.mark.asyncio
async def test_the_linux_backend_creates_configs_as_before(session_factory, monkeypatch):
    """Die Absicherung darf den eigentlichen Betriebsfall nicht treffen."""
    fans = [_fan("nct6798-isa-0290:pwm1", "nct6798 PWM1")]
    service = _service(session_factory, monkeypatch,
                       linux=True, dev_mode=False, fans=fans)

    await service._load_fan_configs()

    assert _fan_ids(session_factory) == {"nct6798-isa-0290:pwm1"}
