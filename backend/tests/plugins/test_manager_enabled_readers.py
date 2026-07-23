"""The manager's status readers answer from the DB cache, not from _enabled (#448)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.plugins.manager import PluginManager
from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


def _manager(tmp_path) -> PluginManager:
    return PluginManager(plugins_dir=tmp_path)


def _grant(permissions=None, scopes=None) -> dict:
    """Build a ``_fetch()``-shaped cache entry for one plugin."""
    return {
        "granted_permissions": list(permissions or []),
        "granted_api_scopes": list(scopes or []),
    }


class TestIsEnabled:
    async def test_reports_enabled_although_this_worker_never_loaded_it(self, tmp_path):
        """The bug, in one assertion.

        Worker B never handled the toggle, so its _enabled is empty - but the
        database says the plugin is on, and that is what a client must see.
        """
        worker_b = _manager(tmp_path)
        assert worker_b._enabled == set()

        with patch.object(pe, "_fetch", return_value={"demo": _grant()}):
            await pe.refresh()

        assert worker_b.is_enabled("demo") is True

    async def test_reports_disabled_although_this_worker_still_has_it_loaded(self, tmp_path):
        """The reverse direction: disabling used to survive on other workers."""
        worker_b = _manager(tmp_path)
        worker_b._enabled = {"demo"}

        with patch.object(pe, "_fetch", return_value={}):
            await pe.refresh()

        assert worker_b.is_enabled("demo") is False

    def test_falls_back_to_local_state_when_the_cache_has_no_data(self, tmp_path):
        """A DB outage must not blank the plugin list."""
        worker = _manager(tmp_path)
        worker._enabled = {"demo"}

        assert pe.enabled_plugins() is None
        assert worker.is_enabled("demo") is True


class TestGetAllPlugins:
    async def test_status_flag_comes_from_the_cache(self, tmp_path):
        manager = _manager(tmp_path)
        plugin = MagicMock()
        plugin.metadata.name = "demo"
        plugin.metadata.version = "1.0.0"
        plugin.metadata.display_name = "Demo"
        plugin.metadata.description = ""
        plugin.metadata.author = "test"
        plugin.metadata.category = "general"
        plugin.metadata.required_permissions = []
        plugin.get_ui_manifest.return_value = None
        plugin.get_router.return_value = None
        manager._plugins = {"demo": plugin}
        manager._enabled = set()

        with patch.object(manager, "discover_plugins", return_value=["demo"]), \
             patch.object(manager, "get_discovered", return_value=None), \
             patch.object(pe, "_fetch", return_value={"demo": _grant()}):
            await pe.refresh()
            info = manager.get_all_plugins()

        assert info["demo"]["is_enabled"] is True
