"""Tests for the PluginGateMiddleware."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.plugin_gate import (
    PluginGateMiddleware,
    _is_management_route,
    invalidate_plugin_cache,
)
from app.services import plugin_enablement
from app.services.plugin_enablement import CACHE_TTL_SECONDS


def _grant(permissions=None) -> dict:
    """Build a ``_fetch()``-shaped cache entry for one plugin.

    The cache also carries ``granted_api_scopes`` (Task 3); the gate only
    ever consumes ``granted_permissions`` via ``enabled_plugins()``, so tests
    here only need to populate that half.
    """
    return {"granted_permissions": list(permissions or []), "granted_api_scopes": []}


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
    plugin_enablement.invalidate()
    yield
    plugin_enablement.invalidate()


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


@patch("app.services.plugin_enablement._fetch")
def test_plugin_list_not_gated(mock_fetch):
    """GET /api/plugins (list) should never be gated."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins")
    assert resp.status_code == 200
    mock_fetch.assert_not_called()


@patch("app.services.plugin_enablement._fetch")
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
@patch("app.services.plugin_enablement._fetch")
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
@patch(
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant(["files:read"])},
)
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


@patch("app.services.plugin_enablement._fetch", return_value={})
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
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant(["files:read"])},
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
@patch(
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant()},
)
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
@patch(
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant()},
)
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
@patch(
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant()},
)
def test_cache_expires_after_ttl(mock_fetch, mock_get_instance, monkeypatch):
    """After TTL seconds the cached entry is considered stale.

    The new cache is global (not per-name): advance the shared clock past
    the TTL, the same way test_plugin_enablement.py's own TTL test does,
    rather than reaching into a per-name timestamp that no longer exists.
    """
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    clock = {"now": 1000.0}
    monkeypatch.setattr(plugin_enablement, "_monotonic", lambda: clock["now"])

    client = TestClient(_make_app())

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 1

    clock["now"] += CACHE_TTL_SECONDS + 0.1

    client.get("/api/plugins/my_plugin/data")
    assert mock_fetch.call_count == 2


# ---------------------------------------------------------------------------
# Test: unknown plugin (not in DB at all) -> 403 (treated as disabled)
# ---------------------------------------------------------------------------


@patch("app.services.plugin_enablement._fetch", return_value={})
def test_unknown_plugin_returns_403(mock_fetch):
    """A plugin name that doesn't exist in the DB -> disabled -> 403."""
    client = TestClient(_make_app())
    resp = client.get("/api/plugins/nonexistent/data")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: DB error returns 500
# ---------------------------------------------------------------------------


@patch(
    "app.services.plugin_enablement._fetch",
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
@patch(
    "app.services.plugin_enablement._fetch",
    return_value={"my_plugin": _grant()},
)
def test_no_required_permissions_passes(mock_fetch, mock_get_instance):
    """If a plugin has no required permissions, just being enabled is enough."""
    mock_manager = MagicMock()
    mock_manager.get_required_permissions.return_value = []
    mock_get_instance.return_value = mock_manager

    client = TestClient(_make_app())
    resp = client.get("/api/plugins/my_plugin/data")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test: _storage carve-out is exact-namespace-bounded (regression for #Fix1)
# ---------------------------------------------------------------------------


def test_storage_list_route_is_management():
    """``/_storage`` (exact, the list route) must be a management route."""
    assert _is_management_route("/_storage") is True


def test_storage_key_subpath_is_management():
    """``/_storage/{key}`` (slash-bounded sub-path) must be a management route."""
    assert _is_management_route("/_storage/units") is True


def test_storage_backdoor_is_not_management():
    """``/_storage_backdoor`` must NOT be classified as a management route."""
    assert _is_management_route("/_storage_backdoor") is False


def test_storagex_is_not_management():
    """``/_storagex`` must NOT be classified as a management route."""
    assert _is_management_route("/_storagex") is False
