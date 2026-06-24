"""Tests that GET /api/plugins/ui/manifest includes granted_api_scopes per plugin.

Patching strategy
-----------------
The endpoint calls two things we need to control:

1. ``plugin_manager.get_ui_manifest()`` — patched to return a manifest dict with
   one fake plugin entry so the response always has at least one item.
2. ``plugin_service.get_installed_plugin`` — patched to return a MagicMock record
   whose ``granted_api_scopes`` attribute is a known list so we can assert the
   value end-to-end.

Both patches are applied at their *definition* sites so FastAPI's dependency
injection picks up the stub.  The ``/ui/manifest`` route sits between
``/permissions`` and ``/{name}`` (note: ``/ui/manifest`` must be registered
before ``/{name}`` to avoid being swallowed by the dynamic segment — it is).

Assertions are UNCONDITIONAL — ``assert resp.status_code == 200`` at the top;
never inside an ``if`` that can vacuously pass.

Auth: uses the ``client`` and ``admin_headers`` fixtures from conftest.py, which
set up an in-memory DB with an admin user and provide a valid Bearer token.
"""
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_manifest():
    """Return a minimal manifest dict the endpoint can parse into PluginUIManifestResponse."""
    return {
        "plugins": [
            {
                "name": "storage_analytics",
                "display_name": "Storage Analytics",
                "nav_items": [],
                "bundle_path": "ui/bundle.js",
                "styles_path": None,
                "dashboard_widgets": [],
                "translations": None,
            }
        ]
    }


def _make_fake_db_record(scopes: list):
    """Return a MagicMock InstalledPlugin with the given granted_api_scopes."""
    record = MagicMock()
    record.granted_api_scopes = scopes
    return record


# ---------------------------------------------------------------------------
# Test: scopes from DB record land on each manifest item
# ---------------------------------------------------------------------------

def test_ui_manifest_items_have_granted_api_scopes_from_db(client, admin_headers):
    """Each plugin in the ui/manifest response must carry granted_api_scopes (a list).

    The test uses a fake manifest with one plugin and a fake DB record with two
    known scopes.  The endpoint must merge them and return the scopes in the JSON.
    """
    expected_scopes = ["api:files:read", "api:system:read"]

    fake_manifest = _make_fake_manifest()
    fake_record = _make_fake_db_record(expected_scopes)

    with patch(
        "app.plugins.manager.PluginManager.get_ui_manifest",
        return_value=fake_manifest,
    ), patch(
        "app.services.plugin_service.get_installed_plugin",
        return_value=fake_record,
    ):
        resp = client.get("/api/plugins/ui/manifest", headers=admin_headers)

    # UNCONDITIONAL — must be 200 before any other assertion
    assert resp.status_code == 200, (
        f"Expected 200 from GET /api/plugins/ui/manifest; got {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )

    data = resp.json()
    plugins = data.get("plugins", [])
    assert len(plugins) >= 1, "Expected at least one plugin in manifest response"

    for entry in plugins:
        assert "granted_api_scopes" in entry, (
            f"Plugin entry missing 'granted_api_scopes' key: {entry}"
        )
        assert isinstance(entry["granted_api_scopes"], list), (
            f"'granted_api_scopes' must be a list, got: {type(entry['granted_api_scopes'])}"
        )

    # Verify the actual scopes flow through from the DB record
    first_plugin = plugins[0]
    assert first_plugin["granted_api_scopes"] == expected_scopes, (
        f"Expected scopes {expected_scopes!r}, got {first_plugin['granted_api_scopes']!r}"
    )


def test_ui_manifest_items_have_empty_scopes_when_no_db_record(client, admin_headers):
    """When no DB record exists for a plugin, granted_api_scopes must be [] (not absent/null)."""
    fake_manifest = _make_fake_manifest()

    with patch(
        "app.plugins.manager.PluginManager.get_ui_manifest",
        return_value=fake_manifest,
    ), patch(
        "app.services.plugin_service.get_installed_plugin",
        return_value=None,
    ):
        resp = client.get("/api/plugins/ui/manifest", headers=admin_headers)

    assert resp.status_code == 200, (
        f"Expected 200 from GET /api/plugins/ui/manifest; got {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )

    data = resp.json()
    plugins = data.get("plugins", [])
    assert len(plugins) >= 1, "Expected at least one plugin in manifest response"

    for entry in plugins:
        assert "granted_api_scopes" in entry, (
            f"Plugin entry missing 'granted_api_scopes' key when no DB record: {entry}"
        )
        assert entry["granted_api_scopes"] == [], (
            f"Expected empty list when no DB record, got: {entry['granted_api_scopes']!r}"
        )


def test_ui_manifest_includes_min_runtime_abi(client, admin_headers):
    """Every plugin entry in the ui/manifest response must carry a min_runtime_abi key.

    Key-presence check: load_manifest raises (no plugin.json on disk), so
    min_runtime_abi falls back to None — the key must still be present.
    """
    fake_manifest = _make_fake_manifest()
    fake_record = _make_fake_db_record([])

    with patch(
        "app.plugins.manager.PluginManager.get_ui_manifest",
        return_value=fake_manifest,
    ), patch(
        "app.services.plugin_service.get_installed_plugin",
        return_value=fake_record,
    ):
        resp = client.get("/api/plugins/ui/manifest", headers=admin_headers)

    assert resp.status_code == 200, (
        f"Expected 200 from GET /api/plugins/ui/manifest; got {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )

    data = resp.json()
    plugins = data.get("plugins", [])
    assert len(plugins) >= 1, "Expected at least one plugin in manifest response"

    for entry in plugins:
        assert "min_runtime_abi" in entry, (
            f"Plugin entry missing 'min_runtime_abi' key: {entry}"
        )


def test_ui_manifest_min_runtime_abi_happy_path(client, admin_headers):
    """When load_manifest succeeds and returns min_runtime_abi=1, the manifest
    item must carry that exact value (not None).

    Patches load_manifest at the route-module level (hoisted top-level import).
    """
    fake_manifest = _make_fake_manifest()
    fake_record = _make_fake_db_record([])

    fake_plugin_manifest = MagicMock()
    fake_plugin_manifest.min_runtime_abi = 1

    with patch(
        "app.plugins.manager.PluginManager.get_ui_manifest",
        return_value=fake_manifest,
    ), patch(
        "app.services.plugin_service.get_installed_plugin",
        return_value=fake_record,
    ), patch(
        "app.api.routes.plugins.load_manifest",
        return_value=fake_plugin_manifest,
    ):
        resp = client.get("/api/plugins/ui/manifest", headers=admin_headers)

    assert resp.status_code == 200, (
        f"Expected 200 from GET /api/plugins/ui/manifest; got {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )

    data = resp.json()
    plugins = data.get("plugins", [])
    assert len(plugins) >= 1, "Expected at least one plugin in manifest response"

    first_plugin = plugins[0]
    assert "min_runtime_abi" in first_plugin, (
        f"Plugin entry missing 'min_runtime_abi' key: {first_plugin}"
    )
    assert first_plugin["min_runtime_abi"] == 1, (
        f"Expected min_runtime_abi=1 from patched manifest, got: {first_plugin['min_runtime_abi']!r}"
    )
