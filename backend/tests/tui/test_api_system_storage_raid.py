"""Tests for storage() and raid_status() in baluhost_tui.api.system."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.system import storage, raid_status


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.responses: dict[str, _Resp] = {}

    def get(self, path: str, **_: Any) -> _Resp:
        self.requests.append(path)
        return self.responses[path]


def test_storage_returns_dict():
    c = _FakeClient()
    c.responses["/api/system/storage"] = _Resp(200, {"total": 100, "used": 40, "use_percent": "40%"})
    assert storage(c)["used"] == 40
    assert c.requests == ["/api/system/storage"]


def test_storage_returns_none_on_error():
    c = _FakeClient()
    c.responses["/api/system/storage"] = _Resp(500, {})
    assert storage(c) is None


def test_raid_status_returns_arrays_list():
    c = _FakeClient()
    c.responses["/api/system/raid/status"] = _Resp(200, {"arrays": [
        {"name": "md0", "level": "raid1", "status": "active", "devices": [{"name": "sda"}]},
    ]})
    arrays = raid_status(c)
    assert isinstance(arrays, list)
    assert arrays[0]["name"] == "md0"


def test_raid_status_returns_empty_on_failure():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    assert raid_status(_Boom()) == []


def test_raid_status_returns_empty_when_no_arrays_key():
    c = _FakeClient()
    c.responses["/api/system/raid/status"] = _Resp(200, {"speed_limits": {}})
    assert raid_status(c) == []
