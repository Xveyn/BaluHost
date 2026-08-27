"""Regression: audio_control must appear in the UI manifest (browser-smoke defect).

``AudioControlPlugin`` shipped without overriding ``get_ui_manifest()``, so the
``PluginBase`` default (``None``) applied. ``PluginManager.get_ui_manifest()``
only appends a plugin entry when ``get_ui_manifest()`` returns a truthy
manifest with ``.enabled`` - an enabled-but-manifest-less plugin is silently
absent from ``GET /api/plugins/ui/manifest``. The frontend's
``usePluginEnabled('audio_control')`` reads that exact list, so the topbar
speaker icon (``LayoutHeader.tsx``) never rendered. See
``AudioControlPlugin.get_ui_manifest()`` for the full chain.
"""
from __future__ import annotations

from app.plugins.installed.audio_control import AudioControlPlugin
from app.plugins.manager import PluginManager


class TestAudioControlUiManifest:
    def test_enabled_plugin_appears_in_manifest_with_no_nav_items(self, tmp_path):
        mgr = PluginManager(plugins_dir=tmp_path)
        mgr._plugins["audio_control"] = AudioControlPlugin()
        mgr._enabled.add("audio_control")

        manifest = mgr.get_ui_manifest()

        entries = [p for p in manifest["plugins"] if p["name"] == "audio_control"]
        assert len(entries) == 1, "audio_control missing from GET /api/plugins/ui/manifest"
        assert entries[0]["nav_items"] == []
