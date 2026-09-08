"""Ein PWM-Aufruf holt einen freigegebenen Kanal zurueck (#583).

Die Freigabe an die Board-Automatik (#534) war bisher nur in der Oberflaeche
eine Sperre. `POST /api/fans/pwm` schrieb weiter -- mit `force=True`, also
sogar am Backoff vorbei --, waehrend `fan_runtime_state.released_fans` den
Kanal unveraendert als freigegeben fuehrte. Danach zeigte die Karte "Board
regelt", obwohl BaluHost gerade geschrieben hatte, und der naechste
Regelzyklus uebersprang den Kanal wieder: der Wert blieb als Fremdkoerper
stehen, erklaert weder von der Anzeige noch von der Regelung.

Geheilt wird das nicht durch eine Ablehnung, sondern durch die Invariante
"wer schreibt, besitzt auch": der Aufruf holt den Kanal vorher zurueck.
Gemessen wird deshalb die WIRKUNG auf den veroeffentlichten Zustand, nicht
der Aufruf einer Hilfsmethode -- eine Zusicherung auf `reacquire_fan` waere
gruen, auch wenn die Ruecknahme nie in der Zeile landet.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import FanMode
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData
from app.services.power.fan_ownership import FanOwnership, ReleaseReason
from app.services.power.fan_runtime_store import (
    publish_released_fans,
    read_released_fans,
)

FAN = "nct6798-isa-0290:pwm1"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _service(session_factory):
    """Ein Dienst im MANUAL-Modus -- der einzige, in dem set_fan_pwm schreibt."""
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    config.fan_sample_interval_seconds = 5
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True

    backend = MagicMock()
    backend.set_pwm = AsyncMock(return_value=True)
    backend.get_fans = AsyncMock(return_value=[
        FanData(
            fan_id=FAN, name=FAN, rpm=900, pwm_percent=50,
            temperature_celsius=45.0, mode=FanMode.MANUAL,
            min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
            temp_sensor_id="hwmon:x", curve_points=[], is_active=True,
        ),
    ])
    service._backend = backend

    with session_factory() as db:
        db.add(FanConfig(fan_id=FAN, name=FAN, mode=FanMode.MANUAL.value,
                         is_active=True, min_pwm_percent=0, max_pwm_percent=100,
                         temp_sensor_id="hwmon:x"))
        db.commit()
    return service, backend


def _freigeben(session_factory, zustand):
    with session_factory() as db:
        publish_released_fans(db, {
            FAN: {"state": zustand,
                  "reason": ReleaseReason.NOT_CONTROLLABLE.value},
        })


@pytest.mark.parametrize("zustand", [FanOwnership.RELEASED.value,
                                     FanOwnership.ABANDONED.value])
@pytest.mark.asyncio
async def test_ein_pwm_aufruf_holt_den_kanal_zurueck(session_factory, zustand):
    """Beide Zustaende, aus demselben Grund.

    `released` heisst "die Board-Automatik regelt", `abandoned` heisst "es
    regelt niemand". Fuer die Invariante ist der Unterschied gleichgueltig:
    in beiden Faellen fuehrt die Zeile den Kanal als nicht von BaluHost
    besessen, und in beiden Faellen schreibt der Aufruf gleich darauf.
    """
    service, backend = _service(session_factory)
    _freigeben(session_factory, zustand)

    erfolg, _ = await service.set_fan_pwm(FAN, 50)

    assert erfolg is True
    backend.set_pwm.assert_awaited_once_with(FAN, 50, force=True)
    with session_factory() as db:
        assert read_released_fans(db) == {}


@pytest.mark.asyncio
async def test_ohne_veroeffentlichte_ruecknahme_wird_nicht_geschrieben(
    session_factory, monkeypatch
):
    """Scheitert die Ruecknahme, darf der Write nicht stattfinden.

    Sonst entstuende genau der Zustand, den dieser Fix beseitigt -- nur
    diesmal sehenden Auges: BaluHost schriebe einen Kanal, den die
    veroeffentlichte Zeile weiter dem Board zuschreibt. Lieber ein
    fehlgeschlagener Klick mit Fehlermeldung als ein stiller Widerspruch.
    """
    service, backend = _service(session_factory)
    _freigeben(session_factory, FanOwnership.RELEASED.value)
    monkeypatch.setattr(fan_control_module, "publish_released_fans",
                        lambda db, released: False)

    erfolg, rpm = await service.set_fan_pwm(FAN, 50)

    assert erfolg is False
    assert rpm is None
    backend.set_pwm.assert_not_awaited()


@pytest.mark.asyncio
async def test_ein_besessener_kanal_laeuft_unveraendert(session_factory):
    """Regressionswache fuer den Normalfall: sie ist auch ohne den Fix gruen.

    Ihr Wert liegt in der Gegenrichtung -- eine Ruecknahme, die den
    haeufigsten Weg mitnimmt, wuerde hier auffallen: ein Schreibversuch auf
    die Singleton-Zeile bei jedem PWM-Klick, obwohl nie etwas freigegeben
    war.
    """
    service, backend = _service(session_factory)

    erfolg, _ = await service.set_fan_pwm(FAN, 50)

    assert erfolg is True
    backend.set_pwm.assert_awaited_once_with(FAN, 50, force=True)
    with session_factory() as db:
        assert read_released_fans(db) == {}
