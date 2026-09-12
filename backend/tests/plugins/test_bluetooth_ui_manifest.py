"""Ohne diese Ueberschreibung ist das Plugin im Frontend unsichtbar."""
from app.plugins.installed.bluetooth import BluetoothPlugin


class TestUiManifest:
    def test_the_manifest_is_present_and_enabled(self):
        manifest = BluetoothPlugin().get_ui_manifest()
        assert manifest is not None and manifest.enabled is True

    def test_it_contributes_no_nav_item(self):
        assert BluetoothPlugin().get_ui_manifest().nav_items == []

    def test_the_metadata_name_matches_the_route_prefix(self):
        assert BluetoothPlugin().metadata.name == "bluetooth"
