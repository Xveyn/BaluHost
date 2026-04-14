"""Tests for ``services/plugin_marketplace.py``.

These tests exercise the caching + fetch + delegate logic without hitting
the network or a real ``PluginInstaller`` — the underlying installer
operates on an in-memory fake marketplace (same pattern as
``test_installer.py``) and the index fetcher is a simple callable.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Dict

import pytest

from app.plugins.core_versions import CoreVersions
from app.plugins.installer import PluginInstaller
from app.services.plugin_marketplace import (
    IndexFetchError,
    IndexParseError,
    MarketplaceService,
    PluginNotFoundError,
)


def _build_plugin_zip(name: str, version: str = "1.0.0") -> bytes:
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "display_name": name.title(),
        "description": "test",
        "author": "tests",
        "category": "general",
        "required_permissions": [],
        "plugin_dependencies": [],
        "python_requirements": [],
        "entrypoint": "__init__.py",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("plugin.json", json.dumps(manifest))
        zf.writestr("__init__.py", "# plugin\n")
    return buf.getvalue()


def _make_index(plugins: list[tuple[str, str, bytes, str]]) -> dict:
    """Build an index.json payload. plugins: [(name, version, archive, url)]."""
    grouped: Dict[str, list] = {}
    for name, version, archive, url in plugins:
        grouped.setdefault(name, []).append(
            {
                "version": version,
                "python_requirements": [],
                "required_permissions": [],
                "download_url": url,
                "checksum_sha256": hashlib.sha256(archive).hexdigest(),
                "size_bytes": len(archive),
            }
        )
    return {
        "index_version": 1,
        "generated_at": "2026-04-14T00:00:00Z",
        "plugins": [
            {
                "name": name,
                "latest_version": entries[-1]["version"],
                "versions": entries,
                "display_name": name.title(),
                "description": "test plugin",
                "author": "tests",
                "category": "general",
            }
            for name, entries in grouped.items()
        ],
    }


@pytest.fixture
def core() -> CoreVersions:
    return CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="linux_x86_64",
        abi="cp311",
        packages={},
    )


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    d = tmp_path / "installed-plugins"
    d.mkdir()
    return d


class _Fake:
    """Captures an index JSON + archive map and exposes the two fetchers."""

    def __init__(self, *, index: dict, archives: Dict[str, bytes]):
        self.index_raw = json.dumps(index).encode()
        self.archives = archives
        self.index_calls = 0

    def fetch_index(self, url: str) -> bytes:
        self.index_calls += 1
        return self.index_raw

    def fetch_archive(self, url: str) -> bytes:
        if url not in self.archives:
            raise RuntimeError(f"unexpected archive fetch: {url}")
        return self.archives[url]


def _build_service(
    plugins_dir: Path,
    core: CoreVersions,
    fake: _Fake,
    *,
    cache_ttl: int = 300,
) -> MarketplaceService:
    installer = PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core,
        fetcher=fake.fetch_archive,
        pip_runner=lambda reqs, target, cv: target.mkdir(parents=True, exist_ok=True),
    )
    return MarketplaceService(
        index_url="https://plugins.example/index.json",
        installer=installer,
        index_fetcher=fake.fetch_index,
        cache_ttl=cache_ttl,
    )


class TestIndexFetching:
    def test_fetch_and_cache(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        index = _make_index(
            [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=index, archives={})
        svc = _build_service(plugins_dir, core, fake)

        idx1 = svc.get_index()
        idx2 = svc.get_index()

        assert idx1 is idx2
        assert fake.index_calls == 1
        assert idx1.get_plugin("demo").latest_version == "1.0.0"

    def test_force_refresh_bypasses_cache(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        index = _make_index(
            [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=index, archives={})
        svc = _build_service(plugins_dir, core, fake)

        svc.get_index()
        svc.get_index(force_refresh=True)
        assert fake.index_calls == 2

    def test_cache_expires_after_ttl(
        self, plugins_dir: Path, core: CoreVersions, monkeypatch
    ):
        archive = _build_plugin_zip("demo")
        index = _make_index(
            [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=index, archives={})
        svc = _build_service(plugins_dir, core, fake, cache_ttl=10)

        now = {"t": 1000.0}
        monkeypatch.setattr(
            "app.services.plugin_marketplace.time.monotonic", lambda: now["t"]
        )

        svc.get_index()
        now["t"] += 5
        svc.get_index()
        assert fake.index_calls == 1
        now["t"] += 20
        svc.get_index()
        assert fake.index_calls == 2

    def test_fetcher_error_wrapped(self, plugins_dir: Path, core: CoreVersions):
        def boom(url: str) -> bytes:
            raise RuntimeError("connection refused")

        installer = PluginInstaller(
            plugins_dir=plugins_dir,
            core_versions=core,
            fetcher=lambda url: b"",
            pip_runner=lambda r, t, c: None,
        )
        svc = MarketplaceService(
            index_url="https://x/index.json",
            installer=installer,
            index_fetcher=boom,
        )
        with pytest.raises(IndexFetchError, match="connection refused"):
            svc.get_index()

    def test_invalid_json_raises_parse_error(
        self, plugins_dir: Path, core: CoreVersions
    ):
        fake = _Fake(index={"index_version": 1, "plugins": []}, archives={})
        fake.index_raw = b"{not json"
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(IndexParseError):
            svc.get_index()

    def test_unsupported_index_version(self, plugins_dir: Path, core: CoreVersions):
        fake = _Fake(
            index={"index_version": 99, "plugins": []},
            archives={},
        )
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(IndexParseError, match="unsupported index_version"):
            svc.get_index()

    def test_schema_violation_raises_parse_error(
        self, plugins_dir: Path, core: CoreVersions
    ):
        # checksum too short → pydantic validation error
        fake = _Fake(
            index={
                "index_version": 1,
                "plugins": [
                    {
                        "name": "demo",
                        "latest_version": "1.0.0",
                        "versions": [
                            {
                                "version": "1.0.0",
                                "download_url": "https://x",
                                "checksum_sha256": "too-short",
                                "size_bytes": 1,
                            }
                        ],
                        "display_name": "Demo",
                        "description": "d",
                        "author": "a",
                    }
                ],
            },
            archives={},
        )
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(IndexParseError):
            svc.get_index()


class TestLookups:
    def test_get_plugin_unknown(self, plugins_dir: Path, core: CoreVersions):
        fake = _Fake(index=_make_index([]), archives={})
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(PluginNotFoundError):
            svc.get_plugin("nope")

    def test_get_version_defaults_to_latest(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive1 = _build_plugin_zip("demo", "1.0.0")
        archive2 = _build_plugin_zip("demo", "2.0.0")
        index = _make_index(
            [
                ("demo", "1.0.0", archive1, "https://plugins.example/demo-1.bhplugin"),
                ("demo", "2.0.0", archive2, "https://plugins.example/demo-2.bhplugin"),
            ]
        )
        fake = _Fake(index=index, archives={})
        svc = _build_service(plugins_dir, core, fake)

        ver = svc.get_version_entry("demo")
        assert ver.version == "2.0.0"

    def test_get_version_unknown_version(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        index = _make_index(
            [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=index, archives={})
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(PluginNotFoundError, match="no version"):
            svc.get_version_entry("demo", "9.9.9")


class TestInstallDelegate:
    def test_install_landed(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        url = "https://plugins.example/demo.bhplugin"
        index = _make_index([("demo", "1.0.0", archive, url)])
        fake = _Fake(index=index, archives={url: archive})
        svc = _build_service(plugins_dir, core, fake)

        result = svc.install("demo")
        assert result.name == "demo"
        assert result.version == "1.0.0"
        assert (plugins_dir / "demo" / "plugin.json").exists()

    def test_uninstall_roundtrip(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        url = "https://plugins.example/demo.bhplugin"
        index = _make_index([("demo", "1.0.0", archive, url)])
        fake = _Fake(index=index, archives={url: archive})
        svc = _build_service(plugins_dir, core, fake)

        svc.install("demo")
        assert svc.uninstall("demo") is True
        assert not (plugins_dir / "demo").exists()

    def test_install_caches_index_read(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        url = "https://plugins.example/demo.bhplugin"
        index = _make_index([("demo", "1.0.0", archive, url)])
        fake = _Fake(index=index, archives={url: archive})
        svc = _build_service(plugins_dir, core, fake)

        svc.install("demo")
        svc.uninstall("demo")
        svc.install("demo")
        # Same cached index used for lookup on both installs.
        assert fake.index_calls == 1
