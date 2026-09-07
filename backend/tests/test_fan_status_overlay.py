"""Die sichtbare Haelfte von #568 Punkt 2: die Ueberlagerung in get_status().

Der Kanalzustand `pwm_control` lebt im `_fan_cache` des jeweiligen Workers,
gesetzt wird er nur von dem, der schreibt. Jeder Worker ueberlagert seinen
Cache deshalb mit der Liste, die der Primary veroeffentlicht hat.

Die erste Fassung dieser Datei bildete die Entscheidung in einer Hilfsfunktion
NACH, statt get_status() zu rufen -- sie prueft dann die Testdatei gegen sich
selbst. Nachgemessen: eine semantische Ruecknahme in get_status (`in gesperrt`
zu `not in gesperrt`) liess alle 441 Luefter-Tests gruen. Hier laeuft deshalb
der echte Aufruf.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.schemas.fans import FanMode, PwmControl
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService, FanData
from app.services.power.fan_runtime_store import publish_write_permission


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _fan(fan_id: str, pwm_control: PwmControl) -> FanData:
    return FanData(
        fan_id=fan_id, name=fan_id, rpm=800, pwm_percent=40,
        temperature_celsius=42.0, mode=FanMode.MANUAL,
        min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
        temp_sensor_id=None, curve_points=[], is_active=True,
        pwm_control=pwm_control,
    )


def _service(session_factory, monkeypatch, fans):
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True

    backend = LinuxFanControlBackend(MagicMock())
    backend._has_write_permission = True
    backend._fan_cache = {}
    backend.get_fans = AsyncMock(return_value=fans)
    service._backend = backend

    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        False, raising=False)
    return service


async def _zustand(service, fan_id: str) -> PwmControl:
    status = await service.get_status()
    eintrag = next(f for f in status["fans"] if f["fan_id"] == fan_id)
    return eintrag["pwm_control"]


@pytest.mark.asyncio
async def test_ohne_veroeffentlichte_liste_bleibt_der_eigene_stand(
    session_factory, monkeypatch
):
    """Nichts veroeffentlicht heisst ausdruecklich NICHT 'kein Kanal
    gesperrt' -- der Worker behaelt dann seine eigene Sicht."""
    service = _service(session_factory, monkeypatch,
                       [_fan("nct6798:pwm1", PwmControl.SUPPORTED)])

    assert await _zustand(service, "nct6798:pwm1") is PwmControl.SUPPORTED


@pytest.mark.asyncio
async def test_der_gemeldete_kanal_wird_uebernommen(session_factory, monkeypatch):
    """Der Kern: ein Follower, der selbst nie schreibt, zeigt den Befund des
    Primary. Vorher meldete er weiter `supported`, und das Badge in der Karte
    erschien und verschwand im 5-Sekunden-Poll."""
    with session_factory() as db:
        publish_write_permission(db, True, {"nct6798:pwm1"})
    service = _service(session_factory, monkeypatch,
                       [_fan("nct6798:pwm1", PwmControl.SUPPORTED),
                        _fan("nct6798:pwm2", PwmControl.SUPPORTED)])

    assert await _zustand(service, "nct6798:pwm1") is PwmControl.NO_PERMISSION
    assert await _zustand(service, "nct6798:pwm2") is PwmControl.SUPPORTED


@pytest.mark.asyncio
async def test_ein_firmware_kanal_bleibt_unangetastet(session_factory, monkeypatch):
    """Eine dauerhafte Hardware-Eigenschaft darf ein Laufzeit-Befund nicht
    ueberschreiben -- sonst verschwaende das Firmware-Badge, sobald der Primary
    denselben Kanal einmal als gesperrt gemeldet hat."""
    with session_factory() as db:
        publish_write_permission(db, True, {"amdgpu:pwm1"})
    service = _service(session_factory, monkeypatch,
                       [_fan("amdgpu:pwm1", PwmControl.FIRMWARE_MANAGED)])

    assert await _zustand(service, "amdgpu:pwm1") is PwmControl.FIRMWARE_MANAGED


@pytest.mark.asyncio
async def test_ein_eigener_befund_wird_nicht_zurueckgenommen(
    session_factory, monkeypatch
):
    """Vereinigung statt Ersetzung: eine Nutzer-Eingabe geht ueber irgendeinen
    Worker, und bei EACCES vermerkt genau DER den Kanal. Der Primary hat den
    Write nie versucht, seine Liste kennt den Kanal also nicht -- eine
    Ruecksetzung auf SUPPORTED liesse den frischen Befund sofort wieder
    verschwinden, neben einem `last_write_error`, der stehen bleibt."""
    with session_factory() as db:
        publish_write_permission(db, True, set())
    service = _service(session_factory, monkeypatch,
                       [_fan("nct6798:pwm1", PwmControl.NO_PERMISSION)])

    assert await _zustand(service, "nct6798:pwm1") is PwmControl.NO_PERMISSION


@pytest.mark.asyncio
async def test_ein_leerer_eintrag_nimmt_nichts_zurueck(session_factory, monkeypatch):
    """Die Gegenrichtung derselben Regel: meldet der Primary den Kanal nicht
    mehr, aendert das am eigenen Stand nichts -- zurueck kommt der Kanal ueber
    einen eigenen erfolgreichen Write oder die eigene Probe."""
    with session_factory() as db:
        publish_write_permission(db, True, set())
    service = _service(session_factory, monkeypatch,
                       [_fan("nct6798:pwm1", PwmControl.SUPPORTED)])

    assert await _zustand(service, "nct6798:pwm1") is PwmControl.SUPPORTED
