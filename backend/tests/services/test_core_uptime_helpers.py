"""Unit tests for pure core-uptime helpers (no DB)."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.power.core_uptime import (
    is_in_core_uptime,
    next_core_uptime_start,
    current_window_end,
)


def _w(start: str, end: str, weekdays: str = "0,1,2,3,4,5,6", enabled: bool = True, label: str | None = None):
    """Build a fake CoreUptimeWindow-shaped object for tests."""
    return SimpleNamespace(
        id=1,
        enabled=enabled,
        label=label,
        start_time=start,
        end_time=end,
        weekdays=weekdays,
    )


# ---- is_in_core_uptime ----

def test_in_window_simple_weekday():
    # Wednesday = weekday 2; window Mo-Fr 08:00-22:00; current = Wed 12:00
    now = datetime(2026, 5, 6, 12, 0)  # Wed
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w is windows[0]


def test_outside_window_weekday_match():
    now = datetime(2026, 5, 6, 7, 59)  # Wed before start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    active, w = is_in_core_uptime(now, windows)
    assert active is False
    assert w is None


def test_start_inclusive():
    now = datetime(2026, 5, 6, 8, 0)  # exactly start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is True


def test_end_exclusive():
    now = datetime(2026, 5, 6, 22, 0)  # exactly end
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_wrong_weekday():
    # Saturday = weekday 5; window only weekdays 0-4
    now = datetime(2026, 5, 9, 12, 0)  # Sat
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_disabled_window_ignored():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("08:00", "22:00", "0,1,2,3,4", enabled=False)]
    assert is_in_core_uptime(now, windows) == (False, None)


def test_empty_windows_list():
    now = datetime(2026, 5, 6, 12, 0)
    assert is_in_core_uptime(now, []) == (False, None)


# ---- cross-midnight ----

def test_cross_midnight_active_late():
    # Friday window 22:00 -> 06:00 (Sat morning); now Fri 23:00
    now = datetime(2026, 5, 8, 23, 0)  # Fri
    windows = [_w("22:00", "06:00", "4")]  # Friday only
    assert is_in_core_uptime(now, windows)[0] is True


def test_cross_midnight_active_early_next_day():
    # Same window covers Sat 02:00 (since it started Fri 22:00)
    now = datetime(2026, 5, 9, 2, 0)  # Sat
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is True


def test_cross_midnight_not_active_saturday_evening():
    # Sat 23:00 is NOT covered (window starts on Fri only, already closed at Sat 06:00)
    now = datetime(2026, 5, 9, 23, 0)
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_cross_midnight_end_exclusive():
    # Fri-window 22:00 -> 06:00; Sat 06:00 is NOT inside (end exclusive)
    now = datetime(2026, 5, 9, 6, 0)
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is False


# ---- multiple windows ----

def test_multiple_windows_union():
    now = datetime(2026, 5, 9, 11, 0)  # Sat 11:00
    windows = [
        _w("08:00", "22:00", "0,1,2,3,4"),  # workdays only
        _w("10:00", "23:30", "5,6"),         # weekend
    ]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w.weekdays == "5,6"


def test_overlapping_windows_returns_first_match():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [
        _w("00:00", "12:00", "2", label="A"),  # Wed morning
        _w("11:30", "23:30", "2", label="B"),  # overlaps
    ]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w.label == "B"  # second wins because first ends at 12:00 (exclusive)


# ---- next_core_uptime_start ----

def test_next_start_today_later_today():
    now = datetime(2026, 5, 6, 7, 0)  # Wed before start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 6, 8, 0)


def test_next_start_tomorrow():
    now = datetime(2026, 5, 6, 23, 0)  # Wed after end
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 7, 8, 0)


def test_next_start_skips_weekend():
    now = datetime(2026, 5, 8, 23, 0)  # Fri 23:00
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 11, 8, 0)  # next Mon


def test_next_start_no_enabled_windows():
    assert next_core_uptime_start(datetime(2026, 5, 6, 12, 0), []) is None
    disabled = [_w("08:00", "22:00", "0,1,2,3,4", enabled=False)]
    assert next_core_uptime_start(datetime(2026, 5, 6, 12, 0), disabled) is None


def test_next_start_picks_earliest_across_windows():
    now = datetime(2026, 5, 8, 23, 0)  # Fri evening
    windows = [
        _w("08:00", "22:00", "0,1,2,3,4"),  # next: Mon 08:00
        _w("10:00", "23:30", "5,6"),         # next: Sat 10:00
    ]
    assert next_core_uptime_start(now, windows) == datetime(2026, 5, 9, 10, 0)


# ---- current_window_end ----

def test_current_window_end_same_day():
    now = datetime(2026, 5, 6, 12, 0)
    w = _w("08:00", "22:00", "0,1,2,3,4")
    assert current_window_end(now, w) == datetime(2026, 5, 6, 22, 0)


def test_current_window_end_cross_midnight_late_part():
    now = datetime(2026, 5, 8, 23, 0)  # Fri 23:00 inside window
    w = _w("22:00", "06:00", "4")
    assert current_window_end(now, w) == datetime(2026, 5, 9, 6, 0)


def test_current_window_end_cross_midnight_early_part():
    now = datetime(2026, 5, 9, 2, 0)  # Sat 02:00 inside Fri-started window
    w = _w("22:00", "06:00", "4")
    assert current_window_end(now, w) == datetime(2026, 5, 9, 6, 0)
