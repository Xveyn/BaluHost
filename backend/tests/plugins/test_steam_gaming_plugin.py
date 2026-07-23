"""The Steam gaming plugin's status pill."""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.plugins import run_plugin_menu_action
from app.plugins.installed import steam_gaming as plugin_module
from app.plugins.installed.steam_gaming import SteamGamingPlugin


@pytest.fixture(autouse=True)
def _clear_cache():
    plugin_module._CACHE.clear()
    yield
    plugin_module._CACHE.clear()


@pytest.fixture
def plugin():
    return SteamGamingPlugin()


@pytest.fixture
def prod_mode(monkeypatch):
    """`is_dev_mode` is its own settings FIELD, not derived from nas_mode."""
    monkeypatch.setattr(plugin_module.settings, "is_dev_mode", False)


@pytest.fixture
def dev_mode(monkeypatch):
    monkeypatch.setattr(plugin_module.settings, "is_dev_mode", True)


def test_declares_one_namespaced_pill(plugin):
    specs = plugin.get_status_pills()

    assert len(specs) == 1
    assert specs[0].id == "session"
    assert specs[0].icon == "Gamepad2"
    # Privacy-relevant default: showing what the owner is playing to every
    # NAS user (default_visibility="all") would be a silent regression this
    # test must catch.
    assert specs[0].default_visibility == "admin"


async def test_stays_silent_when_no_game_runs(plugin, monkeypatch, prod_mode):
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: None)

    assert await plugin.collect_status_pill("session", None) is None


async def test_reports_the_game_name_when_resolvable(plugin, monkeypatch, prod_mode):
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: "1449560")
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: "Metro Exodus")

    pill = await plugin.collect_status_pill("session", None)

    assert pill["value"] == "Metro Exodus"
    assert pill["label_text"] == "Gaming Session"
    assert pill["tone"] == "info"


async def test_falls_back_to_the_bare_label_for_an_unknown_game(plugin, monkeypatch, prod_mode):
    """Non-Steam shortcuts have no manifest — the pill still shows up."""
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: "3000000000")
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: None)

    pill = await plugin.collect_status_pill("session", None)

    assert pill["label_text"] == "Gaming Session"
    assert pill.get("value") is None


async def test_repeated_polls_within_the_ttl_scan_once(plugin, monkeypatch, prod_mode):
    calls = []

    def _counting_detect():
        calls.append(1)
        return "1449560"

    monkeypatch.setattr(plugin_module, "detect_running_app_id", _counting_detect)
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: "Metro Exodus")

    clock = {"now": 500.0}
    monkeypatch.setattr(plugin_module, "_monotonic", lambda: clock["now"])

    await plugin.collect_status_pill("session", None)
    await plugin.collect_status_pill("session", None)
    assert len(calls) == 1

    clock["now"] += plugin_module._CACHE_TTL_SECONDS + 0.1
    await plugin.collect_status_pill("session", None)
    assert len(calls) == 2


async def test_dev_mode_shows_a_mock_game(plugin, monkeypatch, dev_mode):
    """Windows dev boxes have no /proc — the strip should still render."""
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: None)

    pill = await plugin.collect_status_pill("session", None)

    assert pill["value"] == "Dev Mode Game"


async def test_an_unknown_pill_id_is_silent(plugin, dev_mode):
    assert await plugin.collect_status_pill("nope", None) is None


_ACTION = "gaming_mode"


def _patch_desktop(ok: bool, message: str = ""):
    service = MagicMock()
    service.enable = AsyncMock(return_value=(ok, message))
    return patch(
        "app.plugins.installed.steam_gaming.get_desktop_service",
        return_value=service,
    ), service


class TestGamingModeMenuItem:
    def test_manifest_declares_the_action(self):
        manifest = SteamGamingPlugin().get_ui_manifest()
        assert [item.id for item in manifest.menu_items] == [_ACTION]

    def test_item_carries_key_and_literal_fallback(self):
        item = SteamGamingPlugin().get_ui_manifest().menu_items[0]
        assert item.label_key == "menu_gaming_mode"
        assert item.label_text
        assert item.icon == "Gamepad2"

    def test_translations_cover_every_key_the_item_uses(self):
        plugin = SteamGamingPlugin()
        item = plugin.get_ui_manifest().menu_items[0]
        translations = plugin.get_translations()
        for lang in ("en", "de"):
            assert item.label_key in translations[lang]
            assert item.description_key in translations[lang]


