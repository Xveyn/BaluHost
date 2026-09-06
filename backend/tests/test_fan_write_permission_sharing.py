"""Das Schreibrecht ist eine Eigenschaft der Maschine, nicht des Prozesses (#552).

`_has_write_permission` war ein reines Instanz-Attribut. Bei vier Uvicorn-
Workern gab es vier Wahrheiten ueber denselben Zustand derselben Hardware, und
geheilt hat sich nur, wer schreibt -- also der Primary ueber den Regelkreis.
Die drei Follower blieben auf ihrem Startwert stehen; der 5-Sekunden-Poll des
Frontends landete abwechselnd auf einem geheilten und drei ungeheilten Workern.

Der Primary veroeffentlicht seinen Stand jetzt in `fan_runtime_state`, alle
Worker lesen ihn von dort. Gleiches Muster wie `PowerRuntimeState` und
`GpuPowerRuntimeState` -- letztere fuehrt dieselbe Spalte fuer denselben Zweck.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanRuntimeState
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService
from app.services.power.fan_runtime_store import (
    publish_write_permission,
    read_write_permission,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _service(session_factory, monkeypatch, *, may_write: bool, primary: bool):
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True

    backend = LinuxFanControlBackend(MagicMock())
    backend._has_write_permission = may_write
    backend.get_fans = AsyncMock(return_value=[])
    service._backend = backend

    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


# --- Der Speicher selbst ------------------------------------------------


def test_reading_without_a_row_returns_none(session_factory):
    """Kein Eintrag heisst "nicht veroeffentlicht" -- nicht "kein Schreibrecht".

    Der Aufrufer muss beides unterscheiden koennen, sonst meldete eine frisch
    migrierte Datenbank faelschlich readonly.
    """
    with session_factory() as db:
        assert read_write_permission(db) is None


def test_publishing_and_reading_round_trip(session_factory):
    with session_factory() as db:
        publish_write_permission(db, True)
    with session_factory() as db:
        assert read_write_permission(db) is True


def test_publishing_twice_keeps_a_single_row(session_factory):
    """Singleton-Zeile wie bei PowerRuntimeState -- kein Verlauf."""
    with session_factory() as db:
        publish_write_permission(db, True)
    with session_factory() as db:
        publish_write_permission(db, False)

    with session_factory() as db:
        rows = list(db.execute(select(FanRuntimeState)).scalars())
    assert len(rows) == 1
    assert rows[0].has_write_permission is False


# --- Die Ableitung in get_status ---------------------------------------


@pytest.mark.asyncio
async def test_a_follower_follows_the_published_value(session_factory, monkeypatch):
    """Der Kern: der Follower haelt sich fuer schreibfaehig und ist es nicht.

    Genau diese Divergenz erzeugte das Flackern -- der eine Worker meldete
    "ok", die anderen "readonly", und der Poll traf mal den einen, mal die
    anderen.
    """
    with session_factory() as db:
        publish_write_permission(db, False)

    service = _service(session_factory, monkeypatch, may_write=True, primary=False)

    status = await service.get_status()

    assert status["permission_status"] == "readonly"


@pytest.mark.asyncio
async def test_a_follower_learns_that_writing_works(session_factory, monkeypatch):
    """Die Gegenrichtung: der Primary hat sich geheilt, der Follower zieht nach."""
    with session_factory() as db:
        publish_write_permission(db, True)

    service = _service(session_factory, monkeypatch, may_write=False, primary=False)

    status = await service.get_status()

    assert status["permission_status"] == "ok"


@pytest.mark.asyncio
async def test_without_a_published_value_the_local_probe_decides(
        session_factory, monkeypatch):
    """Frisch migrierte Datenbank, noch nichts veroeffentlicht."""
    service = _service(session_factory, monkeypatch, may_write=False, primary=True)

    status = await service.get_status()

    assert status["permission_status"] == "readonly"


# --- Der Primary veroeffentlicht ---------------------------------------


@pytest.mark.asyncio
async def test_the_primary_publishes_its_own_state(session_factory, monkeypatch):
    service = _service(session_factory, monkeypatch, may_write=True, primary=True)

    service.publish_write_permission_if_changed()

    with session_factory() as db:
        assert read_write_permission(db) is True


@pytest.mark.asyncio
async def test_a_follower_never_publishes(session_factory, monkeypatch):
    """Sonst ueberschriebe der ungeheilte Follower den Stand des Primary."""
    service = _service(session_factory, monkeypatch, may_write=True, primary=False)

    service.publish_write_permission_if_changed()

    with session_factory() as db:
        assert read_write_permission(db) is None


@pytest.mark.asyncio
async def test_the_primary_writes_only_on_change(session_factory, monkeypatch):
    """Der Aufruf sitzt im 5-Sekunden-Takt -- ein Schreibvorgang je Tick waere
    dieselbe Sorte Last, die #533 beseitigt hat."""
    service = _service(session_factory, monkeypatch, may_write=True, primary=True)
    service.publish_write_permission_if_changed()

    with session_factory() as db:
        first = db.execute(select(FanRuntimeState)).scalar_one().updated_at

    for _ in range(5):
        service.publish_write_permission_if_changed()

    with session_factory() as db:
        assert db.execute(select(FanRuntimeState)).scalar_one().updated_at == first


# --- Verdrahtung -------------------------------------------------------
#
# Ohne diese beiden Tests koennte man beide Aufrufstellen entfernen und die
# Suite bliebe gruen -- bei totem Feature. Die Falle aus dem Review zu #534.


@pytest.mark.asyncio
async def test_start_publishes_the_probe_result(session_factory, monkeypatch):
    """Der Rechte-Probe laeuft beim Backend-Init, nicht im Regelzyklus.

    Ohne die Veroeffentlichung in start() erfuehren die Follower sein
    Ergebnis erst, wenn sich der Zustand spaeter zufaellig aendert.
    """
    service = _service(session_factory, monkeypatch, may_write=True, primary=True)
    service.config.fan_control_enabled = True
    monkeypatch.setattr(service, "_initialize_backend", AsyncMock())
    monkeypatch.setattr(service, "_rebuild_registry", AsyncMock())
    monkeypatch.setattr(service, "_load_fan_configs", AsyncMock())

    await service.start(monitoring=False)

    with session_factory() as db:
        assert read_write_permission(db) is True


@pytest.mark.asyncio
async def test_the_monitoring_loop_publishes_a_later_change(
        session_factory, monkeypatch):
    """Der Fall aus dem Issue: der Probe scheitert, ein Write heilt spaeter.

    Geheilt wird in _write_hwmon_file, tief im Regelzyklus. Ohne den Abgleich
    in der Schleife bliebe das im Primary-Prozess stecken.
    """
    service = _service(session_factory, monkeypatch, may_write=False, primary=True)
    service.config.fan_sample_interval_seconds = 0
    service.publish_write_permission_if_changed()

    with session_factory() as db:
        assert read_write_permission(db) is False

    async def one_cycle():
        # bildet den erfolgreichen Write in _write_hwmon_file nach
        service._backend._has_write_permission = True
        service._is_running = False

    monkeypatch.setattr(service, "_monitor_and_control_fans", one_cycle)
    service._is_running = True

    await service._monitoring_loop()

    with session_factory() as db:
        assert read_write_permission(db) is True
