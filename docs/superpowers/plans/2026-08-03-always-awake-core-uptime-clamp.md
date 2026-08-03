# Always-Awake an Kernbetriebszeit-Fenstern kürzen — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fällt der Always-Awake-Ablaufzeitpunkt in ein künftiges Kernbetriebszeit-Fenster, wird er beim Speichern auf dessen Beginn gekürzt; die UI kündigt die Kürzung vorher an und erklärt sie nachher.

**Architecture:** Vier reine Helper in `backend/app/services/power/core_uptime.py` (lokal-naive Zeitlogik, wie die Datei sie bereits durchgängig verwendet) tragen die Regel. `SleepManagerService.update_config()` ruft sie auf, bevor `always_awake_until` committet wird — der gespeicherte Wert ist damit die Wahrheit, alle Anzeige-Pfade (Status-Endpoint, Countdown, Topbar-Pill) bleiben unverändert. Ein neuer Read-Only-Endpoint löst die Fenster in konkrete Zeitstempel auf, sodass das Frontend die Vorschau mit einem reinen Intervallvergleich berechnet, statt Wochentags- und Mitternachtslogik in TypeScript nachzubauen.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 / Pydantic v2 / pytest — React 18 / TypeScript / Vite / Vitest / i18next.

**Spec:** `docs/superpowers/specs/2026-08-03-always-awake-core-uptime-clamp-design.md`

## Global Constraints

- **Keine Alembic-Migration, kein neues DB-Feld.** `SleepConfig`, `AlwaysAwakeStatus` und `SleepConfigResponse` bleiben unverändert.
- **Zeitkonvention:** Kernbetriebszeit-Fenster sind durchgängig **lokal-naiv** (`datetime.now()` ohne tzinfo), `always_awake_until` ist **UTC-aware**. Umgerechnet wird ausschließlich in `clamp_to_core_uptime_start()` und im neuen Route-Handler.
- **Fenster-Semantik:** `start_time` inklusiv, `end_time` exklusiv, `weekdays` CSV `0..6` (0=Montag), `end < start` bedeutet Mitternachtsüberlauf. Nicht ändern.
- **Bei überlappenden Fenstern gilt der früheste Start** (`min`), nicht der erste Treffer — nur so liefern Backend-Kürzung und Frontend-Vorschau garantiert dasselbe Ergebnis.
- **SQLAlchemy-Filter:** immer `.is_(True)`, nie `== True` — ein Ruff-E712-Autofix zerlegt sonst die Query.
- **Zeilen-Konvention:** `backend/app/services/power/sleep.py` hat bereits 1520 Zeilen. Neue Logik gehört in `core_uptime.py`, nicht dorthin; in `sleep.py` landet nur der Aufruf.
- **Neue Routen:** `Depends(get_current_admin)` + `@user_limiter.limit(get_limit("admin_operations"))`, exakt wie die bestehenden `/core-uptime/*`-Routen.
- **Kein `git push`, kein PR** im Rahmen dieses Plans — nur lokale Commits.

---

## Dateiübersicht

| Datei | Rolle |
|---|---|
| `backend/app/services/power/core_uptime.py` | **Modify** — vier neue reine Helper: `Occurrence`, `current_window_start`, `window_start_containing`, `clamp_to_core_uptime_start`, `expand_occurrences` |
| `backend/tests/services/test_core_uptime_helpers.py` | **Modify** — Tests für die neuen Helper, an die bestehenden angehängt |
| `backend/app/services/power/sleep.py` | **Modify** — Aufruf der Kürzung in `update_config()` (~8 Zeilen) |
| `backend/tests/services/test_sleep_always_awake.py` | **Modify** — Tests der Kürzung in `update_config()` |
| `backend/app/schemas/sleep.py` | **Modify** — `CoreUptimeOccurrence`-Response-Schema |
| `backend/app/api/routes/sleep.py` | **Modify** — `GET /core-uptime/occurrences` |
| `backend/tests/api/test_core_uptime_routes.py` | **Modify** — Route-Tests für den neuen Endpoint |
| `client/src/api/sleep.ts` | **Modify** — `CoreUptimeOccurrence` + `getCoreUptimeOccurrences()` |
| `client/src/lib/coreUptimeClamp.ts` | **Create** — reine `clampToCoreUptime()` / `findRunningOccurrence()` |
| `client/src/__tests__/lib/coreUptimeClamp.test.ts` | **Create** — Vitest für die reinen Funktionen |
| `client/src/components/power/AlwaysAwakePanel.tsx` | **Modify** — Occurrences laden, Vorher-/Nachher-Hinweise, gekürzter Wert beim Speichern |
| `client/src/__tests__/components/power/AlwaysAwakePanel.test.tsx` | **Create** — Panel-Test |
| `client/src/i18n/locales/de/system.json`, `.../en/system.json` | **Modify** — vier neue Keys unter `sleep.alwaysAwake` |

---

## Task 1: Reine Helper in `core_uptime.py`

**Files:**
- Modify: `backend/app/services/power/core_uptime.py`
- Test: `backend/tests/services/test_core_uptime_helpers.py`

**Interfaces:**
- Consumes: bestehende private Helper derselben Datei — `_parse_hhmm`, `_parse_weekdays`, `_crosses_midnight`, `_window_active_at`, `is_in_core_uptime`
- Produces:
  - `class Occurrence(NamedTuple)` mit `window_id: int`, `label: Optional[str]`, `start: datetime`, `end: datetime` (lokal-naiv)
  - `current_window_start(now: datetime, w) -> datetime`
  - `window_start_containing(dt: datetime, windows: Sequence) -> Optional[datetime]`
  - `clamp_to_core_uptime_start(until_utc: datetime, windows: Sequence, now_local: datetime) -> datetime`
  - `expand_occurrences(now: datetime, windows: Sequence, days: int = 7) -> list[Occurrence]`

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An das **Ende** von `backend/tests/services/test_core_uptime_helpers.py` anhängen. Der Datei-lokale Builder `_w(start, end, weekdays, enabled, label)` existiert dort bereits (Zeile 14) und wird wiederverwendet — nicht neu definieren.

Ergänze zuerst die Import-Zeile am Dateikopf (die bestehende `from app.services.power.core_uptime import (...)`-Gruppe erweitern), sodass sie lautet:

```python
from app.services.power.core_uptime import (
    is_in_core_uptime,
    next_core_uptime_start,
    current_window_end,
    current_window_start,
    window_start_containing,
    clamp_to_core_uptime_start,
    expand_occurrences,
)
```

Zusätzlich am Dateikopf ergänzen (die bestehende `from datetime import datetime`-Zeile erweitern):

```python
from datetime import datetime, timedelta, timezone
```

Dann die Tests anhängen:

