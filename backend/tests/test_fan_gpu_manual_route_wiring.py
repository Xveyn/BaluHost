"""Die Route benutzt den persistenten Speicher wirklich (#411).

Ohne diesen Test koennte man beide Zeilen entfernen, die Route und Speicher
verbinden, und die Suite bliebe gruen -- bei totem Feature. Dieselbe Falle,
die das Abschluss-Review zu #534 gefunden hat.

Aufgerufen wird `__wrapped__`, also der Handler ohne den slowapi-Dekorator.
Geprueft wird die Verdrahtung im Handler, nicht das Rate-Limit.
"""
import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import fans as fans_routes
from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import PwmControl
from app.services.power import fan_gpu_manual
from app.services.power.fan_gpu_manual import AmdManualState

FAN_ID = "amdgpu-pci-0300:pwm1"
# Der gemessene Wert auf BaluNode -- ausdruecklich NICHT "auto", damit ein
# geratener Rueckfallwert im Test auffaellt statt zufaellig zu stimmen.
MEASURED = AmdManualState(previous_level="low", previous_pwm_enable=2)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(FanConfig(fan_id=FAN_ID, name="amdgpu PWM1"))
        db.commit()
    return factory


@pytest.fixture
def service(session_factory):
    backend = SimpleNamespace(_fan_cache={
        FAN_ID: {
            "is_gpu_fan": True,
            "gpu_vendor": "amd",
            "pwm_control": PwmControl.SUPPORTED,
            "pwm_path": Path("/sys/class/hwmon/hwmon2/pwm1"),
        }
    })

    @contextmanager
    def factory():
        with session_factory() as db:
            yield db

    return SimpleNamespace(_backend=backend, db_session_factory=factory)


async def _call(service, *, enable: bool):
    handler = fans_routes.set_gpu_manual_mode.__wrapped__
    return await handler(
        request=SimpleNamespace(),
        response=SimpleNamespace(),
        fan_id=FAN_ID,
        body=fans_routes.GpuManualModeRequest(enable=enable),
        current_user=MagicMock(),
        service=service,
    )


@pytest.mark.asyncio
async def test_enable_persists_the_measured_state(service, session_factory, monkeypatch):
    monkeypatch.setattr(fan_gpu_manual, "enable_amd_manual",
                        AsyncMock(return_value=MEASURED))

    await _call(service, enable=True)

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.gpu_manual_prev_level == "low"
    assert row.gpu_manual_prev_pwm_enable == 2


@pytest.mark.asyncio
async def test_disable_restores_what_another_worker_recorded(
        service, session_factory, monkeypatch):
    """Der Kern: einschalten und ausschalten laufen in getrennten Prozessen.

    Der Handler haelt keinen prozesslokalen Zustand mehr; jeder Aufruf liest
    aus der Datenbank. Genau das macht den Worker, der das Ausschalten
    bedient, unabhaengig von dem, der eingeschaltet hat.
    """
    monkeypatch.setattr(fan_gpu_manual, "enable_amd_manual",
                        AsyncMock(return_value=MEASURED))
    await _call(service, enable=True)

    disable = AsyncMock()
    monkeypatch.setattr(fan_gpu_manual, "disable_amd_manual", disable)

    await _call(service, enable=False)

    assert disable.await_count == 1
    assert disable.await_args.kwargs["state"] == MEASURED


@pytest.mark.asyncio
async def test_disable_clears_the_record_so_it_is_used_once(
        service, session_factory, monkeypatch):
    monkeypatch.setattr(fan_gpu_manual, "enable_amd_manual",
                        AsyncMock(return_value=MEASURED))
    await _call(service, enable=True)
    monkeypatch.setattr(fan_gpu_manual, "disable_amd_manual", AsyncMock())

    await _call(service, enable=False)

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.gpu_manual_prev_level is None
    assert row.gpu_manual_prev_pwm_enable is None


@pytest.mark.asyncio
async def test_disable_without_a_record_says_so_before_falling_back(
        service, monkeypatch, caplog):
    """Ohne Aufzeichnung bleibt nur der Treiber-Default -- aber sichtbar.

    Der Rueckfall auf auto/2 ist nicht zu vermeiden, wenn niemand den
    Vorzustand kennt; ein Luefter dauerhaft in Handsteuerung waere schlechter.
    Er darf aber nicht still passieren: auf BaluNode stand dort `low`, und wer
    diese Einstellung verliert, soll es im Log finden.
    """
    disable = AsyncMock()
    monkeypatch.setattr(fan_gpu_manual, "disable_amd_manual", disable)

    with caplog.at_level(logging.WARNING):
        await _call(service, enable=False)

    assert disable.await_args.kwargs["state"] == AmdManualState(
        previous_level="auto", previous_pwm_enable=2
    )
    assert any("auto" in record.message and FAN_ID in record.message
               for record in caplog.records), caplog.text
