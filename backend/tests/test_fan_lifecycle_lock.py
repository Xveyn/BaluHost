"""Es gibt hoechstens eine Regelschleife, und stop() beendet sie (#559).

`start` und der Neustart-Block in `switch_backend` wiesen `_monitoring_task`
unbedingt zu. Ueberlappten zwei Lebenszyklus-Operationen, ueberschrieb die
zweite die Referenz auf die Task der ersten. Diese lief weiter, war von nichts
mehr referenziert und liess sich weder von `stop()` noch von einem weiteren
Aufruf abbrechen -- sie schrieb bis zum Prozess-Ende alle 5 Sekunden
`pwm_enable=1` und hebelte die Rueckgabe an die Board-Automatik aus (#534).

**Korrektur am Ausloeser aus #559.** Dort stand, zwei ueberlappende
`switch_backend`-Aufrufe erzeugten die Waise. Nachgemessen trifft das NICHT
zu: `switch_backend` liest `was_running` und setzt `_is_running` unmittelbar
danach auf False, ohne await dazwischen. Der zweite Aufruf liest deshalb
`was_running=False` und ueberspringt den Neustart im finally. Ein Test dafuer
lief gegen den unveraenderten Code gruen.

Erreichbar ist die Waise ueber die beiden Wege, die dieser Test festhaelt:

* zwei `start(monitoring=True)` -- dort gibt es gar keinen Schutz, die
  Zuweisung erfolgt unbedingt (Admin-Endpunkt /services/fan_control/start)
* ein `stop()`, das in einen laufenden `switch_backend` faellt -- dessen
  finally erzeugt danach eine neue Schleife, obwohl gerade gestoppt wurde
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


@pytest.fixture
def service(monkeypatch):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = True
    svc = FanControlService(config, MagicMock())

    monkeypatch.setattr(fan_control_module, "DevFanControlBackend",
                        lambda *a, **k: MagicMock())
    monkeypatch.setattr(svc, "_release_all_to_board", AsyncMock())
    monkeypatch.setattr(svc, "_rebuild_registry", AsyncMock())
    svc._backend = MagicMock()
    monkeypatch.setattr(svc, "_initialize_backend", AsyncMock())

    async def slow_load():
        # Zwei Yield-Punkte: bildet die await-Strecke im echten Ablauf nach
        # (Chip-Scan, Datenbankzugriffe) und laesst eine zweite Operation
        # tatsaechlich dazwischenfahren.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    monkeypatch.setattr(svc, "_load_fan_configs", slow_load)
    return svc


@pytest.fixture
def loops(service, monkeypatch):
    """Sammelt jede erzeugte Regelschleife, damit Waisen sichtbar werden."""
    created: list[asyncio.Task] = []

    async def fake_loop():
        created.append(asyncio.current_task())
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_monitoring_loop", fake_loop)
    return created


async def _alive(loops) -> list:
    await asyncio.sleep(0)
    return [task for task in loops if not task.done()]


@pytest.mark.asyncio
async def test_starting_twice_leaves_a_single_loop(service, loops):
    """start() hatte keinerlei Schutz: die Zuweisung erfolgte unbedingt."""
    await service.start(monitoring=True)
    await service.start(monitoring=True)

    assert len(await _alive(loops)) == 1, "eine Regelschleife ist verwaist"


@pytest.mark.asyncio
async def test_a_second_start_does_not_survive_stop(service, loops):
    """Der eigentliche Schaden: die Waise ueberlebt stop().

    Sie schreibt danach weiter `pwm_enable=1` -- gegen die Rueckgabe an die
    Board-Automatik, die stop() unmittelbar davor ausgefuehrt hat.
    """
    await service.start(monitoring=True)
    await service.start(monitoring=True)

    await service.stop()

    assert await _alive(loops) == [], "eine Regelschleife hat stop() ueberlebt"


@pytest.mark.asyncio
async def test_stop_during_a_backend_switch_leaves_nothing_running(service, loops):
    """stop() faellt in einen laufenden switch_backend.

    Dessen finally startet die Schleife danach neu -- der Dienst gilt als
    gestoppt und regelt trotzdem weiter.
    """
    service._is_running = True
    service._monitoring_task = asyncio.create_task(service._monitoring_loop())
    await asyncio.sleep(0)

    switching = asyncio.create_task(service.switch_backend(False))
    await asyncio.sleep(0)

    await service.stop()
    await switching

    assert await _alive(loops) == [], "nach stop() laeuft noch eine Schleife"


@pytest.mark.asyncio
async def test_two_concurrent_switches_leave_a_single_loop(service, loops):
    """Haelt die gemessene Eigenschaft fest, statt sie zu behaupten.

    Dieser Fall war der in #559 genannte Ausloeser und ist es nicht: der Test
    laeuft auch gegen den unveraenderten Code gruen. Er bleibt als Beleg
    stehen -- und als Schutz davor, dass ein kuenftiger Umbau des
    `was_running`-Griffs die Eigenschaft still verliert.
    """
    service._is_running = True
    service._monitoring_task = asyncio.create_task(service._monitoring_loop())
    await asyncio.sleep(0)

    await asyncio.gather(
        service.switch_backend(False),
        service.switch_backend(False),
    )

    assert len(await _alive(loops)) == 1
    await service.stop()
    assert await _alive(loops) == []
