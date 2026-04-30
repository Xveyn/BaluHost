"""Pure helpers for lifecycle notifications: human-readable durations and trigger labels."""
from __future__ import annotations

from typing import Optional


_TRIGGER_LABELS_DE: dict[str, str] = {
    "manual": "manuell",
    "schedule": "geplant",
    "auto_idle": "Auto-Idle",
    "auto_escalation": "Auto-Eskalation",
    "auto_wake": "Auto-Wake",
    "api": "API",
    "signal": "Signal",
}


def format_duration_human(seconds: Optional[float]) -> str:
    """Format a duration in seconds as a short German string.

    Examples:
        12        -> "12s"
        125       -> "2min 5s"
        4*3600+32*60 -> "4h 32min"
        3*86400+2*3600 -> "3 Tage 2h"
        None      -> "unbekannt"
    """
    if seconds is None or seconds < 0:
        return "unbekannt"

    s = int(seconds)
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    if days >= 1:
        unit = "Tag" if days == 1 else "Tage"
        if hours:
            return f"{days} {unit} {hours}h"
        return f"{days} {unit}"

    if hours >= 1:
        if minutes:
            return f"{hours}h {minutes}min"
        return f"{hours}h"

    if minutes >= 1:
        if secs:
            return f"{minutes}min {secs}s"
        return f"{minutes}min"

    return f"{secs}s"


def german_trigger_label(trigger: Optional[str]) -> str:
    """Map a SleepTrigger / lifecycle trigger value to a German label.

    Falls back to the raw value (or "unbekannt" if None).
    """
    if trigger is None:
        return "unbekannt"
    return _TRIGGER_LABELS_DE.get(trigger, trigger)
