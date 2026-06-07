"""Monitoring API wrappers: current CPU / memory / network samples.

Each returns the parsed dict, or None on any failure (incl. HTTP 503 which
the backend returns when no sample has been collected yet). Callers render
a placeholder when None.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...


def _current(client: _Client, path: str) -> dict | None:
    try:
        resp = client.get(path)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def current_cpu(client: _Client) -> dict | None:
    """GET /api/monitoring/cpu/current -> dict | None."""
    return _current(client, "/api/monitoring/cpu/current")


def current_memory(client: _Client) -> dict | None:
    """GET /api/monitoring/memory/current -> dict | None."""
    return _current(client, "/api/monitoring/memory/current")


def current_network(client: _Client) -> dict | None:
    """GET /api/monitoring/network/current -> dict | None."""
    return _current(client, "/api/monitoring/network/current")
