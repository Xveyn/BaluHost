"""Tests for baluhost_tui.api.system wrappers."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.system import get_channel_status, restart_app, shutdown_app


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.responses: dict[tuple[str, str], _Resp] = {}

    def get(self, path: str, **_: Any) -> _Resp:
        self.requests.append(("GET", path))
        return self.responses[("GET", path)]

    def post(self, path: str, **_: Any) -> _Resp:
        self.requests.append(("POST", path))
        return self.responses.get(("POST", path), _Resp(200, {"message": "scheduled"}))


def test_get_channel_status_returns_channel_string():
    client = _FakeClient()
    client.responses[("GET", "/api/system/channel-status")] = _Resp(200, {"channel": "local"})
    assert get_channel_status(client) == "local"


def test_get_channel_status_defaults_to_remote_on_failure():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    assert get_channel_status(_Boom()) == "remote"


def test_restart_app_posts_correct_path_and_reports_ok():
    client = _FakeClient()
    ok, msg = restart_app(client)
    assert ok is True
    assert ("POST", "/api/system/restart") in client.requests
    assert "scheduled" in msg


def test_shutdown_app_reports_failure_on_4xx():
    client = _FakeClient()
    client.responses[("POST", "/api/system/shutdown")] = _Resp(403, {"detail": "nope"})
    ok, msg = shutdown_app(client)
    assert ok is False
    assert "403" in msg or "nope" in msg.lower()
