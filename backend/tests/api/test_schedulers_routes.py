"""
API integration tests for scheduler routes.

Tests:
- List all schedulers (admin only)
- Get specific scheduler status
- Run scheduler now
- Get scheduler history
- Toggle scheduler enable/disable
"""
import pytest
from fastapi.testclient import TestClient


class TestListSchedulers:
    """Tests for GET /api/schedulers/."""

    def test_list_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that listing schedulers requires admin."""
        response = client.get("/api/schedulers/", headers=user_headers)
        assert response.status_code == 403

    def test_list_returns_schedulers(self, client: TestClient, admin_headers: dict):
        """Test that admin can list all schedulers."""
        response = client.get("/api/schedulers/", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "schedulers" in data
        assert "total_running" in data
        assert "total_enabled" in data
        assert isinstance(data["schedulers"], list)


class TestGetScheduler:
    """Tests for GET /api/schedulers/{name}."""

    def test_get_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that getting scheduler requires admin."""
        response = client.get("/api/schedulers/sync_check", headers=user_headers)
        assert response.status_code == 403

    def test_get_existing_scheduler(self, client: TestClient, admin_headers: dict):
        """Test getting an existing scheduler."""
        response = client.get("/api/schedulers/sync_check", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "name" in data
        assert data["name"] == "sync_check"
        assert "is_running" in data
        assert "is_enabled" in data

    def test_get_nonexistent_scheduler(self, client: TestClient, admin_headers: dict):
        """Test getting a non-existent scheduler."""
        response = client.get("/api/schedulers/nonexistent", headers=admin_headers)
        assert response.status_code == 404


class TestRunSchedulerNow:
    """Tests for POST /api/schedulers/{name}/run-now."""

    def test_run_now_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that run-now requires admin."""
        response = client.post(
            "/api/schedulers/sync_check/run-now",
            json={},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_run_now_nonexistent_scheduler(self, client: TestClient, admin_headers: dict):
        """Test running a non-existent scheduler."""
        response = client.post(
            "/api/schedulers/nonexistent/run-now",
            json={},
            headers=admin_headers
        )
        assert response.status_code == 400


class TestSchedulerHistory:
    """Tests for GET /api/schedulers/{name}/history."""

    def test_history_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that history requires admin."""
        response = client.get("/api/schedulers/sync_check/history", headers=user_headers)
        assert response.status_code == 403

    def test_history_returns_data(self, client: TestClient, admin_headers: dict):
        """Test getting scheduler history."""
        response = client.get("/api/schedulers/sync_check/history", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "executions" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_history_with_pagination(self, client: TestClient, admin_headers: dict):
        """Test history with pagination parameters."""
        response = client.get(
            "/api/schedulers/sync_check/history",
            params={"page": 1, "page_size": 5},
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5


class TestAllSchedulerHistory:
    """Tests for GET /api/schedulers/history/all."""

    def test_all_history_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that all history requires admin."""
        response = client.get("/api/schedulers/history/all", headers=user_headers)
        assert response.status_code == 403

    def test_all_history_returns_data(self, client: TestClient, admin_headers: dict):
        """Test getting all scheduler history."""
        response = client.get("/api/schedulers/history/all", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "executions" in data
        assert "total" in data


class TestToggleScheduler:
    """Tests for POST /api/schedulers/{name}/toggle."""

    def test_toggle_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that toggling requires admin."""
        response = client.post(
            "/api/schedulers/sync_check/toggle",
            json={"enabled": True},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_toggle_existing_scheduler(self, client: TestClient, admin_headers: dict):
        """Test toggling an existing scheduler."""
        response = client.post(
            "/api/schedulers/sync_check/toggle",
            json={"enabled": True},
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "scheduler_name" in data
        assert "is_enabled" in data


class TestUpdateSchedulerConfig:
    """Tests for PUT /api/schedulers/{name}/config."""

    def test_config_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that updating config requires admin."""
        response = client.put(
            "/api/schedulers/sync_check/config",
            json={"interval_seconds": 600},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_update_config_existing_scheduler(self, client: TestClient, admin_headers: dict):
        """Test updating config for existing scheduler."""
        response = client.put(
            "/api/schedulers/sync_check/config",
            json={"interval_seconds": 300, "is_enabled": True},
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_update_config_nonexistent_scheduler(self, client: TestClient, admin_headers: dict):
        """Test updating config for non-existent scheduler."""
        response = client.put(
            "/api/schedulers/nonexistent/config",
            json={"interval_seconds": 600},
            headers=admin_headers
        )
        assert response.status_code == 404
