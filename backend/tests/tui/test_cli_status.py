"""Tests for the ported `status` CLI render function."""
from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from baluhost_tui.commands.status import show_status


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.responses: dict[str, _Resp] = {}

    def get(self, path: str, **_: Any) -> _Resp:
        return self.responses.get(path, _Resp(200, {}))


def _capture():
    return Console(file=io.StringIO(), width=120)


def test_show_status_renders_channel_users_storage():
    c = _FakeClient()
    c.responses["/api/system/channel-status"] = _Resp(200, {"channel": "local"})
    c.responses["/api/users/"] = _Resp(200, {"users": [], "total": 3, "active": 2, "inactive": 1, "admins": 1})
    c.responses["/api/system/storage"] = _Resp(200, {"total": 100, "used": 40, "use_percent": "40%"})
    con = _capture()
    show_status(c, console=con)
    out = con.file.getvalue()
    assert "local" in out
    assert "3" in out
    assert "40%" in out


def test_show_status_survives_failures():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    con = _capture()
    show_status(_Boom(), console=con)
    out = con.file.getvalue()
    assert "remote" in out
