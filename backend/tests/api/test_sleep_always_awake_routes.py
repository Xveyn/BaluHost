"""API tests for always-awake config field."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings
from app.schemas.sleep import (
    AlwaysAwakeStatus,
    SleepConfigResponse,
    SleepState,
    SleepStatusResponse,
)


@pytest.fixture
def admin_headers(client: TestClient, admin_user) -> dict[str, str]:
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


@pytest.fixture
def mock_sleep_manager(monkeypatch):
    """Patch _get_manager() so PUT /config and GET /status work without a running manager.

    The sleep manager is not started in the test environment (SKIP_APP_INIT=1).
    This fixture provides a stub that mirrors the relevant manager behaviour for
    always-awake fields: update_config validates via SleepConfigUpdate, persists
    the new always_awake_* values in module state, and get_status surfaces them.
    """
    state: dict = {
        "always_awake_enabled": False,
        "always_awake_until": None,
    }

    mock_manager = MagicMock()

    def fake_update_config(update):
        touched = update.model_dump(exclude_unset=True)
        if "always_awake_enabled" in touched:
            state["always_awake_enabled"] = bool(touched["always_awake_enabled"])
            # Disabling clears the until timestamp (Task 9 normalization).
            if not state["always_awake_enabled"]:
                state["always_awake_until"] = None
            elif "always_awake_until" in touched:
                state["always_awake_until"] = touched["always_awake_until"]
        elif "always_awake_until" in touched:
            state["always_awake_until"] = touched["always_awake_until"]
        return SleepConfigResponse(
            always_awake_enabled=state["always_awake_enabled"],
            always_awake_until=state["always_awake_until"],
        )

    def fake_get_status():
        return SleepStatusResponse(
            current_state=SleepState.AWAKE,
            always_awake=AlwaysAwakeStatus(
                enabled=state["always_awake_enabled"],
                until=state["always_awake_until"],
            ),
        )

    mock_manager.update_config.side_effect = fake_update_config
    mock_manager.get_status.side_effect = fake_get_status

    import app.api.routes.sleep as sleep_routes
    monkeypatch.setattr(sleep_routes, "_get_manager", lambda: mock_manager)
    return mock_manager


CONFIG_URL = f"{settings.api_prefix}/system/sleep/config"
STATUS_URL = f"{settings.api_prefix}/system/sleep/status"


def test_admin_can_enable_with_future_until(client, admin_headers, mock_sleep_manager):
    until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = client.put(CONFIG_URL, headers=admin_headers, json={
        "always_awake_enabled": True,
        "always_awake_until": until,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["always_awake_enabled"] is True
    assert body["always_awake_until"] is not None


def test_admin_can_enable_permanent(client, admin_headers, mock_sleep_manager):
    r = client.put(CONFIG_URL, headers=admin_headers, json={
        "always_awake_enabled": True,
        "always_awake_until": None,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["always_awake_enabled"] is True
    assert body["always_awake_until"] is None


def test_past_until_rejected(client, admin_headers, mock_sleep_manager):
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = client.put(CONFIG_URL, headers=admin_headers, json={
        "always_awake_enabled": True,
        "always_awake_until": past,
    })
    assert r.status_code == 422


def test_disabling_normalizes_until(client, admin_headers, mock_sleep_manager):
    until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    client.put(CONFIG_URL, headers=admin_headers, json={
        "always_awake_enabled": True,
        "always_awake_until": until,
    })
    r = client.put(CONFIG_URL, headers=admin_headers, json={"always_awake_enabled": False})
    assert r.status_code == 200
    assert r.json()["always_awake_enabled"] is False
    assert r.json()["always_awake_until"] is None


def test_regular_user_forbidden(client, user_headers):
    r = client.put(CONFIG_URL, headers=user_headers, json={"always_awake_enabled": True})
    assert r.status_code == 403


def test_status_surfaces_always_awake(client, admin_headers, mock_sleep_manager):
    client.put(CONFIG_URL, headers=admin_headers, json={
        "always_awake_enabled": True,
        "always_awake_until": None,
    })
    r = client.get(STATUS_URL, headers=admin_headers)
    assert r.status_code == 200
    aa = r.json()["always_awake"]
    assert aa["enabled"] is True
    assert aa["until"] is None
