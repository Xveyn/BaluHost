"""Reine Terminmathematik für den geplanten Systemneustart.

Konventionen wie in `core_uptime.py`: alle Zeiten sind server-lokale **naive**
`datetime`. Die Umrechnung nach UTC passiert erst an der Speichergrenze
(`reboot_state.py`), damit hier nichts von Zeitzonen weiß.

Zwei Funktionen, weil der Automat zwei verschiedene Fragen stellt:
`next_weekday_occurrence` beantwortet „wann muss ich wecken und wann warnen",
`due_occurrence` beantwortet „ist gerade ein Termin fällig, den ich noch
nachholen darf". Die zweite über die erste zu beantworten geht nicht — sie
liefert per Definition nur Zukunft.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _parse_hhmm(time_hhmm: str) -> tuple[int, int]:
    match = _HHMM.match(time_hhmm or "")
    if match is None:
        raise ValueError(f"Ungültige Uhrzeit: {time_hhmm!r} (erwartet HH:MM)")
    return int(match.group(1)), int(match.group(2))


def _check_weekday(weekday: int) -> None:
    if not isinstance(weekday, int) or not 0 <= weekday <= 6:
        raise ValueError(f"Ungültiger Wochentag: {weekday!r} (erwartet 0..6)")


def _at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def next_weekday_occurrence(now: datetime, weekday: int, time_hhmm: str) -> datetime:
    """Nächstes Vorkommen von (Wochentag, Uhrzeit) strikt NACH `now`.

    Iteriert `day_offset` 0..7 **einschließlich**. Die Sieben ist kein
    Schreibfehler: fällt `now` auf den Zieltag, aber auf oder nach der
    Zielzeit, liegt das nächste Vorkommen exakt sieben Tage später. Mit 0..6
    gäbe es dafür keinen Kandidaten. Dieselbe Falle ist in
    `core_uptime.next_core_uptime_start()` dokumentiert.
    """
    _check_weekday(weekday)
    hour, minute = _parse_hhmm(time_hhmm)

    for day_offset in range(0, 8):
        day = now + timedelta(days=day_offset)
        if day.weekday() != weekday:
            continue
        candidate = _at(day, hour, minute)
        if candidate > now:
            return candidate

    # Unerreichbar: unter 0..7 liegt immer genau ein passender Wochentag mit
    # einem Kandidaten in der Zukunft. Defensiv, damit der Rückgabetyp hält.
    raise AssertionError("kein Termin in acht Tagen gefunden — unmöglich")


def due_occurrence(
    now: datetime,
    weekday: int,
    time_hhmm: str,
    within: timedelta,
) -> Optional[datetime]:
    """Jüngstes Vorkommen <= `now`, sofern es höchstens `within` zurückliegt.

    Sonst `None`. Das ist die Nachholmechanik: ein Termin, dessen Ausführung
    blockiert war oder dessen Zustand durch einen Prozessneustart verloren
    ging, wird so lange wieder als fällig erkannt, wie die Frist läuft.

    ACHTUNG: Diese Funktion kann „Zustand ging verloren" und „Termin ist
    bereits erledigt" nicht unterscheiden. Der Aufrufer MUSS das Ergebnis
    gegen `last_completed_due_at` prüfen, sonst entsteht eine Reboot-Schleife.
    """
    _check_weekday(weekday)
    hour, minute = _parse_hhmm(time_hhmm)

    for day_offset in range(0, 8):
        day = now - timedelta(days=day_offset)
        if day.weekday() != weekday:
            continue
        candidate = _at(day, hour, minute)
        if candidate > now:
            # Heute ist der Zieltag, die Zielzeit aber noch nicht erreicht —
            # das gesuchte Vorkommen liegt sieben Tage früher.
            continue
        return candidate if now - candidate <= within else None

    return None
