"""Tests for plugins/manager.py — PluginManager lifecycle, discovery, hooks."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.plugins.manager import PluginLoadError, PluginManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the PluginManager singleton between tests."""
    PluginManager.reset_instance()
    yield
    PluginManager.reset_instance()


@pytest.fixture
def empty_plugins_dir(tmp_path: Path) -> Path:
    """An empty temporary plugins directory."""
    d = tmp_path / "plugins"
    d.mkdir()
    return d


@pytest.fixture
def plugins_dir_with_plugin(tmp_path: Path) -> Path:
    """A plugins directory containing a valid test plugin."""
    d = tmp_path / "plugins"
    d.mkdir()
    plugin_dir = d / "test_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(
        '''
from app.plugins.base import PluginBase, PluginMetadata


class TestPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            display_name="Test Plugin",
            description="A test plugin",
            author="Test",
            required_permissions=[],
        )

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass
'''
    )
    return d


class TestSingleton:
    def test_get_instance_returns_same_object(self):
        a = PluginManager.get_instance()
        b = PluginManager.get_instance()
        assert a is b

    def test_reset_instance_clears(self):
        a = PluginManager.get_instance()
        PluginManager.reset_instance()
        b = PluginManager.get_instance()
        assert a is not b


class TestDiscoverPlugins:
    def test_empty_directory(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        assert mgr.discover_plugins() == []

    def test_discovers_plugin(self, plugins_dir_with_plugin: Path):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        discovered = mgr.discover_plugins()
        assert "test_plugin" in discovered

    def test_ignores_non_packages(self, empty_plugins_dir: Path):
        # Create a directory without __init__.py
        (empty_plugins_dir / "not_a_plugin").mkdir()
        # Create a plain file
        (empty_plugins_dir / "readme.txt").write_text("hi")
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        assert mgr.discover_plugins() == []

    def test_nonexistent_directory(self, tmp_path: Path):
        mgr = PluginManager(plugins_dir=tmp_path / "doesnotexist")
        assert mgr.discover_plugins() == []


class TestLoadPlugin:
    def test_loads_valid_plugin(self, plugins_dir_with_plugin: Path):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        plugin = mgr.load_plugin("test_plugin")
        assert plugin.metadata.name == "test_plugin"
        assert plugin.metadata.version == "1.0.0"

    def test_caches_loaded_plugin(self, plugins_dir_with_plugin: Path):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        first = mgr.load_plugin("test_plugin")
        second = mgr.load_plugin("test_plugin")
        assert first is second

    def test_raises_for_missing_plugin(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        with pytest.raises(PluginLoadError, match="not found"):
            mgr.load_plugin("nonexistent")

    def test_raises_for_no_init(self, empty_plugins_dir: Path):
        (empty_plugins_dir / "bad_plugin").mkdir()
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        with pytest.raises(PluginLoadError, match="__init__.py"):
            mgr.load_plugin("bad_plugin")

    def test_raises_for_no_plugin_class(self, empty_plugins_dir: Path):
        plugin_dir = empty_plugins_dir / "empty_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# Nothing here\n")
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        with pytest.raises(PluginLoadError, match="No PluginBase subclass"):
            mgr.load_plugin("empty_plugin")


class TestPluginProperties:
    def test_plugins_dir_property(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        assert mgr.plugins_dir == empty_plugins_dir

    def test_get_plugin_returns_none_when_not_loaded(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        assert mgr.get_plugin("nonexistent") is None

    def test_get_plugin_returns_loaded(self, plugins_dir_with_plugin: Path):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        mgr.load_plugin("test_plugin")
        assert mgr.get_plugin("test_plugin") is not None

    def test_is_enabled_false_initially(self, plugins_dir_with_plugin: Path):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        mgr.load_plugin("test_plugin")
        assert mgr.is_enabled("test_plugin") is False


@pytest.mark.asyncio
class TestEnableDisablePlugin:
    async def test_enable_plugin(self, plugins_dir_with_plugin: Path, db_session: Session):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        result = await mgr.enable_plugin("test_plugin", [], db_session)
        assert result is True
        assert mgr.is_enabled("test_plugin")

    async def test_enable_nonexistent_plugin(self, empty_plugins_dir: Path, db_session: Session):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        result = await mgr.enable_plugin("nonexistent", [], db_session)
        assert result is False

    async def test_disable_plugin(self, plugins_dir_with_plugin: Path, db_session: Session):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        await mgr.enable_plugin("test_plugin", [], db_session)
        result = await mgr.disable_plugin("test_plugin")
        assert result is True
        assert not mgr.is_enabled("test_plugin")

    async def test_disable_not_enabled_is_noop(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        result = await mgr.disable_plugin("nonexistent")
        assert result is True

    async def test_enable_with_missing_permissions(self, plugins_dir_with_plugin: Path, db_session: Session):
        """Plugin that requires permissions not in granted list should fail."""
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        plugin = mgr.load_plugin("test_plugin")
        # Patch required_permissions to need something
        original_meta = plugin.metadata
        with patch.object(
            type(plugin), "metadata", new_callable=lambda: property(
                lambda self: original_meta.model_copy(update={"required_permissions": ["file:write"]})
            )
        ):
            result = await mgr.enable_plugin("test_plugin", [], db_session)
            assert result is False


@pytest.mark.asyncio
class TestShutdownAll:
    async def test_shutdown_disables_all(self, plugins_dir_with_plugin: Path, db_session: Session):
        mgr = PluginManager(plugins_dir=plugins_dir_with_plugin)
        await mgr.enable_plugin("test_plugin", [], db_session)
        await mgr.shutdown_all()
        assert not mgr.is_enabled("test_plugin")


class TestEmitHook:
    def test_unknown_hook_returns_empty(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        result = mgr.emit_hook("nonexistent_hook")
        assert result == []


class TestGetRouter:
    def test_returns_router(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        router = mgr.get_router()
        assert router is not None
        assert router.prefix == "/plugins"


class TestGetUiManifest:
    def test_returns_manifest(self, empty_plugins_dir: Path):
        mgr = PluginManager(plugins_dir=empty_plugins_dir)
        manifest = mgr.get_ui_manifest()
        assert "plugins" in manifest
        assert manifest["plugins"] == []
