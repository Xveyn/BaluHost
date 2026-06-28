"""Phase 4: toggling / details / list for external plugins use the manifest path (no exec)."""
import asyncio
import types

from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from app.api.routes import plugins as plugins_route
from app.core.rate_limiter import user_limiter
from app.plugins.manager import DiscoveredPlugin, PluginManager


def _make_mock_request(method: str = "POST", path: str = "/api/plugins/weather/toggle") -> StarletteRequest:
    """Return a minimal starlette Request that satisfies slowapi's isinstance check."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 8080),
    }
    return StarletteRequest(scope)


def _make_mock_response() -> StarletteResponse:
    """Return a minimal starlette Response that satisfies slowapi's header-injection check."""
    return StarletteResponse()


def test_toggle_enable_external_uses_manifest(tmp_path, db_session, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        api_scopes = ["storage"]
        version = "2.0.0"
        display_name = "Weather"
        required_permissions = []

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    enabled = {}

    async def fake_enable(name, perms, db, start_background_tasks=True, granted_api_scopes=None):
        enabled["scopes"] = granted_api_scopes
        return True

    monkeypatch.setattr(mgr, "enable_plugin", fake_enable)

    body = plugins_route.PluginToggleRequest(enabled=True, grant_permissions=[], grant_api_scopes=["storage"])
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.toggle_plugin(
            request=_make_mock_request(), response=_make_mock_response(), name="weather", body=body,
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_enabled is True
    assert enabled["scopes"] == ["storage"]


def test_toggle_disable_external_uses_manifest(tmp_path, db_session, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        api_scopes = ["storage"]
        version = "2.0.0"
        display_name = "Weather"
        required_permissions = []

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    disabled = {}

    async def fake_disable(name):
        disabled["called"] = True
        disabled["name"] = name
        return True

    monkeypatch.setattr(mgr, "disable_plugin", fake_disable)

    body = plugins_route.PluginToggleRequest(enabled=False, grant_permissions=[])
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.toggle_plugin(
            request=_make_mock_request(), response=_make_mock_response(), name="weather", body=body,
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_enabled is False
    assert disabled.get("called") is True
    assert disabled.get("name") == "weather"


def test_get_plugin_details_external_uses_manifest_no_exec(tmp_path, db_session, monkeypatch):
    """get_plugin_details for external+manifest plugin returns manifest data, never calls load_plugin."""
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        name = "weather"
        version = "2.0.0"
        display_name = "Weather Plugin"
        description = "Shows current weather"
        author = "Tester"
        category = "tools"
        homepage = None
        min_baluhost_version = None
        plugin_dependencies = []
        required_permissions = []
        api_scopes = ["storage"]
        ui = None

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    # Verify load_plugin is never invoked (exec-guard)
    def _no_exec(name):
        raise AssertionError("load_plugin must NOT be called for external+manifest plugins")

    monkeypatch.setattr(mgr, "load_plugin", _no_exec)

    # No DB record
    monkeypatch.setattr(plugins_route.plugin_service, "get_installed_plugin", lambda db, name: None)

    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    result = asyncio.run(
        plugins_route.get_plugin_details(
            request=_make_mock_request("GET", "/api/plugins/weather"),
            response=_make_mock_response(),
            name="weather",
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert result.name == "weather"
    assert result.version == "2.0.0"
    assert result.display_name == "Weather Plugin"
    assert result.is_enabled is False
    assert result.is_installed is False
    assert result.has_background_tasks is False
    assert result.has_dashboard_panel is False
    assert result.has_ui is False  # manifest.ui is None
    assert result.nav_items == []
    assert result.config == {}


def test_get_scope_catalog_endpoint_returns_six_entries():
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.get_scope_catalog(
            request=_make_mock_request(), response=_make_mock_response(), current_user=user,
        )
    )
    assert len(resp.scopes) == 6
    keys = {s.key for s in resp.scopes}
    assert "read:system-info" in keys
    assert "core.notify" in keys
    for s in resp.scopes:
        assert s.tier in ("frontend", "backend")
        assert s.dangerous is False


def test_toggle_enable_external_filters_grant_api_scopes_to_catalog(tmp_path, db_session, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        api_scopes = ["storage", "core.notify"]
        version = "2.0.0"
        display_name = "Weather"
        required_permissions = []

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    captured = {}

    async def fake_enable(name, perms, db, start_background_tasks=True, granted_api_scopes=None):
        captured["scopes"] = granted_api_scopes
        return True

    monkeypatch.setattr(mgr, "enable_plugin", fake_enable)

    persisted = {}
    real_enable = plugins_route.plugin_service.enable_plugin

    def spy_enable(db, **kwargs):
        persisted["api_scopes"] = kwargs.get("api_scopes")
        return real_enable(db, **kwargs)

    monkeypatch.setattr(plugins_route.plugin_service, "enable_plugin", spy_enable)

    # "network:evil" is NOT in the catalog -> must be dropped.
    body = plugins_route.PluginToggleRequest(
        enabled=True, grant_permissions=[],
        grant_api_scopes=["storage", "core.notify", "network:evil"],
    )
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.toggle_plugin(
            request=_make_mock_request(), response=_make_mock_response(), name="weather", body=body,
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_enabled is True
    assert sorted(captured["scopes"]) == ["core.notify", "storage"]
    assert sorted(persisted["api_scopes"]) == ["core.notify", "storage"]


def test_get_plugin_details_external_surfaces_requested_scopes_and_flag(tmp_path, db_session):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        manifest_version = 1
        name = "weather"
        version = "2.0.0"
        display_name = "Weather"
        description = "d"
        author = "a"
        category = "general"
        homepage = None
        min_baluhost_version = None
        plugin_dependencies = []
        required_permissions = []
        api_scopes = ["storage", "core.notify"]
        ui = None

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.get_plugin_details(
            request=_make_mock_request(), response=_make_mock_response(),
            name="weather", db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_external is True
    assert sorted(resp.requested_api_scopes) == ["core.notify", "storage"]


def test_ui_manifest_enrichment_uses_discovered_manifest_for_abi(monkeypatch):
    """min_runtime_abi must come from the plugin's OWN discovered manifest, not from
    load_manifest(plugins_dir / name) — that path is wrong for external plugins."""
    from app.api.routes import plugins as plugins_route

    class _Mgr:
        def get_ui_manifest(self):
            return {"plugins": [{
                "name": "weather", "display_name": "Weather",
                "nav_items": [], "bundle_path": "bundle.js",
                "styles_path": None, "dashboard_widgets": [], "translations": None,
            }]}

        def get_discovered(self, name):
            return types.SimpleNamespace(
                manifest=types.SimpleNamespace(min_runtime_abi=2)
            )

    def fake_get_installed(db, name):
        return types.SimpleNamespace(granted_api_scopes=["storage"])

    monkeypatch.setattr(plugins_route.plugin_service, "get_installed_plugin", fake_get_installed)

    # Old code path resolved via load_manifest(plugins_dir / name); guard it.
    def boom(_path):
        raise AssertionError("must not resolve manifest via plugins_dir")

    monkeypatch.setattr(plugins_route, "load_manifest", boom)

    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    result = asyncio.run(
        plugins_route.get_ui_manifest(
            request=_make_mock_request(), response=_make_mock_response(),
            db=object(), current_user=user, plugin_manager=_Mgr(),
        )
    )
    item = next(p for p in result.plugins if p.name == "weather")
    assert item.min_runtime_abi == 2
    assert item.granted_api_scopes == ["storage"]
