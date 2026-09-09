"""Tests for the gaming suspend suppressor.

Companion to test_presence_service.py: presence answers "is a human in the web
app?", this module answers "is a human at the box, playing?". Both feed the
same suspend gates in SleepManagerService.
"""
from unittest.mock import patch

from app.models.sleep import SleepConfig
from app.services.power import gaming_presence


def _config(block_in_gaming_mode=True):
    """A SleepConfig carrying only what this module reads."""
    return SleepConfig(id=1, block_suspend_in_gaming_mode=block_in_gaming_mode)


def test_detector_import_actually_resolved():
    """Guards the import cycle gaming_presence <-> steam_gaming/__init__.

    The plugin package imports this module for its display helper. If that
    import were made at module level, this import would lose the cycle and
    `detect_running_app_id` would fall back to None — leaving the fix in place
    but permanently inert, with only a log line to show for it.
    """
    assert gaming_presence.detect_running_app_id is not None


class TestGameIsRunning:
    def test_true_when_detector_reports_an_app_id(self):
        with patch.object(gaming_presence, "detect_running_app_id", return_value="690790"):
            assert gaming_presence.game_is_running() is True

    def test_false_when_detector_reports_nothing(self):
        with patch.object(gaming_presence, "detect_running_app_id", return_value=None):
            assert gaming_presence.game_is_running() is False

    def test_false_when_detector_is_unavailable(self):
        """Plugin removed: fail toward energy saving, like the presence check."""
        with patch.object(gaming_presence, "detect_running_app_id", None):
            assert gaming_presence.game_is_running() is False

    def test_false_when_detector_raises(self):
        with patch.object(
            gaming_presence, "detect_running_app_id", side_effect=OSError("no /proc")
        ):
            assert gaming_presence.game_is_running() is False

    def test_dev_mode_does_not_invent_a_game(self):
        """Must read the raw detector, not detection.current_app_id().

        The latter substitutes DEV_APP_ID on a box without /proc, which would
        make every Windows dev machine claim a game is running and never sleep.
        """
        with patch.object(gaming_presence.settings, "is_dev_mode", True), \
             patch.object(gaming_presence, "detect_running_app_id", return_value=None):
            assert gaming_presence.game_is_running() is False


class TestGamingModeOnScreen:
    def test_true_when_marker_set_and_a_display_is_lit(self):
        with patch.object(gaming_presence, "_marker_is_active", return_value=True), \
             patch.object(gaming_presence, "displays_on", return_value=True):
            assert gaming_presence.gaming_mode_on_screen() is True

    def test_false_when_marker_set_but_screens_are_dark(self):
        """A stale marker must not block suspend forever."""
        with patch.object(gaming_presence, "_marker_is_active", return_value=True), \
             patch.object(gaming_presence, "displays_on", return_value=False):
            assert gaming_presence.gaming_mode_on_screen() is False

    def test_false_when_marker_absent(self):
        with patch.object(gaming_presence, "_marker_is_active", return_value=False), \
             patch.object(gaming_presence, "displays_on", return_value=True):
            assert gaming_presence.gaming_mode_on_screen() is False


class TestBlocksSuspend:
    def test_running_game_blocks_even_with_the_setting_off(self):
        """The game block is unconditional; the setting only governs Big Picture."""
        with patch.object(gaming_presence, "game_is_running", return_value=True), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=False):
            assert gaming_presence.blocks_suspend(_config(block_in_gaming_mode=False)) is True

    def test_gaming_mode_blocks_when_the_setting_is_on(self):
        with patch.object(gaming_presence, "game_is_running", return_value=False), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=True):
            assert gaming_presence.blocks_suspend(_config(block_in_gaming_mode=True)) is True

    def test_gaming_mode_does_not_block_when_the_setting_is_off(self):
        with patch.object(gaming_presence, "game_is_running", return_value=False), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=True):
            assert gaming_presence.blocks_suspend(_config(block_in_gaming_mode=False)) is False

    def test_idle_box_does_not_block(self):
        with patch.object(gaming_presence, "game_is_running", return_value=False), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=False):
            assert gaming_presence.blocks_suspend(_config()) is False

    def test_unset_column_is_read_as_the_database_default(self):
        """Configs built without the column (older tests) must behave as `true`."""
        with patch.object(gaming_presence, "game_is_running", return_value=False), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=True):
            assert gaming_presence.blocks_suspend(SleepConfig(id=1)) is True

    def test_missing_config_still_blocks_gaming_mode(self):
        with patch.object(gaming_presence, "game_is_running", return_value=False), \
             patch.object(gaming_presence, "gaming_mode_on_screen", return_value=True):
            assert gaming_presence.blocks_suspend(None) is True
