"""
Pure helpers for matching the current time against a set of core-uptime windows.

Conventions:
- Times are server-local (naive datetime), consistent with the existing schedule loop.
- start_time is INCLUSIVE, end_time is EXCLUSIVE.
- weekdays is a CSV of integers 0..6 (0=Monday..6=Sunday) — the days the window STARTS on.
- If end < start, the window crosses midnight (start_today .. 24:00 + 00:00 .. end_next_day).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _parse_weekdays(csv: str) -> set[int]:
    return {int(x) for x in csv.split(",") if x.strip() != ""}


def _crosses_midnight(start: str, end: str) -> bool:
    sh, sm = _parse_hhmm(start)
    eh, em = _parse_hhmm(end)
    return (eh, em) < (sh, sm)


def _window_active_at(now: datetime, w) -> bool:
    """True iff `now` lies inside this enabled window."""
    if not w.enabled:
        return False
    weekdays = _parse_weekdays(w.weekdays)
    sh, sm = _parse_hhmm(w.start_time)
    eh, em = _parse_hhmm(w.end_time)
    today = now.weekday()  # 0..6 Mon..Sun
    yesterday = (today - 1) % 7

    if _crosses_midnight(w.start_time, w.end_time):
        # Late part: started today (today in weekdays) AND now >= start_today
        if today in weekdays:
            start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if now >= start_today:
                return True
        # Early part: started yesterday (yesterday in weekdays) AND now < end_today
        if yesterday in weekdays:
            end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            if now < end_today:
                return True
        return False
    else:
        if today not in weekdays:
            return False
        start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        return start_today <= now < end_today


def is_in_core_uptime(now: datetime, windows: Sequence) -> tuple[bool, Optional[object]]:
    """Return (active, matching_window). First-match wins on overlap."""
    for w in windows:
        if _window_active_at(now, w):
            return True, w
    return False, None


def next_core_uptime_start(now: datetime, windows: Sequence) -> Optional[datetime]:
    """Return the earliest start datetime within the next 8 calendar days, or None.

    Iterates day_offset 0..7 (inclusive) so that single-weekday windows still
    produce a candidate when ``now`` is already past today's start time
    (the next match is exactly 7 days later — needs day_offset=7, not 6).
    """
    enabled = [w for w in windows if w.enabled]
    if not enabled:
        return None

    candidates: list[datetime] = []
    for w in enabled:
        sh, sm = _parse_hhmm(w.start_time)
        weekdays = _parse_weekdays(w.weekdays)
        for day_offset in range(0, 8):  # 0..7 inclusive — see docstring
            candidate_date = now + timedelta(days=day_offset)
            if candidate_date.weekday() not in weekdays:
                continue
            candidate = candidate_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if candidate > now:
                candidates.append(candidate)
                break  # earliest for this window
    return min(candidates) if candidates else None


def current_window_end(now: datetime, w) -> datetime:
    """Return the datetime when the currently-active window ends.

    Caller must ensure `now` is actually inside `w`.
    """
    eh, em = _parse_hhmm(w.end_time)
    if _crosses_midnight(w.start_time, w.end_time):
        sh, sm = _parse_hhmm(w.start_time)
        start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if now >= start_today:
            # We're in the late part — end is tomorrow at end_time
            return (now + timedelta(days=1)).replace(hour=eh, minute=em, second=0, microsecond=0)
        # We're in the early part — end is today at end_time
        return now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return now.replace(hour=eh, minute=em, second=0, microsecond=0)
