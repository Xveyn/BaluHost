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
    client.responses["/api/system/smart/status"] = _FakeResp(200, {
        "devices": [
            {"name": "/dev/sda", "status": "PASSED", "temperature": 38, "attributes": []},
            {"name": "/dev/sdb", "status": "FAILED", "temperature": 55, "attributes": []},
        ]
    })

    disks = fetch_smart(client)

    assert len(disks) == 2
    assert disks[0]["name"] == "/dev/sda"
    assert disks[1]["status"] == "FAILED"


def test_fetch_smart_handles_top_level_list():
    """Some backends return a bare list — accept both shapes."""
    from baluhost_tui.screens.smart import fetch_smart

    client = _FakeClient()
    client.responses["/api/system/smart/status"] = _FakeResp(200, [
        {"name": "/dev/sda", "status": "PASSED"},
    ])

    disks = fetch_smart(client)
    assert len(disks) == 1


def test_fetch_smart_returns_empty_on_failure():
    from baluhost_tui.screens.smart import fetch_smart

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("nope")

    assert fetch_smart(_Boom()) == []


def test_attribute_raw_finds_power_on_hours():
    from baluhost_tui.screens.smart import _attribute_raw

    device = {
        "name": "/dev/sda",
        "attributes": [
            {"id": 9, "name": "Power_On_Hours", "raw": "12345"},
            {"id": 5, "name": "Reallocated_Sector_Ct", "raw": "0"},
        ],
    }
    assert _attribute_raw(device, "power_on_hours") == "12345"
    assert _attribute_raw(device, "reallocated_sector") == "0"


def test_attribute_raw_returns_dash_when_missing():
    from baluhost_tui.screens.smart import _attribute_raw

    assert _attribute_raw({"attributes": []}, "anything") == "-"
    assert _attribute_raw({}, "anything") == "-"