```python
# ---- current_window_start ----

def test_current_window_start_simple():
    # Mi 12:00 innerhalb Mo-Fr 08:00-22:00
    now = datetime(2026, 5, 6, 12, 0)
    w = _w("08:00", "22:00", "0,1,2,3,4")
    assert current_window_start(now, w) == datetime(2026, 5, 6, 8, 0)


def test_current_window_start_overnight_late_half():
    # Fenster 22:00-06:00, jetzt Mi 23:30 -> Beginn ist heute 22:00
    now = datetime(2026, 5, 6, 23, 30)
    w = _w("22:00", "06:00")
    assert current_window_start(now, w) == datetime(2026, 5, 6, 22, 0)


def test_current_window_start_overnight_early_half():
    # Fenster 22:00-06:00, jetzt Do 02:00 -> Beginn war gestern 22:00
    now = datetime(2026, 5, 7, 2, 0)
    w = _w("22:00", "06:00")
    assert current_window_start(now, w) == datetime(2026, 5, 6, 22, 0)


# ---- window_start_containing ----

def test_window_start_containing_hit():
    dt = datetime(2026, 5, 6, 20, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    assert window_start_containing(dt, windows) == datetime(2026, 5, 6, 19, 0)


def test_window_start_containing_miss_returns_none():
    dt = datetime(2026, 5, 6, 18, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    assert window_start_containing(dt, windows) is None


def test_window_start_containing_ignores_disabled_window():
    dt = datetime(2026, 5, 6, 20, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4", enabled=False)]
    assert window_start_containing(dt, windows) is None


def test_window_start_containing_empty_list():
    assert window_start_containing(datetime(2026, 5, 6, 20, 0), []) is None


def test_window_start_containing_overlap_picks_earliest_start():
    # Zwei Fenster enthalten 21:00 — das frueher beginnende gewinnt,
    # unabhaengig von der Listenreihenfolge.
    dt = datetime(2026, 5, 6, 21, 0)
    late = _w("20:00", "23:00")
    early = _w("19:00", "22:00")
    assert window_start_containing(dt, [late, early]) == datetime(2026, 5, 6, 19, 0)
    assert window_start_containing(dt, [early, late]) == datetime(2026, 5, 6, 19, 0)


# ---- clamp_to_core_uptime_start ----
#
# Die Funktion rechnet UTC -> lokale Serverzeit und zurueck. Damit die Tests
# unabhaengig von der TZ der CI-Maschine sind, wird der UTC-Eingabewert aus
# einem lokalen Wunschzeitpunkt abgeleitet statt hart gesetzt.

def _utc(local_naive: datetime) -> datetime:
    """Lokal-naiven Zeitpunkt in den entsprechenden UTC-aware Wert umrechnen."""
    return local_naive.astimezone(timezone.utc)


def test_clamp_shortens_expiry_inside_future_window():
    now_local = datetime(2026, 5, 6, 15, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    until = _utc(datetime(2026, 5, 6, 21, 0))
    result = clamp_to_core_uptime_start(until, windows, now_local)
    assert result == _utc(datetime(2026, 5, 6, 19, 0))
    assert result.tzinfo is not None


def test_clamp_leaves_expiry_before_window_untouched():
    now_local = datetime(2026, 5, 6, 15, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    until = _utc(datetime(2026, 5, 6, 17, 0))
    assert clamp_to_core_uptime_start(until, windows, now_local) == until


def test_clamp_leaves_expiry_past_window_end_untouched():
    now_local = datetime(2026, 5, 6, 15, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    until = _utc(datetime(2026, 5, 7, 1, 0))
    assert clamp_to_core_uptime_start(until, windows, now_local) == until


def test_clamp_expiry_exactly_on_window_start_is_unchanged():
    now_local = datetime(2026, 5, 6, 15, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    until = _utc(datetime(2026, 5, 6, 19, 0))
    assert clamp_to_core_uptime_start(until, windows, now_local) == until


def test_clamp_does_not_shorten_when_window_already_running():
    # Fensterbeginn liegt in der Vergangenheit -> kein Kuerzen moeglich.
    now_local = datetime(2026, 5, 6, 20, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    until = _utc(datetime(2026, 5, 6, 21, 0))
    assert clamp_to_core_uptime_start(until, windows, now_local) == until


def test_clamp_with_no_windows_is_identity():
    now_local = datetime(2026, 5, 6, 15, 0)
    until = _utc(datetime(2026, 5, 6, 21, 0))
    assert clamp_to_core_uptime_start(until, [], now_local) == until


def test_clamp_accepts_naive_until_as_utc():
    # Defensive: ein naiver DB-Wert wird als UTC interpretiert, nicht als lokal.
    now_local = datetime(2026, 5, 6, 15, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]
    aware = _utc(datetime(2026, 5, 6, 21, 0))
    naive = aware.replace(tzinfo=None)
    assert clamp_to_core_uptime_start(naive, windows, now_local) == _utc(
        datetime(2026, 5, 6, 19, 0)
    )


# ---- expand_occurrences ----

def test_expand_occurrences_respects_weekdays():
    now = datetime(2026, 5, 6, 12, 0)  # Mi
    windows = [_w("19:00", "23:30", "0,1,2,3,4")]  # Mo-Fr
    occ = expand_occurrences(now, windows, days=7)
    starts = [o.start for o in occ]
    # Mi/Do/Fr diese Woche + Mo/Di/Mi naechste Woche = 6 Vorkommen
    assert starts == [
        datetime(2026, 5, 6, 19, 0),
        datetime(2026, 5, 7, 19, 0),
        datetime(2026, 5, 8, 19, 0),
        datetime(2026, 5, 11, 19, 0),
        datetime(2026, 5, 12, 19, 0),
        datetime(2026, 5, 13, 19, 0),
    ]


def test_expand_occurrences_sets_end_and_metadata():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("19:00", "23:30", "2", label="Abend")]  # nur Mittwoch
    occ = expand_occurrences(now, windows, days=1)
    assert len(occ) == 1
    assert occ[0].start == datetime(2026, 5, 6, 19, 0)
    assert occ[0].end == datetime(2026, 5, 6, 23, 30)
    assert occ[0].label == "Abend"
    assert occ[0].window_id == 1


def test_expand_occurrences_overnight_end_is_next_day():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("22:00", "06:00", "2")]  # Mittwoch 22:00 -> Donnerstag 06:00
    occ = expand_occurrences(now, windows, days=1)
    assert occ[0].start == datetime(2026, 5, 6, 22, 0)
    assert occ[0].end == datetime(2026, 5, 7, 6, 0)


def test_expand_occurrences_includes_window_started_yesterday():
    # Donnerstag 02:00: das Mittwoch-Fenster 22:00-06:00 laeuft noch.
    now = datetime(2026, 5, 7, 2, 0)
    windows = [_w("22:00", "06:00", "2")]
    occ = expand_occurrences(now, windows, days=7)
    assert occ[0].start == datetime(2026, 5, 6, 22, 0)
    assert occ[0].end == datetime(2026, 5, 7, 6, 0)


def test_expand_occurrences_drops_finished_occurrences():
    # Mittwoch 20:00: das heutige Fenster 08:00-12:00 ist vorbei.
    now = datetime(2026, 5, 6, 20, 0)
    windows = [_w("08:00", "12:00", "2")]  # nur Mittwoch
    occ = expand_occurrences(now, windows, days=7)
    assert [o.start for o in occ] == [datetime(2026, 5, 13, 8, 0)]


def test_expand_occurrences_skips_disabled_windows():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("19:00", "23:30", "0,1,2,3,4", enabled=False)]
    assert expand_occurrences(now, windows, days=7) == []


def test_expand_occurrences_sorted_across_windows():
    now = datetime(2026, 5, 6, 6, 0)
    late = _w("19:00", "23:30", "2")
    early = _w("08:00", "12:00", "2")
    occ = expand_occurrences(now, [late, early], days=1)
    assert [o.start for o in occ] == [
        datetime(2026, 5, 6, 8, 0),
        datetime(2026, 5, 6, 19, 0),
    ]


def test_expand_occurrences_honours_days_horizon():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("19:00", "23:30")]  # taeglich
    assert len(expand_occurrences(now, windows, days=1)) == 2  # heute + morgen
```

