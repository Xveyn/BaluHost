"""Tests for baluhost_tui.api.monitoring wrappers."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.monitoring import current_cpu, current_memory, current_network


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


def test_current_cpu_returns_dict():
    c = _FakeClient()
    c.responses["/api/monitoring/cpu/current"] = _Resp(200, {"usage_percent": 23.4})
    assert current_cpu(c) == {"usage_percent": 23.4}
    assert c.requests == ["/api/monitoring/cpu/current"]


def test_current_memory_returns_dict():
    c = _FakeClient()
    c.responses["/api/monitoring/memory/current"] = _Resp(200, {"percent": 50.0, "used_bytes": 1, "total_bytes": 2})
    assert current_memory(c)["percent"] == 50.0


def test_current_network_returns_dict():
    c = _FakeClient()
    c.responses["/api/monitoring/network/current"] = _Resp(200, {"download_mbps": 12.5, "upload_mbps": 3.2})
    assert current_network(c)["download_mbps"] == 12.5


def test_current_cpu_returns_none_on_503():
    c = _FakeClient()
    c.responses["/api/monitoring/cpu/current"] = _Resp(503, {"detail": "no data"})
    assert current_cpu(c) is None


def test_current_cpu_returns_none_on_transport_error():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    assert current_cpu(_Boom()) is None
