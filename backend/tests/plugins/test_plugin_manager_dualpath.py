"""Phase 4: PluginManager external dual-path (no exec_module in host)."""
import asyncio

import pytest

from app.plugins.manager import DiscoveredPlugin, PluginLoadError, PluginManager


class _FakeSupervisor:
    def __init__(self, plugin_name, plugin_dir, capability_router=None):
        self.plugin_name = plugin_name
        self.started = False
        self.stopped = False
        self.capability_router = capability_router

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


@pytest.fixture
def manager(tmp_path, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    # Pretend an external plugin "weather" was discovered with a parsed manifest.
    plugin_dir = tmp_path / "weather"
    plugin_dir.mkdir()
    # Benign module — guard (not plugin code) must be what raises PluginLoadError.
    (plugin_dir / "__init__.py").write_text("# valid module, must never be exec'd in host\n")

    class _M:
        api_scopes = ["storage", "core.notify"]
        version = "1.0.0"
        display_name = "Weather"

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=plugin_dir, source="external", manifest=_M()),
    }
    mgr._supervisor_factory = _FakeSupervisor
    return mgr


def test_load_plugin_external_refuses_to_exec(manager):
    with pytest.raises(PluginLoadError):
        manager.load_plugin("weather")


def test_enable_external_spawns_supervisor_without_exec(manager):
    ok = asyncio.run(
        manager.enable_plugin("weather", [], db=None, granted_api_scopes=["storage", "core.notify"])
    )
    assert ok is True
    sup = manager.get_sandbox("weather")
    assert sup is not None and sup.started is True
    assert sup.capability_router is not None
    assert manager.is_enabled("weather") is True
    # The external plugin was never instantiated in-process.
    assert manager.get_plugin("weather") is None


def test_disable_external_stops_supervisor(manager):
    asyncio.run(manager.enable_plugin("weather", [], db=None, granted_api_scopes=["storage"]))
    sup = manager.get_sandbox("weather")
    asyncio.run(manager.disable_plugin("weather"))
    assert sup.stopped is True
    assert manager.is_enabled("weather") is False
    assert manager.get_sandbox("weather") is None
