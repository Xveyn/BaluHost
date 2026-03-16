"""Tests for the PluginGateMiddleware."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.plugin_gate import (
    CACHE_TTL_SECONDS,
    PluginGateMiddleware,
    _plugin_cache,
    invalidate_plugin_cache,
)


# ---------------------------------------------------------------------------
# Helpers: minimal FastAPI app with the middleware under test
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Create a tiny FastAPI app with PluginGateMiddleware and dummy routes."""
    app = FastAPI()
    app.add_middleware(PluginGateMiddleware)

    @app.get("/api/plugins")
    async def list_plugins():
        return {"plugins": []}

    @app.get("/api/plugins/permissions")
    async def list_permissions():
        return {"permissions": []}

    @app.get("/api/plugins/{name}")
    async def plugin_details(name: str):
        return {"name": name}

    @app.post("/api/plugins/{name}/toggle")
    async def toggle_plugin(name: str):
        return {"toggled": name}

    @app.get("/api/plugins/{name}/config")
    async def plugin_config(name: str):
        return {"config": {}}

    @app.get("/api/plugins/{name}/ui/{file_path:path}")
    async def plugin_ui(name: str, file_path: str):
        return {"asset": file_path}

    @app.delete("/api/plugins/{name}")
    async def uninstall_plugin(name: str):
        return {"deleted": name}

    # Simulates a plugin-provided route
    @app.get("/api/plugins/{name}/data")
    async def plugin_data(name: str):
        return {"data": "ok", "plugin": name}

    @app.get("/api/plugins/{name}/execute")
    async def plugin_execute(name: str):
        return {"executed": True}

    @app.get("/other")
    async def other():
        return {"other": True}

    return app


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure the module-level cache is empty before each test."""
    _plugin_cache.clear()
    yield
    _plugin_cache.clear()


# ---------------------------------------------------------------------------
# Test: non-plugin paths pass through
# ---------------------------------------------------------------------------


def test_non_plugin_path_passes_through():
    """Requests to non-plugin paths are not intercepted."""
    client = TestClient(_make_app())
    resp = client.get("/other")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test: plugin list / permissions endpoints are not gated
# ---------------------------------------------------------------------------


@patch("app.middleware.plugin_gate._fetch_plugin_status")
def test_plugin_list_not_gated(mock_fetch):
    """GET /api/plugins (list) should never be gated."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins")
    assert resp.status_code == 200
    mock_fetch.assert_not_called()


@patch("app.middleware.plugin_gate._fetch_plugin_status")
def test_permissions_endpoint_not_gated(mock_fetch):
    """GET /api/plugins/permissions should never be gated."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins/permissions")
    assert resp.status_code == 200
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Test: management routes are not gated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/plugins/my_plugin"),          # details
        ("DELETE", "/api/plugins/my_plugin"),        # uninstall
        ("POST", "/api/plugins/my_plugin/toggle"),   # toggle
        ("GET", "/api/plugins/my_plugin/config"),    # config
        ("GET", "/api/plugins/my_plugin/ui/bundle.js"),  # ui asset
    ],
)
@patch("app.middleware.plugin_gate._fetch_plugin_status")
def test_management_routes_not_gated(mock_fetch, method, path):
    """Management routes must pass through even if plugin is disabled."""
    client = TestClient(_make_app())
    resp = client.request(method, path)
    assert resp.status_code == 200
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Test: enabled plugin -> request passes through
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(True, ["files:read"]))
def test_enabled_plugin_passes(mock_fetch, mock_get_instance):
    """An enabled plugin with sufficient permissions -> 200."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = ["files:read"]
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/data")
    assert resp.status_code == 200
    assert resp.json()["data"] == "ok"


# ---------------------------------------------------------------------------
# Test: disabled plugin -> 403
# ---------------------------------------------------------------------------


@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(False, []))
def test_disabled_plugin_blocked(mock_fetch):
    """A disabled plugin -> 403."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/data")
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: enabled but missing permissions -> 403
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch(
    "app.middleware.plugin_gate._fetch_plugin_status",
    return_value=(True, ["files:read"]),
)
def test_missing_permissions_blocked(mock_fetch, mock_get_instance):
    """Plugin is enabled but granted permissions don't cover required -> 403."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = [
        "files:read",
        "system:execute",
    ]
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/execute")
    assert resp.status_code == 403
    assert "missing permissions" in resp.json()["detail"]
    assert "system:execute" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: cache hit — no repeated DB lookup
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(True, []))
def test_cache_hit_no_repeat_db_query(mock_fetch, mock_get_instance):
    """Second request within TTL should use cache, not call DB again."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())

    resp1 = client.get("/api/plugins/my_plugin/data")
    assert resp1.status_code == 200
    assert mock_fetch.call_count == 1

    resp2 = client.get("/api/plugins/my_plugin/data")
    assert resp2.status_code == 200
    # Still only 1 call — cache served the second request
    assert mock_fetch.call_count == 1


# ---------------------------------------------------------------------------
# Test: invalidate_plugin_cache forces fresh lookup
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(True, []))
def test_invalidate_cache_forces_db_query(mock_fetch, mock_get_instance):
    """After invalidate_plugin_cache(), the next request must hit the DB."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 1

    invalidate_plugin_cache("my_plugin")

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 2


# ---------------------------------------------------------------------------
# Test: cache expiry after TTL
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(True, []))
def test_cache_expires_after_ttl(mock_fetch, mock_get_instance):
    """After TTL seconds the cached entry is considered stale."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 1

    # Manually expire the cache entry
    name = "my_plugin"
    is_enabled, perms, _ts = _plugin_cache[name]
    _plugin_cache[name] = (is_enabled, perms, time.monotonic() - CACHE_TTL_SECONDS - 1)

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 2


# ---------------------------------------------------------------------------
# Test: unknown plugin (not in DB at all) -> 403 (treated as disabled)
# ---------------------------------------------------------------------------


@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(False, []))
def test_unknown_plugin_returns_403(mock_fetch):
    """A plugin name that doesn't exist in the DB -> disabled -> 403."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins/nonexistent/data")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: DB error returns 500
# ---------------------------------------------------------------------------


@patch(
    "app.middleware.plugin_gate._fetch_plugin_status",
    side_effect=Exception("DB connection failed"),
)
def test_db_error_returns_500(mock_fetch):
    """If the DB lookup raises an exception, return 500."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/data")
    assert resp.status_code == 500
    assert "Internal error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: plugin with no required permissions -> passes if enabled
# ---------------------------------------------------------------------------


@patch("app.plugins.manager.PluginManager.get_instance")
@patch("app.middleware.plugin_gate._fetch_plugin_status", return_value=(True, []))
def test_no_required_permissions_passes(mock_fetch, mock_get_instance):
    """If a plugin has no required permissions, just being enabled is enough."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/data")
    assert resp.status_code == 200
