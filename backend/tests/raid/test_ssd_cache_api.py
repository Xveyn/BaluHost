"""API endpoint tests for SSD cache (bcache) management."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.hardware.ssd_cache import DevSsdCacheBackend


@pytest.fixture(autouse=True)
def _reset_ssd_cache_backend():
    """Reset the module-level SSD cache backend before each test."""
    import app.services.hardware.ssd_cache as ssd_mod
    ssd_mod._backend = DevSsdCacheBackend()
    yield
    ssd_mod._backend = DevSsdCacheBackend()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_admin(client: TestClient) -> dict[str, str]:
    resp = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _login_user(client: TestClient) -> dict[str, str]:
    resp = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": "testuser", "password": "Testpass123!"},
    )
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


PREFIX = "/api/system/raid/cache"


# ---------------------------------------------------------------------------
# GET /raid/cache/status — all statuses
# ---------------------------------------------------------------------------

class TestGetAllCacheStatuses:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.get(f"{PREFIX}/status")
        assert resp.status_code == 401

    def test_user_can_read(self, client: TestClient):
        headers = _login_user(client)
        resp = client.get(f"{PREFIX}/status", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_read(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.get(f"{PREFIX}/status", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET /raid/cache/status/{array} — single array
# ---------------------------------------------------------------------------

class TestGetCacheStatusByArray:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.get(f"{PREFIX}/status/md0")
        assert resp.status_code == 401

    def test_not_found_when_no_cache(self, client: TestClient):
        headers = _login_user(client)
        resp = client.get(f"{PREFIX}/status/md99", headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /raid/cache/attach — admin only
# ---------------------------------------------------------------------------

class TestAttachCache:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1"},
        )
        assert resp.status_code == 401

    def test_regular_user_forbidden(self, client: TestClient):
        headers = _login_user(client)
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_admin_attach_success(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1", "mode": "writethrough"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "attached" in data["message"].lower() or "DEV MODE" in data["message"]

    def test_admin_attach_duplicate_returns_400(self, client: TestClient):
        headers = _login_admin(client)
        # First attach
        client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1"},
            headers=headers,
        )
        # Second attach — should fail
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme2n1p1"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_invalid_payload(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0"},  # missing cache_device
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /raid/cache/detach — admin only
# ---------------------------------------------------------------------------

class TestDetachCache:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.post(f"{PREFIX}/detach", json={"array": "md0"})
        assert resp.status_code == 401

    def test_regular_user_forbidden(self, client: TestClient):
        headers = _login_user(client)
        resp = client.post(f"{PREFIX}/detach", json={"array": "md0"}, headers=headers)
        assert resp.status_code == 403

    def test_detach_nonexistent_returns_400(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.post(f"{PREFIX}/detach", json={"array": "md99"}, headers=headers)
        assert resp.status_code == 400

    def test_admin_attach_then_detach_success(self, client: TestClient):
        headers = _login_admin(client)
        # Attach first
        client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1"},
            headers=headers,
        )
        # Detach
        resp = client.post(
            f"{PREFIX}/detach",
            json={"array": "md0"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "detached" in resp.json()["message"].lower()


# ---------------------------------------------------------------------------
# POST /raid/cache/configure — admin only
# ---------------------------------------------------------------------------

class TestConfigureCache:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.post(
            f"{PREFIX}/configure",
            json={"array": "md0", "mode": "writeback"},
        )
        assert resp.status_code == 401

    def test_regular_user_forbidden(self, client: TestClient):
        headers = _login_user(client)
        resp = client.post(
            f"{PREFIX}/configure",
            json={"array": "md0", "mode": "writeback"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_configure_nonexistent_returns_400(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.post(
            f"{PREFIX}/configure",
            json={"array": "md99", "mode": "writeback"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_admin_configure_mode(self, client: TestClient):
        headers = _login_admin(client)
        # Attach first
        client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1"},
            headers=headers,
        )
        # Configure
        resp = client.post(
            f"{PREFIX}/configure",
            json={"array": "md0", "mode": "writeback"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "mode=writeback" in resp.json()["message"]


# ---------------------------------------------------------------------------
# POST /raid/cache/external-bitmap — admin only
# ---------------------------------------------------------------------------

class TestExternalBitmap:

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.post(
            f"{PREFIX}/external-bitmap",
            json={"array": "md0", "ssd_partition": "nvme1n1p2"},
        )
        assert resp.status_code == 401

    def test_regular_user_forbidden(self, client: TestClient):
        headers = _login_user(client)
        resp = client.post(
            f"{PREFIX}/external-bitmap",
            json={"array": "md0", "ssd_partition": "nvme1n1p2"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_admin_set_bitmap_success(self, client: TestClient):
        headers = _login_admin(client)
        resp = client.post(
            f"{PREFIX}/external-bitmap",
            json={"array": "md0", "ssd_partition": "nvme1n1p2"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "bitmap" in resp.json()["message"].lower()


# ---------------------------------------------------------------------------
# Integration: attach → status → configure → detach
# ---------------------------------------------------------------------------

class TestCacheLifecycle:

    def test_full_lifecycle(self, client: TestClient):
        headers = _login_admin(client)

        # 1. No caches initially
        resp = client.get(f"{PREFIX}/status", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        # 2. Attach cache
        resp = client.post(
            f"{PREFIX}/attach",
            json={"array": "md0", "cache_device": "nvme1n1p1", "mode": "writethrough"},
            headers=headers,
        )
        assert resp.status_code == 200

        # 3. Check status
        resp = client.get(f"{PREFIX}/status/md0", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["array_name"] == "md0"
        assert data["mode"] == "writethrough"
        assert data["state"] == "running"

        # 4. Configure to writeback
        resp = client.post(
            f"{PREFIX}/configure",
            json={"array": "md0", "mode": "writeback"},
            headers=headers,
        )
        assert resp.status_code == 200

        # 5. Verify mode changed
        resp = client.get(f"{PREFIX}/status/md0", headers=headers)
        assert resp.json()["mode"] == "writeback"

        # 6. Detach
        resp = client.post(
            f"{PREFIX}/detach",
            json={"array": "md0"},
            headers=headers,
        )
        assert resp.status_code == 200

        # 7. Confirm cache gone
        resp = client.get(f"{PREFIX}/status/md0", headers=headers)
        assert resp.status_code == 404
