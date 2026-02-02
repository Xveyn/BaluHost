"""
API integration tests for users routes.

Tests:
- List users endpoint
- Create user (admin only)
- Update user (admin only)
- Delete user (admin only)
- Toggle user active status
"""
import pytest
from fastapi.testclient import TestClient


class TestListUsers:
    """Tests for GET /api/users/."""

    def test_list_requires_auth(self, client: TestClient):
        """Test that listing users requires authentication."""
        response = client.get("/api/users/")
        assert response.status_code == 401

    def test_list_returns_users(self, client: TestClient, user_headers: dict):
        """Test that listing users returns user list."""
        response = client.get("/api/users/", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "users" in data
        assert "total" in data
        assert "active" in data
        assert isinstance(data["users"], list)

    def test_list_with_search(self, client: TestClient, user_headers: dict):
        """Test listing users with search parameter."""
        response = client.get(
            "/api/users/",
            params={"search": "admin"},
            headers=user_headers
        )
        assert response.status_code == 200

    def test_list_with_role_filter(self, client: TestClient, user_headers: dict):
        """Test listing users with role filter."""
        response = client.get(
            "/api/users/",
            params={"role": "admin"},
            headers=user_headers
        )
        assert response.status_code == 200

    def test_list_with_sorting(self, client: TestClient, user_headers: dict):
        """Test listing users with sorting."""
        response = client.get(
            "/api/users/",
            params={"sort_by": "username", "sort_order": "asc"},
            headers=user_headers
        )
        assert response.status_code == 200


class TestCreateUser:
    """Tests for POST /api/users/."""

    def test_create_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that creating user requires admin."""
        response = client.post(
            "/api/users/",
            json={"username": "newuser", "password": "Test1234!"},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_create_user_success(self, client: TestClient, admin_headers: dict):
        """Test creating a new user as admin."""
        response = client.post(
            "/api/users/",
            json={
                "username": "apitest_user",
                "password": "Test1234!",
                "email": "apitest@example.com",
                "role": "user"
            },
            headers=admin_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["username"] == "apitest_user"
        assert "id" in data

    def test_create_user_duplicate_username(self, client: TestClient, admin_headers: dict):
        """Test creating user with duplicate username fails."""
        # First create
        client.post(
            "/api/users/",
            json={
                "username": "duplicate_test",
                "password": "Test1234!",
                "role": "user"
            },
            headers=admin_headers
        )

        # Second create with same username
        response = client.post(
            "/api/users/",
            json={
                "username": "duplicate_test",
                "password": "Test1234!",
                "role": "user"
            },
            headers=admin_headers
        )
        assert response.status_code == 409


class TestUpdateUser:
    """Tests for PUT /api/users/{user_id}."""

    def test_update_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that updating user requires admin."""
        response = client.put(
            "/api/users/1",
            json={"email": "new@example.com"},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_update_nonexistent_user(self, client: TestClient, admin_headers: dict):
        """Test updating non-existent user."""
        response = client.put(
            "/api/users/99999",
            json={"email": "new@example.com"},
            headers=admin_headers
        )
        assert response.status_code == 404


class TestDeleteUser:
    """Tests for DELETE /api/users/{user_id}."""

    def test_delete_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that deleting user requires admin."""
        response = client.delete("/api/users/999", headers=user_headers)
        assert response.status_code == 403

    def test_delete_nonexistent_user(self, client: TestClient, admin_headers: dict):
        """Test deleting non-existent user."""
        response = client.delete("/api/users/99999", headers=admin_headers)
        assert response.status_code == 404


class TestBulkDeleteUsers:
    """Tests for POST /api/users/bulk-delete."""

    def test_bulk_delete_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that bulk delete requires admin."""
        response = client.post(
            "/api/users/bulk-delete",
            json=["999"],
            headers=user_headers
        )
        assert response.status_code == 403

    def test_bulk_delete_returns_stats(self, client: TestClient, admin_headers: dict):
        """Test bulk delete returns delete statistics."""
        response = client.post(
            "/api/users/bulk-delete",
            json=["99999"],  # Non-existent IDs
            headers=admin_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "deleted" in data
        assert "failed" in data


class TestToggleUserActive:
    """Tests for PATCH /api/users/{user_id}/toggle-active."""

    def test_toggle_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that toggling user status requires admin."""
        response = client.patch(
            "/api/users/1/toggle-active",
            headers=user_headers
        )
        assert response.status_code == 403

    def test_toggle_nonexistent_user(self, client: TestClient, admin_headers: dict):
        """Test toggling non-existent user."""
        response = client.patch(
            "/api/users/99999/toggle-active",
            headers=admin_headers
        )
        assert response.status_code == 404
