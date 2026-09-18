"""#606: ein GPU-Luefter bekommt bei der Erstanlage eine GPU-Temperaturquelle.

Vorher war der Default unbedingt der CPU-Sensor -- die Luefterkarte einer
Grafikkarte zeigte die CPU- (oder, nach dem Abgleich aus #532, sogar eine
Mainboard-)Temperatur, und die Temperaturwarnungen des Kanals schauten auf den
falschen Chip.

Drei Ebenen:
- die reine Auswahlregel ``default_temp_sensor_id``,
- die Anlage-Schleife in ``_load_fan_configs`` (Regressionstest aus dem Issue),
- die einmalige Datenmigration fuer Bestandszeilen.
"""
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from app.core import lifespan
from app.models.fans import FanConfig
from app.schemas.fans import FanCurvePoint, FanMode
from app.services.power.fan_control import FanControlService, FanData, TempSensorData
from app.services.power.fan_sources import default_temp_sensor_id

CPU = "k10temp-pci-00c3:temp1"


# --- Auswahlregel -------------------------------------------------------------

def test_amd_gpu_fan_gets_edge_even_with_cpu_sensor():
    assert default_temp_sensor_id(
        is_gpu_fan=True, gpu_vendor="amd", cpu_sensor_id=CPU,
        scan_sensor_id=CPU,
    ) == "gpu:edge"


def test_amd_gpu_fan_gets_edge_without_any_sensor():
    assert default_temp_sensor_id(
        is_gpu_fan=True, gpu_vendor="amd", cpu_sensor_id=None,
        scan_sensor_id=None,
    ) == "gpu:edge"


def test_nvidia_gpu_fan_keeps_cpu_default():
    """nouveau: gpu:* stammt aus nvidia-smi, das neben nouveau nicht laeuft --
    eine gpu:-Quelle waere praktisch immer tot. Bisheriges Verhalten bleibt."""
    assert default_temp_sensor_id(
        is_gpu_fan=True, gpu_vendor="nvidia", cpu_sensor_id=CPU,
        scan_sensor_id=CPU,
    ) == f"hwmon:{CPU}"


def test_board_fan_gets_normalized_cpu_sensor():
    assert default_temp_sensor_id(
        is_gpu_fan=False, gpu_vendor=None, cpu_sensor_id=CPU,
        scan_sensor_id="nct6798-isa-0290:temp1",
    ) == f"hwmon:{CPU}"


def test_board_fan_without_cpu_sensor_falls_back_to_scan_sensor():
    assert default_temp_sensor_id(
        is_gpu_fan=False, gpu_vendor=None, cpu_sensor_id=None,
        scan_sensor_id="nct6798-isa-0290:temp1",
    ) == "hwmon:nct6798-isa-0290:temp1"


def test_no_sensor_at_all_gives_none():
    assert default_temp_sensor_id(
        is_gpu_fan=False, gpu_vendor=None, cpu_sensor_id=None,
        scan_sensor_id=None,
    ) is None


# --- Anlage-Schleife ----------------------------------------------------------

class _Settings:
    is_dev_mode = True
    fan_control_enabled = True
    fan_min_pwm_percent = 30
    fan_emergency_temp_celsius = 90.0
    fan_force_dev_backend = True


def _fan(fan_id: str, name: str, *, is_gpu_fan=False, gpu_vendor=None) -> FanData:
    return FanData(
        fan_id=fan_id, name=name, rpm=900, pwm_percent=40,
        temperature_celsius=None, mode=FanMode.AUTO,
        min_pwm_percent=0, max_pwm_percent=100, emergency_temp_celsius=85.0,
        # So liefert es der Linux-Scan heute: der CPU-Sensor ueberschreibt den
        # lokalen Sensor fuer JEDEN Kanal, auch fuer amdgpu.
        temp_sensor_id=CPU,
        curve_points=[FanCurvePoint(temp=35, pwm=30), FanCurvePoint(temp=70, pwm=80)],
        is_active=True, is_gpu_fan=is_gpu_fan, gpu_vendor=gpu_vendor,
    )


