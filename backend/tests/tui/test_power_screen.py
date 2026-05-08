"""Tests for PowerActionsScreen API helpers (logic only, no Textual loop)."""
from __future__ import annotations

from typing import Any

import pytest


class _FakeResp:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.responses: dict[tuple[str, str], _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("GET", path, None))
        return self.responses[("GET", path)]

    def post(self, path: str, json: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
        self.requests.append(("POST", path, json))
        return self.responses.get(("POST", path), _FakeResp(200, {"success": True}))


def test_fetch_status_returns_normalized_dict():
    from baluhost_tui.screens.power import fetch_status

    client = _FakeClient()
    client.responses[("GET", "/api/sleep/status")] = _FakeResp(200, {
        "state": "awake",
        "since": "2026-05-08T10:00:00Z",
        "always_awake_enabled": False,
    })

    status = fetch_status(client)

    assert status["state"] == "awake"
    assert client.requests == [("GET", "/api/sleep/status", None)]


def test_fetch_status_returns_none_on_failure():
    from baluhost_tui.screens.power import fetch_status

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("offline")

    assert fetch_status(_Boom()) is None


def test_perform_action_sends_correct_endpoint():
    from baluhost_tui.screens.power import perform_action

    client = _FakeClient()
    ok, msg = perform_action(client, "soft")
    assert ok is True
    assert client.requests == [("POST", "/api/sleep/soft", {})]

    ok, msg = perform_action(client, "wake")
    assert ok is True
    assert client.requests[-1] == ("POST", "/api/sleep/wake", {})

    ok, msg = perform_action(client, "suspend")
    assert ok is True
    assert client.requests[-1] == ("POST", "/api/sleep/suspend", {})

    ok, msg = perform_action(client, "wol")
    assert ok is True
    assert client.requests[-1] == ("POST", "/api/sleep/wol", {})


def test_perform_action_rejects_unknown():
    from baluhost_tui.screens.power import perform_action

    ok, msg = perform_action(_FakeClient(), "explode")
    assert ok is False
    assert "unknown" in msg.lower()


def test_perform_action_reports_http_error():
    from baluhost_tui.screens.power import perform_action

    client = _FakeClient()
    client.responses[("POST", "/api/sleep/soft")] = _FakeResp(409, {"detail": "already sleeping"})

    ok, msg = perform_action(client, "soft")
    assert ok is False
    assert "409" in msg or "already" in msg.lower()
