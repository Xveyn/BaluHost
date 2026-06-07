"""Tests for baluhost_tui.api.logging."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.logging import query_audit, filter_logs


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict | None = None, **_: Any) -> _Resp:
        self.calls.append((path, params or {}))
        return self._resp


def test_query_audit_returns_logs_list():
    c = _FakeClient(_Resp(200, {"logs": [{"id": 1, "action": "login"}], "total": 1}))
    logs = query_audit(c, limit=50)
    assert logs == [{"id": 1, "action": "login"}]
    path, params = c.calls[0]
    assert path == "/api/logging/audit"
    assert params["page_size"] == 50


def test_query_audit_passes_user_and_action_filters():
    c = _FakeClient(_Resp(200, {"logs": []}))
    query_audit(c, user="admin", action="login", days=30)
    _, params = c.calls[0]
    assert params["user"] == "admin"
    assert params["action"] == "login"
    assert params["days"] == 30


def test_query_audit_omits_empty_filters():
    c = _FakeClient(_Resp(200, {"logs": []}))
    query_audit(c, user="", action=None)
    _, params = c.calls[0]
    assert "user" not in params
    assert "action" not in params


def test_query_audit_returns_empty_on_failure():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    assert query_audit(_Boom()) == []


def test_query_audit_caps_page_size_at_100():
    c = _FakeClient(_Resp(200, {"logs": []}))
    query_audit(c, limit=500)
    _, params = c.calls[0]
    assert params["page_size"] == 100


def test_filter_logs_matches_action_resource_user():
    logs = [
        {"action": "login", "resource": "auth", "user": "admin"},
        {"action": "delete", "resource": "raid", "user": "bob"},
    ]
    assert filter_logs(logs, "raid") == [logs[1]]
    assert filter_logs(logs, "admin") == [logs[0]]
    assert filter_logs(logs, "") == logs
    assert filter_logs(logs, "LOGIN") == [logs[0]]
