"""Pro-Connector-Zustaende aus sysfs, mit KWin-kompatiblen Namen."""
import pytest

from app.services.power.gpu.display_detector import (
    get_active_display_count_sync,
    get_connector_states,
    get_connector_states_sync,
)


def _connector(root, name: str, status: str, enabled: str) -> None:
    d = root / "sys" / "class" / "drm" / name
    d.mkdir(parents=True)
    (d / "status").write_text(status)
    (d / "enabled").write_text(enabled)


class TestConnectorStates:
    def test_strips_the_card_prefix_to_match_kwin_names(self, tmp_path):
        _connector(tmp_path, "card0-DP-3", "connected", "enabled")
        assert get_connector_states_sync(tmp_path) == {"DP-3": True}

    def test_a_dark_connector_is_false_not_absent(self, tmp_path):
        # DPMS-off: verbunden, aber es werden keine Pixel getrieben.
        _connector(tmp_path, "card0-DP-3", "connected", "disabled")
        assert get_connector_states_sync(tmp_path) == {"DP-3": False}

    def test_a_disconnected_connector_is_reported_as_dark(self, tmp_path):
        _connector(tmp_path, "card0-DP-1", "disconnected", "disabled")
        assert get_connector_states_sync(tmp_path) == {"DP-1": False}

    def test_a_writeback_connector_is_never_lit(self, tmp_path):
        # Gemessen auf BaluNode: status=unknown, enabled=disabled. Ein
        # Writeback-Connector ist kein Bildschirm.
        _connector(tmp_path, "card0-Writeback-1", "unknown", "disabled")
        assert get_connector_states_sync(tmp_path) == {"Writeback-1": False}

    def test_entries_that_are_not_connectors_are_skipped(self, tmp_path):
        drm = tmp_path / "sys" / "class" / "drm" / "renderD128"
        drm.mkdir(parents=True)
        _connector(tmp_path, "card0-DP-3", "connected", "enabled")
        assert list(get_connector_states_sync(tmp_path)) == ["DP-3"]

    def test_a_missing_drm_directory_yields_an_empty_map(self, tmp_path):
        assert get_connector_states_sync(tmp_path) == {}

    @pytest.mark.asyncio
    async def test_the_async_variant_agrees_with_the_sync_one(self, tmp_path):
        _connector(tmp_path, "card0-HDMI-A-1", "connected", "enabled")
        assert await get_connector_states(tmp_path) == get_connector_states_sync(tmp_path)

    def test_same_name_on_two_cards_both_lit_counts_as_two(self, tmp_path):
        # card0-DP-1 and card1-DP-1 both strip to "DP-1". The count must not
        # collapse two real, independently lit connectors into one.
        _connector(tmp_path, "card0-DP-1", "connected", "enabled")
        _connector(tmp_path, "card1-DP-1", "connected", "enabled")
        assert get_active_display_count_sync(tmp_path) == 2

    def test_same_name_on_two_cards_one_dark_counts_as_one_and_map_has_one_key(
        self, tmp_path
    ):
        _connector(tmp_path, "card0-DP-1", "connected", "enabled")
        _connector(tmp_path, "card1-DP-1", "disconnected", "disabled")
        assert get_active_display_count_sync(tmp_path) == 1
        states = get_connector_states_sync(tmp_path)
        assert list(states) == ["DP-1"]
