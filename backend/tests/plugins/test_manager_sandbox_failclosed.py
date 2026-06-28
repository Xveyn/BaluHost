from pathlib import Path
from unittest.mock import patch

import pytest

from app.plugins.manager import PluginManager, DiscoveredPlugin


def _external_discovered(tmp_path: Path) -> DiscoveredPlugin:
    return DiscoveredPlugin(
        name="demo", path=tmp_path, source="external",
        manifest=object(),  # truthy manifest → external+manifest path
    )


@pytest.mark.asyncio
async def test_enable_external_fails_closed_when_hook_none(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=None), \
         patch("app.plugins.manager.get_audit_logger_db") as audit:
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is False
    assert "demo" not in mgr._sandboxes
    audit.return_value.log_security_event.assert_called_once()
    kwargs = audit.return_value.log_security_event.call_args.kwargs
    assert kwargs["action"] == "plugin_sandbox_hardening_unavailable"
    assert kwargs["success"] is False


@pytest.mark.asyncio
async def test_enable_external_uses_selected_hook(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)

    captured = {}

    class _FakeSupervisor:
        def __init__(self, name, path, *, capability_router=None, spawn_hook=None):
            captured["spawn_hook"] = spawn_hook
        async def start(self):
            return None

    sentinel_hook = lambda argv, cwd: None  # noqa: E731
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=sentinel_hook), \
         patch("app.plugins.sandbox.supervisor.SandboxSupervisor", _FakeSupervisor), \
         patch("app.plugins.sandbox.host_capabilities.build_capability_router", return_value=object()):
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is True
    assert captured["spawn_hook"] is sentinel_hook
    assert "demo" in mgr._sandboxes
