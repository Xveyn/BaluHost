"""Tests for SmartScreen API helper."""
from __future__ import annotations

from typing import Any


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
        self.responses: dict[str, _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        return self.responses[path]


def test_fetch_smart_returns_list_of_disks():
    from baluhost_tui.screens.smart import fetch_smart

    client = _FakeClient()
    client.responses["/api/system/smart"] = _FakeResp(200, {
        "disks": [
            {"device": "/dev/sda", "health": "PASSED", "temperature": 38, "power_on_hours": 12345},
            {"device": "/dev/sdb", "health": "FAILED", "temperature": 55, "power_on_hours": 30000},
        ]
    })

    disks = fetch_smart(client)

    assert len(disks) == 2
    assert disks[0]["device"] == "/dev/sda"
    assert disks[1]["health"] == "FAILED"


def test_fetch_smart_handles_top_level_list():
    """Some backends return a bare list — accept both shapes."""
    from baluhost_tui.screens.smart import fetch_smart

    client = _FakeClient()
    client.responses["/api/system/smart"] = _FakeResp(200, [
        {"device": "/dev/sda", "health": "PASSED"},
    ])

    disks = fetch_smart(client)
    assert len(disks) == 1


def test_fetch_smart_returns_empty_on_failure():
    from baluhost_tui.screens.smart import fetch_smart

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("nope")

    assert fetch_smart(_Boom()) == []
