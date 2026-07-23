"""GET /api/plugins/{name} surfaces restart_required (#448 review finding 3).

The manager-level logic (PluginManager.router_restart_required()) is pinned
in test_plugin_manager.py::TestRouterRestartRequired. These tests go one
layer up and prove the route actually wires that value into the response.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter

from app.api.routes.plugins import get_plugin_details
from app.plugins.base import PluginMetadata
from app.plugins.manager import PluginManager


def _plugin(has_router: bool) -> MagicMock:
    plugin = MagicMock()
    plugin.metadata = PluginMetadata(
        name="demo", version="1.0.0", display_name="Demo",
        description="", author="test",
    )
    plugin.get_ui_manifest.return_value = None
    # A real APIRouter, not a MagicMock: get_router() feeds the value straight
    # into router.include_router(), whose circularity check (FastAPI >=0.115.x)
    # rejects a mock. The mock only passed on the older local FastAPI that
    # lacked that check - exactly the local-green / CI-red gap here.
    plugin.get_router.return_value = APIRouter() if has_router else None
    plugin.get_background_tasks.return_value = []
    plugin.get_dashboard_panel.return_value = None
    plugin.get_translations.return_value = None
    plugin.get_config_schema.return_value = None
    plugin.get_default_config.return_value = {}
    return plugin


@pytest.mark.asyncio
class TestGetPluginDetailsRestartRequiredField:
    @pytest.fixture(autouse=True)
    def _reset_enablement_cache(self):
        from app.services import plugin_enablement as pe

        pe.invalidate()
        yield
        pe.invalidate()

    async def _call(self, mgr: PluginManager):
        with patch(
            "app.api.routes.plugins.plugin_service.get_installed_plugin", return_value=None
        ), patch("app.api.routes.plugins.user_limiter.enabled", False):
            return await get_plugin_details(
                request=MagicMock(), response=MagicMock(),
                name="demo", db=MagicMock(),
                current_user=MagicMock(), plugin_manager=mgr,
            )

    async def test_true_for_a_router_carrying_plugin_enabled_after_startup(self, tmp_path):
        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.get_router()  # simulate the startup mount, before this plugin exists

        plugin = _plugin(has_router=True)
        mgr._plugins["demo"] = plugin
        mgr._enabled.add("demo")

        result = await self._call(mgr)
        assert result.restart_required is True

    async def test_false_for_a_router_carrying_plugin_mounted_at_startup(self, tmp_path):
        mgr = PluginManager(plugins_dir=tmp_path)
        plugin = _plugin(has_router=True)
        mgr._plugins["demo"] = plugin
        mgr._enabled.add("demo")
        mgr.get_router()  # startup mount runs with the plugin already enabled

        result = await self._call(mgr)
        assert result.restart_required is False

    async def test_false_for_a_plugin_without_a_router(self, tmp_path):
        mgr = PluginManager(plugins_dir=tmp_path)
        plugin = _plugin(has_router=False)
        mgr._plugins["demo"] = plugin
        mgr._enabled.add("demo")
        mgr.get_router()

        result = await self._call(mgr)
        assert result.restart_required is False
