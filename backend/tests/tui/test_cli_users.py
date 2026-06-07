"""Tests for the ported `users` CLI render function."""
from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from baluhost_tui.commands.users import render_users


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    def get(self, path: str, **_: Any) -> _Resp:
        assert path == "/api/users/"
        return self._resp


def _capture():
    return Console(file=io.StringIO(), width=120)


def test_render_users_lists_rows():
    client = _FakeClient(_Resp(200, {
        "users": [{"id": 1, "username": "admin", "email": "a@x.io", "role": "admin", "is_active": True}],
        "total": 1, "active": 1, "inactive": 0, "admins": 1,
    }))
    con = _capture()
    render_users(client, console=con)
    out = con.file.getvalue()
    assert "admin" in out
    assert "Total: 1" in out


def test_render_users_handles_empty():
    client = _FakeClient(_Resp(403, {"detail": "nope"}))
    con = _capture()
    render_users(client, console=con)
    out = con.file.getvalue()
    assert "Total: 0" in out
