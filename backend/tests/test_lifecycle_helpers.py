"""Tests for lifecycle helpers (pure functions, no DB)."""
import pytest

from app.services.notifications.lifecycle_helpers import (
    format_duration_human,
    german_trigger_label,
)


def test_format_duration_handles_none():
    assert format_duration_human(None) == "unbekannt"


def test_format_duration_seconds_only():
    assert format_duration_human(0) == "0s"
    assert format_duration_human(12) == "12s"
    assert format_duration_human(59) == "59s"


def test_format_duration_minutes():
    assert format_duration_human(60) == "1min"
    assert format_duration_human(125) == "2min 5s"
    assert format_duration_human(3599) == "59min 59s"


def test_format_duration_hours():
    assert format_duration_human(3600) == "1h"
    assert format_duration_human(4 * 3600 + 32 * 60) == "4h 32min"
    assert format_duration_human(86399) == "23h 59min"


def test_format_duration_days():
    assert format_duration_human(86400) == "1 Tag"
    assert format_duration_human(2 * 86400) == "2 Tage"
    assert format_duration_human(3 * 86400 + 2 * 3600) == "3 Tage 2h"


def test_format_duration_negative_returns_unknown():
    # Clock skew / wrong timestamps shouldn't crash
    assert format_duration_human(-5) == "unbekannt"


def test_german_trigger_label_known():
    assert german_trigger_label("manual") == "manuell"
    assert german_trigger_label("schedule") == "geplant"
    assert german_trigger_label("auto_idle") == "Auto-Idle"
    assert german_trigger_label("auto_escalation") == "Auto-Eskalation"
    assert german_trigger_label("api") == "API"
    assert german_trigger_label("signal") == "Signal"


def test_german_trigger_label_unknown_falls_back():
    assert german_trigger_label("xyz") == "xyz"
    assert german_trigger_label(None) == "unbekannt"
