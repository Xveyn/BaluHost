"""Tests for GET /api/system/sleep/os-settings."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings
from app.services.power.os_sleep_inspector import OsSleepIssue, OsSleepReport


OS_SETTINGS_URL = f"{settings.api_prefix}/system/sleep/os-settings"


@pytest.fixture
def admin_headers(client: TestClient, admin_user) -> dict[str, str]:
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


@pytest.fixture
def stub_report():
    return OsSleepReport(
        platform_supported=True,
        logind={"IdleAction": "suspend"},
        sleep_conf={"AllowSuspend": "yes"},
        targets={"suspend.target": "enabled"},
        issues=[OsSleepIssue(
            severity="warning",
            key="logind.idle_action.suspend",
            message="logind suspends after idle",
            detail="30min",
        )],
        sources=["/etc/systemd/logind.conf"],
        collected_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    )


def test_requires_admin(client, user_headers):
    """Non-admin users get 403."""
    res = client.get(OS_SETTINGS_URL, headers=user_headers)
    assert res.status_code == 403


def test_returns_report_for_admin(client, admin_headers, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ):
        res = client.get(OS_SETTINGS_URL, headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["platform_supported"] is True
    assert body["logind"]["IdleAction"] == "suspend"
    assert body["issues"][0]["key"] == "logind.idle_action.suspend"


def test_force_param_bypasses_cache(client, admin_headers, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ) as inspect_mock:
        res = client.get(
            f"{OS_SETTINGS_URL}?force=true",
            headers=admin_headers,
        )
    assert res.status_code == 200
    inspect_mock.assert_called_once_with(force_refresh=True)


def test_default_does_not_force_refresh(client, admin_headers, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ) as inspect_mock:
        client.get(OS_SETTINGS_URL, headers=admin_headers)
    inspect_mock.assert_called_once_with(force_refresh=False)
