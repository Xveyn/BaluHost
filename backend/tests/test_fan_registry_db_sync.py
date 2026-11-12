"""Composite-Sensoren und Labels erreichen jeden Worker, nicht nur den bedienenden (#708).

Produktion laeuft mit vier Uvicorn-Workern, jeder mit einer eigenen
`TempSourceRegistry`. Die Composite- und Label-Routen aktualisierten nur die
Registry des Workers, der die Anfrage bediente. Der Primary -- der einzige, der
regelt -- lernte einen frisch angelegten `mix:`-Sensor erst nach einem Neustart
kennen: `get_temp()` lieferte None, kein Zielwert, und nach der Frist aus #534
gab BaluHost den Kanal still an die Board-Automatik ab.

Die Tests bauen deshalb zwei (oder drei) echte Service-Instanzen auf DERSELBEN
Datenbank: "Worker A" bedient die Schreib-Route, "Worker B" ist der Primary
bzw. ein anderer Follower. Die Routen laufen ueber `__wrapped__`, also ohne den
slowapi-Dekorator -- geprueft wird die Verdrahtung, nicht das Rate-Limit.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import fans as fans_routes
from app.models.base import Base
from app.models.fans import FanConfig
from app.schemas.fans import (
    CompositeSensorCreate,
    CompositeSensorUpdate,
    FanMode,
    PwmControl,
    TempSensorLabelUpdate,
)
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData
from app.services.power.fan_sources import (
    DiskTempSource,
    GpuTempSource,
    HwmonTempSource,
    MixTempSource,
)

FAN_ID = "nct6798:pwm1"
HWMON_ID = "hwmon:hwmon0_temp1"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _reset_singleton():
    FanControlService._instance = None
    yield
    FanControlService._instance = None


def _fan(pwm: int = 40) -> FanData:
    return FanData(
        fan_id=FAN_ID, name=FAN_ID, rpm=800, pwm_percent=pwm,
        temperature_celsius=30.0, mode=FanMode.AUTO,
        min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
        temp_sensor_id=None, curve_points=[], is_active=True,
        pwm_control=PwmControl.SUPPORTED,
    )


def _worker(session_factory) -> FanControlService:
    """Eine Service-Instanz, wie sie ein Worker nach dem Start haette.

    hwmon/gpu/disk sind von Hand registriert -- in Produktion kommen sie aus
    dem Scan bzw. dem SHM und haben mit der Datenbank nichts zu tun.
    """
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    config.fan_sample_interval_seconds = 5
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True

    backend = MagicMock()
    backend.get_fans = AsyncMock(return_value=[_fan()])
    backend.set_pwm = AsyncMock(return_value=True)
    backend.release_to_board = AsyncMock(return_value=True)
    backend.write_failure_state = MagicMock(return_value=(0, False))
    backend.clear_write_failures = MagicMock()
    backend.recheck_write_permission = AsyncMock()
    service._backend = backend
    service._restore_values = {FAN_ID: 5}

    service._registry.register(HwmonTempSource(
        sensor_id="hwmon0_temp1", device_name="k10temp", backend_label="Tctl",
        is_cpu_sensor=True, read_fn=AsyncMock(return_value=45.0),
    ))
    service._registry.register(GpuTempSource(
        channel="edge", read_fn=AsyncMock(return_value=60.0),
    ))
    service._registry.register(DiskTempSource(
        device="sda", read_fn=AsyncMock(return_value=35.0),
    ))
    FanControlService._instance = None
    return service


def _primary(session_factory, monkeypatch) -> FanControlService:
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)
    return _worker(session_factory)


def _ids(service: FanControlService) -> set:
    return {s.id for s in service._registry.all_sources()}


def _route_kwargs(service: FanControlService) -> dict:
    return dict(request=SimpleNamespace(), response=SimpleNamespace(),
                current_user=MagicMock(), service=service)


async def _create(service, *, name="max(CPU, GPU edge)", function="max",
                  sources=(HWMON_ID, "gpu:edge")) -> str:
    handler = fans_routes.create_composite_sensor.__wrapped__
    info = await handler(
        body=CompositeSensorCreate(name=name, function=function,
                                   source_ids=list(sources)),
        **_route_kwargs(service),
    )
    return info.id


async def _update(service, composite_id: str, **fields):
    handler = fans_routes.update_composite_sensor.__wrapped__
    return await handler(composite_id=composite_id,
                         body=CompositeSensorUpdate(**fields),
                         **_route_kwargs(service))


async def _delete(service, composite_id: str):
    handler = fans_routes.delete_composite_sensor.__wrapped__
    return await handler(composite_id=composite_id, **_route_kwargs(service))


async def _set_label(service, sensor_id: str, label: str):
    handler = fans_routes.set_sensor_label.__wrapped__
    return await handler(sensor_id=sensor_id, body=TempSensorLabelUpdate(label=label),
                         **_route_kwargs(service))


async def _clear_label(service, sensor_id: str):
    handler = fans_routes.clear_sensor_label.__wrapped__
    return await handler(sensor_id=sensor_id, **_route_kwargs(service))


def _point_fan_at(session_factory, sensor_id: str) -> None:
    with session_factory() as db:
        db.add(FanConfig(
            fan_id=FAN_ID, name=FAN_ID, mode=FanMode.AUTO.value, is_active=True,
            min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
            temp_sensor_id=sensor_id, curve_type="graph",
            curve_json='[{"temp": 30, "pwm": 30}, {"temp": 70, "pwm": 90}]',
        ))
        db.commit()


# --- Der Kern: der Primary regelt nach einem Composite eines Followers -----


@pytest.mark.asyncio
async def test_primary_regelt_nach_composite_der_auf_einem_follower_entstand(
        session_factory, monkeypatch):
    follower = _worker(session_factory)
    primary = _primary(session_factory, monkeypatch)

    mix_id = await _create(follower)
    _point_fan_at(session_factory, mix_id)

    await primary._monitor_and_control_fans()

    # Ohne Abgleich: get_temp() -> None, die Zielwert-Uhr laeuft los.
    assert FAN_ID not in primary._kein_zielwert_seit
    assert await primary._registry.get_temp(mix_id) == 60.0
    # Und es wurde tatsaechlich nach der Kurve geregelt, nicht der PWM gehalten.
    primary._backend.set_pwm.assert_awaited()
    assert primary._backend.set_pwm.await_args.args[1] != 40


@pytest.mark.asyncio
async def test_der_bedienende_worker_sieht_den_composite_sofort(session_factory):
    worker = _worker(session_factory)

    mix_id = await _create(worker)

    assert await worker._registry.get_temp(mix_id) == 60.0


# --- Update und Delete kommen an --------------------------------------------


@pytest.mark.asyncio
async def test_update_kommt_beim_anderen_worker_an(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    mix_id = await _create(a)
    b.sync_registry_from_db()
    assert await b._registry.get_temp(mix_id) == 60.0

    await _update(a, mix_id, function="min",
                  source_ids=[HWMON_ID, "disk:sda"], name="kuehlster")
    b.sync_registry_from_db()

    src = b._registry._sources[mix_id]
    assert isinstance(src, MixTempSource)
    assert src.function == "min"
    assert src.source_ids == [HWMON_ID, "disk:sda"]
    assert src.name == "kuehlster"
    assert await b._registry.get_temp(mix_id) == 35.0


@pytest.mark.asyncio
async def test_delete_kommt_beim_anderen_worker_an(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    mix_id = await _create(a)
    b.sync_registry_from_db()
    assert mix_id in _ids(b)

    await _delete(a, mix_id)
    b.sync_registry_from_db()

    assert mix_id not in _ids(b)
    assert await b._registry.get_temp(mix_id) is None


# --- Labels -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_labels_kommen_an_und_verschwinden_wieder(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)

    # Legacy-Form ohne Namespace: der Schluessel muss trotzdem passen.
    await _set_label(a, "hwmon0_temp1", "CPU")
    await _set_label(a, "gpu:edge", "Grafik")
    b.sync_registry_from_db()
    assert b._registry.display_label(HWMON_ID) == "CPU"
    assert b._registry.display_label("gpu:edge") == "Grafik"

    await _clear_label(a, "gpu:edge")
    b.sync_registry_from_db()
    assert b._registry.display_label(HWMON_ID) == "CPU"
    assert "gpu:edge" not in b._registry._labels
    assert b._registry.display_label("gpu:edge") == "edge"


@pytest.mark.asyncio
async def test_label_route_wirkt_im_bedienenden_worker_sofort(session_factory):
    worker = _worker(session_factory)

    await _set_label(worker, HWMON_ID, "CPU")
    assert worker._registry.display_label(HWMON_ID) == "CPU"

    await _clear_label(worker, HWMON_ID)
    assert worker._registry.display_label(HWMON_ID) == "Tctl"


# --- Die Signatur -----------------------------------------------------------


@pytest.mark.asyncio
async def test_unveraenderte_db_registriert_nichts_erneut(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    await _create(a)
    await _set_label(a, HWMON_ID, "CPU")

    assert b.sync_registry_from_db() is True

    b._registry.register = MagicMock(wraps=b._registry.register)
    b._registry.unregister = MagicMock(wraps=b._registry.unregister)
    b._registry.set_label = MagicMock(wraps=b._registry.set_label)

    assert b.sync_registry_from_db() is False
    assert b.sync_registry_from_db() is False

    b._registry.register.assert_not_called()
    b._registry.unregister.assert_not_called()
    b._registry.set_label.assert_not_called()


@pytest.mark.asyncio
async def test_inhaltliche_aenderung_wird_erkannt(session_factory):
    """Die Signatur haengt am Inhalt, nicht an count/max(updated_at).

    Ein Update, das nur die Funktion tauscht, aendert weder die Anzahl noch
    zwingend den Zeitstempel (SQLite: Sekundenaufloesung von func.now()).
    """
    a = _worker(session_factory)
    b = _worker(session_factory)
    mix_id = await _create(a)
    b.sync_registry_from_db()

    await _update(a, mix_id, function="avg")

    assert b.sync_registry_from_db() is True
    assert await b._registry.get_temp(mix_id) == pytest.approx(52.5)


# --- Fehler im Abgleich -----------------------------------------------------


@pytest.mark.asyncio
async def test_db_fehler_laesst_registry_stehen_und_regelzyklus_laeuft(
        session_factory, monkeypatch):
    follower = _worker(session_factory)
    primary = _primary(session_factory, monkeypatch)
    mix_id = await _create(follower)
    _point_fan_at(session_factory, mix_id)
    primary.sync_registry_from_db()
    vorher = dict(primary._registry._sources)

    def kaputt(db):
        raise RuntimeError("DB weg")

    monkeypatch.setattr(primary, "_load_db_backed_rows", kaputt)

    assert primary.sync_registry_from_db() is False
    assert primary._registry._sources == vorher

    # Der Regelzyklus laeuft durch und regelt weiter auf dem Composite.
    await primary._monitor_and_control_fans()
    assert FAN_ID not in primary._kein_zielwert_seit
    primary._backend.set_pwm.assert_awaited()

    # Ein Fehlschlag vergiftet die Signatur nicht: ist die DB zurueck, kommt
    # die zwischenzeitliche Aenderung an.
    monkeypatch.undo()
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)
    await _delete(follower, mix_id)
    assert primary.sync_registry_from_db() is True
    assert mix_id not in _ids(primary)


# --- Nicht-DB-Quellen bleiben unangetastet ---------------------------------


@pytest.mark.asyncio
async def test_hwmon_gpu_disk_ueberleben_den_abgleich(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    vorher = {s.id: s for s in b._registry.all_sources()}

    mix_id = await _create(a)
    b.sync_registry_from_db()
    await _delete(a, mix_id)
    b.sync_registry_from_db()

    nachher = {s.id: s for s in b._registry.all_sources()}
    assert nachher.keys() == vorher.keys()
    for sid, src in vorher.items():
        assert nachher[sid] is src


# --- Zusammenspiel mit _rebuild_registry ----------------------------------


@pytest.mark.asyncio
async def test_rebuild_und_abgleich_passen_zusammen(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    b._backend.get_available_temp_sensors = AsyncMock(return_value=[])
    mix_id = await _create(a)
    await _set_label(a, HWMON_ID, "CPU")

    b.sync_registry_from_db()
    await b._rebuild_registry()

    # Nach dem Rebuild ist der Composite genau einmal da ...
    assert [s.id for s in b._registry.all_sources()].count(mix_id) == 1
    assert b._registry._labels == {HWMON_ID: "CPU"}
    # ... und der Abgleich danach erkennt den Stand als aktuell.
    assert b.sync_registry_from_db() is False


# --- Routen auf einem anderen Worker --------------------------------------


@pytest.mark.asyncio
async def test_composite_liste_eines_anderen_workers_liefert_temperatur(session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    mix_id = await _create(a)

    handler = fans_routes.list_composite_sensors.__wrapped__
    antwort = await handler(**_route_kwargs(b))

    eintrag = next(c for c in antwort.composites if c.id == mix_id)
    assert eintrag.current_temp == 60.0


@pytest.mark.asyncio
async def test_sensorliste_eines_anderen_workers_zeigt_composite_und_label(
        session_factory):
    a = _worker(session_factory)
    b = _worker(session_factory)
    b._refresh_disk_sources = AsyncMock()
    mix_id = await _create(a)
    await _set_label(a, HWMON_ID, "CPU")

    handler = fans_routes.list_temp_sensors.__wrapped__
    antwort = await handler(**_route_kwargs(b))

    by_id = {s.sensor_id: s for s in antwort.sensors}
    assert mix_id in by_id
    assert by_id[mix_id].current_temp == 60.0
    assert by_id[HWMON_ID].custom_label == "CPU"


@pytest.mark.asyncio
async def test_status_eines_anderen_workers_zeigt_composite_temperatur(
        session_factory, monkeypatch):
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        False, raising=False)
    a = _worker(session_factory)
    b = _worker(session_factory)
    mix_id = await _create(a)
    _point_fan_at(session_factory, mix_id)

    status = await b.get_status()

    eintrag = next(f for f in status["fans"] if f["fan_id"] == FAN_ID)
    # Ohne Abgleich fiele die Anzeige auf die Scan-Temperatur (30) zurueck.
    assert eintrag["temperature_celsius"] == 60.0


# --- Platten-Quellen: dieselbe Luecke, andere Herkunft ----------------------


@pytest.mark.asyncio
async def test_primary_lernt_eine_platte_die_nach_seinem_start_auftaucht(
        session_factory, monkeypatch):
    """`disk:*` kommt aus dem SMART-Summary im SHM, nicht aus der DB. Beim
    Start des Backends kann die Datei noch fehlen (der Monitoring-Worker
    schreibt sie erst nach seinem ersten SMART-Lauf), und nachgetragen hat sie
    bisher nur die Sensorlisten-Route -- in dem Worker, der sie bedient."""
    primary = _primary(session_factory, monkeypatch)
    primary._registry.unregister("disk:sda")
    monkeypatch.setattr(primary, "_read_smart_summary", lambda: {"sdb": 41.0})
    _point_fan_at(session_factory, "disk:sdb")

    await primary._monitor_and_control_fans()

    assert "disk:sdb" in _ids(primary)
    assert FAN_ID not in primary._kein_zielwert_seit
    primary._backend.set_pwm.assert_awaited()
