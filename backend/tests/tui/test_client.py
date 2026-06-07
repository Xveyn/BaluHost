"""Tests for the TUI BackendClient and transport resolution."""
from __future__ import annotations

from baluhost_tui.client import resolve_transport, DEFAULT_SOCKET, DEFAULT_SERVER


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
