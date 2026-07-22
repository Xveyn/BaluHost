"""The Steam gaming plugin's status pill."""

import pytest

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