- [ ] **Step 2: Tests laufen lassen — sie müssen fehlschlagen**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_helpers.py -v
```

Erwartet: `ImportError: cannot import name 'current_window_start'` — die ganze Datei bricht beim Import ab. Das ist der erwartete Fehlschlag.

- [ ] **Step 3: Die Helper implementieren**

In `backend/app/services/power/core_uptime.py` den Import-Block am Dateikopf ersetzen:

```python
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional, Sequence
```

Danach `current_window_end` (endet in Zeile 109) als letzten Block belassen und **darunter** anfügen:

```python
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
```

- [ ] **Step 4: Tests laufen lassen — sie müssen bestehen**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_helpers.py -v
```

Erwartet: alle Tests PASS (die bestehenden ebenso wie die neuen).

- [ ] **Step 5: Regression der Kernbetriebszeit-Nachbarn**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_inhibitor.py tests/services/test_core_uptime_rtc_guard.py tests/services/test_sleep_core_uptime_integration.py -q
```

Erwartet: alle PASS — die neuen Funktionen sind rein additiv.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/core_uptime.py backend/tests/services/test_core_uptime_helpers.py
git commit -m "feat(sleep): Helper zum Aufloesen und Kuerzen an Kernbetriebszeit-Fenstern"
```

---

## Task 2: Kürzung in `update_config()`

**Files:**
- Modify: `backend/app/services/power/sleep.py:1339-1378` (`update_config`)
- Test: `backend/tests/services/test_sleep_always_awake.py`

**Interfaces:**
- Consumes: `core_uptime_helpers.clamp_to_core_uptime_start(until_utc, windows, now_local)` aus Task 1. `sleep.py` importiert das Modul bereits als `core_uptime_helpers` (Zeile 28) und `CoreUptimeWindow as CoreUptimeWindowModel` (Zeile 26) — keine neuen Imports nötig.
- Produces: keine neue öffentliche API. `update_config()` schreibt ab jetzt einen ggf. gekürzten `always_awake_until`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An das Ende von `backend/tests/services/test_sleep_always_awake.py` anhängen. `_build_service`, `patch`, `MagicMock`, `datetime`, `timedelta`, `timezone` und `SleepConfig` sind dort bereits importiert.

```python
# ---------------------------------------------------------------------------
# Kuerzung von always_awake_until an Kernbetriebszeit-Fenstern
# ---------------------------------------------------------------------------

def _clamp_row(*, core_uptime_enabled: bool = True, until=None):
    """SleepConfig-Zeile fuer die Kuerzungstests."""
    return SleepConfig(
        id=1, auto_idle_enabled=False, idle_timeout_minutes=15,
        idle_cpu_threshold=5.0, idle_disk_io_threshold=0.5, idle_http_threshold=5.0,
        auto_escalation_enabled=False, escalation_after_minutes=60,
        schedule_enabled=False, schedule_sleep_time="23:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=core_uptime_enabled,
        always_awake_enabled=True,
        always_awake_until=until,
    )


def _window(start: str, end: str, weekdays: str = "0,1,2,3,4,5,6"):
    """Fake CoreUptimeWindow — duck-typed, wie in test_core_uptime_helpers."""
    from types import SimpleNamespace
    return SimpleNamespace(
        id=1, enabled=True, label=None,
        start_time=start, end_time=end, weekdays=weekdays,
    )


def _session_with(row, windows):
    """MagicMock-Session: scalar_one_or_none -> row, scalars().all() -> windows."""
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = row
    session.execute.return_value.scalars.return_value.all.return_value = windows
    return session


def _local_utc(local_naive):
    """Lokal-naiven Zeitpunkt in den entsprechenden UTC-aware Wert umrechnen."""
    return local_naive.astimezone(timezone.utc)


def test_update_config_clamps_until_into_future_window():
    """Ablauf im kuenftigen Fenster wird auf den Fensterbeginn gekuerzt."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row()
    session = _session_with(row, [_window("19:00", "23:30")])

    now_local = datetime(2026, 5, 6, 15, 0)
    requested = _local_utc(datetime(2026, 5, 6, 21, 0))
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = now_local
        svc.update_config(update)

    assert row.always_awake_until == _local_utc(datetime(2026, 5, 6, 19, 0))


def test_update_config_leaves_until_past_window_end_untouched():
    """Ablauf hinter dem Fensterende bleibt unveraendert."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row()
    session = _session_with(row, [_window("19:00", "23:30")])

    requested = _local_utc(datetime(2026, 5, 7, 1, 0))
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 0)
        svc.update_config(update)

    assert row.always_awake_until == requested


def test_update_config_does_not_clamp_when_core_uptime_disabled():
    """Hauptschalter aus -> keine Kuerzung, Fenster werden nicht einmal geladen."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(core_uptime_enabled=False)
    session = _session_with(row, [_window("19:00", "23:30")])

    requested = _local_utc(datetime(2026, 5, 6, 21, 0))
    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=requested)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 0)
        svc.update_config(update)

    assert row.always_awake_until == requested


def test_update_config_clamps_when_core_uptime_enabled_in_same_request():
    """core_uptime_enabled wird im selben Request eingeschaltet -> Kuerzung greift."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(core_uptime_enabled=False)
    session = _session_with(row, [_window("19:00", "23:30")])

    requested = _local_utc(datetime(2026, 5, 6, 21, 0))
    update = SleepConfigUpdate(
        always_awake_enabled=True,
        always_awake_until=requested,
        core_uptime_enabled=True,
    )

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 0)
        svc.update_config(update)

    assert row.always_awake_until == _local_utc(datetime(2026, 5, 6, 19, 0))


def test_update_config_no_clamp_for_permanent_override():
    """until=None (dauerhaft) bleibt None — nichts zu kuerzen."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(until=_local_utc(datetime(2026, 5, 6, 21, 0)))
    session = _session_with(row, [_window("19:00", "23:30")])

    update = SleepConfigUpdate(always_awake_enabled=True, always_awake_until=None)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 0)
        svc.update_config(update)

    assert row.always_awake_until is None


def test_update_config_disabling_still_clears_until_with_windows_present():
    """enabled=False raeumt until ab — die Kuerzung darf da nichts wiederbeleben."""
    from app.schemas.sleep import SleepConfigUpdate
    svc = _build_service()
    row = _clamp_row(until=_local_utc(datetime(2026, 5, 6, 21, 0)))
    session = _session_with(row, [_window("19:00", "23:30")])

    update = SleepConfigUpdate(always_awake_enabled=False)

    with patch("app.services.power.sleep.SessionLocal", return_value=session), \
         patch("app.services.power.sleep.datetime") as mock_dt, \
         patch.object(svc, "get_config", return_value=MagicMock()):
        mock_dt.now.return_value = datetime(2026, 5, 6, 15, 0)
        svc.update_config(update)

    assert row.always_awake_enabled is False
    assert row.always_awake_until is None
```

