"""Tests for the plugin menu-action extension point."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    MenuActionResult,
    PluginBase,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
)


class TestPluginMenuItem:
    def test_minimal_item(self):
        item = PluginMenuItem(
            id="gaming_mode", icon="Gamepad2",
            label_key="menu_gaming_mode", label_text="Gaming Mode",
        )
        assert item.tone == "neutral"
        assert item.order == 100
        assert item.description_key is None

    @pytest.mark.parametrize("bad_id", ["Gaming", "gaming-mode", "gaming.mode", "../etc", "", "a b"])
    def test_rejects_ids_outside_the_namespace(self, bad_id):
        with pytest.raises(ValidationError):
            PluginMenuItem(
                id=bad_id, icon="Gamepad2",
                label_key="k", label_text="t",
            )

    def test_has_no_admin_only_field(self):
        """The core decides who may run an action - a plugin must not widen it."""
        assert "admin_only" not in PluginMenuItem.model_fields


class TestMenuActionResult:
    def test_message_text_is_required(self):
        with pytest.raises(ValidationError):
            MenuActionResult(ok=True)

    def test_key_is_optional(self):
        result = MenuActionResult(ok=False, message_text="boom")
        assert result.message_key is None


class _BarePlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bare", display_name="Bare", version="1.0.0",
            description="", author="test",
        )


class TestPluginBaseDefaults:
    def test_no_menu_items_by_default(self):
        assert _BarePlugin().get_menu_items() == []

    async def test_run_menu_action_returns_none_by_default(self):
        assert await _BarePlugin().run_menu_action("anything", db=None) is None

    def test_ui_manifest_menu_items_default_empty(self):
        assert PluginUIManifest().menu_items == []


from unittest.mock import MagicMock

from app.plugins.manager import PluginManager
from app.schemas.plugin import PluginUIInfo


def _plugin_with_menu(name: str = "demo") -> MagicMock:
    plugin = MagicMock()
    plugin.metadata.display_name = "Demo"
    plugin.get_ui_manifest.return_value = PluginUIManifest(
        enabled=True,
        menu_items=[PluginMenuItem(
            id="do_it", icon="Zap", label_key="menu_do_it", label_text="Do it",
        )],
    )
    plugin.get_translations.return_value = {"en": {"menu_do_it": "Do it"}}
    return plugin


class TestManifestCarriesMenuItems:
    def test_enabled_plugin_menu_items_reach_the_manifest(self, tmp_path):
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": _plugin_with_menu()}
        manager._enabled = {"demo"}

        entry = manager.get_ui_manifest()["plugins"][0]

        assert entry["menu_items"] == [{
            "id": "do_it", "icon": "Zap",
            "label_key": "menu_do_it", "label_text": "Do it",
            "description_key": None, "description_text": None,
            "tone": "neutral", "order": 100,
        }]

    def test_plugin_without_menu_items_yields_empty_list(self, tmp_path):
        plugin = _plugin_with_menu()
        plugin.get_ui_manifest.return_value = PluginUIManifest(enabled=True)
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": plugin}
        manager._enabled = {"demo"}

        assert manager.get_ui_manifest()["plugins"][0]["menu_items"] == []

    def test_schema_defaults_to_empty(self):
        info = PluginUIInfo(name="demo", display_name="Demo")
        assert info.menu_items == []
