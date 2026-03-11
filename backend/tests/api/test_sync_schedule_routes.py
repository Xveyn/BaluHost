"""
Tests for sync schedule API routes (sync_advanced.py).

Tests:
- POST /api/sync/schedule/create
- GET /api/sync/schedule/list
- POST /api/sync/schedule/{id}/disable
- POST /api/sync/schedule/{id}/enable
- PUT /api/sync/schedule/{id}
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.user import User


class TestCreateSchedule:
    """Tests for POST /api/sync/schedule/create."""

    def test_create_daily_schedule(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={
                "device_id": "test-device-001",
                "schedule_type": "daily",
                "time_of_day": "03:00",
            },
            headers=user_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schedule_id"] is not None
        assert data["device_id"] == "test-device-001"
        assert data["schedule_type"] == "daily"
        assert data["auto_vpn"] is False
        assert data["enabled"] is True

    def test_create_with_auto_vpn(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={
                "device_id": "test-device-001",
                "schedule_type": "daily",
                "time_of_day": "04:00",
                "auto_vpn": True,
            },
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["auto_vpn"] is True

    def test_create_weekly_schedule(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={
                "device_id": "test-device-001",
                "schedule_type": "weekly",
                "time_of_day": "22:00",
                "day_of_week": 5,
            },
            headers=user_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schedule_type"] == "weekly"
        assert data["day_of_week"] == 5

    def test_create_requires_auth(self, client: TestClient):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={
                "device_id": "test-device-001",
                "schedule_type": "daily",
            },
        )
        assert response.status_code == 401

    def test_create_with_all_sync_settings(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={
                "device_id": "test-device-001",
                "schedule_type": "monthly",
                "time_of_day": "01:00",
                "day_of_month": 15,
                "sync_deletions": False,
                "resolve_conflicts": "keep_local",
                "auto_vpn": True,
            },
            headers=user_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sync_deletions"] is False
        assert data["resolve_conflicts"] == "keep_local"
        assert data["auto_vpn"] is True
        assert data["day_of_month"] == 15


class TestListSchedules:
    """Tests for GET /api/sync/schedule/list."""

    def test_list_empty(self, client: TestClient, user_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/sync/schedule/list",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["schedules"] == []

    def test_list_returns_created_schedules(self, client: TestClient, user_headers: dict):
        # Create two schedules
        client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily"},
            headers=user_headers,
        )
        client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d2", "schedule_type": "weekly", "day_of_week": 1},
            headers=user_headers,
        )

        response = client.get(
            f"{settings.api_prefix}/sync/schedule/list",
            headers=user_headers,
        )

        assert response.status_code == 200
        schedules = response.json()["schedules"]
        assert len(schedules) == 2

    def test_list_includes_disabled(self, client: TestClient, user_headers: dict):
        create_resp = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily"},
            headers=user_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]

        # Disable it
        client.post(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}/disable",
            headers=user_headers,
        )

        response = client.get(
            f"{settings.api_prefix}/sync/schedule/list",
            headers=user_headers,
        )

        schedules = response.json()["schedules"]
        assert len(schedules) == 1
        assert schedules[0]["enabled"] is False

    def test_list_includes_auto_vpn(self, client: TestClient, user_headers: dict):
        client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily", "auto_vpn": True},
            headers=user_headers,
        )

        response = client.get(
            f"{settings.api_prefix}/sync/schedule/list",
            headers=user_headers,
        )

        schedules = response.json()["schedules"]
        assert schedules[0]["auto_vpn"] is True

    def test_list_requires_auth(self, client: TestClient):
        response = client.get(f"{settings.api_prefix}/sync/schedule/list")
        assert response.status_code == 401


class TestDisableSchedule:
    """Tests for POST /api/sync/schedule/{id}/disable."""

    def test_disable_schedule(self, client: TestClient, user_headers: dict):
        create_resp = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily"},
            headers=user_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]

        response = client.post(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}/disable",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["disabled"] is True

    def test_disable_nonexistent(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/9999/disable",
            headers=user_headers,
        )
        assert response.status_code == 404


class TestEnableSchedule:
    """Tests for POST /api/sync/schedule/{id}/enable."""

    def test_enable_disabled_schedule(self, client: TestClient, user_headers: dict):
        create_resp = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily"},
            headers=user_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]

        # Disable first
        client.post(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}/disable",
            headers=user_headers,
        )

        # Enable
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}/enable",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["enabled"] is True

        # Verify via list
        list_resp = client.get(
            f"{settings.api_prefix}/sync/schedule/list",
            headers=user_headers,
        )
        assert list_resp.json()["schedules"][0]["enabled"] is True

    def test_enable_nonexistent(self, client: TestClient, user_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/9999/enable",
            headers=user_headers,
        )
        assert response.status_code == 404

    def test_enable_requires_auth(self, client: TestClient):
        response = client.post(
            f"{settings.api_prefix}/sync/schedule/1/enable",
        )
        assert response.status_code == 401


class TestUpdateSchedule:
    """Tests for PUT /api/sync/schedule/{id}."""

    def test_update_time(self, client: TestClient, user_headers: dict):
        create_resp = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily", "time_of_day": "02:00"},
            headers=user_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]

        response = client.put(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}",
            json={"time_of_day": "06:00"},
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["time_of_day"] == "06:00"

    def test_update_auto_vpn(self, client: TestClient, user_headers: dict):
        create_resp = client.post(
            f"{settings.api_prefix}/sync/schedule/create",
            json={"device_id": "d1", "schedule_type": "daily", "auto_vpn": False},
            headers=user_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]

        response = client.put(
            f"{settings.api_prefix}/sync/schedule/{schedule_id}",
            json={"auto_vpn": True},
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["auto_vpn"] is True

    def test_update_nonexistent(self, client: TestClient, user_headers: dict):
        response = client.put(
            f"{settings.api_prefix}/sync/schedule/9999",
            json={"time_of_day": "06:00"},
            headers=user_headers,
        )
        assert response.status_code == 404

    def test_update_requires_auth(self, client: TestClient):
        response = client.put(
            f"{settings.api_prefix}/sync/schedule/1",
            json={"time_of_day": "06:00"},
        )
        assert response.status_code == 401
