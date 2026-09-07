"""Die Dienstschicht erfasst die Baseline und wendet desired an (#516).

Zwei Zusagen: nur der Primary schreibt Hardware (#555, #559), und die
Baseline wird VOR dem ersten Write erfasst -- danach nicht mehr, sonst
zeichnete sie den eigenen Eingriff auf.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService
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


def _service(session_factory, monkeypatch, *, primary: bool = True):
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    service._backend = MagicMock()
    service._backend._fan_cache = {
        "amdgpu-pci-0300:pwm1": {
            "gpu_vendor": "amd",
            "pwm_path": Path("/sys/class/hwmon/hwmon2/pwm1"),
        }
    }
    service._backend._write_hwmon_file = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def _patch_module(monkeypatch, *, current: dict, written: list):
    monkeypatch.setattr(fan_control_module, "find_fan_ctrl_dir",
                        lambda hwmon: Path("/fake/fan_ctrl"))
    monkeypatch.setattr(fan_control_module, "read_acoustics",
                        AsyncMock(return_value=current))

    async def write(fan_ctrl, name, value, writer):
        written.append((name, value))
        return True

    monkeypatch.setattr(fan_control_module, "write_acoustic", write)


CURRENT = {
    "fan_target_temperature": ParsedNode(value=95, minimum=25, maximum=105),
    "fan_minimum_pwm": ParsedNode(value=23, minimum=23, maximum=100),
}


@pytest.mark.asyncio
async def test_captures_the_baseline_before_the_first_write(
        session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_gpu_acoustics()

    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.baseline.fan_target_temperature == 95, "Baseline nicht erfasst"
    assert written == [("fan_target_temperature", 75)]


@pytest.mark.asyncio
async def test_an_existing_baseline_is_not_overwritten(
        session_factory, monkeypatch):
    """Sonst zeichnete der zweite Start den eigenen Eingriff als Baseline auf."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=88)))

    await service.apply_gpu_acoustics()

    with session_factory() as db:
        assert load_acoustics_config(db).baseline.fan_target_temperature == 88


@pytest.mark.asyncio
async def test_nothing_desired_writes_nothing(session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)

    await service.apply_gpu_acoustics()

    assert written == []


@pytest.mark.asyncio
async def test_a_follower_writes_no_hardware(session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch, primary=False)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_gpu_acoustics()

    assert written == []


@pytest.mark.asyncio
async def test_the_put_path_writes_even_on_a_follower(session_factory, monkeypatch):
    """Der Blocker: eine ausdrueckliche Nutzeraktion landet bei vier Workern
    in drei von vier Faellen auf einem Follower. Ohne diesen Test quittierte
    der Endpunkt mit 200 und aenderte an der Karte nichts."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch, primary=False)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_acoustics()

    assert written == [("fan_target_temperature", 75)]


@pytest.mark.asyncio
async def test_start_applies_the_configuration(session_factory, monkeypatch):
    """Verdrahtung: ohne diesen Test koennte man den Aufruf in start()
    entfernen und die Suite bliebe gruen."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    service.config.fan_control_enabled = True
    monkeypatch.setattr(service, "_initialize_backend", AsyncMock())
    monkeypatch.setattr(service, "_rebuild_registry", AsyncMock())
    monkeypatch.setattr(service, "_load_fan_configs", AsyncMock())
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_minimum_pwm=40)))

    await service.start(monitoring=False)

    assert written == [("fan_minimum_pwm", 40)]


@pytest.mark.asyncio
async def test_apply_acoustics_nutzt_den_weichen_loader(
    session_factory, monkeypatch
):
    """apply_acoustics() muss den WEICHEN Loader nehmen (#570).

    Geprueft wird hier direkt apply_acoustics(), nicht der Startpfad --
    der ruft apply_acoustics() seinerseits auf (siehe
    test_start_applies_the_configuration), das Primary-Gate von start()
    ist fuer diese Frage ohne Bedeutung. Naehme apply_acoustics stattdessen
    die harte Ladevariante, wuerde eine unlesbare Zeile
    AcousticsConfigUnreadable werfen. Dass ein Aufrufer wie start() das in
    try/except faengt, macht die Wahl des Loaders nicht ueberfluessig -- es
    verbirgt nur ihren Verlust.
    """
    from app.models.fans import GpuFanAcousticsConfigDb

    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kein gueltiges json"))
        db.commit()

    service = _service(session_factory, monkeypatch)
    written: list = []
    _patch_module(monkeypatch, current={}, written=written)

    result = await service.apply_acoustics()

    assert result == {}
    assert written == []
