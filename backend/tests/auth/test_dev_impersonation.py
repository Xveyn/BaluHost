"""Tests for dev-only admin → user impersonation endpoint."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service


def test_create_access_token_includes_impersonated_by_when_set():
    """`impersonated_by` claim is included when the kwarg is passed."""
    fake_user = {"id": 42, "username": "alice", "role": "user"}
    token = create_access_token(fake_user, impersonated_by=7)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"
    assert payload["type"] == "access"
    assert payload["impersonated_by"] == 7


def test_create_access_token_omits_impersonated_by_by_default():
    """Existing callers get the same payload they had before."""
    fake_user = {"id": 1, "username": "admin", "role": "admin"}
    token = create_access_token(fake_user)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    assert "impersonated_by" not in payload


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

IMPERSONATE_URL = f"{settings.api_prefix}/auth/dev/impersonate"


@pytest.fixture
def target_user(db_session: Session) -> User:
    """Secondary regular user used as impersonation target.

    Named `target_user` (not `regular_user`) to avoid colliding with the
    conftest-level `regular_user` fixture used by the rest of the suite.
    """
    existing = user_service.get_user_by_username("alice_imp", db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(
            username="alice_imp",
            email="alice_imp@example.com",
            password="Passw0rd!",
            role="user",
        ),
        db=db_session,
    )


@pytest.fixture
def target_user_headers(client: TestClient, target_user: User) -> dict[str, str]:
    response = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": target_user.username, "password": "Passw0rd!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_impersonate_as_admin_in_dev_mode_returns_token(
    client: TestClient, admin_headers: dict, target_user: User
):
    response = client.post(
        f"{IMPERSONATE_URL}/{target_user.id}",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == target_user.username

    payload = jwt.decode(body["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == str(target_user.id)
    assert payload["username"] == target_user.username
    assert payload["role"] == "user"
    assert "impersonated_by" in payload


def test_impersonate_as_regular_user_returns_403(
    client: TestClient, target_user_headers: dict, target_user: User
):
    response = client.post(
        f"{IMPERSONATE_URL}/{target_user.id}",
        headers=target_user_headers,
    )
    assert response.status_code == 403


def test_impersonate_without_auth_returns_401(client: TestClient, target_user: User):
    response = client.post(f"{IMPERSONATE_URL}/{target_user.id}")
    assert response.status_code == 401


def test_impersonate_nonexistent_user_returns_404(client: TestClient, admin_headers: dict):
    response = client.post(
        f"{IMPERSONATE_URL}/999999",
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_impersonate_inactive_user_returns_404(
    client: TestClient, admin_headers: dict, db_session: Session, target_user: User
):
    target_user.is_active = False
    db_session.commit()
    response = client.post(
        f"{IMPERSONATE_URL}/{target_user.id}",
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_impersonate_self_returns_400(
    client: TestClient, admin_headers: dict, db_session: Session
):
    admin = user_service.get_user_by_username(settings.admin_username, db=db_session)
    response = client.post(
        f"{IMPERSONATE_URL}/{admin.id}",
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_impersonation_token_works_for_user_endpoints(
    client: TestClient, admin_headers: dict, target_user: User
):
    imp_response = client.post(
        f"{IMPERSONATE_URL}/{target_user.id}",
        headers=admin_headers,
    )
    imp_token = imp_response.json()["access_token"]

    me = client.get(
        f"{settings.api_prefix}/auth/me",
        headers={"Authorization": f"Bearer {imp_token}"},
    )
    assert me.status_code == 200
    # /auth/me returns UserPublic directly (not wrapped in {"user": ...})
    assert me.json()["username"] == target_user.username


def test_impersonate_writes_audit_log(
    client: TestClient, admin_headers: dict, target_user: User, db_session: Session
):
    from app.models.audit_log import AuditLog

    client.post(
        f"{IMPERSONATE_URL}/{target_user.id}",
        headers=admin_headers,
    )
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "dev_impersonation_started")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert entry is not None
    assert entry.user == settings.admin_username
    assert str(target_user.id) in (entry.details or "")
