"""Does a plugin bring its own page? (#454)

Plugins that only contribute a topbar control, a status pill or a menu action
still need a UI manifest - otherwise the frontend treats them as disabled. That
put them into the sandbox host, which then loaded a bundle that does not exist.
``has_page`` reports whether the bundle the host would load is really there,
resolved exactly like the host.html bootstrap does.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.routes.plugins import get_plugin_manager
from app.main import app
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.manager import PluginManager


class _UiPlugin(PluginBase):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name, version="1.0.0", display_name=self._name,
            description="test", author="test",
        )

    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(enabled=True)


def _plugin_dir(root: Path, name: str, bundle: str | None) -> None:
    (root / name).mkdir()
    if bundle is not None:
        (root / name / "ui").mkdir()
        (root / name / "ui" / bundle).write_text("// bundle", encoding="utf-8")


def _manifest_with_bundle(bundle: str) -> MagicMock:
    manifest = MagicMock()
    manifest.ui.bundle = bundle
    return manifest


class TestHasUiPage:
    def test_plugin_without_ui_dir_has_no_page(self, tmp_path):
        _plugin_dir(tmp_path, "topbar_only", bundle=None)

        assert PluginManager(plugins_dir=tmp_path).has_ui_page("topbar_only") is False

    def test_default_bundle_present_is_a_page(self, tmp_path):
        _plugin_dir(tmp_path, "with_page", bundle="bundle.js")

        assert PluginManager(plugins_dir=tmp_path).has_ui_page("with_page") is True

    def test_bundle_named_in_plugin_json_is_used(self, tmp_path):
        _plugin_dir(tmp_path, "custom", bundle="app.js")
        mgr = PluginManager(plugins_dir=tmp_path)

        with patch("app.plugins.manager.load_manifest", return_value=_manifest_with_bundle("ui/app.js")):
            assert mgr.ui_bundle_name("custom") == "app.js"
            assert mgr.has_ui_page("custom") is True

    def test_bundle_named_in_plugin_json_but_missing_is_no_page(self, tmp_path):
        _plugin_dir(tmp_path, "custom", bundle="bundle.js")
        mgr = PluginManager(plugins_dir=tmp_path)

        with patch("app.plugins.manager.load_manifest", return_value=_manifest_with_bundle("ui/app.js")):
            assert mgr.has_ui_page("custom") is False

    def test_unreadable_plugin_json_falls_back_to_bundle_js(self, tmp_path):
        _plugin_dir(tmp_path, "broken", bundle="bundle.js")
        mgr = PluginManager(plugins_dir=tmp_path)

        with patch("app.plugins.manager.load_manifest", side_effect=ValueError("bad json")):
            assert mgr.ui_bundle_name("broken") == "bundle.js"
            assert mgr.has_ui_page("broken") is True


class TestUiManifestCarriesHasPage:
    def test_manifest_entries_report_has_page(self, tmp_path):
        _plugin_dir(tmp_path, "topbar_only", bundle=None)
        _plugin_dir(tmp_path, "with_page", bundle="bundle.js")
        mgr = PluginManager(plugins_dir=tmp_path)
        mgr._plugins = {"topbar_only": _UiPlugin("topbar_only"), "with_page": _UiPlugin("with_page")}
        mgr._enabled = {"topbar_only", "with_page"}

        entries = {e["name"]: e for e in mgr.get_ui_manifest()["plugins"]}

        assert entries["topbar_only"]["has_page"] is False
        assert entries["with_page"]["has_page"] is True

    def test_route_passes_has_page_through(self, client, admin_headers):
        manifest = {"plugins": [{"name": "topbar_only", "display_name": "T", "has_page": False}]}
        fake = MagicMock()
        fake.get_ui_manifest.return_value = manifest
        fake.get_discovered.return_value = None
        app.dependency_overrides[get_plugin_manager] = lambda: fake
        try:
            resp = client.get("/api/plugins/ui/manifest", headers=admin_headers)
        finally:
            app.dependency_overrides.pop(get_plugin_manager, None)

        assert resp.status_code == 200
        assert resp.json()["plugins"][0]["has_page"] is False
