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
