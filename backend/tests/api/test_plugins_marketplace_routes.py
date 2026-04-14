"""API integration tests for the plugin marketplace routes.

The real :func:`get_marketplace_service` builds a singleton against the
configured plugins directory. Tests override that dependency with a fake
service that uses an in-memory marketplace + a temporary plugins directory
so no network or pip is involved.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plugins.core_versions import CoreVersions
from app.plugins.installer import PluginInstaller
from app.services.plugin_marketplace import (
    MarketplaceService,
    get_marketplace_service,
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


def _make_index(entries: list[tuple[str, str, bytes, str]]) -> dict:
    grouped: Dict[str, list] = {}
    for name, version, archive, url in entries:
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
                "latest_version": versions[-1]["version"],
                "versions": versions,
                "display_name": name.title(),
                "description": "test",
                "author": "tests",
                "category": "general",
            }
            for name, versions in grouped.items()
        ],
    }


def _build_service(plugins_dir: Path, *, index: dict, archives: Dict[str, bytes]):
    core = CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="linux_x86_64",
        abi="cp311",
        packages={},
    )
    installer = PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core,
        fetcher=lambda url: archives[url],
        pip_runner=lambda r, t, c: t.mkdir(parents=True, exist_ok=True),
    )
    index_bytes = json.dumps(index).encode()
    return MarketplaceService(
        index_url="https://plugins.example/index.json",
        installer=installer,
        index_fetcher=lambda url: index_bytes,
    )


@pytest.fixture
def override_marketplace(tmp_path: Path):
    """Yield (plugins_dir, attach(service_builder))."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    created: dict = {}

    def _attach(index: dict, archives: Dict[str, bytes]) -> MarketplaceService:
        service = _build_service(plugins_dir, index=index, archives=archives)
        created["svc"] = service
        app.dependency_overrides[get_marketplace_service] = lambda: service
        return service

    yield plugins_dir, _attach
    app.dependency_overrides.pop(get_marketplace_service, None)


class TestListMarketplace:
    def test_requires_admin(self, client: TestClient, user_headers: dict):
        response = client.get("/api/plugins/marketplace", headers=user_headers)
        assert response.status_code == 403

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/plugins/marketplace")
        assert response.status_code == 401

    def test_returns_index(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        archive = _build_plugin_zip("demo")
        attach(
            _make_index(
                [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
            ),
            {},
        )

        response = client.get("/api/plugins/marketplace", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["index_version"] == 1
        assert len(data["plugins"]) == 1
        assert data["plugins"][0]["name"] == "demo"
        assert data["plugins"][0]["latest_version"] == "1.0.0"
        assert data["plugins"][0]["versions"][0]["checksum_sha256"]

    def test_refresh_query_invalidates_cache(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        archive = _build_plugin_zip("demo")
        svc = attach(
            _make_index(
                [("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]
            ),
            {},
        )

        call_count = {"n": 0}
        original = svc._fetch

        def counted(url):
            call_count["n"] += 1
            return original(url)

        svc._fetch = counted
        client.get("/api/plugins/marketplace", headers=admin_headers)
        client.get("/api/plugins/marketplace", headers=admin_headers)
        assert call_count["n"] == 1
        client.get(
            "/api/plugins/marketplace?refresh=true", headers=admin_headers
        )
        assert call_count["n"] == 2


class TestInstallPlugin:
    def test_install_happy_path(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        plugins_dir, attach = override_marketplace
        archive = _build_plugin_zip("demo")
        url = "https://plugins.example/demo.bhplugin"
        attach(_make_index([("demo", "1.0.0", archive, url)]), {url: archive})

        response = client.post(
            "/api/plugins/marketplace/demo/install",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["name"] == "demo"
        assert data["version"] == "1.0.0"
        assert Path(data["installed_path"]).exists()
        assert (plugins_dir / "demo" / "plugin.json").exists()

    def test_install_requires_admin(
        self,
        client: TestClient,
        user_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        attach(_make_index([]), {})
        response = client.post(
            "/api/plugins/marketplace/demo/install",
            json={},
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_install_unknown_plugin_returns_404(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        attach(_make_index([]), {})
        response = client.post(
            "/api/plugins/marketplace/nope/install",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_install_specific_version(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        plugins_dir, attach = override_marketplace
        a1 = _build_plugin_zip("demo", "1.0.0")
        a2 = _build_plugin_zip("demo", "2.0.0")
        url1 = "https://plugins.example/demo-1.bhplugin"
        url2 = "https://plugins.example/demo-2.bhplugin"
        attach(
            _make_index(
                [
                    ("demo", "1.0.0", a1, url1),
                    ("demo", "2.0.0", a2, url2),
                ]
            ),
            {url1: a1, url2: a2},
        )

        response = client.post(
            "/api/plugins/marketplace/demo/install",
            json={"version": "1.0.0"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["version"] == "1.0.0"


class TestUninstallPlugin:
    def test_uninstall_happy_path(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        plugins_dir, attach = override_marketplace
        archive = _build_plugin_zip("demo")
        url = "https://plugins.example/demo.bhplugin"
        attach(_make_index([("demo", "1.0.0", archive, url)]), {url: archive})

        install = client.post(
            "/api/plugins/marketplace/demo/install",
            json={},
            headers=admin_headers,
        )
        assert install.status_code == 201

        response = client.delete(
            "/api/plugins/marketplace/demo", headers=admin_headers
        )
        assert response.status_code == 204
        assert not (plugins_dir / "demo").exists()

    def test_uninstall_missing_returns_404(
        self,
        client: TestClient,
        admin_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        attach(_make_index([]), {})

        response = client.delete(
            "/api/plugins/marketplace/nope", headers=admin_headers
        )
        assert response.status_code == 404

    def test_uninstall_requires_admin(
        self,
        client: TestClient,
        user_headers: dict,
        override_marketplace,
    ):
        _, attach = override_marketplace
        attach(_make_index([]), {})
        response = client.delete(
            "/api/plugins/marketplace/demo", headers=user_headers
        )
        assert response.status_code == 403
