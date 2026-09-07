"""Die Rueckgabe im laufenden Regelkreis (#534 Punkt 1).

Geprueft wird der Regelkreis selbst, nicht eine Nachbildung: die Befunde, an
denen der erste Anlauf scheiterte, betreffen fast alle die Stelle, an der der
Uebersprung sitzt -- ob der Sample-Puffer weiterlaeuft, ob die Notfall-Emitter
erhalten bleiben, ob _last_pwm_by_fan fortgeschrieben wird. Eine Hilfsfunktion,
die diese Entscheidung nachbaut, wuerde genau das nicht messen.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import FanMode, PwmControl
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData
from app.services.power.fan_ownership import FanOwnership
from app.services.power.fan_runtime_store import read_released_fans


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _fan(fan_id="nct6798:pwm1", pwm=40, pwm_control=PwmControl.SUPPORTED) -> FanData:
    return FanData(
        fan_id=fan_id, name=fan_id, rpm=800, pwm_percent=pwm,
        temperature_celsius=45.0, mode=FanMode.AUTO,
        min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
        temp_sensor_id="hwmon:x", curve_points=[], is_active=True,
        pwm_control=pwm_control,
    )


def _service(session_factory, monkeypatch, *, fans, am_deckel, beobachtet=5,
             rueckgabe_glueckt=True):
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    config.fan_sample_interval_seconds = 5
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True

    backend = MagicMock()
    backend.get_fans = AsyncMock(return_value=fans)
    backend.set_pwm = AsyncMock(return_value=True)
    backend.release_to_board = AsyncMock(return_value=rueckgabe_glueckt)
    backend.write_failure_state = MagicMock(return_value=(8 if am_deckel else 1, am_deckel))
    service._backend = backend

    service._restore_values = (
        {f.fan_id: beobachtet for f in fans} if beobachtet is not None else {}
    )
    service._registry = MagicMock()
    service._registry.get_temp = AsyncMock(return_value=45.0)
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    with session_factory() as db:
        for f in fans:
            db.add(FanConfig(fan_id=f.fan_id, name=f.name, mode=FanMode.AUTO.value,
                             is_active=True, min_pwm_percent=0, max_pwm_percent=100,
                             temp_sensor_id="hwmon:x",
                             curve_json='[{"temp": 30, "pwm": 30}, {"temp": 60, "pwm": 80}]'))
        db.commit()
    return service, backend


@pytest.mark.asyncio
async def test_ein_kanal_am_deckel_wird_zurueckgegeben(session_factory, monkeypatch):
    service, backend = _service(session_factory, monkeypatch,
                                fans=[_fan()], am_deckel=True)

    await service._monitor_and_control_fans()

    backend.release_to_board.assert_awaited_once_with("nct6798:pwm1", 5)
    with session_factory() as db:
        assert read_released_fans(db) == {"nct6798:pwm1": FanOwnership.RELEASED.value}


@pytest.mark.asyncio
async def test_unterhalb_des_deckels_bleibt_alles_wie_bisher(session_factory, monkeypatch):
    service, backend = _service(session_factory, monkeypatch,
                                fans=[_fan()], am_deckel=False)

    await service._monitor_and_control_fans()

    backend.release_to_board.assert_not_awaited()
    with session_factory() as db:
        assert read_released_fans(db) == {}


@pytest.mark.asyncio
async def test_ohne_beobachteten_wert_wird_nicht_zurueckgegeben(
    session_factory, monkeypatch
):
    """Die geerbte Randbedingung aus #556 -- auf BaluNode betrifft das pwm7."""
    service, backend = _service(session_factory, monkeypatch,
                                fans=[_fan()], am_deckel=True, beobachtet=None)

    await service._monitor_and_control_fans()

    backend.release_to_board.assert_not_awaited()


@pytest.mark.asyncio
async def test_eine_gescheiterte_rueckgabe_heisst_niemand_regelt(
    session_factory, monkeypatch
):
    """Bei einem nicht schreibbaren Kanal der wahrscheinliche Fall -- derselbe
    Knoten, dieselben Rechte. Eine Oberflaeche, die hier 'das Board regelt'
    anzeigt, waere unehrlich."""
    service, _ = _service(session_factory, monkeypatch, fans=[_fan()],
                          am_deckel=True, rueckgabe_glueckt=False)

    await service._monitor_and_control_fans()

    with session_factory() as db:
        assert read_released_fans(db) == {"nct6798:pwm1": FanOwnership.ABANDONED.value}


