"""
Tests for share API routes (api/routes/shares.py).

Covers:
- Share link CRUD endpoints
- Public share link access
- File share (user-to-user) endpoints
- Authentication and authorization checks
- Statistics endpoint
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.models.file_metadata import FileMetadata


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def owned_file(db_session, regular_user) -> FileMetadata:
    """Create a file owned by regular_user."""
    meta = FileMetadata(
        path="api_test_file.txt",
        name="api_test_file.txt",
        owner_id=regular_user.id,
        size_bytes=1024,
        is_directory=False,
        mime_type="text/plain",
    )
    db_session.add(meta)
    db_session.commit()
    db_session.refresh(meta)
    return meta


# ============================================================================
# Share Link Endpoints
# ============================================================================

class TestShareLinkRoutes:
    """Test share link CRUD API endpoints."""

    def test_create_share_link(self, client, auth_headers, owned_file):
        response = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "token" in data
        assert data["file_id"] == owned_file.id

    def test_create_share_link_unauthenticated(self, client, owned_file):
        response = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
        )
        assert response.status_code == 401

    def test_list_share_links(self, client, auth_headers, owned_file):
        # Create a share link first
        client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )

        response = client.get("/api/shares/links", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_share_link(self, client, auth_headers, owned_file):
        create_resp = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        link_id = create_resp.json()["id"]

        response = client.get(f"/api/shares/links/{link_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == link_id

    def test_get_share_link_not_found(self, client, auth_headers):
        response = client.get("/api/shares/links/999999", headers=auth_headers)
        assert response.status_code == 404

    def test_update_share_link(self, client, auth_headers, owned_file):
        create_resp = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        link_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/shares/links/{link_id}",
            json={"description": "Updated", "max_downloads": 5},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated"

    def test_delete_share_link(self, client, auth_headers, owned_file):
        create_resp = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        link_id = create_resp.json()["id"]

        response = client.delete(f"/api/shares/links/{link_id}", headers=auth_headers)
        assert response.status_code in (200, 204)

        # Verify it's gone
        get_resp = client.get(f"/api/shares/links/{link_id}", headers=auth_headers)
        assert get_resp.status_code == 404


class TestPublicShareAccess:
    """Test public share link access endpoints."""

    def test_get_share_link_info(self, client, auth_headers, owned_file):
        create_resp = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        token = create_resp.json()["token"]

        # Public endpoint — no auth needed
        response = client.get(f"/api/shares/public/{token}/info")
        assert response.status_code == 200

    def test_get_share_link_info_not_found(self, client):
        response = client.get("/api/shares/public/nonexistent-token/info")
        assert response.status_code == 404

    def test_access_share_link_no_password(self, client, auth_headers, owned_file):
        create_resp = client.post(
            "/api/shares/links",
            json={"file_id": owned_file.id},
            headers=auth_headers,
        )
        token = create_resp.json()["token"]

        response = client.post(
            f"/api/shares/public/{token}/access",
            json={},
        )
        assert response.status_code == 200


# ============================================================================
# File Share Endpoints
# ============================================================================

class TestFileShareRoutes:
    """Test user-to-user file sharing endpoints."""

    def test_create_file_share(self, client, auth_headers, owned_file, another_user):
        response = client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
            headers=auth_headers,
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["file_id"] == owned_file.id
        assert data["shared_with_user_id"] == another_user.id

    def test_create_file_share_unauthenticated(self, client, owned_file, another_user):
        response = client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
        )
        assert response.status_code == 401

    def test_list_file_shares(self, client, auth_headers, owned_file, another_user):
        client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
            headers=auth_headers,
        )

        response = client.get("/api/shares/user-shares", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_files_shared_with_me(self, client, auth_headers, another_user_headers, owned_file, another_user):
        # Share file with another_user
        client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
            headers=auth_headers,
        )

        # another_user checks what's shared with them
        response = client.get("/api/shares/shared-with-me", headers=another_user_headers)
        assert response.status_code == 200

    def test_update_file_share(self, client, auth_headers, owned_file, another_user):
        create_resp = client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
            headers=auth_headers,
        )
        share_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/shares/user-shares/{share_id}",
            json={"can_write": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["can_write"] is True

    def test_delete_file_share(self, client, auth_headers, owned_file, another_user):
        create_resp = client.post(
            "/api/shares/user-shares",
            json={
                "file_id": owned_file.id,
                "shared_with_user_id": another_user.id,
            },
            headers=auth_headers,
        )
        share_id = create_resp.json()["id"]

        response = client.delete(f"/api/shares/user-shares/{share_id}", headers=auth_headers)
        assert response.status_code in (200, 204)


# ============================================================================
# Statistics
# ============================================================================

class TestShareStatistics:
    """Test sharing statistics endpoint."""

    def test_get_statistics(self, client, auth_headers):
        response = client.get("/api/shares/statistics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_share_links" in data
        assert "total_file_shares" in data

    def test_get_statistics_unauthenticated(self, client):
        response = client.get("/api/shares/statistics")
        assert response.status_code == 401
