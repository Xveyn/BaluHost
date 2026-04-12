"""Tests for dev-only admin → user impersonation endpoint."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User


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
