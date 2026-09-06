"""Ein Admin-Neustart darf die Worker-Rolle nicht verlieren (#555).

`POST /api/admin/services/fan_control/restart` hat kein Primary-Gate; bei vier
Uvicorn-Workern bedient die Anfrage mit 3/4 Wahrscheinlichkeit einen Sekundaer.
`restart_service` ruft `start_fn()` ohne Argument auf, und registriert war die
nackte `start_fan_control`, deren Default `monitoring=True` lautet. Der
Sekundaer startete damit eine zweite, vollwertige Regelschleife.

power_manager und gpu_power_manager sind gegen genau das abgesichert: sie
registrieren einen Wrapper, der die Rolle des Workers festhaelt.
"""
from unittest.mock import AsyncMock

import pytest

from app.core import service_registry
from app.services.power import fan_control
from app.services import service_status


@pytest.fixture
def registry_snapshot():
    """register_all_services schreibt in ein Modul-Dict -- danach aufraeumen."""
    previous = dict(service_status._service_registry)
    yield
    service_status._service_registry.clear()
    service_status._service_registry.update(previous)


def _registered_start(monkeypatch, *, primary: bool) -> AsyncMock:
    """Registriert neu und liefert das Mock, das der start_fn treffen muss.

    Gepatcht wird VOR der Registrierung: die alte Fassung uebergab die nackte
    Funktion als start_fn, ein spaeterer Patch haette diese Referenz nicht
    mehr erreicht.
    """
    started = AsyncMock()
    monkeypatch.setattr(fan_control, "start_fan_control", started)
    service_registry.register_all_services(
        is_primary_worker=primary, discovery_service=None
    )
    return started


@pytest.mark.asyncio
async def test_follower_restart_starts_no_monitoring_loop(monkeypatch, registry_snapshot):
    started = _registered_start(monkeypatch, primary=False)
    start_fn = service_status._service_registry["fan_control"]["start"]

    await start_fn()

    assert started.await_count == 1
    assert started.await_args.kwargs.get("monitoring") is False


@pytest.mark.asyncio
async def test_primary_restart_starts_the_monitoring_loop(monkeypatch, registry_snapshot):
    """Die Rolle wird ausdruecklich uebergeben, nicht dem Default ueberlassen.

    Auf dem Primary war das Ergebnis schon vorher richtig -- aber nur durch
    Zufall, weil der Default zufaellig passte.
    """
    started = _registered_start(monkeypatch, primary=True)
    start_fn = service_status._service_registry["fan_control"]["start"]

    await start_fn()

    assert started.await_args.kwargs.get("monitoring") is True
