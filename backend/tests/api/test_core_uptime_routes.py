"""Tests for /api/system/sleep/core-uptime/* endpoints."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings
from app.schemas.sleep import SleepConfigResponse, ScheduleMode


@pytest.fixture
def admin_headers(client: TestClient, admin_user) -> dict[str, str]:
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


BASE = f"{settings.api_prefix}/system/sleep/core-uptime/windows"


def test_list_empty(client, admin_headers):
    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_window_happy_path(client, admin_headers):
    payload = {
        "label": "Werktage",
        "start_time": "08:00",
        "end_time": "22:00",
        "weekdays": [0, 1, 2, 3, 4],
    }
    r = client.post(BASE, headers=admin_headers, json=payload)
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["label"] == "Werktage"
    assert body["weekdays"] == [0, 1, 2, 3, 4]
    assert body["enabled"] is True
    assert "id" in body and body["id"] > 0


def test_create_rejects_empty_weekdays(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [],
    })
    assert r.status_code == 422


def test_create_rejects_equal_times(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "08:00", "weekdays": [0],
    })
    assert r.status_code == 422


def test_create_rejects_invalid_hhmm(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "25:00", "end_time": "22:00", "weekdays": [0],
    })
    assert r.status_code == 422


def test_create_forbidden_for_regular_user(client, user_headers):
    r = client.post(BASE, headers=user_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [0],
    })
    assert r.status_code == 403


def test_update_partial(client, admin_headers):
    created = client.post(BASE, headers=admin_headers, json={
        "label": "Werktage", "start_time": "08:00", "end_time": "22:00", "weekdays": [0, 1, 2, 3, 4],
    }).json()
    wid = created["id"]
    r = client.put(f"{BASE}/{wid}", headers=admin_headers, json={"label": "Office", "enabled": False})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Office"
    assert body["enabled"] is False
    assert body["weekdays"] == [0, 1, 2, 3, 4]  # unchanged


def test_update_404(client, admin_headers):
    r = client.put(f"{BASE}/9999", headers=admin_headers, json={"label": "x"})
    assert r.status_code == 404


def test_delete_happy(client, admin_headers):
    created = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [0],
    }).json()
    r = client.delete(f"{BASE}/{created['id']}", headers=admin_headers)
    assert r.status_code == 204
    listing = client.get(BASE, headers=admin_headers).json()
    assert listing == []


def test_delete_404(client, admin_headers):
    r = client.delete(f"{BASE}/9999", headers=admin_headers)
    assert r.status_code == 404


def test_master_toggle_via_config_endpoint(client, admin_headers, monkeypatch):
    """Verify core_uptime_enabled is accepted and returned by the config endpoint.

    The sleep manager is not started in the test environment (SKIP_APP_INIT=1).
    We mock get_sleep_manager() to return a manager that delegates update_config
    to the real SleepConfigUpdate schema, proving the field is wired through.
    """
    mock_manager = MagicMock()

    def fake_update_config(update):
        cfg = SleepConfigResponse(
            core_uptime_enabled=update.core_uptime_enabled
            if update.core_uptime_enabled is not None
            else False,
        )
        return cfg

    mock_manager.update_config.side_effect = fake_update_config

    import app.api.routes.sleep as sleep_routes
    monkeypatch.setattr(sleep_routes, "_get_manager", lambda: mock_manager)

    r = client.put(
        f"{settings.api_prefix}/system/sleep/config",
        headers=admin_headers,
        json={"core_uptime_enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["core_uptime_enabled"] is True
