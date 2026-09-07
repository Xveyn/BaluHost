"""Die Akustik-Endpunkte (#516).

Aufgerufen wird __wrapped__, also der Handler ohne slowapi-Dekorator:
geprueft wird die Verdrahtung, nicht das Rate-Limit.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import fans as fans_routes
from app.models.base import Base
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics import ParsedNode
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def service(session_factory):
    @contextmanager
    def factory():
        with session_factory() as db:
            yield db

    svc = SimpleNamespace(db_session_factory=factory)
    svc._backend = MagicMock()
    svc._backend._write_hwmon_file = AsyncMock(return_value=(True, None))
    # apply_acoustics, nicht apply_gpu_acoustics: der PUT-Pfad darf nicht am
    # Primary-Gate haengen (#516).
    #
    # Das side_effect ist nicht Zierde: ein blosses AsyncMock() liefert beim
    # await wieder ein AsyncMock, dessen .get(name, False) ein Coroutine-Objekt
    # ist -- immer truthy. Der PUT haette dann jeden Wert als angenommen
    # gebucht, und der Test waere gruen, ohne noch etwas zu pruefen (dazu eine
    # RuntimeWarning ueber die nie erwartete Coroutine). Hier antwortet die
    # Attrappe wie eine Karte, die alles annimmt.
    svc.apply_acoustics = AsyncMock(
        side_effect=lambda desired: {name: True for name in desired}
    )
    svc._gpu_fan_ctrl_dir = lambda: Path("/fake/fan_ctrl")
    return svc


CURRENT = {
    "fan_target_temperature": ParsedNode(value=95, minimum=25, maximum=105),
}


@pytest.fixture(autouse=True)
def patched_module(monkeypatch, tmp_path):
    monkeypatch.setattr(fans_routes, "read_acoustics",
                        AsyncMock(return_value=CURRENT))
    monkeypatch.setattr(fans_routes, "LACT_CONFIG_PATH", tmp_path / "lact.yaml")


async def _get(service):
    handler = fans_routes.get_gpu_acoustics.__wrapped__
    return await handler(request=SimpleNamespace(), response=SimpleNamespace(),
                         current_user=MagicMock(), service=service)


async def _put(service, values):
    handler = fans_routes.set_gpu_acoustics.__wrapped__
    return await handler(request=SimpleNamespace(), response=SimpleNamespace(),
                         body=values, current_user=MagicMock(), service=service)


@pytest.mark.asyncio
async def test_get_reports_values_and_ranges(service):
    body = await _get(service)
    assert body.available is True
    node = body.nodes["fan_target_temperature"]
    assert (node.current, node.minimum, node.maximum) == (95, 25, 105)
    assert node.desired is None


@pytest.mark.asyncio
async def test_a_card_without_the_interface_reports_unavailable(service):
    service._gpu_fan_ctrl_dir = lambda: None
    body = await _get(service)
    assert body.available is False
    assert body.nodes == {}


@pytest.mark.asyncio
async def test_a_competing_manager_is_named(service, monkeypatch, tmp_path):
    config = tmp_path / "lact.yaml"
    config.write_text("daemon:\n  pmfw_options:\n    acoustic_limit: 3000\n")
    monkeypatch.setattr(fans_routes, "LACT_CONFIG_PATH", config)

    body = await _get(service)

    assert body.competing_manager == "lact"


@pytest.mark.asyncio
async def test_put_stores_and_applies(service, session_factory):
    await _put(service, GpuFanAcousticsValues(fan_target_temperature=75))

    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature == 75
    service.apply_acoustics.assert_awaited()


@pytest.mark.asyncio
async def test_put_with_null_restores_the_baseline(
        service, session_factory, monkeypatch):
    """Der Zuruecksetzen-Knopf: alle Felder null.

    Gepatcht wird ueber monkeypatch, nicht per Zuweisung an das Modul -- eine
    Zuweisung ueberlebt den Test und leckt in die naechsten.
    """
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))

    written = []

    async def recording(fan_ctrl, name, value, writer):
        written.append((name, value))
        return True

    monkeypatch.setattr(fans_routes, "write_acoustic", recording)

    await _put(service, GpuFanAcousticsValues())

    assert written == [("fan_target_temperature", 95)], "Baseline nicht zurueckgeschrieben"
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature is None
