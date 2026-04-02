"""Tests for sleep window overlap check."""
import pytest
from app.services.sync.sleep_check import is_time_in_sleep_window


class TestIsTimeInSleepWindow:
    """Test the time-in-sleep-window helper."""

    def test_normal_window_inside(self):
        """14:00-16:00 window, sync at 15:00 -> conflict."""
        assert is_time_in_sleep_window("15:00", "14:00", "16:00") is True

    def test_normal_window_outside_before(self):
        """14:00-16:00 window, sync at 13:00 -> no conflict."""
        assert is_time_in_sleep_window("13:00", "14:00", "16:00") is False

    def test_normal_window_outside_after(self):
        """14:00-16:00 window, sync at 17:00 -> no conflict."""
        assert is_time_in_sleep_window("17:00", "14:00", "16:00") is False

    def test_overnight_window_inside_before_midnight(self):
        """23:00-06:00 window, sync at 23:30 -> conflict."""
        assert is_time_in_sleep_window("23:30", "23:00", "06:00") is True

    def test_overnight_window_inside_after_midnight(self):
        """23:00-06:00 window, sync at 02:00 -> conflict."""
        assert is_time_in_sleep_window("02:00", "23:00", "06:00") is True

    def test_overnight_window_outside(self):
        """23:00-06:00 window, sync at 12:00 -> no conflict."""
        assert is_time_in_sleep_window("12:00", "23:00", "06:00") is False

    def test_boundary_sleep_time_equals_sync(self):
        """Sync at exact sleep_time -> conflict (inclusive start)."""
        assert is_time_in_sleep_window("23:00", "23:00", "06:00") is True

    def test_boundary_wake_time_equals_sync(self):
        """Sync at exact wake_time -> no conflict (exclusive end)."""
        assert is_time_in_sleep_window("06:00", "23:00", "06:00") is False

    def test_same_time_window(self):
        """sleep_time == wake_time -> no valid window -> no conflict."""
        assert is_time_in_sleep_window("12:00", "06:00", "06:00") is False
