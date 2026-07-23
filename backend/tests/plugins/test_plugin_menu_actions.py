"""Tests for the plugin menu-action extension point."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    MenuActionResult,
    PluginBase,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
)


class TestPluginMenuItem:
    def test_minimal_item(self):
        item = PluginMenuItem(
            id="gaming_mode", icon="Gamepad2",
            label_key="menu_gaming_mode", label_text="Gaming Mode",
        )
        assert item.tone == "neutral"
        assert item.order == 100
        assert item.description_key is None

    @pytest.mark.parametrize("bad_id", ["Gaming", "gaming-mode", "gaming.mode", "../etc", "", "a b"])
    def test_rejects_ids_outside_the_namespace(self, bad_id):
        with pytest.raises(ValidationError):
            PluginMenuItem(
                id=bad_id, icon="Gamepad2",
                label_key="k", label_text="t",
            )

    def test_has_no_admin_only_field(self):
        """The core decides who may run an action - a plugin must not widen it."""
        assert "admin_only" not in PluginMenuItem.model_fields


class TestMenuActionResult:
    def test_message_text_is_required(self):
        with pytest.raises(ValidationError):
            MenuActionResult(ok=True)

    def test_key_is_optional(self):
        result = MenuActionResult(ok=False, message_text="boom")
        assert result.message_key is None


class _BarePlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bare", display_name="Bare", version="1.0.0",
            description="", author="test",
        )


class TestPluginBaseDefaults:
    def test_no_menu_items_by_default(self):
        assert _BarePlugin().get_menu_items() == []

    async def test_run_menu_action_returns_none_by_default(self):
        assert await _BarePlugin().run_menu_action("anything", db=None) is None

    def test_ui_manifest_menu_items_default_empty(self):
        assert PluginUIManifest().menu_items == []


from unittest.mock import MagicMock

from app.plugins.manager import PluginManager
from app.schemas.plugin import PluginUIInfo, PluginUIManifestResponse


def _plugin_with_menu(name: str = "demo") -> MagicMock:
    plugin = MagicMock()
    plugin.metadata.display_name = "Demo"
    plugin.get_ui_manifest.return_value = PluginUIManifest(
        enabled=True,
        menu_items=[PluginMenuItem(
            id="do_it", icon="Zap", label_key="menu_do_it", label_text="Do it",
        )],
    )
    plugin.get_translations.return_value = {"en": {"menu_do_it": "Do it"}}
    return plugin


class TestManifestCarriesMenuItems:
    def test_enabled_plugin_menu_items_reach_the_manifest(self, tmp_path):
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": _plugin_with_menu()}
        manager._enabled = {"demo"}

        entry = manager.get_ui_manifest()["plugins"][0]

        assert entry["menu_items"] == [{
            "id": "do_it", "icon": "Zap",
            "label_key": "menu_do_it", "label_text": "Do it",
            "description_key": None, "description_text": None,
            "tone": "neutral", "order": 100,
        }]

    def test_plugin_without_menu_items_yields_empty_list(self, tmp_path):
        plugin = _plugin_with_menu()
        plugin.get_ui_manifest.return_value = PluginUIManifest(enabled=True)
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": plugin}
        manager._enabled = {"demo"}

        assert manager.get_ui_manifest()["plugins"][0]["menu_items"] == []

    def test_schema_defaults_to_empty(self):
        info = PluginUIInfo(name="demo", display_name="Demo")
        assert info.menu_items == []


import asyncio
import inspect
import time
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.deps import get_current_admin
from app.api.routes.plugins import (
    PLUGIN_MENU_ACTION_TIMEOUT_SECONDS,
    run_plugin_menu_action,
)


def _declaring_plugin(action_id: str = "do_it") -> MagicMock:
    plugin = MagicMock()
    plugin.get_menu_items.return_value = [PluginMenuItem(
        id=action_id, icon="Zap", label_key="k", label_text="Do it",
    )]
    return plugin


async def _call(plugin, name: str = "demo", action_id: str = "do_it"):
    manager = MagicMock()
    manager.get_plugin.return_value = plugin
    # Bypass slowapi's isinstance(Request) check for direct (non-ASGI)
    # coroutine calls - see test_dashboard_panel.py for the established
    # per-call pattern this mirrors.
    with patch("app.api.routes.plugins.user_limiter.enabled", False):
        return await run_plugin_menu_action(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            response=MagicMock(),
            name=name,
            action_id=action_id,
            db=MagicMock(),
            current_user=MagicMock(username="admin"),
            plugin_manager=manager,
        )


class TestMenuActionRouteRequiresAdmin:
    def test_current_user_dependency_is_get_current_admin(self):
        """Pin the admin gate on the route signature itself.

        Every other test here calls the route function directly with a
        fabricated ``current_user``, so FastAPI's dependency injection is
        never exercised - a downgrade to ``get_current_user`` would leave
        every other test green. Assert the ``Depends`` object actually
        wraps ``get_current_admin``.
        """
        sig = inspect.signature(run_plugin_menu_action)
        dependency = sig.parameters["current_user"].default
        assert dependency.dependency is get_current_admin


class TestMenuActionRoute:
    async def test_unknown_plugin_is_404(self):
        manager = MagicMock()
        manager.get_plugin.return_value = None
        with patch("app.api.routes.plugins.user_limiter.enabled", False), \
             pytest.raises(HTTPException) as exc:
            await run_plugin_menu_action(
                request=MagicMock(), response=MagicMock(),
                name="nope", action_id="do_it", db=MagicMock(),
                current_user=MagicMock(username="admin"), plugin_manager=manager,
            )
        assert exc.value.status_code == 404

    async def test_undeclared_action_is_404_and_never_dispatches(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await _call(plugin, action_id="something_else")
        assert exc.value.status_code == 404
        plugin.run_menu_action.assert_not_awaited()

    async def test_get_menu_items_raising_is_404_and_never_dispatches(self):
        """A plugin that cannot even declare its actions must not 500.

        Fails closed the same way an unknown action does: 404, no dispatch.
        """
        plugin = MagicMock()
        plugin.get_menu_items.side_effect = RuntimeError("boom")
        plugin.run_menu_action = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await _call(plugin)
        assert exc.value.status_code == 404
        plugin.run_menu_action.assert_not_awaited()

    async def test_happy_path_returns_result_and_audits_success(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(
            return_value=MenuActionResult(ok=True, message_key="ok_key", message_text="done")
        )
        with patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            result = await _call(plugin)
        assert (result.ok, result.message_key, result.message_text) == (True, "ok_key", "done")
        kwargs = audit.return_value.log_event.call_args.kwargs
        assert kwargs["event_type"] == "PLUGIN"
        assert kwargs["action"] == "menu_action"
        assert kwargs["resource"] == "demo:do_it"
        assert kwargs["success"] is True

    async def test_raising_action_stays_200_with_generic_message(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(side_effect=RuntimeError("secret path /opt/baluhost"))
        with patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            result = await _call(plugin)
        assert result.ok is False
        assert "secret path" not in result.message_text
        assert audit.return_value.log_event.call_args.kwargs["success"] is False

    async def test_hanging_action_is_cut_off_by_the_timeout(self):
        async def _hang(action_id, db):
            await asyncio.sleep(60)

        plugin = _declaring_plugin()
        plugin.run_menu_action = _hang
        with patch("app.api.routes.plugins.PLUGIN_MENU_ACTION_TIMEOUT_SECONDS", 0.01), \
             patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            started = time.monotonic()
            result = await _call(plugin)
            elapsed = time.monotonic() - started
        # Discriminating against a deleted wait_for(): without it, _hang
        # would run its full 60s sleep, return None, and fall into the
        # "returned None" branch - also ok=False, but slow and with a
        # different message. Pin both the message only the timeout branch
        # produces and a wall-clock bound well under the 60s sleep.
        assert result.message_text == "Action timed out"
        assert result.ok is False
        assert elapsed < 5.0
        assert audit.return_value.log_event.call_args.kwargs["success"] is False

    async def test_plugin_returning_none_despite_declaration_is_not_ok(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(return_value=None)
        with patch("app.api.routes.plugins.get_audit_logger_db"):
            result = await _call(plugin)
        assert result.ok is False

    async def test_plugin_returning_non_result_type_is_not_ok_and_no_500(self):
        """A plugin returning a dict/str instead of MenuActionResult must not 500.

        model_dump() on a plain dict/str would raise inside the route -
        guard against any non-MenuActionResult return, not only None.
        """
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(return_value={"ok": True, "message_text": "not a model"})
        with patch("app.api.routes.plugins.get_audit_logger_db") as audit:
            result = await _call(plugin)
        assert result.ok is False
        assert audit.return_value.log_event.call_args.kwargs["success"] is False

    def test_timeout_pins_the_spec_value(self):
        """kscreen-doctor carries a 30s subprocess timeout of its own."""
        assert PLUGIN_MENU_ACTION_TIMEOUT_SECONDS == 20.0


from app.middleware.plugin_gate import _is_management_route


class TestMenuActionIsGatedByMiddleware:
    def test_menu_action_path_is_not_a_management_route(self):
        """A disabled plugin must not be able to run actions.

        Management routes (toggle/config/ui) stay reachable while a plugin is
        disabled - menu actions must NOT, or disabling a plugin would leave its
        actions live.
        """
        assert _is_management_route("/menu-actions/gaming_mode") is False

    def test_management_routes_still_bypass(self):
        assert _is_management_route("/toggle") is True
        assert _is_management_route("/config") is True


class TestDisabledPluginIsRefusedInTheRouteToo:
    """The route must not lean on PluginGateMiddleware alone.

    disable_plugin() drops the name from _enabled but leaves the instance in
    _plugins, so get_plugin() still hands one back. Without a local check the
    only thing standing between a disabled plugin and execution is a path
    prefix in middleware plus a 5s DB cache - and a router move or prefix
    change would defeat it with every test still green.
    """

    async def test_loaded_but_disabled_plugin_is_refused(self):
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock()
        manager = MagicMock()
        manager.get_plugin.return_value = plugin
        manager.is_enabled.return_value = False

        with patch("app.api.routes.plugins.user_limiter.enabled", False):
            with pytest.raises(HTTPException) as exc:
                await run_plugin_menu_action(
                    request=MagicMock(), response=MagicMock(),
                    name="demo", action_id="do_it", db=MagicMock(),
                    current_user=MagicMock(username="admin"), plugin_manager=manager,
                )

        assert exc.value.status_code == 404
        plugin.run_menu_action.assert_not_awaited()

    async def test_enabled_plugin_still_runs(self):
        """Pins that the new check refuses only the disabled case."""
        plugin = _declaring_plugin()
        plugin.run_menu_action = AsyncMock(
            return_value=MenuActionResult(ok=True, message_text="done")
        )
        manager = MagicMock()
        manager.get_plugin.return_value = plugin
        manager.is_enabled.return_value = True

        with patch("app.api.routes.plugins.user_limiter.enabled", False), \
             patch("app.api.routes.plugins.get_audit_logger_db"):
            result = await run_plugin_menu_action(
                request=MagicMock(client=MagicMock(host="127.0.0.1")),
                response=MagicMock(), name="demo", action_id="do_it",
                db=MagicMock(), current_user=MagicMock(username="admin"),
                plugin_manager=manager,
            )

        assert result.ok is True


class TestManifestEnabledFlagIsRespected:
    def test_disabled_manifest_declares_no_actions(self):
        """A manifest with enabled=False advertises nothing to the frontend.

        PluginManager.get_ui_manifest() filters on that flag, so if the
        derivation ignored it, a plugin could have a dispatchable action that
        is invisible in the UI - the same two-sites drift in reverse.
        """
        class _Plugin(_BarePlugin):
            def get_ui_manifest(self):
                return PluginUIManifest(
                    enabled=False,
                    menu_items=[PluginMenuItem(
                        id="hidden", icon="Zap", label_key="k", label_text="Hidden",
                    )],
                )

        assert _Plugin().get_menu_items() == []

    def test_enabled_manifest_declares_its_actions(self):
        class _Plugin(_BarePlugin):
            def get_ui_manifest(self):
                return PluginUIManifest(
                    enabled=True,
                    menu_items=[PluginMenuItem(
                        id="shown", icon="Zap", label_key="k", label_text="Shown",
                    )],
                )

        assert [item.id for item in _Plugin().get_menu_items()] == ["shown"]


class TestManifestResponseModelCarriesMenuItems:
    def test_menu_items_survive_the_response_model(self, tmp_path):
        """Nothing else asserts this leg.

        The manager test checks its raw dict and the frontend tests feed
        hand-written objects - so dropping menu_items from PluginUIInfo would
        keep every test green while the menu entry vanishes in production.
        """
        manager = PluginManager(plugins_dir=tmp_path)
        manager._plugins = {"demo": _plugin_with_menu()}
        manager._enabled = {"demo"}

        response = PluginUIManifestResponse(**manager.get_ui_manifest())

        assert [item.id for item in response.plugins[0].menu_items] == ["do_it"]


class TestMenuActionThroughTheRealStack:
    """The one test that goes through the ASGI stack instead of around it.

    Every other route test here calls the endpoint function directly, so the
    middleware never runs. That is exactly where the "a disabled plugin cannot
    run actions" invariant lives - and it was asserted only against
    _is_management_route()'s return value, a helper, not the gate.

    What is stubbed: PluginGateMiddleware reads plugin state through its own
    SessionLocal(), which points at the app's database, not the in-memory one
    the test fixtures build - so the DB lookup is replaced. Everything else is
    real: middleware dispatch, path matching, routing, auth, the route.
    """

    def _post(self, client, headers):
        return client.post(
            "/api/plugins/demo/menu-actions/do_it", headers=headers
        )

    def test_disabled_plugin_is_refused_by_the_stack(self, client, admin_headers):
        from app.middleware import plugin_gate

        plugin_gate._plugin_cache.clear()
        with patch.object(
            plugin_gate, "_fetch_plugin_status", return_value=(False, [])
        ):
            response = self._post(client, admin_headers)

        assert response.status_code == 403
        assert "disabled" in response.json()["detail"]

    def test_enabled_plugin_reaches_the_route(self, client, admin_headers):
        """Discriminates the 403 above: with the same request and an enabled
        plugin the gate lets it through, and the 404 comes from the route
        itself (no such plugin loaded in this process)."""
        from app.middleware import plugin_gate

        plugin_gate._plugin_cache.clear()
        with patch.object(
            plugin_gate, "_fetch_plugin_status", return_value=(True, [])
        ):
            response = self._post(client, admin_headers)

        assert response.status_code == 404

    def test_non_admin_is_refused_on_an_enabled_plugin(self, client, user_headers):
        from app.middleware import plugin_gate

        plugin_gate._plugin_cache.clear()
        with patch.object(
            plugin_gate, "_fetch_plugin_status", return_value=(True, [])
        ):
            response = self._post(client, user_headers)

        assert response.status_code == 403
        assert "disabled" not in response.json()["detail"]
