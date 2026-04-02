"""Tests for power permissions API endpoints and delegated sleep access."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service


@pytest.fixture
def admin_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={
        "username": settings.admin_username,
        "password": settings.admin_password,
    })
    return resp.json()["access_token"]


@pytest.fixture
def regular_user(db_session: Session) -> User:
    existing = user_service.get_user_by_username("poweruser", db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(username="poweruser", email="power@test.com", password="Test1234", role="user"),
        db=db_session,
    )


@pytest.fixture
def user_token(client: TestClient, regular_user: User) -> str:
    resp = client.post("/api/auth/login", json={
        "username": "poweruser",
        "password": "Test1234",
    })
    return resp.json()["access_token"]


class TestGetPowerPermissions:
    def test_admin_can_get_permissions(self, client: TestClient, admin_token: str, regular_user: User):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is False
        assert data["can_wake"] is False

    def test_non_admin_cannot_get_permissions(self, client: TestClient, user_token: str, regular_user: User):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


class TestUpdatePowerPermissions:
    def test_admin_can_set_permissions(self, client: TestClient, admin_token: str, regular_user: User):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is True
        assert data["can_wake"] is True  # implied

    def test_non_admin_cannot_set_permissions(self, client: TestClient, user_token: str, regular_user: User):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


class TestMyPermissions:
    def test_user_can_see_own_permissions(self, client: TestClient, user_token: str):
        resp = client.get(
            "/api/system/sleep/my-permissions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is False

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.get("/api/system/sleep/my-permissions")
        assert resp.status_code == 401


class TestDelegatedSleepAccess:
    def test_user_without_permission_gets_403(self, client: TestClient, user_token: str):
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    def test_user_with_permission_can_access(
        self, client: TestClient, admin_token: str, user_token: str, regular_user: User,
    ):
        # Grant permission
        client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # User can now access (will get 503 because sleep manager isn't running in test, but not 403)
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code != 403  # 503 expected (service not running), not 403

    def test_admin_still_works(self, client: TestClient, admin_token: str):
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code != 403  # 503 expected (service not running), not 403