> **Hinweis zum `datetime`-Patch:** `patch("app.services.power.sleep.datetime")` ersetzt das ganze Modul-Symbol. Der bestehende Test `test_schedule_loop_skips_sleep_trigger_during_core_uptime` in `tests/services/test_sleep_core_uptime_integration.py` verwendet dasselbe Muster — es ist in diesem Repo etabliert. `datetime.now(timezone.utc)` im Ablauf-Cleanup wird davon nicht berührt, weil `update_config` diesen Pfad nicht ausführt.

- [ ] **Step 2: Tests laufen lassen — sie müssen fehlschlagen**

```bash
cd backend && python -m pytest tests/services/test_sleep_always_awake.py -k clamp -v
```

Erwartet: `test_update_config_clamps_until_into_future_window` und `test_update_config_clamps_when_core_uptime_enabled_in_same_request` schlagen fehl (`until` bleibt beim Wunschwert 21:00). Die übrigen neuen Tests bestehen bereits — sie sichern ab, dass die Implementierung sie nicht bricht.

- [ ] **Step 3: Die Kürzung implementieren**

In `backend/app/services/power/sleep.py`, in `update_config()`, direkt **nach** dem Block

```python
                # Disabling always-awake clears any pending expiry
                if update_data.get("always_awake_enabled") is False:
                    config.always_awake_until = None
```

und **vor** `db.commit()` einfügen:

```python
                # Shorten a pending expiry that lands inside a FUTURE core-uptime
                # window: from that window's start on, core uptime keeps the system
                # awake anyway, so the manual override closes out there. An expiry
                # beyond the window's end survives untouched — it is still needed.
                if config.always_awake_until is not None and config.core_uptime_enabled:
                    windows = db.execute(
                        select(CoreUptimeWindowModel).where(
                            CoreUptimeWindowModel.enabled.is_(True)
                        )
                    ).scalars().all()
                    if windows:
                        config.always_awake_until = (
                            core_uptime_helpers.clamp_to_core_uptime_start(
                                config.always_awake_until,
                                list(windows),
                                datetime.now(),
                            )
                        )
```

- [ ] **Step 4: Tests laufen lassen — sie müssen bestehen**

```bash
cd backend && python -m pytest tests/services/test_sleep_always_awake.py -v
```

Erwartet: alle Tests PASS, inklusive der bestehenden `test_update_config_can_clear_until` und `test_update_config_disabling_normalizes_until`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_always_awake.py
git commit -m "feat(sleep): Always-Awake-Ablauf auf Kernbetriebszeit-Fensterbeginn kuerzen"
```

---

## Task 3: Endpoint `GET /core-uptime/occurrences`

**Files:**
- Modify: `backend/app/schemas/sleep.py`
- Modify: `backend/app/api/routes/sleep.py`
- Test: `backend/tests/api/test_core_uptime_routes.py`

**Interfaces:**
- Consumes: `core_uptime_helpers.expand_occurrences(now, windows, days)` und `Occurrence` aus Task 1
- Produces: `GET /api/system/sleep/core-uptime/occurrences?days=<1..7>` → `list[CoreUptimeOccurrence]` mit `window_id: int`, `label: str | null`, `start: datetime` (UTC), `end: datetime` (UTC)

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An das Ende von `backend/tests/api/test_core_uptime_routes.py` anhängen. Die Fixtures `admin_headers`/`user_headers` und die Konstante `BASE` existieren dort bereits.

```python
OCCURRENCES = f"{settings.api_prefix}/system/sleep/core-uptime/occurrences"


