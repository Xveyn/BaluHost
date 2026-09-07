"""Was passiert, wenn der Hardware-Write oder die Datenbank nicht mitspielt (#516).

Vier Zusagen, die der Entwurf macht und die vorher niemand geprueft hat:

1. Ein abgelehnter Wert wird nicht als ``desired`` persistiert, und die Antwort
   des PUT sagt je Knoten, ob der Write geglueckt ist.
2. Ein zweites 'Zuruecksetzen' greift wieder, wenn das erste gescheitert ist.
3. Ein Lesefehler der Konfiguration bricht den Schreibpfad ab, statt die
   beobachtete Baseline zu ueberschreiben.
4. Ein veralteter Snapshot kann die Baseline nicht mit BaluHosts eigenem
   Eingriff kontaminieren.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import fans as fans_routes
from app.core.exceptions import ServiceUnavailableError
from app.models.base import Base
from app.models.fans import GpuFanAcousticsConfigDb
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


# --- Der PUT-Endpunkt ----------------------------------------------------


@pytest.fixture
def service(session_factory):
    @contextmanager
    def factory():
        with session_factory() as db:
            yield db

    svc = SimpleNamespace(db_session_factory=factory)
    svc._backend = MagicMock()
    svc._backend._write_hwmon_file = AsyncMock(return_value=(True, None))
    # Der PUT reicht seine Wuensche an apply_acoustics und liest deren
    # Ergebnis je Knoten -- hier stellbar, um einen abgelehnten Write
    # nachzustellen.
    svc.apply_acoustics = AsyncMock(return_value={})
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


async def _put(service, values):
    handler = fans_routes.set_gpu_acoustics.__wrapped__
    return await handler(request=SimpleNamespace(), response=SimpleNamespace(),
                         body=values, current_user=MagicMock(), service=service)


@pytest.mark.asyncio
async def test_a_rejected_value_is_not_persisted_as_desired(
        service, session_factory):
    """Befund 1: 200 liegt ausserhalb des gemeldeten Bereichs.

    Das Schema laesst es durch, der Treiber lehnt ab. Wuerde der Wert
    trotzdem gespeichert, versuchte ihn JEDER Start erneut -- sichtbar nur
    als WARNING im Log.
    """
    service.apply_acoustics = AsyncMock(
        return_value={"fan_target_temperature": False})

    body = await _put(service, GpuFanAcousticsValues(fan_target_temperature=200))

    assert body.writes["fan_target_temperature"].ok is False
    with session_factory() as db:
        stored = load_acoustics_config(db).desired.fan_target_temperature
    assert stored is None, f"abgelehnter Wert dauerhaft gespeichert: {stored}"


@pytest.mark.asyncio
async def test_a_failed_write_keeps_the_previous_desired(
        service, session_factory):
    """Ein gescheiterter Write darf einen funktionierenden Wert nicht
    verdraengen -- sonst verliert der Nutzer seine Einstellung an einen
    Versuch, den die Karte nie angenommen hat."""
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))
    service.apply_acoustics = AsyncMock(
        return_value={"fan_target_temperature": False})

    await _put(service, GpuFanAcousticsValues(fan_target_temperature=200))

    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature == 75


@pytest.mark.asyncio
async def test_a_successful_write_is_reported_and_persisted(
        service, session_factory):
    service.apply_acoustics = AsyncMock(
        return_value={"fan_target_temperature": True})

    body = await _put(service, GpuFanAcousticsValues(fan_target_temperature=75))

    assert body.writes["fan_target_temperature"].ok is True
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature == 75


@pytest.mark.asyncio
async def test_a_second_reset_still_works_after_a_failed_one(
        service, session_factory, monkeypatch):
    """Befund 2: heute loescht der PUT desired VOR den Restores.

    Nach dem ersten -- auch gescheiterten -- Zuruecksetzen ist
    previous_desired ueberall None, und resolve_restores liefert {}. Ein
    zweiter Klick tut dann nachweislich nichts, und der Ausweg ist ueber die
    Oberflaeche nicht erkennbar.
    """
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))

    attempts = []
    outcome = {"ok": False}

    async def flaky(fan_ctrl, name, value, writer):
        attempts.append((name, value))
        return outcome["ok"]

    monkeypatch.setattr(fans_routes, "write_acoustic", flaky)

    first = await _put(service, GpuFanAcousticsValues())

    assert first.writes["fan_target_temperature"].ok is False
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature == 75, \
            "gescheitertes Zuruecksetzen hat desired trotzdem geleert"

    outcome["ok"] = True
    second = await _put(service, GpuFanAcousticsValues())

    assert attempts == [("fan_target_temperature", 95),
                        ("fan_target_temperature", 95)], \
        "der zweite Reset hat die Karte nicht mehr angefasst"
    assert second.writes["fan_target_temperature"].ok is True
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature is None


@pytest.mark.asyncio
async def test_an_unreadable_config_aborts_the_put(service, session_factory):
    """Befund 3: der PUT baute auf einem fehlgeschlagenen Load auf.

    load lieferte leere Vorgaben, der PUT schrieb das GANZE Objekt zurueck --
    und damit baseline={} ueber die echte Zeile. Danach hat 'Zuruecksetzen'
    nichts mehr, worauf es zuruecksetzen koennte.
    """
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()

    with pytest.raises(ServiceUnavailableError):
        await _put(service, GpuFanAcousticsValues(fan_target_temperature=75))

    with session_factory() as db:
        row = db.execute(select(GpuFanAcousticsConfigDb)).scalar_one()
    assert row.config_json == "{kaputt", \
        "die unlesbare Zeile wurde ueberschrieben"


# --- Die Dienstschicht ---------------------------------------------------


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


@pytest.mark.asyncio
async def test_apply_acoustics_returns_its_results(session_factory, monkeypatch):
    """Befund 1: der Rueckgabewert von write_acoustic wurde an beiden
    Aufrufstellen weggeworfen -- auch das Ergebnis der Ruecklese-Kontrolle,
    die eigens gebaut wurde, weil ein angenommener Write auf dieser Karte
    nichts beweist (#480)."""
    monkeypatch.setattr(fan_control_module, "find_fan_ctrl_dir",
                        lambda hwmon: Path("/fake/fan_ctrl"))
    monkeypatch.setattr(fan_control_module, "read_acoustics", AsyncMock(
        return_value={
            "fan_target_temperature": ParsedNode(value=95, minimum=25, maximum=105),
            "fan_minimum_pwm": ParsedNode(value=23, minimum=23, maximum=100),
        }))

    async def write(fan_ctrl, name, value, writer):
        return name == "fan_minimum_pwm"

    monkeypatch.setattr(fan_control_module, "write_acoustic", write)
    service = _service(session_factory, monkeypatch)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75,
                                          fan_minimum_pwm=40)))

    results = await service.apply_acoustics()

    assert results == {"fan_target_temperature": False, "fan_minimum_pwm": True}


