"""Integration tests for /api/system/sleep/os-auto-suspend routes."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings
from app.schemas.sleep import OsAutoSuspendResponse, OsAutoSuspendAction

OS_AUTO_SUSPEND_URL = f"{settings.api_prefix}/system/sleep/os-auto-suspend"


@pytest.fixture
def admin_headers(client: TestClient, admin_user) -> dict[str, str]:
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


_UNSUPPORTED_RESPONSE = OsAutoSuspendResponse(
    supported=False,
    source="none",
    backend_label="",
    enabled=False,
    timeout_minutes=0,
    action=OsAutoSuspendAction.IGNORE,
)


class TestOsAutoSuspendGet:
    def test_requires_auth(self, client: TestClient):
        r = client.get(OS_AUTO_SUSPEND_URL)
        assert r.status_code in (401, 403)

    def test_requires_admin(self, client: TestClient, user_headers):
        r = client.get(OS_AUTO_SUSPEND_URL, headers=user_headers)
        assert r.status_code == 403

    def test_get_returns_supported_false_when_no_backend(self, client: TestClient, admin_headers):
        with patch(
            "app.api.routes.sleep.os_auto_suspend.get_os_auto_suspend",
            return_value=_UNSUPPORTED_RESPONSE,
        ):
            r = client.get(OS_AUTO_SUSPEND_URL, headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["supported"] is False
        assert body["source"] == "none"


class TestOsAutoSuspendPut:
    def test_requires_admin(self, client: TestClient, user_headers):
        r = client.put(
            OS_AUTO_SUSPEND_URL,
            headers=user_headers,
            json={"enabled": True, "timeout_minutes": 15, "action": "suspend"},
        )
        assert r.status_code == 403

    def test_validates_timeout_zero(self, client: TestClient, admin_headers):
        r = client.put(
            OS_AUTO_SUSPEND_URL,
            headers=admin_headers,
            json={"enabled": True, "timeout_minutes": 0, "action": "suspend"},
        )
        assert r.status_code == 422

    def test_validates_timeout_too_large(self, client: TestClient, admin_headers):
        r = client.put(
            OS_AUTO_SUSPEND_URL,
            headers=admin_headers,
            json={"enabled": True, "timeout_minutes": 2000, "action": "suspend"},
        )
        assert r.status_code == 422

    def test_happy_path_returns_readback(self, client: TestClient, admin_headers):
        def fake_set(update):
            return OsAutoSuspendResponse(
                supported=True,
                source="kde",
                backend_label="KDE PowerDevil",
                enabled=update.enabled,
                timeout_minutes=update.timeout_minutes,
                action=update.action,
            )

        with patch(
            "app.api.routes.sleep.os_auto_suspend.get_os_auto_suspend",
            return_value=_UNSUPPORTED_RESPONSE,
        ), patch(
            "app.api.routes.sleep.os_auto_suspend.set_os_auto_suspend",
            side_effect=fake_set,
        ):
            r = client.put(
                OS_AUTO_SUSPEND_URL,
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 20, "action": "suspend"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["timeout_minutes"] == 20
        assert body["source"] == "kde"

    def test_returns_503_when_no_backend(self, client: TestClient, admin_headers):
        def fake_get():
            return _UNSUPPORTED_RESPONSE

        def fake_set(update):
            raise RuntimeError("no active power manager detected")

        with patch(
            "app.api.routes.sleep.os_auto_suspend.get_os_auto_suspend",
            side_effect=fake_get,
        ), patch(
            "app.api.routes.sleep.os_auto_suspend.set_os_auto_suspend",
            side_effect=fake_set,
        ):
            r = client.put(
                OS_AUTO_SUSPEND_URL,
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 15, "action": "suspend"},
            )
        assert r.status_code == 503
