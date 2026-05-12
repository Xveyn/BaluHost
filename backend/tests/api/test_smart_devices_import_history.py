"""Integration tests for POST /api/smart-devices/{id}/import-history."""
from unittest.mock import patch

import pytest

from app.models.smart_device import SmartDevice


@pytest.fixture
def tapo_device(db_session):
    d = SmartDevice(
        name="Test Tapo",
        plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110",
        address="192.168.1.50",
        capabilities=["switch", "power_monitor"],
        is_active=True,
        is_online=True,
        created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_import_history_requires_admin(client, user_headers, tapo_device):
    """Non-admin users get 403."""
    resp = client.post(
        f"/api/smart-devices/{tapo_device.id}/import-history",
        json={
            "interval": "hourly",
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "conflict_strategy": "live_wins",
        },
        headers=user_headers,
    )
    assert resp.status_code == 403


def test_import_history_404_for_unknown_device(client, admin_headers):
    resp = client.post(
        "/api/smart-devices/99999/import-history",
        json={
            "interval": "hourly",
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "conflict_strategy": "live_wins",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_import_history_validation_error(client, admin_headers, tapo_device):
    """Daily interval with non-quarter start should be rejected by schema."""
    resp = client.post(
        f"/api/smart-devices/{tapo_device.id}/import-history",
        json={
            "interval": "daily",
            "start_date": "2026-04-15",  # not a quarter start
            "end_date": "2026-06-30",
            "conflict_strategy": "live_wins",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_import_history_success(client, admin_headers, tapo_device, db_session):
    """End-to-end import via API (uses dev mock fetcher because _is_dev_mode is patched True)."""
    from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
    from app.plugins.smart_device.manager import get_smart_device_manager

    # Register the plugin so the route can look it up via manager._plugins
    plugin_instance = TapoSmartPlugPlugin()
    manager = get_smart_device_manager()
    manager.register_plugin(plugin_instance)

    _fake_info = type("Info", (), {"ip": "192.168.1.50", "email": "x@x.com", "password": "secret"})()

    with patch.object(
        plugin_instance,
        "_ensure_device_info",
        return_value=_fake_info,
    ), patch.object(
        plugin_instance,
        "_is_dev_mode",
        return_value=True,
    ):
        resp = client.post(
            f"/api/smart-devices/{tapo_device.id}/import-history",
            json={
                "interval": "hourly",
                "start_date": "2026-04-01",
                "end_date": "2026-04-01",
                "conflict_strategy": "live_wins",
            },
            headers=admin_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["device_id"] == tapo_device.id
    assert body["interval"] == "hourly"
    assert body["buckets_fetched"] == 24  # mock generates 24 hourly buckets
    assert body["samples_inserted"] == 24
