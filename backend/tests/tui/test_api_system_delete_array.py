"""Tests for delete_array() in baluhost_tui.api.system."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.system import delete_array


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.responses: dict[str, _Resp] = {}

    def post(self, path: str, json: Any = None, **_: Any) -> _Resp:
        self.calls.append((path, json))
        return self.responses.get(path, _Resp(200, {"message": "Array deleted"}))


def test_delete_array_posts_correct_body_and_reports_ok():
    c = _Client()
    ok, msg = delete_array(c, "md0")
    assert ok is True
    assert c.calls == [("/api/system/raid/delete-array", {"array": "md0", "force": False})]
    assert "deleted" in msg.lower()


def test_delete_array_passes_force():
    c = _Client()
    delete_array(c, "md0", force=True)
    _, body = c.calls[0]
    assert body == {"array": "md0", "force": True}


def test_delete_array_reports_failure_with_detail():
    c = _Client()
    c.responses["/api/system/raid/delete-array"] = _Resp(409, {"detail": "array busy"})
    ok, msg = delete_array(c, "md0")
    assert ok is False
    assert "busy" in msg.lower() or "409" in msg


def test_delete_array_handles_local_channel_dict_detail():
    c = _Client()
    c.responses["/api/system/raid/delete-array"] = _Resp(
        403, {"detail": {"error": "local_channel_required", "message": "Companion app only"}}
    )
    ok, msg = delete_array(c, "md0")
    assert ok is False
    assert "companion" in msg.lower() or "local_channel" in msg.lower()


def test_delete_array_wraps_transport_error():
    class _Boom:
        def post(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    ok, msg = delete_array(_Boom(), "md0")
    assert ok is False
    assert "failed" in msg.lower()
