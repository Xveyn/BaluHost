import json
from pathlib import Path
import pytest
from app.plugins.manifest import load_manifest, PluginManifest


def _write(tmp_path: Path, extra: dict) -> Path:
    base = {
        "manifest_version": 1, "name": "weather", "version": "1.0.0",
        "display_name": "Weather", "description": "d", "author": "a",
    }
    base.update(extra)
    (tmp_path / "plugin.json").write_text(json.dumps(base), encoding="utf-8")
    return tmp_path


def test_api_scopes_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, {}))
    assert m.api_scopes == []
    assert m.min_runtime_abi is None


def test_api_scopes_parsed(tmp_path):
    m = load_manifest(_write(tmp_path, {"api_scopes": ["read:storage"], "min_runtime_abi": 1}))
    assert m.api_scopes == ["read:storage"]
    assert m.min_runtime_abi == 1
