"""Phase 4: catch-all proxy — auth gating, header allowlist, error scrubbing."""
import asyncio
import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.plugins.sandbox import proxy
from app.plugins.sandbox.supervisor import SupervisorError, SupervisorTimeout


def _make_request(method="GET", headers=None, body=b"", query=b""):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "method": method, "path": "/api/plugins/weather/status",
        "query_string": query, "headers": hdrs,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class _Sup:
    def __init__(self, **kw):
        self.kw = None
        self._resp = kw.get("resp", {"status": 200, "headers": {"content-type": "application/json"}, "body": {"ok": True}})
        self._raise = kw.get("raise_exc")

    async def dispatch(self, method, path, body, context, *, query=None, headers=None, timeout=30.0):
        if self._raise:
            raise self._raise
        self.kw = dict(method=method, path=path, body=body, context=context, query=query, headers=headers)
        return self._resp


class _Mgr:
    def __init__(self, sup):
        self._sup = sup

    def get_sandbox(self, name):
        return self._sup


_USER = types.SimpleNamespace(id=7, username="alice", role="user")


def test_proxy_forwards_without_token_headers():
    sup = _Sup()
    req = _make_request(headers={"authorization": "Bearer x", "cookie": "s=1", "content-type": "application/json"}, query=b"a=1")
    resp = asyncio.run(proxy.proxy_request("weather", "status", req, _USER, _Mgr(sup)))
    assert resp.status_code == 200
    assert "authorization" not in sup.kw["headers"]
    assert "cookie" not in sup.kw["headers"]
    assert sup.kw["headers"] == {"content-type": "application/json"}
    assert sup.kw["query"] == {"a": "1"}
    assert sup.kw["context"] == {"user_id": 7, "username": "alice", "role": "user"}


def test_proxy_unknown_plugin_404():
    class _Empty:
        def get_sandbox(self, name):
            return None

    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("nope", "x", req, _USER, _Empty()))
    assert ei.value.status_code == 404


def test_proxy_body_too_large_413():
    req = _make_request(method="POST", body=b"x" * (proxy.REQUEST_BODY_MAX + 1))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup())))
    assert ei.value.status_code == 413


def test_proxy_timeout_504():
    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup(raise_exc=SupervisorTimeout("t")))))
    assert ei.value.status_code == 504


def test_proxy_crash_scrubbed_502():
    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup(raise_exc=SupervisorError("boom")))))
    assert ei.value.status_code == 502
    assert "boom" not in str(ei.value.detail)


def test_proxy_content_length_precheck_413():
    """Verify Content-Length precheck rejects before buffering."""
    headers = {"content-length": str(proxy.REQUEST_BODY_MAX + 1)}
    req = _make_request(method="POST", headers=headers, body=b"")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup())))
    assert ei.value.status_code == 413


def test_proxy_bare_exception_scrubbed_502():
    """Verify bare Exception (not SupervisorError) is scrubbed without leaking details."""
    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup(raise_exc=RuntimeError("internal secret detail")))))
    assert ei.value.status_code == 502
    assert "secret" not in str(ei.value.detail).lower()
