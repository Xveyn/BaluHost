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


class _WResp:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


class _WClient:
    """Records write calls and returns a queued response per (method, path)."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.responses: dict[tuple[str, str], _WResp] = {}

    def post(self, path: str, json: Any = None, **_: Any) -> _WResp:
        self.calls.append(("POST", path, json))
        return self.responses.get(("POST", path), _WResp(201, {"id": 9}))

    def put(self, path: str, json: Any = None, **_: Any) -> _WResp:
        self.calls.append(("PUT", path, json))
        return self.responses.get(("PUT", path), _WResp(200, {"id": 9}))

    def delete(self, path: str, **_: Any) -> _WResp:
        self.calls.append(("DELETE", path, None))
        return self.responses.get(("DELETE", path), _WResp(204))


def test_create_user_posts_and_reports_ok():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    ok, msg = create_user(c, username="bob", password="Secret123", email="b@x.io", role="user")
    assert ok is True
    assert c.calls == [("POST", "/api/users/", {"username": "bob", "password": "Secret123", "role": "user", "email": "b@x.io"})]
    assert "bob" in msg


def test_create_user_omits_empty_email():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    create_user(c, username="bob", password="Secret123", email=None)
    _, _, body = c.calls[0]
    assert "email" not in body
    assert body["role"] == "user"


def test_create_user_reports_failure_with_detail():
    from baluhost_tui.api.users import create_user
    c = _WClient()
    c.responses[("POST", "/api/users/")] = _WResp(409, {"detail": "username exists"})
    ok, msg = create_user(c, username="bob", password="Secret123")
    assert ok is False
    assert "exists" in msg.lower() or "409" in msg


def test_update_user_sends_only_provided_fields():
    from baluhost_tui.api.users import update_user
    c = _WClient()
    ok, msg = update_user(c, 5, email="new@x.io", role="admin", is_active=False)
    assert ok is True
    assert c.calls == [("PUT", "/api/users/5", {"email": "new@x.io", "role": "admin", "is_active": False})]


def test_update_user_omits_none_fields():
    from baluhost_tui.api.users import update_user
    c = _WClient()
    update_user(c, 5, role="admin")
    _, _, body = c.calls[0]
    assert body == {"role": "admin"}


def test_set_password_puts_password_only():
    from baluhost_tui.api.users import set_password
    c = _WClient()
    ok, msg = set_password(c, 7, "NewPass123")
    assert ok is True
    assert c.calls == [("PUT", "/api/users/7", {"password": "NewPass123"})]


def test_delete_user_deletes_and_reports_ok():
    from baluhost_tui.api.users import delete_user
    c = _WClient()
    ok, msg = delete_user(c, 3)
    assert ok is True
    assert c.calls == [("DELETE", "/api/users/3", None)]


def test_delete_user_reports_failure():
    from baluhost_tui.api.users import delete_user
    c = _WClient()
    c.responses[("DELETE", "/api/users/3")] = _WResp(403, {"detail": "cannot delete last admin"})
    ok, msg = delete_user(c, 3)
    assert ok is False
    assert "admin" in msg.lower() or "403" in msg


def test_write_ops_wrap_transport_errors():
    from baluhost_tui.api.users import create_user, update_user, delete_user, set_password

    class _Boom:
        def post(self, *_: Any, **__: Any): raise RuntimeError("offline")
        def put(self, *_: Any, **__: Any): raise RuntimeError("offline")
        def delete(self, *_: Any, **__: Any): raise RuntimeError("offline")

    assert create_user(_Boom(), "a", "Secret123")[0] is False
    assert update_user(_Boom(), 1, role="user")[0] is False
    assert set_password(_Boom(), 1, "Secret123")[0] is False
    assert delete_user(_Boom(), 1)[0] is False