@pytest.mark.asyncio
async def test_scanned_amdgpu_fan_gets_gpu_source_on_creation(monkeypatch):
    """Regressionstest aus #606: ein gescannter amdgpu-Kanal erhaelt bei der
    Erstanlage eine gpu:*-Quelle, obwohl ein CPU-Sensor vorhanden ist. Ein
    Mainboard-Luefter im selben Lauf behaelt den CPU-Default."""
    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True, raising=False)

    backend = AsyncMock()
    backend.get_fans.return_value = [
        _fan("amdgpu-pci-0300:pwm1", "amdgpu PWM1", is_gpu_fan=True, gpu_vendor="amd"),
        _fan("nct6798-isa-0290:pwm1", "nct6798 PWM1"),
    ]
    backend.get_available_temp_sensors.return_value = [
        TempSensorData(sensor_id="nct6798-isa-0290:temp1", device_name="nct6798",
                       label="SYSTIN", is_cpu_sensor=False, current_temp=37.0),
        TempSensorData(sensor_id=CPU, device_name="k10temp",
                       label="Tctl", is_cpu_sensor=True, current_temp=45.0),
    ]

    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # keine Bestandszeile
    db = MagicMock()
    db.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=db)
    factory.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(FanControlService, "_instance", None):
        service = FanControlService.__new__(FanControlService)
        service.config = _Settings()
        service.db_session_factory = factory
        service._backend = backend
        service._use_linux_backend = False
        await service._load_fan_configs()

    created = {
        call.args[0].fan_id: call.args[0].temp_sensor_id
        for call in db.add.call_args_list
        if isinstance(call.args[0], FanConfig)
    }
    assert created == {
        "amdgpu-pci-0300:pwm1": "gpu:edge",
        "nct6798-isa-0290:pwm1": f"hwmon:{CPU}",
    }


# --- Datenmigration -----------------------------------------------------------

def _load_migration():
    path = next(
        (Path(__file__).resolve().parents[1] / "alembic" / "versions")
        .glob("*_gpu_fan_default_temp_source.py")
    )
    spec = importlib.util.spec_from_file_location("gpu_fan_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(rows):
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    table = sa.Table(
        "fan_configs", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fan_id", sa.String(100)),
        sa.Column("name", sa.String(100)),
        sa.Column("temp_sensor_id", sa.String(100), nullable=True),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(table.insert(), rows)
        _load_migration().retarget_gpu_fans(conn)
    with engine.connect() as conn:
        return {
            r.fan_id: r.temp_sensor_id
            for r in conn.execute(sa.select(table.c.fan_id, table.c.temp_sensor_id))
        }


def test_migration_retargets_only_defaulted_amdgpu_rows():
    result = _run_migration([
        # prod-Fall: Board-Sensor aus dem Abgleich (#658)
        {"fan_id": "amdgpu-pci-0300:pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": "hwmon:nct6798-isa-0290:temp1"},
        # Altzeile mit hwmon-Index-ID, erkannt am Namen; nackte Alt-Sensor-ID
        {"fan_id": "hwmon1_pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": "hwmon3_temp1"},
        # kein Sensor gesetzt
        {"fan_id": "amdgpu-pci-0400:pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": None},
        # bewusste Wahl -- nie ein Default gewesen, bleibt
        {"fan_id": "amdgpu-pci-0500:pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": "gpu:mem"},
        {"fan_id": "amdgpu-pci-0600:pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": "mix:gpu-und-cpu"},
        {"fan_id": "amdgpu-pci-0700:pwm1", "name": "amdgpu PWM1",
         "temp_sensor_id": "disk:nvme0n1"},
        # kein GPU-Luefter -- bleibt
        {"fan_id": "nct6798-isa-0290:pwm1", "name": "nct6798 PWM1",
         "temp_sensor_id": "hwmon:nct6798-isa-0290:temp1"},
        # nouveau bekommt keinen gpu:-Default (siehe Auswahlregel) -- bleibt
        {"fan_id": "nouveau-pci-0100:pwm1", "name": "nouveau PWM1",
         "temp_sensor_id": f"hwmon:{CPU}"},
    ])

    assert result == {
        "amdgpu-pci-0300:pwm1": "gpu:edge",
        "hwmon1_pwm1": "gpu:edge",
        "amdgpu-pci-0400:pwm1": "gpu:edge",
        "amdgpu-pci-0500:pwm1": "gpu:mem",
        "amdgpu-pci-0600:pwm1": "mix:gpu-und-cpu",
        "amdgpu-pci-0700:pwm1": "disk:nvme0n1",
        "nct6798-isa-0290:pwm1": "hwmon:nct6798-isa-0290:temp1",
        "nouveau-pci-0100:pwm1": f"hwmon:{CPU}",
    }
