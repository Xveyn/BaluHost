"""Tests for ServiceHealthScreen API helpers."""
from __future__ import annotations

from typing import Any

import pytest


class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.responses: dict[tuple[str, str], _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("GET", path))
        return self.responses[("GET", path)]

    def post(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("POST", path))
        return self.responses.get(("POST", path), _FakeResp(200, {"success": True, "current_state": "running"}))


def test_fetch_services_returns_list():
    from baluhost_tui.screens.services import fetch_services

    client = _FakeClient()
    client.responses[("GET", "/api/admin/services")] = _FakeResp(200, [
        {"name": "telemetry", "state": "running", "uptime_seconds": 123},
        {"name": "disk_monitor", "state": "stopped", "uptime_seconds": None},
    ])

    services = fetch_services(client)

    assert isinstance(services, list)
    assert len(services) == 2
    assert services[0]["name"] == "telemetry"


def test_fetch_services_returns_empty_on_failure():
    from baluhost_tui.screens.services import fetch_services

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("offline")

    assert fetch_services(_Boom()) == []


def test_restart_service_posts_correct_path():
    from baluhost_tui.screens.services import restart_service

    client = _FakeClient()
    ok, msg = restart_service(client, "telemetry")

    assert ok is True
    assert ("POST", "/api/admin/services/telemetry/restart") in client.requests


def test_restart_service_returns_failure_on_4xx():
    from baluhost_tui.screens.services import restart_service

    client = _FakeClient()
    client.responses[("POST", "/api/admin/services/foo/restart")] = _FakeResp(404, {"detail": "not found"})

    ok, msg = restart_service(client, "foo")
    assert ok is False
    assert "404" in msg or "not found" in msg.lower()
