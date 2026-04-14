"""Tests for plugins/manifest.py — static plugin.json loading and validation."""

import json
from pathlib import Path

import pytest

from app.plugins.manifest import (
    ManifestError,
    PluginManifest,
    UnsupportedManifestVersionError,
    load_manifest,
)


def _write_manifest(plugin_dir: Path, data: dict) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    path = plugin_dir / "plugin.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def valid_manifest_data() -> dict:
    return {
        "manifest_version": 1,
        "name": "weather_station",
        "version": "1.2.0",
        "display_name": "Weather Station",
        "description": "Pulls local weather and exposes a dashboard panel.",
        "author": "Jane Hobby",
        "category": "monitoring",
        "homepage": "https://example.com/weather",
        "min_baluhost_version": "1.30.0",
        "max_baluhost_version": None,
        "required_permissions": ["network:outbound", "system:info"],
        "plugin_dependencies": [],
        "python_requirements": ["pyowm==3.3.0", "tzdata>=2024.1"],
        "entrypoint": "__init__.py",
        "ui": {"bundle": "ui/bundle.js", "styles": None},
    }


class TestLoadManifest:
    def test_loads_valid_manifest(self, tmp_path: Path, valid_manifest_data: dict):
        plugin_dir = tmp_path / "weather_station"
        _write_manifest(plugin_dir, valid_manifest_data)

        manifest = load_manifest(plugin_dir)

        assert isinstance(manifest, PluginManifest)
        assert manifest.name == "weather_station"
        assert manifest.version == "1.2.0"
        assert manifest.python_requirements == ["pyowm==3.3.0", "tzdata>=2024.1"]
        assert manifest.required_permissions == ["network:outbound", "system:info"]
        assert manifest.ui is not None
        assert manifest.ui.bundle == "ui/bundle.js"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path / "ghost")

    def test_invalid_json_raises(self, tmp_path: Path):
        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{not valid json")

        with pytest.raises(ManifestError, match="invalid JSON"):
            load_manifest(plugin_dir)

    def test_missing_required_field_raises(self, tmp_path: Path, valid_manifest_data: dict):
        del valid_manifest_data["version"]
        plugin_dir = tmp_path / "p"
        _write_manifest(plugin_dir, valid_manifest_data)

        with pytest.raises(ManifestError, match="version"):
            load_manifest(plugin_dir)

    def test_unsupported_manifest_version_raises(
        self, tmp_path: Path, valid_manifest_data: dict
    ):
        valid_manifest_data["manifest_version"] = 99
        plugin_dir = tmp_path / "p"
        _write_manifest(plugin_dir, valid_manifest_data)

        with pytest.raises(UnsupportedManifestVersionError, match="99"):
            load_manifest(plugin_dir)

    def test_defaults_for_optional_fields(self, tmp_path: Path):
        minimal = {
            "manifest_version": 1,
            "name": "minimal",
            "version": "0.1.0",
            "display_name": "Minimal",
            "description": "Bare minimum",
            "author": "Tester",
        }
        plugin_dir = tmp_path / "minimal"
        _write_manifest(plugin_dir, minimal)

        manifest = load_manifest(plugin_dir)

        assert manifest.category == "general"
        assert manifest.required_permissions == []
        assert manifest.plugin_dependencies == []
        assert manifest.python_requirements == []
        assert manifest.entrypoint == "__init__.py"
        assert manifest.ui is None
        assert manifest.min_baluhost_version is None


class TestToMetadata:
    def test_converts_to_plugin_metadata(self, tmp_path: Path, valid_manifest_data: dict):
        plugin_dir = tmp_path / "p"
        _write_manifest(plugin_dir, valid_manifest_data)
        manifest = load_manifest(plugin_dir)

        meta = manifest.to_metadata()

        assert meta.name == "weather_station"
        assert meta.version == "1.2.0"
        assert meta.display_name == "Weather Station"
        assert meta.author == "Jane Hobby"
        assert meta.category == "monitoring"
        assert meta.homepage == "https://example.com/weather"
        assert meta.min_baluhost_version == "1.30.0"
        assert meta.required_permissions == ["network:outbound", "system:info"]
        assert meta.dependencies == []  # plugin_dependencies → dependencies on PluginMetadata


class TestPythonRequirements:
    def test_pep508_strings_are_preserved(self, tmp_path: Path, valid_manifest_data: dict):
        valid_manifest_data["python_requirements"] = [
            "requests>=2.30,<3",
            "pyowm==3.3.0",
            "anyio",
        ]
        plugin_dir = tmp_path / "p"
        _write_manifest(plugin_dir, valid_manifest_data)

        manifest = load_manifest(plugin_dir)

        assert manifest.python_requirements == [
            "requests>=2.30,<3",
            "pyowm==3.3.0",
            "anyio",
        ]
