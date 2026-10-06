"""Plugin names that reach the filesystem must match one rule (#634).

Before: the marketplace uninstall ran ``shutil.rmtree(plugins_dir / name)`` on
the raw URL segment, ``load_plugin`` fell back to ``plugins_dir / name`` and
imported whatever it found there, and the asset route's containment check used
``str.startswith`` against a base built from the same unchecked name.

The experiments behind these tests ran in throw-away temp trees; none of them
points at a real plugin directory.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.manager import PluginLoadError, PluginManager
from app.plugins.naming import PLUGIN_NAME_PATTERN, is_valid_plugin_name

# Names a route can actually receive, written the way a client would encode
# them (a literal ".." is normalised away by most clients, "%2e%2e" is not).
DOT_SEGMENTS = ["%2e%2e", "%2e"]


class TestIsValidPluginName:
    @pytest.mark.parametrize("name", [
        "a", "audio_control", "steam_gaming", "plugin2", "_x", "x" * 64,
    ])
    def test_accepts_safe_names(self, name):
        assert is_valid_plugin_name(name)

    @pytest.mark.parametrize("name", [
        "", ".", "..", "../x", "a/b", "a\\b", "Upper", "with-dash", "with space",
        "x" * 65, "demo\n", "demo\x00", "dé", "a.b",
    ])
    def test_rejects_everything_else(self, name):
        assert not is_valid_plugin_name(name)

    @pytest.mark.parametrize("value", [None, 1, b"demo", ["demo"]])
    def test_rejects_non_strings(self, value):
        assert not is_valid_plugin_name(value)

    def test_pattern_agrees_with_the_function(self):
        # The same rule is handed to FastAPI's Path(pattern=...); the two must
        # not drift apart.
        import re
        for name in ["demo", "..", "demo\n", "x" * 65, "ok_1"]:
            assert bool(re.fullmatch(PLUGIN_NAME_PATTERN, name)) == is_valid_plugin_name(name)


class TestLoadPlugin:
    def test_dot_dot_does_not_execute_the_parent_package(self, tmp_path):
        marker = tmp_path / "executed"
        parent = tmp_path / "parent"
        (parent / "installed").mkdir(parents=True)
        (parent / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
        )
        manager = PluginManager(plugins_dir=parent / "installed")

        with pytest.raises(PluginLoadError):
            manager.load_plugin("..")

        assert not marker.exists(), "load_plugin('..') ran the parent's __init__.py"

    @pytest.mark.parametrize("name", ["", ".", "..", "a/b", "Upper"])
    def test_invalid_names_are_refused_before_any_path_is_built(self, tmp_path, name):
        manager = PluginManager(plugins_dir=tmp_path)
        with pytest.raises(PluginLoadError, match="[Ii]nvalid plugin name"):
            manager.load_plugin(name)

    def test_nothing_is_registered_for_a_refused_name(self, tmp_path):
        import sys
        manager = PluginManager(plugins_dir=tmp_path)
        before = set(sys.modules)
        with pytest.raises(PluginLoadError):
            manager.load_plugin("..")
        assert not [k for k in set(sys.modules) - before if k.endswith("..")]


class TestInstaller:
    @pytest.fixture
    def tree(self, tmp_path):
        plugins = tmp_path / "plugins"
        (plugins / "real_plugin").mkdir(parents=True)
        (tmp_path / "sibling_data").mkdir()
        (tmp_path / "sibling_data" / "keep.txt").write_text("x")
        return tmp_path, plugins

    @staticmethod
    def _installer(plugins: Path, fetcher=None):
        from app.plugins.installer import PluginInstaller
        return PluginInstaller(plugins, MagicMock(), fetcher=fetcher)

    @pytest.mark.parametrize("name", ["..", ".", "", "a/b", "../sibling_data"])
    def test_uninstall_refuses_unsafe_names_and_deletes_nothing(self, tree, name):
        from app.plugins.installer import InvalidPluginNameError

        base, plugins = tree
        with pytest.raises(InvalidPluginNameError):
            self._installer(plugins).uninstall(name)

        assert (plugins / "real_plugin").is_dir()
        assert (base / "sibling_data" / "keep.txt").is_file()

    def test_uninstall_still_removes_a_valid_plugin(self, tree):
        _, plugins = tree
        assert self._installer(plugins).uninstall("real_plugin") is True
        assert not (plugins / "real_plugin").exists()

    def test_uninstall_of_an_unknown_valid_name_is_false(self, tree):
        _, plugins = tree
        assert self._installer(plugins).uninstall("not_installed") is False

    @pytest.mark.parametrize("name", ["..", "a/b", "Upper"])
    def test_install_refuses_unsafe_names_before_downloading(self, tree, name):
        from app.plugins.installer import InvalidPluginNameError

        _, plugins = tree
        fetcher = MagicMock()
        entry = MagicMock(size_bytes=1, checksum_sha256="0" * 64)
        with pytest.raises(InvalidPluginNameError):
            self._installer(plugins, fetcher).install(entry, name)

        fetcher.assert_not_called()


class TestRoutes:
    @pytest.mark.parametrize("segment", DOT_SEGMENTS)
    def test_marketplace_uninstall_rejects_dot_segments(self, client, admin_headers, segment):
        with patch("app.plugins.installer.PluginInstaller.uninstall") as uninstall:
            resp = client.delete(f"/api/plugins/marketplace/{segment}", headers=admin_headers)

        assert resp.status_code == 422
        uninstall.assert_not_called()

    @pytest.mark.parametrize("segment", DOT_SEGMENTS)
    def test_toggle_rejects_dot_segments(self, client, admin_headers, segment):
        with patch("app.plugins.manager.PluginManager.load_plugin") as load:
            resp = client.post(
                f"/api/plugins/{segment}/toggle",
                json={"enabled": True, "grant_permissions": []},
                headers=admin_headers,
            )

        assert resp.status_code == 422
        load.assert_not_called()

    def test_marketplace_install_rejects_uppercase(self, client, admin_headers):
        resp = client.post(
            "/api/plugins/marketplace/Not_Valid/install",
            json={"version": "1.0.0"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


class TestWhereNamesEnter:
    """The rule is enforced where a name enters the system, not only where it is
    consumed: otherwise a plugin is listed but cannot be managed."""

    BAD = ["my-plugin", "Upper", "a" * 65, "..", "a/b"]

    @pytest.mark.parametrize("name", BAD)
    def test_manifest_rejects_the_name(self, tmp_path, name):
        import json
        from app.plugins.manifest import ManifestError, load_manifest

        (tmp_path / "plugin.json").write_text(json.dumps({
            "manifest_version": 1, "name": name, "version": "1.0.0",
            "display_name": "X", "description": "x", "author": "x",
        }))
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)

    @pytest.mark.parametrize("name", BAD)
    def test_index_entry_rejects_the_name(self, name):
        from pydantic import ValidationError
        from app.plugins.marketplace import MarketplaceEntry

        with pytest.raises(ValidationError):
            MarketplaceEntry(
                name=name, latest_version="1.0.0", versions=[],
                display_name="X", description="x", author="x",
            )

    def test_index_entry_accepts_a_valid_name(self):
        from app.plugins.marketplace import MarketplaceEntry

        entry = MarketplaceEntry(
            name="good_plugin", latest_version="1.0.0", versions=[],
            display_name="X", description="x", author="x",
        )
        assert entry.name == "good_plugin"


class TestInvalidNameMapping:
    """If a name ever gets past PluginNameParam, the answer is 422, not a 500."""

    @pytest.fixture
    def service(self, client):
        from app.main import app
        from app.services.plugin_marketplace import get_marketplace_service

        mock = MagicMock()
        app.dependency_overrides[get_marketplace_service] = lambda: mock
        try:
            yield mock
        finally:
            app.dependency_overrides.pop(get_marketplace_service, None)

    def test_install_maps_invalid_name_to_422(self, client, admin_headers, service):
        from app.plugins.installer import InvalidPluginNameError

        service.install.side_effect = InvalidPluginNameError("bad")
        resp = client.post(
            "/api/plugins/marketplace/good_name/install",
            json={"version": "1.0.0"}, headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_uninstall_maps_invalid_name_to_422(self, client, admin_headers, service):
        from app.plugins.installer import InvalidPluginNameError

        service.uninstall.side_effect = InvalidPluginNameError("bad")
        resp = client.delete("/api/plugins/marketplace/good_name", headers=admin_headers)
        assert resp.status_code == 422


class TestDbOnlyUninstallStaysPermissive:
    def test_a_row_under_a_name_the_rule_rejects_can_still_be_removed(
        self, client, admin_headers
    ):
        """`DELETE /api/plugins/{name}` touches no filesystem. A stale row from
        before the rule must stay removable, otherwise it is stuck for good."""
        with patch("app.services.plugin_service.uninstall_plugin", return_value=True) as rm:
            resp = client.delete("/api/plugins/Old-Plugin", headers=admin_headers)

        assert resp.status_code == 200
        rm.assert_called_once()


class TestServePluginAsset:
    """The containment check must be a path check, not a string-prefix check."""

    @pytest.fixture
    def served(self, client, tmp_path):
        from app.api.routes.plugins import get_plugin_manager
        from app.main import app

        plugin = tmp_path / "demo_plugin"
        (plugin / "ui").mkdir(parents=True)
        (plugin / "ui" / "bundle.js").write_text("// bundle")
        (plugin / "ui_private").mkdir()
        (plugin / "ui_private" / "secret.txt").write_text("secret")
        (plugin / "secrets.env").write_text("TOKEN=x")

        manager = PluginManager(plugins_dir=tmp_path)
        app.dependency_overrides[get_plugin_manager] = lambda: manager
        try:
            with patch("app.services.plugin_service.get_enabled_plugin", return_value=MagicMock()):
                yield client
        finally:
            app.dependency_overrides.pop(get_plugin_manager, None)

    def test_serves_a_file_inside_ui(self, served):
        resp = served.get("/api/plugins/demo_plugin/ui/bundle.js")
        assert resp.status_code == 200

    def test_refuses_a_sibling_directory_that_shares_the_ui_prefix(self, served):
        resp = served.get("/api/plugins/demo_plugin/ui/%2e%2e/ui_private/secret.txt")
        assert resp.status_code == 403
        assert "secret" not in resp.text

    def test_refuses_a_file_next_to_ui(self, served):
        resp = served.get("/api/plugins/demo_plugin/ui/%2e%2e/secrets.env")
        assert resp.status_code == 403
