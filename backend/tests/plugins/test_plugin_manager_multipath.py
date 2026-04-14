"""Tests for the multi-directory + manifest-first + namespace-aware loader.

Phase 1 of the plugin marketplace refactor.  See
``docs/superpowers/specs/2026-04-13-plugin-marketplace-design.md``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.plugins.manager import BUNDLED_PLUGINS_DIR, PluginManager


@pytest.fixture(autouse=True)
def reset_singleton():
    PluginManager.reset_instance()
    yield
    PluginManager.reset_instance()


@pytest.fixture(autouse=True)
def cleanup_synthetic_namespaces():
    """Drop any synthetic namespace packages between tests so import state
    from one test cannot leak into the next."""
    yield
    for mod in list(sys.modules):
        if mod == "baluhost_plugins" or mod.startswith("baluhost_plugins."):
            sys.modules.pop(mod, None)


def _write_plugin(
    parent: Path,
    name: str,
    *,
    with_manifest: bool = True,
    python_requirements: list[str] | None = None,
    extra_init: str = "",
) -> Path:
    plugin_dir = parent / name
    plugin_dir.mkdir(parents=True)
    if with_manifest:
        manifest = {
            "manifest_version": 1,
            "name": name,
            "version": "1.0.0",
            "display_name": name.replace("_", " ").title(),
            "description": f"{name} test plugin",
            "author": "tests",
            "category": "general",
            "required_permissions": [],
            "plugin_dependencies": [],
            "python_requirements": python_requirements or [],
            "entrypoint": "__init__.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text(
        f'''
from app.plugins.base import PluginBase, PluginMetadata


class TestPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="{name}",
            version="1.0.0",
            display_name="{name}",
            description="test",
            author="tests",
            required_permissions=[],
        )

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

{extra_init}
'''
    )
    return plugin_dir


class TestMultiPathDiscovery:
    def test_discovers_across_two_directories(self, tmp_path: Path):
        bundled = tmp_path / "bundled"
        external = tmp_path / "external"
        bundled.mkdir()
        external.mkdir()
        _write_plugin(bundled, "alpha")
        _write_plugin(external, "beta")

        mgr = PluginManager(plugins_dirs=[bundled, external])
        names = mgr.discover_plugins()
        assert set(names) == {"alpha", "beta"}

    def test_first_directory_wins_on_name_conflict(self, tmp_path: Path):
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        _write_plugin(first, "dup")
        _write_plugin(second, "dup")

        mgr = PluginManager(plugins_dirs=[first, second])
        mgr.discover_plugins()
        info = mgr.get_discovered("dup")
        assert info is not None
        assert info.path.parent.resolve() == first.resolve()

    def test_force_rescan_picks_up_new_plugin(self, tmp_path: Path):
        ext = tmp_path / "external"
        ext.mkdir()
        mgr = PluginManager(plugins_dirs=[ext])
        assert mgr.discover_plugins() == []

        _write_plugin(ext, "lateboot")
        # cached result should still be empty without force
        assert mgr.discover_plugins() == []
        # force rescans
        assert "lateboot" in mgr.discover_plugins(force=True)

    def test_missing_external_dir_is_tolerated(self, tmp_path: Path):
        bundled = tmp_path / "b"
        bundled.mkdir()
        _write_plugin(bundled, "only_bundled")
        missing = tmp_path / "does_not_exist"

        mgr = PluginManager(plugins_dirs=[bundled, missing])
        assert "only_bundled" in mgr.discover_plugins()


class TestManifestFirst:
    def test_invalid_manifest_skips_plugin(self, tmp_path: Path):
        ext = tmp_path / "ext"
        ext.mkdir()
        bad = ext / "broken"
        bad.mkdir()
        (bad / "plugin.json").write_text("{not valid json")
        (bad / "__init__.py").write_text("# noop")

        mgr = PluginManager(plugins_dirs=[ext])
        assert mgr.discover_plugins() == []

    def test_manifest_loaded_without_executing_code(self, tmp_path: Path):
        """Discovery must not import the plugin module — that's the whole
        point of having a static plugin.json: marketplace UI / install can
        inspect a plugin without trusting its Python."""
        ext = tmp_path / "ext"
        ext.mkdir()
        plugin_dir = ext / "boom"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "name": "boom",
                    "version": "1.0.0",
                    "display_name": "Boom",
                    "description": "would explode if imported",
                    "author": "tests",
                }
            )
        )
        # Importing this would raise — discovery must not.
        (plugin_dir / "__init__.py").write_text(
            "raise RuntimeError('discovery imported me')"
        )

        mgr = PluginManager(plugins_dirs=[ext])
        names = mgr.discover_plugins()
        assert "boom" in names
        info = mgr.get_discovered("boom")
        assert info is not None
        assert info.manifest is not None
        assert info.manifest.name == "boom"

    def test_legacy_plugin_without_manifest_still_discovered(self, tmp_path: Path):
        ext = tmp_path / "ext"
        ext.mkdir()
        _write_plugin(ext, "legacy", with_manifest=False)

        mgr = PluginManager(plugins_dirs=[ext])
        assert "legacy" in mgr.discover_plugins()
        info = mgr.get_discovered("legacy")
        assert info is not None
        assert info.manifest is None


class TestExternalNamespace:
    def test_external_plugin_loads_under_baluhost_plugins_namespace(
        self, tmp_path: Path
    ):
        ext = tmp_path / "ext"
        ext.mkdir()
        _write_plugin(ext, "marketplace_demo")

        mgr = PluginManager(plugins_dirs=[ext])
        plugin = mgr.load_plugin("marketplace_demo")
        assert plugin.metadata.name == "marketplace_demo"

        assert "baluhost_plugins" in sys.modules
        assert "baluhost_plugins.marketplace_demo" in sys.modules

    def test_bundled_directory_is_classified_as_bundled(self, tmp_path: Path):
        """A scan of the canonical BUNDLED_PLUGINS_DIR yields source=bundled."""
        mgr = PluginManager(plugins_dirs=[BUNDLED_PLUGINS_DIR])
        mgr.discover_plugins()
        for name in ("optical_drive", "storage_analytics", "tapo_smart_plug"):
            info = mgr.get_discovered(name)
            assert info is not None, f"{name} not discovered"
            assert info.source == "bundled"
            assert info.manifest is not None  # phase-1 added plugin.json files

    def test_arbitrary_directory_is_classified_as_external(self, tmp_path: Path):
        ext = tmp_path / "ext"
        ext.mkdir()
        _write_plugin(ext, "thirdparty")
        mgr = PluginManager(plugins_dirs=[ext])
        mgr.discover_plugins()
        info = mgr.get_discovered("thirdparty")
        assert info is not None
        assert info.source == "external"


class TestSitePackagesIsolation:
    def test_site_packages_prepended_to_sys_path_on_load(self, tmp_path: Path):
        ext = tmp_path / "ext"
        ext.mkdir()
        plugin_dir = _write_plugin(ext, "with_deps")
        site_pkg = plugin_dir / "site-packages"
        site_pkg.mkdir()

        mgr = PluginManager(plugins_dirs=[ext])
        mgr.load_plugin("with_deps")
        assert str(site_pkg) in sys.path
        # cleanup so we don't pollute other tests
        sys.path.remove(str(site_pkg))

    def test_no_site_packages_means_no_sys_path_change(self, tmp_path: Path):
        ext = tmp_path / "ext"
        ext.mkdir()
        _write_plugin(ext, "no_deps")
        before = list(sys.path)

        mgr = PluginManager(plugins_dirs=[ext])
        mgr.load_plugin("no_deps")
        # Only difference allowed: nothing — there is no site-packages dir.
        assert sys.path == before
