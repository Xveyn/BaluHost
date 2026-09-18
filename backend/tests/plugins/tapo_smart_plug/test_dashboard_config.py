"""Tapo dashboard panel honours panel_devices via get_config() (#522)."""
from unittest.mock import patch

import pytest

from app.models.smart_device import SmartDevice
from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
from app.services import plugin_service


def _device(db_session, name: str) -> SmartDevice:
    d = SmartDevice(
        name=name, plugin_name="tapo_smart_plug", device_type_id="tapo_p110",
        address="192.168.1.50", capabilities=["switch", "power_monitor"],
        is_active=True, is_online=True, created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _shm(*devices: SmartDevice) -> dict:
    return {"devices": {
        str(d.id): {"state": {"power_monitor": {"watts": 50.0, "energy_today_kwh": 1.0}}}
        for d in devices
    }}


@pytest.mark.asyncio
async def test_panel_devices_narrows_the_gauge(db_session):
    a, b = _device(db_session, "A"), _device(db_session, "B")
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"panel_devices": [a.id]}
    )

    with patch("app.plugins.installed.tapo_smart_plug.read_shm", return_value=_shm(a, b)):
        data = await TapoSmartPlugPlugin().get_dashboard_data(db_session)

    assert data["value"] == "50.0 W"


@pytest.mark.asyncio
async def test_invalid_config_counts_all_devices(db_session):
    a, b = _device(db_session, "A"), _device(db_session, "B")
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": -1}
    )

    with patch("app.plugins.installed.tapo_smart_plug.read_shm", return_value=_shm(a, b)):
        data = await TapoSmartPlugPlugin().get_dashboard_data(db_session)

    assert data["value"] == "100.0 W"
