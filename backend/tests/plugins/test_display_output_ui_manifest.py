"""Ohne diese Ueberschreibung ist das Plugin im Frontend unsichtbar."""
from app.plugins.installed.display_output import DisplayOutputPlugin


class TestUiManifest:
    def test_the_manifest_is_present_and_enabled(self):
        manifest = DisplayOutputPlugin().get_ui_manifest()
        assert manifest is not None
        assert manifest.enabled is True

    def test_it_contributes_no_nav_item(self):
        # Ein Nav-Eintrag erzeugte eine Route und damit einen bundle.js-Abruf.
        # Die Bedienung sitzt in der Topbar.
        assert DisplayOutputPlugin().get_ui_manifest().nav_items == []

    def test_the_metadata_name_matches_the_route_prefix(self):
        assert DisplayOutputPlugin().metadata.name == "display_output"
