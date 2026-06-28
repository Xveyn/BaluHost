"""Gap C: external sandboxed plugins surface their static UI in get_ui_manifest()."""
import types
from pathlib import Path

from app.plugins.manager import PluginManager, DiscoveredPlugin
from app.plugins.manifest import PluginManifestUI, ManifestNavItem


def _external_manifest(tmp_path: Path):
    return types.SimpleNamespace(
        name="weather",
        display_name="Weather",
        ui=PluginManifestUI(
            bundle="bundle.js",
            styles="styles.css",
            nav_items=[ManifestNavItem(path="weather", label="Weather", icon="cloud", order=50)],
            dashboard_widgets=["WeatherWidget"],
        ),
    )


def test_external_plugin_appears_in_ui_manifest(tmp_path):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()
    mgr._discovered = {
        "weather": DiscoveredPlugin(
            name="weather", path=pdir, source="external",
            manifest=_external_manifest(tmp_path),
        ),
    }
    # External enabled: present in _enabled + _sandboxes, NOT in _plugins.
    mgr._enabled.add("weather")
    mgr._sandboxes["weather"] = object()

    manifest = mgr.get_ui_manifest()
    entry = next(p for p in manifest["plugins"] if p["name"] == "weather")
    assert entry["bundle_path"] == "bundle.js"
    assert entry["styles_path"] == "styles.css"
    assert entry["dashboard_widgets"] == ["WeatherWidget"]
    assert entry["nav_items"][0]["path"] == "weather"
    assert entry["nav_items"][0]["label"] == "Weather"
    assert entry["translations"] is None


def test_external_plugin_without_ui_is_absent(tmp_path):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "noui"
    pdir.mkdir()
    mgr._discovered = {
        "noui": DiscoveredPlugin(
            name="noui", path=pdir, source="external",
            manifest=types.SimpleNamespace(name="noui", display_name="NoUI", ui=None),
        ),
    }
    mgr._enabled.add("noui")
    mgr._sandboxes["noui"] = object()

    manifest = mgr.get_ui_manifest()
    assert all(p["name"] != "noui" for p in manifest["plugins"])
