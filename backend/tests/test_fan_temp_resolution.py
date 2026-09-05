"""get_temperature loest stabile, praefixierte und Alt-IDs auf (#532)."""
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.fixture
def backend(tmp_path):
    hwmon = tmp_path / "hwmon3"
    hwmon.mkdir()
    (hwmon / "temp1_input").write_text("42000\n")
    be = LinuxFanControlBackend(get_settings())
    be._hwmon_base = tmp_path
    be._temp_paths = {"nct6798-isa-0290:temp1": hwmon / "temp1_input"}
    return be


@pytest.mark.asyncio
async def test_resolves_stable_id(backend):
    assert await backend.get_temperature("nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_strips_hwmon_namespace_prefix(backend):
    assert await backend.get_temperature("hwmon:nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_still_resolves_legacy_id(backend):
    # Waehrend der Umstellung stehen Alt-IDs noch in der Datenbank.
    assert await backend.get_temperature("hwmon3_temp1") == 42.0


@pytest.mark.asyncio
async def test_unknown_id_is_none(backend):
    assert await backend.get_temperature("nope-isa-0000:temp9") is None


def _k10temp_tree(tmp_path: Path) -> Path:
    """k10temp an platform/k10temp-sim.1 mit echtem device/subsystem-Symlink.

    Doppelpunktfreier Geraetename (kein "0000:00:18.3"), damit der Baum auch
    unter Windows/NTFS anlegbar ist. k10temp steht in _CPU_SENSOR_DRIVERS
    und ist der CPU-Sensor der Zielmaschine -- damit durchlaeuft dieser
    Baum, anders als die Treiber-losen Faelle in test_fan_scan_stable_ids.py
    (nct6798) und die device-losen Faelle in test_fan_control.py, tatsaechlich
    den stabilen derive_all()+build_sensor_id()-Pfad in
    _find_cpu_temp_sensor().
    """
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "k10temp-sim.1"
    hwmon = device / "hwmon" / "hwmon1"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("k10temp\n")
    (hwmon / "temp1_input").write_text("55000\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    if not (device / "subsystem").exists():
        os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon1", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_cpu_sensor_id_agrees_between_lookup_and_scan(tmp_path):
    """Kern von #532: _find_cpu_temp_sensor() und die Rueckabbildung aus
    _scan_pwm_fans() duerfen fuer denselben physischen Sensor NIE
    auseinanderlaufen -- sonst findet get_temperature() die Quelle des per
    _find_cpu_temp_sensor() gewaehlten Default-Sensors nicht mehr, und die
    Kurve regelt lautlos nicht (das Symptom von #517).
    """
    klass = _k10temp_tree(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    backend._hwmon_base = klass

    found = backend._find_cpu_temp_sensor()
    assert found is not None
    sensor_id, temp_path = found

    # Stabile Form, nicht die Altform "hwmon1_temp1".
    assert sensor_id == "k10temp-isa-0001:temp1"
    assert temp_path.name == "temp1_input"

    await backend._scan_pwm_fans()

    # Kern der Garantie: dieselbe ID zeigt in beiden Wegen auf dieselbe Datei.
    assert backend._temp_paths.get(sensor_id) == temp_path

    assert await backend.get_temperature(sensor_id) == 55.0


@pytest.mark.asyncio
async def test_sensor_discovered_after_scan_is_still_resolvable(tmp_path):
    """I-3: ein hwmon-Chip, der erst NACH dem Startscan erscheint (Treiber
    nachgeladen), muss trotzdem lesbar bleiben. _temp_paths wurde bisher
    ausschliesslich in _scan_pwm_fans() gefuellt -- get_available_temp_sensors()
    und _find_cpu_temp_sensor() bildeten zwar eine stabile ID, trugen sie
    aber nie ein. Ohne Unterstrich in der Kennung greift auch der
    Alt-Format-Rueckfall (_legacy_temp_path) nicht -- get_temperature()
    lieferte fuer einen solchen Sensor dauerhaft None."""
    klass = tmp_path / "sys" / "class" / "hwmon"
    klass.mkdir(parents=True)
    backend = LinuxFanControlBackend(get_settings())
    backend._hwmon_base = klass

    await backend._scan_pwm_fans()   # Startscan: der Chip existiert noch nicht

    _k10temp_tree(tmp_path)          # Chip erscheint erst jetzt (Treiber nachgeladen)

    sensors = await backend.get_available_temp_sensors()
    assert any(s.sensor_id == "k10temp-isa-0001:temp1" for s in sensors)

    assert await backend.get_temperature("k10temp-isa-0001:temp1") == 55.0
