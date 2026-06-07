"""Tests for baluhost_tui.api.users.list_users."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.users import list_users


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[str] = []

    def get(self, path: str, **_: Any) -> _Resp:
        self.calls.append(path)
        return self._resp


def test_list_users_returns_full_dict():
    c = _FakeClient(_Resp(200, {
        "users": [{"id": 1, "username": "admin", "role": "admin", "is_active": True}],
        "total": 1, "active": 1, "inactive": 0, "admins": 1,
    }))
    data = list_users(c)
    assert data["total"] == 1
    assert data["users"][0]["username"] == "admin"
    assert c.calls == ["/api/users/"]


def test_list_users_returns_empty_skeleton_on_failure():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    data = list_users(_Boom())
    assert data["users"] == []
    assert data["total"] == 0


def test_list_users_returns_empty_skeleton_on_non_200():
    c = _FakeClient(_Resp(403, {"detail": "nope"}))
    data = list_users(c)
    assert data["users"] == []
    assert data["total"] == 0