class TestGamingModeAction:
    async def test_unknown_action_returns_none(self):
        assert await SteamGamingPlugin().run_menu_action("nope", db=None) is None

    async def test_turns_displays_on_then_opens_big_picture(self):
        desktop_patch, service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(True, "requested"),
        ) as launcher:
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        service.enable.assert_awaited_once()
        launcher.assert_called_once()
        assert result.ok is True
        assert result.message_key == "menu_gaming_mode_started"

    async def test_does_not_open_big_picture_on_dark_displays(self):
        desktop_patch, _service = _patch_desktop(False, "kscreen-doctor not found")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
        ) as launcher:
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        launcher.assert_not_called()
        assert result.ok is False
        assert result.message_key == "menu_displays_failed"

    async def test_reports_partial_success_when_steam_is_missing(self):
        desktop_patch, _service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(False, "steam binary not found"),
        ):
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        assert result.ok is False
        assert result.message_key == "menu_steam_failed"


class TestManifestAndRouteAgreeOnDeclaredActions:
    """Regression test for the manifest/get_menu_items split.

    The plugin only declares ``gaming_mode`` in get_ui_manifest() - that is
    what makes the entry render in the frontend menu. get_menu_items() is
    what the route validates the clicked action_id against. If those two
    ever disagree again, the entry renders and the click 404s - invisible to
    every test that drives run_menu_action() directly or mocks
    get_menu_items(). Use the real plugin and the real route function.
    """

    def test_every_manifest_menu_item_id_is_declared(self):
        plugin = SteamGamingPlugin()
        manifest_ids = {item.id for item in plugin.get_ui_manifest().menu_items}
        declared_ids = {item.id for item in plugin.get_menu_items()}

        assert manifest_ids, "the manifest must actually declare something for this test to mean anything"
        assert manifest_ids == declared_ids

    async def test_route_does_not_404_the_action_the_manifest_advertises(self):
        plugin = SteamGamingPlugin()
        manager = MagicMock()
        manager.get_plugin.return_value = plugin

        desktop_patch, _service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            return_value=(True, "requested"),
        ), patch("app.api.routes.plugins.user_limiter.enabled", False), patch(
            "app.api.routes.plugins.get_audit_logger_db"
        ):
            result = await run_plugin_menu_action(
                request=MagicMock(client=MagicMock(host="127.0.0.1")),
                response=MagicMock(),
                name="steam_gaming",
                action_id=_ACTION,
                db=MagicMock(),
                current_user=MagicMock(username="admin"),
                plugin_manager=manager,
            )

        assert result.ok is True


class TestGamingModeRunsLauncherOffTheEventLoop:
    """asyncio.wait_for() in the route can only interrupt awaits, not a
    blocking call made directly on the event loop thread - the launcher must
    run via asyncio.to_thread() or the route's timeout is decorative.
    """

    async def test_open_big_picture_runs_on_a_worker_thread(self):
        caller_thread_idents: list[int] = []

        def _record_ident_and_launch():
            caller_thread_idents.append(threading.get_ident())
            return True, "requested"

        desktop_patch, _service = _patch_desktop(True, "ok")
        with desktop_patch, patch(
            "app.plugins.installed.steam_gaming.open_big_picture",
            side_effect=_record_ident_and_launch,
        ):
            result = await SteamGamingPlugin().run_menu_action(_ACTION, db=None)

        assert result.ok is True
        assert caller_thread_idents, "open_big_picture was never called"
        assert caller_thread_idents[0] != threading.get_ident(), (
            "open_big_picture ran on the event loop's own thread - "
            "asyncio.to_thread() is missing, so the route's wait_for timeout "
            "cannot interrupt it"
        )
