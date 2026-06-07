"""Tests for baluhost_tui.api.auth.login."""
from __future__ import annotations

from typing import Any

import pytest

from baluhost_tui.api.auth import login, LoginError, TwoFactorRequired


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[tuple[str, Any]] = []

    def post(self, path: str, json: Any = None, **_: Any) -> _Resp:
        self.calls.append((path, json))
        return self._resp


def test_login_returns_access_token():
    client = _FakeClient(_Resp(200, {"access_token": "jwt-xyz", "user": {"role": "admin"}}))
    token = login(client, "admin", "pw")
    assert token == "jwt-xyz"
    assert client.calls == [("/api/auth/login", {"username": "admin", "password": "pw"})]


def test_login_raises_login_error_on_401():
    client = _FakeClient(_Resp(401, {"detail": "Invalid credentials"}))
    with pytest.raises(LoginError):
        login(client, "admin", "wrong")


def test_login_raises_two_factor_required_on_pending_token():
    client = _FakeClient(_Resp(200, {"pending_token": "pend-123"}))
    with pytest.raises(TwoFactorRequired):
        login(client, "admin", "pw")


def test_login_raises_login_error_on_unexpected_200_shape():
    client = _FakeClient(_Resp(200, {"something_else": 1}))
    with pytest.raises(LoginError):
        login(client, "admin", "pw")
