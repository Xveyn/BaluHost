"""Beobachtung -> Persistenz -> Rueckgabe -> erneuter Scan (#534).

Der Test bildet zwei Startzyklen auf demselben sysfs-Baum ab und belegt, dass
der zurueckgegebene Wert beim naechsten Start wieder als Beobachtung ankommt --
ohne dass sich etwas verschiebt.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from app.core.config import get_settings
from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService


def _tree(tmp_path: Path, enable_value: str) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text(enable_value + "\n")
    (hwmon / "fan1_input").write_text("900\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_observation_survives_a_full_cycle(tmp_path, monkeypatch):
    klass = _tree(tmp_path, "5")   # Kaltstart: BIOS hat Smart Fan IV gesetzt
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, factory)
    service._use_linux_backend = True

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()
    service._backend = backend
    fan_id = next(iter(backend._fan_cache))

    with factory() as db:
        db.add(FanConfig(fan_id=fan_id, name="nct6798 PWM1", mode="auto",
                         is_active=True))
        db.commit()

    # Erster Zyklus: Beobachtung persistieren
    service._persist_restore_values({fan_id: 5})
    with factory() as db:
        assert db.execute(select(FanConfig)).scalar_one().pwm_enable_restore == 5

    # BaluHost regelt: pwm_enable steht auf 1
    backend._fan_cache[fan_id]["pwm_enable_path"].write_text("1\n")

    # Beenden: Rueckgabe
    await service._release_all_to_board()
    assert backend._fan_cache[fan_id]["pwm_enable_path"].read_text().strip() == "5"

    # Zweiter Zyklus: neuer Scan liest den zurueckgegebenen Wert
    backend2 = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend2, "_hwmon_base", klass)
    await backend2._scan_pwm_fans()
    assert backend2._fan_cache[fan_id]["pwm_enable_at_scan"] == 5

    # ... und die Persistenz aendert nichts mehr
    service._backend = backend2
    with factory() as db:
        before = db.execute(select(FanConfig)).scalar_one().updated_at
    service._persist_restore_values({fan_id: 5})
    with factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore == 5
    assert row.updated_at == before
