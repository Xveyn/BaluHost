"""
Pure helpers for matching the current time against a set of core-uptime windows.

Conventions:
- Times are server-local (naive datetime), consistent with the existing schedule loop.
- start_time is INCLUSIVE, end_time is EXCLUSIVE.
- weekdays is a CSV of integers 0..6 (0=Monday..6=Sunday) — the days the window STARTS on.
- If end < start, the window crosses midnight (start_today .. 24:00 + 00:00 .. end_next_day).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional, Sequence


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


def current_window_start(now: datetime, w) -> datetime:
    """Return the datetime when the currently-active window started.

    Mirror of `current_window_end`. Caller must ensure `now` is inside `w`.
    """
    sh, sm = _parse_hhmm(w.start_time)
    if _crosses_midnight(w.start_time, w.end_time):
        start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if now >= start_today:
            # Late part — the window started today
            return start_today
        # Early part — the window started yesterday
        return (now - timedelta(days=1)).replace(
            hour=sh, minute=sm, second=0, microsecond=0
        )
    return now.replace(hour=sh, minute=sm, second=0, microsecond=0)


def window_start_containing(dt: datetime, windows: Sequence) -> Optional[datetime]:
    """Start of the window containing `dt`, or None.

    On overlapping windows the EARLIEST start wins — deliberately not
    first-match, so the result does not depend on list order (the frontend
    preview computes the same value from resolved occurrences).
    """
    starts = [
        current_window_start(dt, w) for w in windows if _window_active_at(dt, w)
    ]
    return min(starts) if starts else None


def clamp_to_core_uptime_start(
    until_utc: datetime,
    windows: Sequence,
    now_local: datetime,
) -> datetime:
    """Shorten an always-awake expiry to the start of the core-uptime window
    containing it — but only if that start is still in the future.

    `until_utc` is UTC-aware (naive values are read as UTC, matching
    `SleepManagerService._is_always_awake`); `windows` and `now_local` are
    server-local, per this module's convention. The return value is UTC-aware.
    """
    if until_utc.tzinfo is None:
        until_utc = until_utc.replace(tzinfo=timezone.utc)
    until_local = until_utc.astimezone().replace(tzinfo=None)
    start_local = window_start_containing(until_local, windows)
    if start_local is None or start_local <= now_local:
        return until_utc
    # astimezone() on a naive value reads it as local time — exactly what we want.
    return start_local.astimezone(timezone.utc)


class Occurrence(NamedTuple):
    """One resolved instance of a recurring window, in server-local time."""
    window_id: int
    label: Optional[str]
    start: datetime
    end: datetime


def expand_occurrences(
    now: datetime,
    windows: Sequence,
    days: int = 7,
) -> list[Occurrence]:
    """Resolve recurring windows into concrete occurrences.

    Iterates day_offset -1..days: the -1 catches a window that started
    yesterday and crosses midnight. Occurrences that already ended are
    dropped. Result is sorted by start.
    """
    out: list[Occurrence] = []
    for w in windows:
        if not w.enabled:
            continue
        sh, sm = _parse_hhmm(w.start_time)
        eh, em = _parse_hhmm(w.end_time)
        weekdays = _parse_weekdays(w.weekdays)
        crosses = _crosses_midnight(w.start_time, w.end_time)
        for day_offset in range(-1, days + 1):
            day = now + timedelta(days=day_offset)
            if day.weekday() not in weekdays:
                continue
            start = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_day = day + timedelta(days=1) if crosses else day
            end = end_day.replace(hour=eh, minute=em, second=0, microsecond=0)
            if end <= now:
                continue
            out.append(
                Occurrence(window_id=w.id, label=w.label, start=start, end=end)
            )
    return sorted(out, key=lambda o: o.start)
