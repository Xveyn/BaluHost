"""Der GPU-Tick ueberlebt einen Neustart im Zustand STANDBY (#570-Nachlese).

Auf BaluNode gemessen (2026-09-07): 778 Logzeilen `GPU power monitor tick
failed: ` seit dem 06.09. 15:27 -- mit LEERER Meldung. Ursache war ein
`assert self._standby_since is not None` im Tick: _hydrate_from_runtime_state
holt _state aus der Datenbank, _standby_since lebt aber nur im Prozess. Ein
AssertionError ohne Argumente stringifiziert zu '', deshalb sagte die Zeile
nichts.

Der Schaden war nicht der Logeintrag: der Tick brach VOR dem Uebergang nach
DEEP_IDLE ab. Nach einem Neustart im STANDBY erreichte die GPU den Tiefschlaf
also nie wieder.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.power.gpu import manager as manager_module
from app.services.power.gpu.manager import GpuPowerManagerService
from app.schemas.gpu_power import GpuPowerState


def _service(monkeypatch, *, state: GpuPowerState, last_transition):
    """Ein Dienst, dessen Zustand aus der Laufzeittabelle kommt -- wie nach
    einem Neustart."""
    svc = object.__new__(GpuPowerManagerService)
    svc._state = GpuPowerState.ACTIVE
    svc._standby_since = None
    svc._idle_since = datetime.now(timezone.utc)
    svc._last_transition = None
    svc._last_reason = None
    monkeypatch.setattr(
        manager_module, "load_runtime_state",
        lambda: {"current_state": state.value, "last_transition": last_transition,
                 "last_reason": "idle_window_elapsed"},
    )
    return svc


def test_standby_seit_wird_aus_der_laufzeittabelle_wiederhergestellt(monkeypatch):
    """Der letzte Uebergang IST der Beginn des STANDBY -- die Deep-Idle-Frist
    ueberlebt damit den Neustart, statt neu zu beginnen."""
    vorher = datetime.now(timezone.utc) - timedelta(minutes=42)
    svc = _service(monkeypatch, state=GpuPowerState.STANDBY, last_transition=vorher)

    svc._hydrate_from_runtime_state()

    assert svc._state is GpuPowerState.STANDBY
    assert svc._standby_since == vorher


def test_ein_naiver_zeitstempel_wird_als_utc_gelesen(monkeypatch):
    """Die Datenbank liefert je nach Treiber einen naiven datetime. Ohne
    tzinfo wuerde der Vergleich im Tick mit TypeError fliegen -- also genau
    wieder eine Ausnahme im Tick, nur mit anderem Text."""
    naiv = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    svc = _service(monkeypatch, state=GpuPowerState.STANDBY, last_transition=naiv)

    svc._hydrate_from_runtime_state()

    assert svc._standby_since is not None
    assert svc._standby_since.tzinfo is not None
    # Vergleichbar mit einem aware datetime, ohne zu werfen:
    assert datetime.now(timezone.utc) - svc._standby_since >= timedelta(minutes=4)


def test_ohne_letzten_uebergang_bleibt_es_offen(monkeypatch):
    """Kein Zeitstempel in der Tabelle: dann faengt der Tick die Luecke ab,
    nicht das Hydrieren."""
    svc = _service(monkeypatch, state=GpuPowerState.STANDBY, last_transition=None)

    svc._hydrate_from_runtime_state()

    assert svc._standby_since is None


@pytest.mark.asyncio
async def test_der_tick_wirft_nicht_wenn_der_zeitpunkt_fehlt(monkeypatch):
    """Der eigentliche Regressionstest: STANDBY ohne _standby_since darf den
    Tick nicht abbrechen. Vor dem Fix stand hier ein assert."""
    svc = object.__new__(GpuPowerManagerService)
    svc._state = GpuPowerState.STANDBY
    svc._standby_since = None
    svc._idle_since = datetime.now(timezone.utc)

    class _Config:
        enabled = True
        usage_threshold_percent = 10.0
        idle_window_seconds = 60
        deep_idle_extra_seconds = 300
        deep_idle_grace_seconds = 0

    class _Backend:
        detected = True

    svc._config = _Config()
    svc._backend = _Backend()
    svc._demands = {}

    async def _keine_displays():
        return 0

    async def _keine_last():
        return 0.0

    async def _nichts_zu_raeumen():
        return None

    monkeypatch.setattr(svc, "_get_displays", _keine_displays, raising=False)
    monkeypatch.setattr(svc, "_get_usage_percent", _keine_last, raising=False)
    monkeypatch.setattr(svc, "_purge_expired_demands", _nichts_zu_raeumen, raising=False)

    await svc._tick()

    # Der Tick hat die Frist eroeffnet statt zu werfen; DEEP_IDLE kommt beim
    # naechsten Durchlauf, sobald deep_idle_extra_seconds verstrichen sind.
    assert svc._standby_since is not None
    assert svc._state is GpuPowerState.STANDBY
