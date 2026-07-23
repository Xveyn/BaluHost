"""PluginGateMiddleware reads the shared enablement cache (#448)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.middleware import plugin_gate
from app.services import plugin_enablement as pe


def _grant(permissions=None, scopes=None) -> dict:
    """Build a ``_fetch()``-shaped cache entry for one plugin.

    NOTE: the brief's Step 1 code block shows ``{"demo": []}`` /
    ``{"demo": ["files.read"]}`` for these patches - that shape predates the
    Task 3 extension that added ``granted_api_scopes`` to ``_fetch()``'s
    return value. Using the stale shape here would make ``enabled_plugins()``
    raise (``entry["granted_permissions"]`` on a plain list), which the task
    brief's own correction note calls out explicitly.
    """
    return {
        "granted_permissions": list(permissions or []),
        "granted_api_scopes": list(scopes or []),
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


def _request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    return request


async def _dispatch(path: str):
    middleware = plugin_gate.PluginGateMiddleware(app=MagicMock())

    async def _call_next(_request):
        return "PASSED"

    return await middleware.dispatch(_request(path), _call_next)


class TestGateUsesTheSharedCache:
    async def test_enabled_plugin_passes(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant()}), \
             patch.object(plugin_gate.PluginManager, "get_instance") as manager:
            manager.return_value.get_required_permissions.return_value = []
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result == "PASSED"

    async def test_disabled_plugin_is_403(self):
        with patch.object(pe, "_fetch", return_value={}):
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 403

    async def test_missing_permission_is_403(self):
        with patch.object(pe, "_fetch", return_value={"demo": _grant(["files.read"])}), \
             patch.object(plugin_gate.PluginManager, "get_instance") as manager:
            manager.return_value.get_required_permissions.return_value = ["files.write"]
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 403

    async def test_db_failure_fails_closed(self):
        """Opposite direction to the display path: no state, no entry."""
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            result = await _dispatch("/api/plugins/demo/menu-actions/go")
        assert result.status_code == 500

    async def test_management_routes_still_bypass_the_gate(self):
        with patch.object(pe, "_fetch", side_effect=AssertionError("should not be consulted")):
            assert await _dispatch("/api/plugins/demo/toggle") == "PASSED"
            assert await _dispatch("/api/plugins/ui/manifest") == "PASSED"
