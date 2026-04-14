"""Tests for ``scripts/build_index.py``.

Exercise the end-to-end build against an ad-hoc plugins tree under
``tmp_path``. Verify that the emitted ``index.json`` matches the shape
validated by the backend marketplace schema, artifacts are real zips,
and checksums/sizes line up with the files on disk.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make ``scripts/build_index`` importable without touching sys.path during
# runtime. The script has no package/__init__ so we import by path.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_index  # noqa: E402  (dynamic sys.path)


def _write_plugin(
    source_dir: Path,
    name: str,
    version: str = "1.0.0",
    *,
    extra_files: dict[str, str] | None = None,
    manifest_overrides: dict | None = None,
) -> Path:
    plugin_dir = source_dir / name
    plugin_dir.mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "display_name": name.replace("_", " ").title(),
        "description": f"{name} description",
        "author": "tests",
        "category": "general",
        "required_permissions": [],
        "python_requirements": [],
        "entrypoint": "__init__.py",
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("# entrypoint\n")
    for rel, content in (extra_files or {}).items():
        target = plugin_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return plugin_dir


class TestBuildBasics:
    def test_builds_single_plugin(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "weather")

        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        index = build_index.build(
            source, dist, base_url="https://plugins.example", now=now,
        )

        assert index["index_version"] == 1
        assert index["generated_at"] == "2026-04-14T12:00:00Z"
        assert len(index["plugins"]) == 1
        plugin = index["plugins"][0]
        assert plugin["name"] == "weather"
        assert plugin["latest_version"] == "1.0.0"
        assert len(plugin["versions"]) == 1

    def test_index_file_is_written(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "weather")

        build_index.build(source, dist, base_url="https://plugins.example")

        index_path = dist / "index.json"
        assert index_path.exists()
        parsed = json.loads(index_path.read_text(encoding="utf-8"))
        assert parsed["index_version"] == 1

    def test_empty_source_yields_empty_index(self, tmp_path: Path):
        source = tmp_path / "plugins"
        source.mkdir()
        dist = tmp_path / "dist"

        index = build_index.build(source, dist, base_url="https://plugins.example")

        assert index["plugins"] == []
        assert (dist / "index.json").exists()

    def test_multiple_plugins_are_sorted(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "zeta")
        _write_plugin(source, "alpha")
        _write_plugin(source, "mu")

        index = build_index.build(source, dist, base_url="https://plugins.example")

        assert [p["name"] for p in index["plugins"]] == ["alpha", "mu", "zeta"]


class TestArtifact:
    def test_archive_contains_plugin_files(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(
            source,
            "weather",
            extra_files={"service.py": "x = 1\n", "ui/bundle.js": "export default {}\n"},
        )

        build_index.build(source, dist, base_url="https://plugins.example")

        archive = dist / "weather-1.0.0.bhplugin"
        assert archive.exists()
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
        assert "plugin.json" in names
        assert "__init__.py" in names
        assert "service.py" in names
        assert "ui/bundle.js" in names

    def test_archive_excludes_site_packages_and_pycache(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(
            source,
            "weather",
            extra_files={
                "site-packages/lib/__init__.py": "pass\n",
                "__pycache__/foo.pyc": "garbage",
                "module.pyc": "garbage",
            },
        )

        build_index.build(source, dist, base_url="https://plugins.example")

        with zipfile.ZipFile(dist / "weather-1.0.0.bhplugin") as zf:
            names = zf.namelist()
        assert not any("site-packages" in n for n in names)
        assert not any("__pycache__" in n for n in names)
        assert not any(n.endswith(".pyc") for n in names)

    def test_checksum_and_size_match_archive(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "weather")

        index = build_index.build(source, dist, base_url="https://plugins.example")

        archive = dist / "weather-1.0.0.bhplugin"
        raw = archive.read_bytes()
        ver = index["plugins"][0]["versions"][0]
        assert ver["checksum_sha256"] == hashlib.sha256(raw).hexdigest()
        assert ver["size_bytes"] == len(raw)
        assert len(ver["checksum_sha256"]) == 64

    def test_download_url_uses_base_url(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "weather")

        index = build_index.build(
            source, dist, base_url="https://plugins.example/subdir/",
        )

        ver = index["plugins"][0]["versions"][0]
        assert ver["download_url"] == "https://plugins.example/subdir/weather-1.0.0.bhplugin"


class TestManifestValidation:
    def test_missing_plugin_json_is_skipped(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        (source / "not_a_plugin").mkdir(parents=True)
        _write_plugin(source, "real")

        index = build_index.build(source, dist, base_url="https://plugins.example")

        assert [p["name"] for p in index["plugins"]] == ["real"]

    def test_hidden_dir_is_skipped(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        source.mkdir()
        # Even a .hidden/plugin.json is ignored.
        hidden = source / ".hidden"
        hidden.mkdir()
        (hidden / "plugin.json").write_text("{}")
        _write_plugin(source, "real")

        index = build_index.build(source, dist, base_url="https://plugins.example")

        assert [p["name"] for p in index["plugins"]] == ["real"]

    def test_missing_required_field_raises(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        plugin_dir = source / "broken"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"manifest_version": 1, "name": "broken"})
        )

        with pytest.raises(build_index.BuildError, match="missing required fields"):
            build_index.build(source, dist, base_url="https://plugins.example")

    def test_unsupported_manifest_version_raises(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(
            source, "weather", manifest_overrides={"manifest_version": 99},
        )

        with pytest.raises(build_index.BuildError, match="unsupported manifest_version"):
            build_index.build(source, dist, base_url="https://plugins.example")

    def test_name_mismatch_raises(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(source, "weather", manifest_overrides={"name": "other"})

        with pytest.raises(build_index.BuildError, match="does not match directory name"):
            build_index.build(source, dist, base_url="https://plugins.example")

    def test_invalid_json_raises(self, tmp_path: Path):
        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        plugin_dir = source / "broken"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("{not json")

        with pytest.raises(build_index.BuildError, match="not valid JSON"):
            build_index.build(source, dist, base_url="https://plugins.example")

    def test_missing_source_dir_raises(self, tmp_path: Path):
        with pytest.raises(build_index.BuildError, match="does not exist"):
            build_index.build(
                tmp_path / "nope",
                tmp_path / "dist",
                base_url="https://plugins.example",
            )


class TestIndexShape:
    def test_index_validates_against_backend_schema(self, tmp_path: Path):
        """The emitted index parses cleanly via the backend Pydantic models.

        This is the canonical cross-repo contract: if the backend tightens
        the schema, this test catches it before CI publishes a broken index.
        """
        pytest.importorskip("pydantic")
        # Import the real backend schema. Tests run with the backend package
        # on sys.path (see conftest.py).
        from app.plugins.marketplace import MarketplaceIndex  # type: ignore

        source = tmp_path / "plugins"
        dist = tmp_path / "dist"
        _write_plugin(
            source,
            "weather",
            manifest_overrides={
                "python_requirements": ["pyowm>=3.0"],
                "required_permissions": ["network:outbound"],
                "min_baluhost_version": "1.30.0",
            },
        )
        _write_plugin(source, "co2")

        index = build_index.build(source, dist, base_url="https://plugins.example")

        parsed = MarketplaceIndex.model_validate(index)
        assert len(parsed.plugins) == 2
        weather = parsed.get_plugin("weather")
        assert weather is not None
        assert weather.versions[0].python_requirements == ["pyowm>=3.0"]
        assert weather.versions[0].required_permissions == ["network:outbound"]
