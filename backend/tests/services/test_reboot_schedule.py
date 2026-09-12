"""Reine Terminmathematik für den geplanten Systemneustart."""
from datetime import datetime, timedelta

import pytest

from app.services.power.reboot_schedule import (
    due_occurrence,
    next_weekday_occurrence,
)

# 2026-09-13 ist ein Sonntag (weekday 6), 2026-09-14 ein Montag (weekday 0).


def test_next_occurrence_later_today():
    now = datetime(2026, 9, 13, 1, 0)  # Sonntag 01:00
    assert next_weekday_occurrence(now, 6, "04:00") == datetime(2026, 9, 13, 4, 0)


def test_next_occurrence_same_day_but_already_past_is_seven_days_later():
    """Der day_offset=7-Fall. Mit 0..6 käme hier nichts heraus."""
    now = datetime(2026, 9, 13, 5, 0)  # Sonntag 05:00, Termin 04:00 vorbei
    assert next_weekday_occurrence(now, 6, "04:00") == datetime(2026, 9, 20, 4, 0)


def test_next_occurrence_across_the_week():
    now = datetime(2026, 9, 14, 12, 0)  # Montag
    assert next_weekday_occurrence(now, 6, "04:00") == datetime(2026, 9, 20, 4, 0)


def test_next_occurrence_is_strictly_after_now():
    now = datetime(2026, 9, 13, 4, 0)  # exakt auf dem Termin
    assert next_weekday_occurrence(now, 6, "04:00") == datetime(2026, 9, 20, 4, 0)


def test_due_occurrence_within_window():
    now = datetime(2026, 9, 13, 6, 0)  # zwei Stunden nach dem Termin
    assert due_occurrence(now, 6, "04:00", timedelta(hours=6)) == datetime(2026, 9, 13, 4, 0)


def test_due_occurrence_exactly_on_time():
    now = datetime(2026, 9, 13, 4, 0)
    assert due_occurrence(now, 6, "04:00", timedelta(hours=6)) == datetime(2026, 9, 13, 4, 0)


def test_due_occurrence_outside_window_is_none():
    now = datetime(2026, 9, 13, 11, 0)  # sieben Stunden danach, Frist sechs
    assert due_occurrence(now, 6, "04:00", timedelta(hours=6)) is None


def test_due_occurrence_before_first_ever_is_none():
    now = datetime(2026, 9, 13, 3, 0)  # Termin heute noch nicht erreicht
    # Der letzte Sonntag 04:00 war der 6.9. — weit außerhalb der Frist.
    assert due_occurrence(now, 6, "04:00", timedelta(hours=6)) is None


def test_due_occurrence_looks_back_across_the_week_boundary():
    now = datetime(2026, 9, 14, 2, 0)  # Montag 02:00, Termin war So 22:00
    assert due_occurrence(now, 6, "22:00", timedelta(hours=6)) == datetime(2026, 9, 13, 22, 0)


@pytest.mark.parametrize("bad", ["24:00", "4:00", "04:60", "", "0400"])
def test_invalid_time_raises(bad):
    with pytest.raises(ValueError):
        next_weekday_occurrence(datetime(2026, 9, 13, 1, 0), 6, bad)


@pytest.mark.parametrize("bad", [-1, 7, 99])
def test_invalid_weekday_raises(bad):
    with pytest.raises(ValueError):
        next_weekday_occurrence(datetime(2026, 9, 13, 1, 0), bad, "04:00")
