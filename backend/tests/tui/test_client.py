"""Tests for the TUI BackendClient and transport resolution."""
from __future__ import annotations

import httpx

from baluhost_tui.client import (
    BackendClient,
    DEFAULT_SERVER,
    DEFAULT_SOCKET,
    resolve_transport,
)


def test_explicit_server_wins_over_socket():
    mode, target = resolve_transport(
        socket_path="/run/baluhost/local.sock",
        server="http://127.0.0.1:3001",
        exists=lambda p: True,
    )
    assert mode == "tcp"
    assert target == "http://127.0.0.1:3001"


def test_explicit_socket_when_no_server():
    mode, target = resolve_transport(
        socket_path="/tmp/custom.sock", server=None, exists=lambda p: True
    )
    assert mode == "uds"
    assert target == "/tmp/custom.sock"


def test_default_socket_used_when_it_exists():
    mode, target = resolve_transport(
        socket_path=None, server=None, exists=lambda p: p == DEFAULT_SOCKET
    )
    assert mode == "uds"
    assert target == DEFAULT_SOCKET


def test_falls_back_to_tcp_default_when_no_socket():
    mode, target = resolve_transport(
        socket_path=None, server=None, exists=lambda p: False
    )
    assert mode == "tcp"
    assert target == DEFAULT_SERVER


def test_explicit_socket_path_used_even_if_missing():
    """An explicitly requested socket is honored regardless of existence —
    surfacing a connection error later is clearer than silently using TCP."""
    mode, target = resolve_transport(
        socket_path="/tmp/missing.sock", server=None, exists=lambda p: False
    )
    assert mode == "uds"
    assert target == "/tmp/missing.sock"


def _mock_backend_client(handler) -> BackendClient:
    """Build a BackendClient backed by an httpx.MockTransport for offline tests."""
    transport = httpx.MockTransport(handler)
    raw = httpx.Client(transport=transport, base_url="http://localhost")
    return BackendClient(_client=raw)


def test_get_passes_through_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"ok": True})

    client = _mock_backend_client(handler)
    resp = client.get("/api/admin/services")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert seen == {"method": "GET", "path": "/api/admin/services"}


def test_set_token_adds_authorization_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    client = _mock_backend_client(handler)
    client.set_token("jwt-abc")
    client.get("/api/system/channel-status")

    assert seen["auth"] == "Bearer jwt-abc"


def test_post_sends_json_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content"] = request.content
        return httpx.Response(200, json={"created": True})

    client = _mock_backend_client(handler)
    resp = client.post("/api/users/bulk-delete", json=[1, 2, 3])

    assert resp.json() == {"created": True}
    assert seen["method"] == "POST"
    assert b"1" in seen["content"]


def test_clear_token_removes_authorization_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    client = _mock_backend_client(handler)
    client.set_token("jwt-abc")
    client.clear_token()
    client.get("/api/system/channel-status")

    assert seen["auth"] is None


def test_put_passes_through_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={})

    client = _mock_backend_client(handler)
    client.put("/api/example/1")

    assert seen == {"method": "PUT", "path": "/api/example/1"}


def test_delete_passes_through_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={})

    client = _mock_backend_client(handler)
    client.delete("/api/example/1")

    assert seen == {"method": "DELETE", "path": "/api/example/1"}
