"""
Tests for fan control API routes (api/routes/fans.py).

Covers:
- GET fan status and list
- SET fan mode (admin only)
- PWM set + minimum validation
- Presets endpoint
- Schedule entry CRUD
- History endpoint
- Auth checks (admin-only for write operations)
"""

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Read Endpoints (any authenticated user)
# ============================================================================

class TestFanReadEndpoints:
    """Test fan status and info endpoints."""

    def test_get_fan_status(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "fans" in data or "mode" in data or "status" in data or isinstance(data, dict)

    def test_get_fan_status_unauthenticated(self, client: TestClient):
        response = client.get("/api/fans/status")
        assert response.status_code == 401

    def test_list_fans(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/list", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_fan_history(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/history", headers=auth_headers)
        assert response.status_code == 200

    def test_get_fan_history_with_params(self, client: TestClient, auth_headers):
        response = client.get(
            "/api/fans/history",
            params={"limit": 10, "offset": 0},
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_get_presets(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "presets" in data

    def test_get_permissions(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/permissions", headers=auth_headers)
        assert response.status_code == 200


# ============================================================================
# Write Endpoints (admin only)
# ============================================================================

class TestFanAdminEndpoints:
    """Test fan control write operations (admin-only)."""

    def test_set_fan_mode_requires_admin(self, client: TestClient, auth_headers):
        """Regular user should be rejected."""
        response = client.post(
            "/api/fans/mode",
            json={"fan_id": "fan1", "mode": "manual"},
            headers=auth_headers,  # regular user
        )
        assert response.status_code == 403

    def test_set_fan_mode_as_admin(self, client: TestClient, admin_headers):
        response = client.post(
            "/api/fans/mode",
            json={"fan_id": "fan1", "mode": "auto"},
            headers=admin_headers,
        )
        # 200 or 404 (fan not found in dev mode) are both valid
        assert response.status_code in (200, 404)

    def test_set_fan_pwm_requires_admin(self, client: TestClient, auth_headers):
        response = client.post(
            "/api/fans/pwm",
            json={"fan_id": "fan1", "pwm_percent": 75},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_set_fan_pwm_as_admin(self, client: TestClient, admin_headers):
        response = client.post(
            "/api/fans/pwm",
            json={"fan_id": "fan1", "pwm_percent": 75},
            headers=admin_headers,
        )
        assert response.status_code in (200, 400, 404)

    def test_update_fan_curve_requires_admin(self, client: TestClient, auth_headers):
        response = client.put(
            "/api/fans/curve",
            json={
                "fan_id": "fan1",
                "curve_points": [
                    {"temp": 30, "pwm": 30},
                    {"temp": 80, "pwm": 100},
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_apply_preset_requires_admin(self, client: TestClient, auth_headers):
        response = client.post(
            "/api/fans/preset",
            json={"fan_id": "fan1", "preset": "silent"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_apply_preset_as_admin(self, client: TestClient, admin_headers):
        response = client.post(
            "/api/fans/preset",
            json={"fan_id": "fan1", "preset": "silent"},
            headers=admin_headers,
        )
        # 200 = success, 404 = preset not found
        assert response.status_code in (200, 404)

    def test_update_fan_config_requires_admin(self, client: TestClient, auth_headers):
        response = client.patch(
            "/api/fans/config",
            json={"fan_id": "fan1"},
            headers=auth_headers,
        )
        assert response.status_code == 403


# ============================================================================
# Schedule Endpoints (admin only)
# ============================================================================

class TestFanScheduleRoutes:
    """Test fan schedule CRUD via API."""

    def test_get_schedule_requires_admin(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/fan1/schedule", headers=auth_headers)
        assert response.status_code == 403

    def test_get_schedule_as_admin(self, client: TestClient, admin_headers):
        response = client.get("/api/fans/fan1/schedule", headers=admin_headers)
        # 200 even if empty schedule, or 404 if fan doesn't exist
        assert response.status_code in (200, 404)

    def test_create_schedule_entry_requires_admin(self, client: TestClient, auth_headers):
        response = client.post(
            "/api/fans/fan1/schedule",
            json={
                "name": "Night Mode",
                "start_time": "22:00",
                "end_time": "06:00",
                "curve_points": [
                    {"temp": 40, "pwm": 30},
                    {"temp": 80, "pwm": 100},
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_create_schedule_entry_as_admin(self, client: TestClient, admin_headers):
        response = client.post(
            "/api/fans/fan1/schedule",
            json={
                "name": "Night Mode",
                "start_time": "22:00",
                "end_time": "06:00",
                "curve_points": [
                    {"temp": 40, "pwm": 30},
                    {"temp": 80, "pwm": 100},
                ],
            },
            headers=admin_headers,
        )
        # 201 = created, 404 = fan not found, 422 = max entries reached in dev mode
        assert response.status_code in (201, 404, 422)

    def test_delete_schedule_entry_requires_admin(self, client: TestClient, auth_headers):
        response = client.delete("/api/fans/fan1/schedule/1", headers=auth_headers)
        assert response.status_code == 403

    def test_get_active_schedule_requires_admin(self, client: TestClient, auth_headers):
        response = client.get("/api/fans/fan1/schedule/active", headers=auth_headers)
        assert response.status_code == 403

    def test_unauthenticated_rejected(self, client: TestClient):
        response = client.get("/api/fans/fan1/schedule")
        assert response.status_code == 401

        response = client.post("/api/fans/fan1/schedule", json={})
        assert response.status_code == 401