@pytest.mark.asyncio
async def test_a_stale_snapshot_must_not_record_baluhosts_own_write(
        session_factory, monkeypatch):
    """Befund 4: vier Uvicorn-Worker, getrennte Sessions, kein Lock.

    Worker B laedt die Konfiguration (Baseline noch leer), Worker A erfasst
    zwischenzeitlich baseline=95 und schreibt 75 auf die Karte. B liest die
    Hardware, sieht 75, prueft seinen VERALTETEN Snapshot, findet None -- und
    traegt BaluHosts eigenen Eingriff als 'wie es vorher war' ein.
    """
    hardware = {"fan_target_temperature": 95}

    async def read(fan_ctrl):
        return {name: ParsedNode(value=value, minimum=25, maximum=105)
                for name, value in hardware.items()}

    async def write(fan_ctrl, name, value, writer):
        hardware[name] = value
        return True

    monkeypatch.setattr(fan_control_module, "find_fan_ctrl_dir",
                        lambda hwmon: Path("/fake/fan_ctrl"))
    monkeypatch.setattr(fan_control_module, "write_acoustic", write)

    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    worker_a = _service(session_factory, monkeypatch)
    worker_b = _service(session_factory, monkeypatch)

    interleaved = {"done": False}

    async def read_with_worker_a_in_between(fan_ctrl):
        # Genau hier, zwischen B's Load und B's Baseline-Entscheidung, laeuft
        # Worker A vollstaendig durch.
        if not interleaved["done"]:
            interleaved["done"] = True
            monkeypatch.setattr(fan_control_module, "read_acoustics", read)
            await worker_a.apply_acoustics()
            monkeypatch.setattr(fan_control_module, "read_acoustics",
                                read_with_worker_a_in_between)
        return await read(fan_ctrl)

    monkeypatch.setattr(fan_control_module, "read_acoustics",
                        read_with_worker_a_in_between)

    await worker_b.apply_acoustics()

    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.baseline.fan_target_temperature == 95, (
        "Baseline mit BaluHosts eigenem Eingriff kontaminiert: "
        f"{config.baseline.fan_target_temperature}"
    )
    assert config.desired.fan_target_temperature == 75, "desired verloren"