@pytest.mark.asyncio
async def test_ein_freigegebener_kanal_wird_nicht_mehr_geschrieben(
    session_factory, monkeypatch
):
    service, backend = _service(session_factory, monkeypatch,
                                fans=[_fan()], am_deckel=True)
    await service._monitor_and_control_fans()
    backend.set_pwm.reset_mock()

    await service._monitor_and_control_fans()

    backend.set_pwm.assert_not_awaited()
    # Und kein zweiter Rueckgabeversuch: die Bedingung ist ein Zustand, keine
    # Flanke -- sonst schriebe jeder Zyklus erneut gegen den Knoten.
    assert backend.release_to_board.await_count == 1


@pytest.mark.asyncio
async def test_der_sample_puffer_laeuft_weiter(session_factory, monkeypatch):
    """Der Uebersprung darf die Messwerte nicht mitnehmen -- sonst risse der
    Verlaufsgraph genau dort ab, wo man nachsieht. Deshalb kein `continue`."""
    service, _ = _service(session_factory, monkeypatch, fans=[_fan()], am_deckel=True)

    await service._monitor_and_control_fans()
    service._sample_buffer.clear()
    await service._monitor_and_control_fans()

    assert len(service._sample_buffer) == 1
    probe = service._sample_buffer[0]
    assert probe["fan_id"] == "nct6798:pwm1"
    assert probe["rpm"] == 800
    assert probe["temperature_celsius"] == 45.0


@pytest.mark.asyncio
async def test_der_notfall_wird_weiter_gemeldet(session_factory, monkeypatch):
    """Bei einem freigegebenen Kanal ist die Temperatur weiter lesbar. Ein
    Uebersprung, der die Emitter mitnimmt, machte aus einem gemeldeten
    Ueberhitzungsfall einen stillen."""
    gemeldet = []
    import app.services.notifications.events as events
    monkeypatch.setattr(events, "emit_temperature_critical_sync",
                        lambda *a: gemeldet.append(a), raising=False)

    service, _ = _service(session_factory, monkeypatch, fans=[_fan()], am_deckel=True)
    service._registry.get_temp = AsyncMock(return_value=95.0)

    await service._monitor_and_control_fans()

    assert gemeldet, "die Ueberhitzung eines freigegebenen Kanals muss gemeldet werden"


@pytest.mark.asyncio
async def test_last_pwm_traegt_den_ist_wert(session_factory, monkeypatch):
    """Sonst ginge nach der Wiederuebernahme ein minutenalter Wert als `prev`
    in die Glaettung ein."""
    service, _ = _service(session_factory, monkeypatch,
                          fans=[_fan(pwm=37)], am_deckel=True)

    await service._monitor_and_control_fans()

    assert service._last_pwm_by_fan["nct6798:pwm1"] == 37


@pytest.mark.asyncio
async def test_wieder_uebernehmen_erzwingt_genau_einen_write(
    session_factory, monkeypatch
):
    """Ohne den erzwungenen Write bliebe pwm_enable auf dem Auto-Wert stehen,
    falls das Board zufaellig denselben PWM eingestellt hat, den die Kurve
    berechnet -- der Regelkreis schreibt nur bei Wertaenderung."""
    service, backend = _service(session_factory, monkeypatch,
                                fans=[_fan()], am_deckel=True)
    await service._monitor_and_control_fans()
    backend.set_pwm.reset_mock()

    assert await service.reacquire_fan("nct6798:pwm1") is True

    backend.set_pwm.assert_awaited_once()
    assert backend.set_pwm.await_args.kwargs.get("force") is True
    with session_factory() as db:
        assert read_released_fans(db) == {}


@pytest.mark.asyncio
async def test_wieder_uebernehmen_eines_nicht_freigegebenen_kanals(
    session_factory, monkeypatch
):
    service, _ = _service(session_factory, monkeypatch, fans=[_fan()], am_deckel=False)

    assert await service.reacquire_fan("nct6798:pwm1") is False


@pytest.mark.asyncio
async def test_ein_firmware_kanal_wird_nicht_freigegeben(session_factory, monkeypatch):
    service, backend = _service(
        session_factory, monkeypatch,
        fans=[_fan(pwm_control=PwmControl.FIRMWARE_MANAGED)], am_deckel=True)

    await service._monitor_and_control_fans()

    backend.release_to_board.assert_not_awaited()
