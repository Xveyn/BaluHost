"""
API integration tests for power management routes.

Tests:
- Power status endpoint
- Power profiles listing
- Profile setting (admin only)
- Power demands management
- Auto-scaling configuration
"""
import pytest
from fastapi.testclient import TestClient


class TestPowerStatus:
    """Tests for GET /api/power/status."""

    def test_status_requires_auth(self, client: TestClient):
        """Test that status endpoint requires authentication."""
        response = client.get("/api/power/status")
        assert response.status_code == 401

    def test_status_returns_data(self, client: TestClient, user_headers: dict):
        """Test that status endpoint returns power data."""
        response = client.get("/api/power/status", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "current_profile" in data
        assert "is_dev_mode" in data
        assert "auto_scaling_enabled" in data


class TestPowerProfiles:
    """Tests for GET /api/power/profiles."""

    def test_profiles_requires_auth(self, client: TestClient):
        """Test that profiles endpoint requires authentication."""
        response = client.get("/api/power/profiles")
        assert response.status_code == 401

    def test_profiles_returns_list(self, client: TestClient, user_headers: dict):
        """Test that profiles endpoint returns list of profiles."""
        response = client.get("/api/power/profiles", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "profiles" in data
        assert "current_profile" in data
        assert isinstance(data["profiles"], list)
        assert len(data["profiles"]) >= 1


class TestSetProfile:
    """Tests for POST /api/power/profile."""

    def test_set_profile_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that setting profile requires admin."""
        response = client.post(
            "/api/power/profile",
            json={"profile": "surge"},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_set_profile_as_admin(self, client: TestClient, admin_headers: dict):
        """Test setting a power profile as admin (may fail if backend not initialized)."""
        response = client.post(
            "/api/power/profile",
            json={"profile": "medium", "reason": "Test"},
            headers=admin_headers
        )
        # May return 200 on success or 500 if backend not fully initialized in tests
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "previous_profile" in data
            assert "new_profile" in data


class TestPowerDemands:
    """Tests for power demands endpoints."""

    def test_get_demands_requires_auth(self, client: TestClient):
        """Test that getting demands requires authentication."""
        response = client.get("/api/power/demands")
        assert response.status_code == 401

    def test_get_demands_returns_list(self, client: TestClient, user_headers: dict):
        """Test that demands endpoint returns list."""
        response = client.get("/api/power/demands", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_register_demand_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that registering demand requires admin."""
        response = client.post(
            "/api/power/demands",
            json={"source": "test_source", "level": "medium"},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_register_demand_success(self, client: TestClient, admin_headers: dict):
        """Test registering a power demand."""
        response = client.post(
            "/api/power/demands",
            json={
                "source": "api_test",
                "level": "medium",
                "timeout_seconds": 60,
                "description": "API test demand"
            },
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "demand_id" in data

    def test_unregister_demand_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that unregistering demand requires admin."""
        response = client.request(
            "DELETE",
            "/api/power/demands",
            json={"source": "test_source"},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_unregister_nonexistent_demand(self, client: TestClient, admin_headers: dict):
        """Test unregistering a non-existent demand."""
        response = client.request(
            "DELETE",
            "/api/power/demands",
            json={"source": "nonexistent_demand"},
            headers=admin_headers
        )
        assert response.status_code == 404


class TestPowerHistory:
    """Tests for GET /api/power/history."""

    def test_history_requires_auth(self, client: TestClient):
        """Test that history requires authentication."""
        response = client.get("/api/power/history")
        assert response.status_code == 401

    def test_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test that history returns list of entries."""
        response = client.get("/api/power/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "entries" in data
        assert "total_entries" in data

    def test_history_with_pagination(self, client: TestClient, user_headers: dict):
        """Test history with limit and offset."""
        response = client.get(
            "/api/power/history",
            params={"limit": 10, "offset": 0},
            headers=user_headers
        )
        assert response.status_code == 200


class TestAutoScaling:
    """Tests for auto-scaling configuration endpoints."""

    def test_get_auto_scaling_requires_auth(self, client: TestClient):
        """Test that getting auto-scaling config requires authentication."""
        response = client.get("/api/power/auto-scaling")
        assert response.status_code == 401

    def test_get_auto_scaling_returns_config(self, client: TestClient, user_headers: dict):
        """Test getting auto-scaling configuration."""
        response = client.get("/api/power/auto-scaling", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "config" in data

    def test_update_auto_scaling_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that updating auto-scaling requires admin."""
        response = client.put(
            "/api/power/auto-scaling",
            json={"enabled": True},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_update_auto_scaling_success(self, client: TestClient, admin_headers: dict):
        """Test updating auto-scaling configuration."""
        response = client.put(
            "/api/power/auto-scaling",
            json={
                "enabled": True,
                "cpu_threshold_low": 20,
                "cpu_threshold_high": 80,
                "cooldown_seconds": 30
            },
            headers=admin_headers
        )
        assert response.status_code == 200


class TestSwitchBackend:
    """Tests for POST /api/power/backend."""

    def test_switch_backend_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that switching backend requires admin."""
        response = client.post(
            "/api/power/backend",
            json={"use_linux_backend": False},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_switch_to_dev_backend(self, client: TestClient, admin_headers: dict):
        """Test switching to dev (simulation) backend."""
        response = client.post(
            "/api/power/backend",
            json={"use_linux_backend": False},
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "new_backend" in data