def test_occurrences_empty_without_windows(client, admin_headers):
    r = client.get(OCCURRENCES, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_occurrences_resolves_window_to_timestamps(client, admin_headers):
    create = client.post(BASE, headers=admin_headers, json={
        "label": "Abend",
        "start_time": "19:00",
        "end_time": "23:30",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
    })
    assert create.status_code in (200, 201)
    window_id = create.json()["id"]

    r = client.get(OCCURRENCES, headers=admin_headers, params={"days": 2})
    assert r.status_code == 200
    body = r.json()
    # Taegliches Fenster ueber 2 Tage Horizont: mindestens 2 Vorkommen.
    assert len(body) >= 2
    first = body[0]
    assert first["window_id"] == window_id
    assert first["label"] == "Abend"
    # Zeitstempel sind absolut und tragen einen Zeitzonen-Offset.
    assert first["start"] != first["end"]
    from datetime import datetime as _dt
    assert _dt.fromisoformat(first["start"]).tzinfo is not None
    assert _dt.fromisoformat(first["end"]).tzinfo is not None
    # Aufsteigend sortiert.
    starts = [o["start"] for o in body]
    assert starts == sorted(starts)


def test_occurrences_skips_disabled_windows(client, admin_headers):
    create = client.post(BASE, headers=admin_headers, json={
        "start_time": "19:00", "end_time": "23:30", "weekdays": [0, 1, 2, 3, 4, 5, 6],
    })
    window_id = create.json()["id"]
    disable = client.put(f"{BASE}/{window_id}", headers=admin_headers, json={"enabled": False})
    assert disable.status_code == 200

    r = client.get(OCCURRENCES, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_occurrences_rejects_days_out_of_range(client, admin_headers):
    assert client.get(OCCURRENCES, headers=admin_headers, params={"days": 0}).status_code == 422
    assert client.get(OCCURRENCES, headers=admin_headers, params={"days": 8}).status_code == 422


def test_occurrences_forbidden_for_regular_user(client, user_headers):
    r = client.get(OCCURRENCES, headers=user_headers)
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Tests laufen lassen — sie müssen fehlschlagen**

```bash
cd backend && python -m pytest tests/api/test_core_uptime_routes.py -k occurrences -v
```

Erwartet: 404 statt 200 — die Route existiert noch nicht.

- [ ] **Step 3: Das Response-Schema ergänzen**

In `backend/app/schemas/sleep.py` direkt **nach** der bestehenden Klasse `CoreUptimeWindowResponse` einfügen:

```python
class CoreUptimeOccurrence(BaseModel):
    """One resolved instance of a core-uptime window, as absolute UTC timestamps.

    Consumed by the Always-Awake UI to preview whether a chosen expiry would be
    clamped to a window start — a plain interval comparison, so the frontend
    needs no weekday/midnight logic of its own.
    """
    window_id: int
    label: Optional[str] = None
    start: datetime
    end: datetime
```

`BaseModel`, `Optional` und `datetime` sind in dieser Datei bereits importiert.

- [ ] **Step 4: Die Route ergänzen**

In `backend/app/api/routes/sleep.py`:

Zuerst den Datei-Kopf um zwei Importe erweitern — nach `import logging` (Zeile 4):

```python
from datetime import datetime, timezone
```

und nach `from app.services.power import os_auto_suspend` (Zeile 41):

```python
from app.services.power import core_uptime as core_uptime_helpers
```

Außerdem `CoreUptimeOccurrence` in den bestehenden `from app.schemas.sleep import (...)`-Block aufnehmen (neben `CoreUptimeWindowResponse`).

Dann **nach** `list_core_uptime_windows` (endet Zeile 411) einfügen:

```python
@router.get(
    "/core-uptime/occurrences",
    response_model=list[CoreUptimeOccurrence],
)
@user_limiter.limit(get_limit("admin_operations"))
async def list_core_uptime_occurrences(
    request: Request, response: Response,
    days: int = Query(7, ge=1, le=7, description="Horizon in days"),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[CoreUptimeOccurrence]:
    """Resolve enabled core-uptime windows into concrete occurrences (admin only).

    Windows are stored as recurring server-local patterns; this returns them as
    absolute UTC timestamps so clients can compare them against
    `always_awake_until` directly.
    """
    rows = (
        db.query(CoreUptimeWindowModel)
        .filter(CoreUptimeWindowModel.enabled.is_(True))
        .order_by(CoreUptimeWindowModel.id.asc())
        .all()
    )
    occurrences = core_uptime_helpers.expand_occurrences(datetime.now(), rows, days=days)
    return [
        CoreUptimeOccurrence(
            window_id=o.window_id,
            label=o.label,
            start=o.start.astimezone(timezone.utc),
            end=o.end.astimezone(timezone.utc),
        )
        for o in occurrences
    ]
```

- [ ] **Step 5: Tests laufen lassen — sie müssen bestehen**

```bash
cd backend && python -m pytest tests/api/test_core_uptime_routes.py -v
```

Erwartet: alle PASS, auch die bestehenden Fenster-Tests.

- [ ] **Step 6: Die volle Sleep-Testgruppe als Regression**

```bash
cd backend && python -m pytest tests/test_sleep.py tests/test_sleep_schemas.py tests/services/test_sleep_always_awake.py tests/services/test_sleep_core_uptime_integration.py tests/api/test_sleep_always_awake_routes.py tests/api/test_core_uptime_routes.py -q
```

Erwartet: alle PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/sleep.py backend/app/api/routes/sleep.py backend/tests/api/test_core_uptime_routes.py
git commit -m "feat(sleep): Endpoint fuer aufgeloeste Kernbetriebszeit-Termine"
```

---

## Task 4: Frontend-API-Client und reiner Clamp-Helper

**Files:**
- Modify: `client/src/api/sleep.ts`
- Create: `client/src/lib/coreUptimeClamp.ts`
- Test: `client/src/__tests__/lib/coreUptimeClamp.test.ts`

**Interfaces:**
- Consumes: `GET /api/system/sleep/core-uptime/occurrences` aus Task 3
- Produces:
  - `interface CoreUptimeOccurrence { window_id: number; label: string | null; start: string; end: string }` (exportiert aus `api/sleep.ts`)
  - `getCoreUptimeOccurrences(days?: number): Promise<CoreUptimeOccurrence[]>`
  - `clampToCoreUptime(untilIso: string, occurrences: CoreUptimeOccurrence[], now?: Date): { until: string; clampedTo: CoreUptimeOccurrence | null }`
  - `findRunningOccurrence(occurrences: CoreUptimeOccurrence[], now?: Date): CoreUptimeOccurrence | null`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Neue Datei `client/src/__tests__/lib/coreUptimeClamp.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { clampToCoreUptime, findRunningOccurrence } from '../../lib/coreUptimeClamp';
import type { CoreUptimeOccurrence } from '../../api/sleep';

/** Occurrence aus lokalen Wanduhrzeiten bauen — unabhaengig von der TZ der CI. */
function occ(
  startLocal: string,
  endLocal: string,
  window_id = 1,
  label: string | null = null,
): CoreUptimeOccurrence {
  return {
    window_id,
    label,
    start: new Date(startLocal).toISOString(),
    end: new Date(endLocal).toISOString(),
  };
}

const NOW = new Date('2026-05-06T15:00:00');
const WINDOW = occ('2026-05-06T19:00:00', '2026-05-06T23:30:00', 7, 'Abend');

describe('clampToCoreUptime', () => {
  it('shortens an expiry that falls inside a future window', () => {
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(WINDOW.start);
    expect(result.clampedTo).toEqual(WINDOW);
  });

  it('leaves an expiry before the window untouched', () => {
    const until = new Date('2026-05-06T17:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('leaves an expiry past the window end untouched', () => {
    const until = new Date('2026-05-07T01:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('treats an expiry exactly on the window start as already clamped', () => {
    const result = clampToCoreUptime(WINDOW.start, [WINDOW], NOW);
    expect(result.until).toBe(WINDOW.start);
    expect(result.clampedTo).toEqual(WINDOW);
  });

  it('does not shorten when the window is already running', () => {
    const now = new Date('2026-05-06T20:00:00');
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], now);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('returns the earliest start when windows overlap', () => {
    const late = occ('2026-05-06T20:00:00', '2026-05-06T23:00:00', 2);
    const early = occ('2026-05-06T19:00:00', '2026-05-06T22:00:00', 3);
    const until = new Date('2026-05-06T21:00:00').toISOString();
    expect(clampToCoreUptime(until, [late, early], NOW).until).toBe(early.start);
    expect(clampToCoreUptime(until, [early, late], NOW).until).toBe(early.start);
  });

  it('is the identity with no occurrences', () => {
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });
});

describe('findRunningOccurrence', () => {
  it('returns the occurrence covering now', () => {
    const now = new Date('2026-05-06T20:00:00');
    expect(findRunningOccurrence([WINDOW], now)).toEqual(WINDOW);
  });

  it('returns null before the window starts', () => {
    expect(findRunningOccurrence([WINDOW], NOW)).toBeNull();
  });

  it('returns null exactly at the end (end is exclusive)', () => {
    const now = new Date('2026-05-06T23:30:00');
    expect(findRunningOccurrence([WINDOW], now)).toBeNull();
  });
});
```

- [ ] **Step 2: Test laufen lassen — er muss fehlschlagen**

```bash
cd client && npx vitest run src/__tests__/lib/coreUptimeClamp.test.ts
```

Erwartet: `Failed to resolve import "../../lib/coreUptimeClamp"`.

- [ ] **Step 3: Typ und API-Funktion ergänzen**

In `client/src/api/sleep.ts` nach dem bestehenden `CoreUptimeStatus`-Interface (Zeile 43-49) einfügen:

```ts
export interface CoreUptimeOccurrence {
  window_id: number;
  label: string | null;
  start: string;  // ISO 8601, UTC
  end: string;    // ISO 8601, UTC
}
```

Und ans Ende des Abschnitts „API functions", nach `getSleepCapabilities()`:

```ts
export async function getCoreUptimeOccurrences(days = 7): Promise<CoreUptimeOccurrence[]> {
  const response = await apiClient.get<CoreUptimeOccurrence[]>(
    '/api/system/sleep/core-uptime/occurrences',
    { params: { days } },
  );
  return response.data;
}
```

- [ ] **Step 4: Den reinen Helper implementieren**

Neue Datei `client/src/lib/coreUptimeClamp.ts`:

```ts
/**
 * Kernbetriebszeit-Kuerzung fuer den Always-Awake-Override.
 *
 * Reiner Intervallvergleich auf bereits aufgeloesten Fenster-Terminen — die
 * Wochentags- und Mitternachtslogik bleibt im Backend
 * (`services/power/core_uptime.py`). Ergebnisse muessen mit
 * `clamp_to_core_uptime_start()` dort uebereinstimmen; darum gewinnt bei
 * Ueberlappung ebenfalls der FRUEHESTE Start.
 */
import type { CoreUptimeOccurrence } from '../api/sleep';

export interface ClampResult {
  /** ISO-Zeitstempel, der gespeichert werden soll (gekuerzt oder original). */
  until: string;
  /** Das Fenster, auf dessen Beginn gekuerzt wurde — null, wenn nicht gekuerzt. */
  clampedTo: CoreUptimeOccurrence | null;
}

export function clampToCoreUptime(
  untilIso: string,
  occurrences: CoreUptimeOccurrence[],
  now: Date = new Date(),
): ClampResult {
  const until = new Date(untilIso).getTime();
  const nowMs = now.getTime();

  let best: CoreUptimeOccurrence | null = null;
  let bestStart = Number.POSITIVE_INFINITY;

  for (const o of occurrences) {
    const start = new Date(o.start).getTime();
    const end = new Date(o.end).getTime();
    // Nur kuenftige Fensterbeginne kuerzen: ein bereits laufendes Fenster
    // hat seinen Beginn in der Vergangenheit, da gibt es nichts zu kuerzen.
    if (start > nowMs && until >= start && until < end && start < bestStart) {
      best = o;
      bestStart = start;
    }
  }

  if (best === null) return { until: untilIso, clampedTo: null };
  return { until: best.start, clampedTo: best };
}

export function findRunningOccurrence(
  occurrences: CoreUptimeOccurrence[],
  now: Date = new Date(),
): CoreUptimeOccurrence | null {
  const nowMs = now.getTime();
  for (const o of occurrences) {
    // start inklusiv, end exklusiv — wie im Backend.
    if (new Date(o.start).getTime() <= nowMs && nowMs < new Date(o.end).getTime()) {
      return o;
    }
  }
  return null;
}
```

- [ ] **Step 5: Test laufen lassen — er muss bestehen**

```bash
cd client && npx vitest run src/__tests__/lib/coreUptimeClamp.test.ts
```

Erwartet: alle 10 Tests PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/api/sleep.ts client/src/lib/coreUptimeClamp.ts client/src/__tests__/lib/coreUptimeClamp.test.ts
git commit -m "feat(sleep): Frontend-Helper fuer die Kernbetriebszeit-Kuerzung"
```

---

## Task 5: Panel-Integration, Hinweise und i18n

**Files:**
- Modify: `client/src/components/power/AlwaysAwakePanel.tsx`
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`
- Test: `client/src/__tests__/components/power/AlwaysAwakePanel.test.tsx` (Create)

**Interfaces:**
- Consumes: `getCoreUptimeOccurrences()`, `clampToCoreUptime()`, `findRunningOccurrence()`, `CoreUptimeOccurrence` aus Task 4
- Produces: keine — Endpunkt der Feature-Kette

- [ ] **Step 1: Die i18n-Keys ergänzen**

In `client/src/i18n/locales/de/system.json`, im Block `sleep.alwaysAwake`, nach `"scheduleHint"` einfügen (Komma am vorigen Eintrag nicht vergessen):

```json
      "clampPreview": "Wird auf {{time}} gekürzt — ab dann übernimmt die Kernbetriebszeit (wach bis {{end}}).",
      "clampActive": "Endet um {{time}} mit dem Beginn der Kernbetriebszeit (wach bis {{end}}).",
      "clampBadge": "Wird auf den Beginn der Kernbetriebszeit gekürzt",
      "coreUptimeRunning": "Kernbetriebszeit läuft bis {{end}} — bis dahin bleibt das System ohnehin wach."
```

In `client/src/i18n/locales/en/system.json`, an derselben Stelle:

```json
      "clampPreview": "Will be shortened to {{time}} — core operating hours take over from then (awake until {{end}}).",
      "clampActive": "Ends at {{time}} when core operating hours begin (awake until {{end}}).",
      "clampBadge": "Will be shortened to the start of core operating hours",
      "coreUptimeRunning": "Core operating hours run until {{end}} — the system stays awake until then anyway."
```

- [ ] **Step 2: JSON-Gültigkeit prüfen**

```bash
cd client && node -e "const de=require('./src/i18n/locales/de/system.json'); const en=require('./src/i18n/locales/en/system.json'); const d=Object.keys(de.sleep.alwaysAwake), e=Object.keys(en.sleep.alwaysAwake); console.log('DE', d.length, 'EN', e.length); const miss=d.filter(k=>!e.includes(k)).concat(e.filter(k=>!d.includes(k))); if (miss.length) { console.error('MISMATCH', miss); process.exit(1); } console.log('keys match');"
```

Erwartet: gleiche Anzahl, Ausgabe `keys match`.

- [ ] **Step 3: Den fehlschlagenden Panel-Test schreiben**

Neue Datei `client/src/__tests__/components/power/AlwaysAwakePanel.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AlwaysAwakePanel } from '../../../components/power/AlwaysAwakePanel';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
  getCoreUptimeOccurrences,
} from '../../../api/sleep';

vi.mock('../../../api/sleep', () => ({
  getSleepConfig: vi.fn(),
  getSleepStatus: vi.fn(),
  updateSleepConfig: vi.fn(),
  getCoreUptimeOccurrences: vi.fn(),
}));

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}));

const mockedConfig = vi.mocked(getSleepConfig);
const mockedStatus = vi.mocked(getSleepStatus);
const mockedUpdate = vi.mocked(updateSleepConfig);
const mockedOccurrences = vi.mocked(getCoreUptimeOccurrences);

/** Fenster, das in 4 Stunden beginnt und 6 Stunden dauert. */
function windowInHours(startInHours: number, durationHours: number) {
  const start = new Date(Date.now() + startInHours * 3600 * 1000);
  const end = new Date(start.getTime() + durationHours * 3600 * 1000);
  return {
    window_id: 1,
    label: 'Abend',
    start: start.toISOString(),
    end: end.toISOString(),
  };
}

function baseConfig(overrides: Record<string, unknown> = {}) {
  return {
    always_awake_enabled: false,
    always_awake_until: null,
    schedule_enabled: false,
    core_uptime_enabled: true,
    ...overrides,
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedStatus.mockResolvedValue({ always_awake: { expires_in_seconds: null } } as never);
  mockedUpdate.mockResolvedValue({} as never);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AlwaysAwakePanel — Kernbetriebszeit-Kuerzung', () => {
  // i18n ist in Component-Tests nicht initialisiert: t() liefert den rohen Key.

  it('sends the clamped value when the chosen expiry falls into a window', async () => {
    const occurrence = windowInHours(4, 6); // beginnt in 4h, laeuft 6h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    // "8h" landet 8h in der Zukunft — also innerhalb des Fensters (4h..10h).
    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    expect(mockedUpdate).toHaveBeenCalledWith({
      always_awake_enabled: true,
      always_awake_until: occurrence.start,
    });
  });

  it('sends the raw value when the chosen expiry clears the window end', async () => {
    const occurrence = windowInHours(1, 2); // 1h..3h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    const sent = mockedUpdate.mock.calls[0][0] as { always_awake_until: string };
    expect(sent.always_awake_until).not.toBe(occurrence.start);
  });

  it('shows the clamp hint while the affected preset is focused', async () => {
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([windowInHours(4, 6)] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(screen.queryByText('sleep.alwaysAwake.clampPreview')).not.toBeInTheDocument();
    await user.hover(button);
    expect(await screen.findByText('sleep.alwaysAwake.clampPreview')).toBeInTheDocument();
  });

  it('explains an already-clamped active override after reload', async () => {
    const occurrence = windowInHours(4, 6);
    mockedConfig.mockResolvedValue(
      baseConfig({ always_awake_enabled: true, always_awake_until: occurrence.start }),
    );
    mockedStatus.mockResolvedValue({
      always_awake: { expires_in_seconds: 4 * 3600 },
    } as never);
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    render(<AlwaysAwakePanel />);

    expect(await screen.findByText('sleep.alwaysAwake.clampActive')).toBeInTheDocument();
  });

  it('reports a currently running window instead of a clamp hint', async () => {
    const start = new Date(Date.now() - 3600 * 1000);
    const end = new Date(Date.now() + 3 * 3600 * 1000);
    mockedConfig.mockResolvedValue(
      baseConfig({ always_awake_enabled: true, always_awake_until: end.toISOString() }),
    );
    mockedStatus.mockResolvedValue({
      always_awake: { expires_in_seconds: 3 * 3600 },
    } as never);
    mockedOccurrences.mockResolvedValue([
      { window_id: 1, label: null, start: start.toISOString(), end: end.toISOString() },
    ] as never);

    render(<AlwaysAwakePanel />);

    expect(await screen.findByText('sleep.alwaysAwake.coreUptimeRunning')).toBeInTheDocument();
    expect(screen.queryByText('sleep.alwaysAwake.clampActive')).not.toBeInTheDocument();
  });

  it('does not request occurrences when core uptime is disabled', async () => {
    mockedConfig.mockResolvedValue(baseConfig({ core_uptime_enabled: false }));
    mockedOccurrences.mockResolvedValue([] as never);

    render(<AlwaysAwakePanel />);

    await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(mockedOccurrences).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 4: Test laufen lassen — er muss fehlschlagen**

```bash
cd client && npx vitest run src/__tests__/components/power/AlwaysAwakePanel.test.tsx
```

Erwartet: FAIL — `getCoreUptimeOccurrences` wird vom Panel noch nicht importiert, der ungekürzte Wert wird gesendet, die Hinweis-Keys existieren im DOM nicht.

- [ ] **Step 5: Das Panel anpassen**

In `client/src/components/power/AlwaysAwakePanel.tsx`:

**5a — Importe erweitern** (Zeile 13-17):

```tsx
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
  getCoreUptimeOccurrences,
  type CoreUptimeOccurrence,
} from '../../api/sleep';
import { clampToCoreUptime, findRunningOccurrence } from '../../lib/coreUptimeClamp';
```

**5b — State ergänzen** (neben den bestehenden `useState`-Zeilen):

```tsx
  const [occurrences, setOccurrences] = useState<CoreUptimeOccurrence[]>([]);
  const [hoveredPreset, setHoveredPreset] = useState<Exclude<Preset, 'permanent' | 'custom'> | null>(null);
```

**5c — In `refresh()`** direkt nach `setCoreUptimeEnabled(cfg.core_uptime_enabled ?? false);` einfügen:

```tsx
      if (cfg.core_uptime_enabled) {
        setOccurrences(await getCoreUptimeOccurrences(7));
      } else {
        setOccurrences([]);
      }
```

**5d — `setPreset()`**: die Berechnung von `newUntil` (Zeile 159-162) ersetzen durch:

```tsx
    const rawUntil =
      preset === 'permanent'
        ? null
        : new Date(Date.now() + PRESET_HOURS[preset] * 3600 * 1000).toISOString();
    // Ein Ablauf innerhalb eines kuenftigen Kernbetriebszeit-Fensters wird auf
    // dessen Beginn gekuerzt — dieselbe Regel wie im Backend. Der optimistische
    // State muss den gekuerzten Wert tragen, sonst springt die Anzeige nach dem
    // naechsten refresh() zurueck.
    const newUntil = rawUntil ? clampToCoreUptime(rawUntil, occurrences).until : null;
```

und die Zeile `setExpiresIn(newUntil ? PRESET_HOURS[...] * 3600 : null);` ersetzen durch:

```tsx
    setExpiresIn(
      newUntil ? Math.max(0, Math.floor((new Date(newUntil).getTime() - Date.now()) / 1000)) : null,
    );
```

**5e — `setCustomPreset()`**: nach `const target = new Date(localValue);` die Zeile `const newUntil = target.toISOString();` ersetzen durch:

```tsx
    const newUntil = clampToCoreUptime(target.toISOString(), occurrences).until;
```

und `setExpiresIn(Math.floor(delta / 1000));` ersetzen durch:

```tsx
    setExpiresIn(Math.max(0, Math.floor((new Date(newUntil).getTime() - Date.now()) / 1000)));
```

Die Zeile `const delta = target.getTime() - Date.now();` wird dadurch verwaist und **muss gelöscht** werden — sonst schlägt `npx eslint .` mit `no-unused-vars` fehl (0-Error-Gate). Die Validierung rechnet ihr eigenes Delta in `computePickerError()`.

**5f — Abgeleitete Werte** vor dem `if (loading)`-Block einfügen:

```tsx
  const runningOccurrence = findRunningOccurrence(occurrences);

  const activeClamp =
    until && !runningOccurrence
      ? occurrences.find((o) => new Date(o.start).getTime() === new Date(until).getTime()) ?? null
      : null;

  const previewFor = (p: Exclude<Preset, 'permanent' | 'custom'>) =>
    clampToCoreUptime(
      new Date(Date.now() + PRESET_HOURS[p] * 3600 * 1000).toISOString(),
      occurrences,
    );

  const hoveredClamp = hoveredPreset ? previewFor(hoveredPreset) : null;
  const pickerClamp =
    pickerOpen && pickerValue && !pickerError
      ? clampToCoreUptime(new Date(pickerValue).toISOString(), occurrences)
      : null;
```

**5g — Hinweise im aktiven Bereich**: den bestehenden Block

```tsx
          {(scheduleEnabled || coreUptimeEnabled) && until && (
```

so erweitern, dass die neuen Hinweise **davor** stehen und der bestehende Hinweis nur greift, wenn keiner der neuen zutrifft:

```tsx
          {runningOccurrence && (
            <div className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-300">
              {t('sleep.alwaysAwake.coreUptimeRunning', {
                end: formatTime(runningOccurrence.end),
              })}
            </div>
          )}
          {activeClamp && (
            <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.alwaysAwake.clampActive', {
                time: formatTime(activeClamp.start),
                end: formatTime(activeClamp.end),
              })}
            </div>
          )}
          {(scheduleEnabled || coreUptimeEnabled) && until && !runningOccurrence && !activeClamp && (
```

Der `!until`-Zweig (`hintPermanentClearToResume`) bleibt unverändert.

**5h — Preset-Buttons markieren**: im `.map()` über `['1h','4h','8h','permanent']` vor dem `return` ergänzen:

```tsx
          const clampPreview = p === 'permanent' ? null : previewFor(p).clampedTo;
```

und am `<button>` ergänzen:

```tsx
              title={clampPreview ? t('sleep.alwaysAwake.clampBadge') : undefined}
              onMouseEnter={() => { if (p !== 'permanent') setHoveredPreset(p); }}
              onMouseLeave={() => setHoveredPreset(null)}
              onFocus={() => { if (p !== 'permanent') setHoveredPreset(p); }}
              onBlur={() => setHoveredPreset(null)}
```

> **Wichtig:** die `if`-Form ist Pflicht. Mit `p !== 'permanent' && setHoveredPreset(p)` narrowt TypeScript `p` nicht auf `Exclude<Preset, 'permanent' | 'custom'>`, und `npm run build` (tsc -b) schlägt fehl.

sowie im `className`-Ausdruck den Nicht-Aktiv-Zweig um den Marker erweitern — aus

```tsx
                  : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
```

wird

```tsx
                  : clampPreview
                    ? 'bg-slate-800/40 text-slate-400 border border-dashed border-amber-500/40 hover:text-amber-300'
                    : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
```

**5i — Vorschauzeile unter der Preset-Reihe**: direkt **nach** dem schließenden `</div>` des `flex flex-wrap gap-2 pt-1`-Containers einfügen:

```tsx
      {hoveredClamp?.clampedTo && (
        <p className="text-[11px] text-amber-300">
          {t('sleep.alwaysAwake.clampPreview', {
            time: formatTime(hoveredClamp.until),
            end: formatTime(hoveredClamp.clampedTo.end),
          })}
        </p>
      )}
```

**5j — Vorschau im Picker**: im Popover nach dem `{pickerError && ...}`-Block einfügen:

```tsx
              {pickerClamp?.clampedTo && (
                <p className="text-[11px] text-amber-300">
                  {t('sleep.alwaysAwake.clampPreview', {
                    time: formatTime(pickerClamp.until),
                    end: formatTime(pickerClamp.clampedTo.end),
                  })}
                </p>
              )}
```

- [ ] **Step 6: Test laufen lassen — er muss bestehen**

```bash
cd client && npx vitest run src/__tests__/components/power/AlwaysAwakePanel.test.tsx
```

Erwartet: alle 6 Tests PASS.

- [ ] **Step 7: Frontend-Gates**

```bash
cd client && npx eslint . ; if ($?) { npm run build }
```

Erwartet: eslint mit 0 Fehlern (das CI-Gate ist 0-Error), `npm run build` (tsc -b über app/node/TEST-Projekte + Vite-Build) ohne Fehler.

- [ ] **Step 8: Volle Frontend-Suite als Regression**

```bash
cd client && npx vitest run
```

Erwartet: alle PASS — insbesondere `AlwaysAwakePill.test.tsx` und `SleepConfigPanel.test.tsx`.

- [ ] **Step 9: Commit**

```bash
git add client/src/components/power/AlwaysAwakePanel.tsx client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json client/src/__tests__/components/power/AlwaysAwakePanel.test.tsx
git commit -m "feat(sleep): UI-Hinweise fuer die Kernbetriebszeit-Kuerzung von Always-Awake"
```

---

## Abschluss

- [ ] **Backend-Regression über die betroffenen Suiten**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_helpers.py tests/services/test_core_uptime_inhibitor.py tests/services/test_core_uptime_rtc_guard.py tests/services/test_sleep_always_awake.py tests/services/test_sleep_core_uptime_integration.py tests/api/test_core_uptime_routes.py tests/api/test_sleep_always_awake_routes.py tests/test_sleep.py tests/test_sleep_schemas.py -q
```

Erwartet: alle PASS.

> Die **vollständige** Backend-Suite unter Windows ist bekanntermaßen unzuverlässig (Isolations-Flakes in Permission-Tests, `os_sleep_inspector`-Subprozess-Tests). Sie gehört in die CI, nicht in diesen Durchlauf.

- [ ] **Doku-Abgleich**

Prüfen, ob `docs/` eine Beschreibung des Always-Awake-Verhaltens enthält, die die Kürzungsregel erwähnen sollte. `grep`/`rg` sind in diesem Repo per Hook gesperrt — stattdessen PowerShell:

```powershell
Get-ChildItem "D:\Programme (x86)\Baluhost\docs" -Recurse -Include *.md |
  Where-Object { $_.FullName -notmatch "superpowers" } |
  Select-String -Pattern "always.awake|immer wach" |
  Select-Object -ExpandProperty Path -Unique
```

Falls Treffer: die Kürzungsregel dort in zwei Sätzen ergänzen und mitcommitten. Falls keine Treffer: nichts tun.

- [ ] **CHANGELOG**

Nicht anfassen. Der `## [Unreleased]`-Abschnitt wird beim Release-Prepare hand-kuratiert (siehe `.claude/rules/production.md`).
