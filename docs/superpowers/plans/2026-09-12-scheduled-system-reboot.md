# Geplanter Systemneustart — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Admin konfiguriert Wochentag und Uhrzeit; BaluHost startet die Box dann vollständig neu, weckt sie dafür bei Bedarf aus dem Suspend und legt sie danach wieder schlafen — mit Notifications, die den Vorgang als geplant erkennbar machen.

**Architecture:** Die Ausführung liegt im Power-Layer (`services/power/`), angestoßen vom bestehenden 60-Sekunden-Tick in `SleepManagerService._schedule_check_loop()`. Dort liegen bereits Kernbetriebszeit, Display-Erkennung, `enter_true_suspend()` und die `wake_at`-Klemmung. Im Scheduler erscheint das Feature als Registry-Eintrag `system_reboot` für Toggle, Konfiguration und Historie — **ohne** APScheduler-Job.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest; React 18 + TypeScript + Vitest, i18next.

**Spec:** `docs/superpowers/specs/2026-09-12-scheduled-system-reboot-design.md`

## Global Constraints

- **Standardmäßig deaktiviert.** Kein `scheduler_configs`-Row = aus. Beide `_is_enabled`-Pfade brauchen einen expliziten `system_reboot`-Zweig, sonst greift ihr `return True`-Fallback.
- **Nur Admins.** Alle Schreibrouten hängen bereits an `Depends(deps.get_current_admin)`. Keine neuen Power-Rechte.
- **Die Wiederholungssperre ist nicht optional.** `last_completed_due_at` muss auf **allen drei** Wegen aus `armed` heraus gesetzt werden (Erfolg, Fristablauf, Ausführungsfehler) und zusätzlich beim Zurücksetzen vor einem Suspend. Fehlt einer, startet die Box in einer Schleife neu.
- **Zeitmodell.** Terminberechnung in server-lokaler **naiver** Zeit (wie `core_uptime.py`), Persistenz in **UTC-aware** `timestamptz`. Umrechnung ausschließlich an der Speichergrenze.
- **Sudoers-Zeile:** `@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl reboot` — genau so, ein Verb, keine Argumente, keine Wildcards.
- **Alembic:** neue Revision auf `down_revision = "e7c2a9d41f86"` (aktueller `alembic heads`, geprüft 2026-09-12). Nicht auf den Head der lokalen Dev-DB.
- **Windows/Dev:** Die volle Backend-Suite hängt auf Windows. Lokal nur die im jeweiligen Task genannten Testdateien laufen lassen; die volle Suite gehört der CI.
- **CRLF:** Das Repo läuft mit `core.autocrlf=true`. Neue Dateien normal schreiben, keine manuelle Zeilenendenbehandlung.
- **Dateigröße:** Konvention max. 500 Zeilen pro Datei (#301). Deshalb drei kleine Module statt eines großen.

---

## Dateistruktur

**Neu (Backend)**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/power/reboot_schedule.py` | Reine Terminmathematik. Keine DB, kein I/O. |
| `backend/app/services/power/reboot_state.py` | Zugriff auf `scheduled_reboot_state` und die Konfiguration; Phasenübergänge; `claim_wakeup()`. |
| `backend/app/services/power/scheduled_reboot.py` | Gates, Zustandsautomat (`tick`), Ausführung, `on_boot`. |
| `backend/app/models/scheduled_reboot.py` | ORM-Modell `ScheduledRebootState`. |
| `backend/alembic/versions/<rev>_scheduled_reboot_state.py` | Migration. |

**Geändert (Backend)**

| Datei | Änderung |
|---|---|
| `backend/app/schemas/scheduler.py` | Registry-Eintrag, `worker_job`-Flag, `RebootScheduleConfig`, `RebootPreviewResponse` |
| `backend/app/services/scheduler/service.py` | Default-Aus, Status-Zweig, Preview |
| `backend/app/services/scheduler/worker.py` | drei Stellen respektieren `worker_job` |
| `backend/app/api/routes/schedulers.py` | Validierung der `extra_config`, Audit, Preview-Route |
| `backend/app/schemas/sleep.py` | `SleepTrigger.SCHEDULED_REBOOT` |
| `backend/app/services/notifications/events.py` | vier EventTypes + Configs + Emitter |
| `backend/app/services/notifications/lifecycle_helpers.py` | Trigger-Label |
| `backend/app/services/power/sleep.py` | Tick-Aufruf, Klemmung, Suspend-Verdrängung |
| `backend/app/core/lifespan.py` | Boot-Übergabe, Unterdrückung der generischen Meldungen |
| `backend/app/models/__init__.py` | Modell-Import |

**Geändert (Frontend / Deploy / Doku)**

`client/src/api/schedulers.ts`, `client/src/components/scheduler/SchedulerConfigModal.tsx`,
`client/src/i18n/locales/{de,en}/scheduler.json`,
`deploy/install/templates/sudoers-baluhost-power`,
`.claude/rules/ci-cd-security.md`, `.claude/rules/architecture.md`, `CLAUDE.md`.

---

## Task 1: Reine Terminmathematik

**Files:**
- Create: `backend/app/services/power/reboot_schedule.py`
- Test: `backend/tests/services/test_reboot_schedule.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `next_weekday_occurrence(now: datetime, weekday: int, time_hhmm: str) -> datetime`
  - `due_occurrence(now: datetime, weekday: int, time_hhmm: str, within: timedelta) -> Optional[datetime]`
  - Beide arbeiten mit **naiven** server-lokalen `datetime`.

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_schedule.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.power.reboot_schedule'`

- [ ] **Step 3: Write the implementation**

`backend/app/services/power/reboot_schedule.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_reboot_schedule.py -v`
Expected: PASS (12 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/reboot_schedule.py backend/tests/services/test_reboot_schedule.py
git commit -m "feat(reboot): reine Terminmathematik für den geplanten Neustart"
```

---

## Task 2: Modell, Migration und Zustandszugriff

**Files:**
- Create: `backend/app/models/scheduled_reboot.py`
- Create: `backend/alembic/versions/<rev>_scheduled_reboot_state.py`
- Create: `backend/app/services/power/reboot_state.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/scheduler.py` (nur `RebootScheduleConfig`)
- Test: `backend/tests/services/test_reboot_state.py`

**Interfaces:**
- Consumes: `next_weekday_occurrence` aus Task 1.
- Produces:
  - `ScheduledRebootState` (ORM)
  - Konstanten `PHASE_IDLE`, `PHASE_ARMED`, `PHASE_EXECUTING`, `PHASE_RESUSPEND_PENDING`
  - `RebootScheduleConfig` (Pydantic, in `schemas/scheduler.py`)
  - `get_state(db) -> ScheduledRebootState`
  - `load_enabled_config(db) -> Optional[RebootScheduleConfig]`
  - `next_reboot_due(db, now_local: datetime) -> Optional[datetime]` (naiv-lokal)
  - `to_utc(naive_local: datetime) -> datetime`, `to_local(aware: datetime) -> datetime`

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_state.py`:

```python
"""Zustands- und Konfigurationszugriff für den geplanten Systemneustart."""
import json
from datetime import datetime, timedelta, timezone

from app.models.scheduler_history import SchedulerConfig
from app.services.power import reboot_state
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_IDLE,
    get_state,
    load_enabled_config,
    next_reboot_due,
    to_local,
    to_utc,
)


def _write_config(db, *, enabled: bool, extra: dict | None = None) -> None:
    row = SchedulerConfig(
        scheduler_name="system_reboot",
        is_enabled=enabled,
        interval_seconds=604800,
        extra_config=json.dumps(extra) if extra is not None else None,
    )
    db.add(row)
    db.commit()


def test_get_state_creates_singleton(db_session):
    state = get_state(db_session)
    assert state.id == 1
    assert state.phase == PHASE_IDLE
    assert state.woke_for_reboot is False
    # Zweiter Aufruf legt keine zweite Zeile an.
    again = get_state(db_session)
    assert again.id == 1


def test_get_state_persists_changes(db_session):
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    db_session.commit()
    assert get_state(db_session).phase == PHASE_ARMED


def test_load_enabled_config_none_without_row(db_session):
    assert load_enabled_config(db_session) is None


def test_load_enabled_config_none_when_disabled(db_session):
    _write_config(db_session, enabled=False, extra={"weekday": 6, "time": "04:00"})
    assert load_enabled_config(db_session) is None


def test_load_enabled_config_returns_defaults_for_empty_extra(db_session):
    _write_config(db_session, enabled=True, extra=None)
    cfg = load_enabled_config(db_session)
    assert cfg is not None
    assert cfg.weekday == 6
    assert cfg.time == "04:00"
    assert cfg.retry_window_hours == 6
    assert cfg.warning_lead_minutes == 10


def test_load_enabled_config_reads_values(db_session):
    _write_config(
        db_session,
        enabled=True,
        extra={"weekday": 2, "time": "03:30", "retry_window_hours": 2,
               "warning_lead_minutes": 0},
    )
    cfg = load_enabled_config(db_session)
    assert (cfg.weekday, cfg.time, cfg.retry_window_hours, cfg.warning_lead_minutes) == (
        2, "03:30", 2, 0
    )


def test_load_enabled_config_survives_corrupt_json(db_session):
    row = SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config="{nicht json",
    )
    db_session.add(row)
    db_session.commit()
    cfg = load_enabled_config(db_session)
    assert cfg is not None and cfg.time == "04:00"  # Defaults statt Absturz


def test_next_reboot_due_none_when_disabled(db_session):
    assert next_reboot_due(db_session, datetime(2026, 9, 13, 1, 0)) is None


def test_next_reboot_due_uses_config(db_session):
    _write_config(db_session, enabled=True, extra={"weekday": 6, "time": "04:00"})
    due = next_reboot_due(db_session, datetime(2026, 9, 13, 1, 0))
    assert due == datetime(2026, 9, 13, 4, 0)


def test_utc_roundtrip_keeps_wall_clock():
    naive_local = datetime(2026, 9, 13, 4, 0)
    aware = to_utc(naive_local)
    assert aware.tzinfo is not None
    assert to_local(aware) == naive_local


def test_to_local_accepts_naive_as_utc():
    """Spiegelt `_is_always_awake`: naive Werte aus SQLite gelten als UTC."""
    aware = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    naive_from_db = aware.replace(tzinfo=None)
    assert to_local(naive_from_db) == to_local(aware)
```

> Die Fixture `db_session` existiert bereits in `backend/tests/conftest.py`. Wenn
> sie unter einem anderen Namen läuft, den vorhandenen Namen verwenden statt eine
> neue Fixture zu bauen — vorher `sed -n '/def db_session/,+10p' backend/tests/conftest.py` prüfen.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.power.reboot_state'`

- [ ] **Step 3: Add the Pydantic config schema**

In `backend/app/schemas/scheduler.py`, direkt vor `SCHEDULER_REGISTRY`:

```python
class RebootScheduleConfig(BaseModel):
    """`extra_config` des Schedulers `system_reboot`.

    Zeiten sind server-lokal, wie die Kernbetriebszeit-Fenster.
    """

    weekday: int = Field(
        default=6, ge=0, le=6,
        description="0=Montag .. 6=Sonntag, wie CoreUptimeWindow.weekdays",
    )
    time: str = Field(
        default="04:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
        description="Uhrzeit HH:MM, server-lokal",
    )
    retry_window_hours: int = Field(
        default=6, ge=1, le=24,
        description="Nachholfrist ab dem Termin, in Stunden",
    )
    warning_lead_minutes: int = Field(
        default=10, ge=0, le=120,
        description="Vorwarnung in Minuten; 0 schaltet sie ab",
    )
```

- [ ] **Step 4: Write the ORM model**

`backend/app/models/scheduled_reboot.py`:

```python
"""Datenbankmodell für den geplanten Systemneustart.

Eine einzige Zeile (id=1). Bewusst getrennt von `scheduler_configs.extra_config`
(dort steht, was der Admin gesetzt hat — hier, wo der Automat steht) und von
`scheduler_executions` (dieser Zustand wird beim Boot in `lifespan` gelesen,
bevor irgendein Scheduler-Code läuft).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ScheduledRebootState(Base):
    """Singleton-Zustand des Neustart-Automaten (id=1)."""

    __tablename__ = "scheduled_reboot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    phase: Mapped[str] = mapped_column(
        String(24), nullable=False, default="idle", server_default="idle"
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Wiederholungssperre. Ohne sie erkennt der Automat nach dem Neustart
    # denselben Termin erneut als fällig und startet in einer Schleife neu.
    last_completed_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Die Box wurde für diesen Termin aus dem Suspend geholt; nur dann wird
    # nach dem Neustart wieder suspendiert.
    woke_for_reboot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # Der vom Termin verdrängte reguläre Weckzeitpunkt. NULL ist gültig und
    # bedeutet „suspendieren ohne RTC-Alarm".
    resuspend_wake_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    execution_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_skip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    warned_for_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phase_entered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScheduledRebootState(phase={self.phase}, due_at={self.due_at})>"
```

In `backend/app/models/__init__.py` den Import ergänzen — die vorhandene
Import-/`__all__`-Form der Datei übernehmen, zum Beispiel:

```python
from app.models.scheduled_reboot import ScheduledRebootState  # noqa: F401
```

- [ ] **Step 5: Create the Alembic migration**

Run: `cd backend && python -m alembic revision -m "scheduled reboot state"`

Den erzeugten Rumpf füllen. **`down_revision` muss `"e7c2a9d41f86"` sein** — das
ist der echte `alembic heads` vom 2026-09-12. Nicht den Head der lokalen Dev-DB
übernehmen; das hat schon einmal einen Multi-Head-Deploy-Fehler erzeugt
(PR #123 → #124). Vor dem Schreiben mit `python -m alembic heads` gegenprüfen.

```python
def upgrade() -> None:
    op.create_table(
        "scheduled_reboot_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=24), server_default="idle", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("woke_for_reboot", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("resuspend_wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_id", sa.Integer(), nullable=True),
        sa.Column("last_skip_reason", sa.String(length=64), nullable=True),
        sa.Column("warned_for_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scheduled_reboot_state")
```

- [ ] **Step 6: Write the state access module**

`backend/app/services/power/reboot_state.py`:

```python
"""Zustands- und Konfigurationszugriff für den geplanten Systemneustart.

Hier — und nur hier — liegt die Grenze zwischen der naiv-lokalen Rechnung in
`reboot_schedule.py` und der UTC-aware Persistenz in der Datenbank.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.scheduled_reboot import ScheduledRebootState
from app.models.scheduler_history import SchedulerConfig
from app.schemas.scheduler import RebootScheduleConfig
from app.services.power.reboot_schedule import next_weekday_occurrence

logger = logging.getLogger(__name__)

SCHEDULER_NAME = "system_reboot"

PHASE_IDLE = "idle"
PHASE_ARMED = "armed"
PHASE_EXECUTING = "executing"
PHASE_RESUSPEND_PENDING = "resuspend_pending"


def to_utc(naive_local: datetime) -> datetime:
    """Naive server-lokale Zeit -> UTC-aware.

    `astimezone()` auf einem naiven Wert liest ihn als lokale Zeit — genau das
    ist hier gewollt (dasselbe Vorgehen wie in `core_uptime.clamp_to_core_uptime_start`).
    """
    return naive_local.astimezone(timezone.utc)


def to_local(value: datetime) -> datetime:
    """DB-Wert -> naive server-lokale Zeit.

    Naive Werte gelten als UTC (SQLite liefert timestamptz naiv zurück) —
    dieselbe Annahme wie in `SleepManagerService._is_always_awake`.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().replace(tzinfo=None)


def get_state(db: Session) -> ScheduledRebootState:
    """Die Singleton-Zeile, bei Bedarf angelegt."""
    state = db.query(ScheduledRebootState).filter(ScheduledRebootState.id == 1).first()
    if state is None:
        state = ScheduledRebootState(id=1, phase=PHASE_IDLE, woke_for_reboot=False)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def load_enabled_config(db: Session) -> Optional[RebootScheduleConfig]:
    """Die Konfiguration, oder `None` wenn das Feature aus ist.

    Kein Row = aus. Unlesbares JSON fällt auf die Defaults zurück statt zu
    werfen: ein kaputtes Konfigurationsfeld darf den Sleep-Tick nicht abreißen.
    """
    row = (
        db.query(SchedulerConfig)
        .filter(SchedulerConfig.scheduler_name == SCHEDULER_NAME)
        .first()
    )
    if row is None or not row.is_enabled:
        return None

    raw: dict = {}
    if row.extra_config:
        try:
            parsed = json.loads(row.extra_config)
            if isinstance(parsed, dict):
                raw = parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("system_reboot: extra_config unlesbar — nutze Defaults")

    try:
        return RebootScheduleConfig(**raw)
    except Exception as exc:
        logger.warning("system_reboot: extra_config ungültig (%s) — nutze Defaults", exc)
        return RebootScheduleConfig()


def next_reboot_due(db: Session, now_local: datetime) -> Optional[datetime]:
    """Nächster Neustart-Termin als naive lokale Zeit, oder `None`."""
    config = load_enabled_config(db)
    if config is None:
        return None
    try:
        return next_weekday_occurrence(now_local, config.weekday, config.time)
    except ValueError as exc:
        logger.warning("system_reboot: Termin nicht berechenbar (%s)", exc)
        return None


def reset_to_idle(
    db: Session,
    state: ScheduledRebootState,
    *,
    completed_due_at: Optional[datetime] = None,
) -> None:
    """Zurück auf `idle` und alle Termin-gebundenen Felder räumen.

    `completed_due_at` setzt die Wiederholungssperre. Sie MUSS auf jedem Weg
    aus `armed` heraus gesetzt werden — Erfolg, Fristablauf, Ausführungsfehler
    und Rücksetzen vor einem Suspend. Fehlt einer davon, erkennt der Automat
    denselben Termin erneut als fällig und startet in einer Schleife neu.
    """
    if completed_due_at is not None:
        state.last_completed_due_at = completed_due_at
    state.phase = PHASE_IDLE
    state.due_at = None
    state.deadline_at = None
    state.execution_id = None
    state.woke_for_reboot = False
    state.resuspend_wake_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_state.py -v`
Expected: PASS (11 Tests)

- [ ] **Step 8: Verify the migration applies and reverts**

Run: `cd backend && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: dreimal ohne Fehler; danach `python -m alembic heads` zeigt genau **einen** Head.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/scheduled_reboot.py backend/app/models/__init__.py \
        backend/alembic/versions/ backend/app/services/power/reboot_state.py \
        backend/app/schemas/scheduler.py backend/tests/services/test_reboot_state.py
git commit -m "feat(reboot): Zustandstabelle, Migration und Konfigurationszugriff"
```

---

## Task 3: Registry-Eintrag ohne Worker-Job

**Files:**
- Modify: `backend/app/schemas/scheduler.py` (Registry)
- Modify: `backend/app/services/scheduler/worker.py` (drei Stellen)
- Modify: `backend/app/services/scheduler/service.py` (Default-Aus)
- Test: `backend/tests/services/test_scheduler_reboot_registry.py`

**Interfaces:**
- Consumes: nichts aus früheren Tasks.
- Produces: Registry-Schlüssel `"system_reboot"` mit `worker_job: False`; der Worker legt für ihn weder Job noch `scheduler_state`-Zeile an.

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_scheduler_reboot_registry.py`:

```python
"""system_reboot ist ein Registry-Eintrag OHNE APScheduler-Job."""
from unittest.mock import MagicMock

from app.schemas.scheduler import SCHEDULER_REGISTRY
from app.services.scheduler.worker import SchedulerWorker


def test_registry_entry_exists_and_declares_no_worker_job():
    entry = SCHEDULER_REGISTRY["system_reboot"]
    assert entry["worker_job"] is False
    assert entry["can_run_manually"] is False


def test_every_other_entry_keeps_its_worker_job():
    """Der info.get(..., True)-Default darf nichts anderes abschalten."""
    for name, info in SCHEDULER_REGISTRY.items():
        if name == "system_reboot":
            continue
        assert info.get("worker_job", True) is True, name


def test_worker_does_not_schedule_a_job_for_system_reboot(monkeypatch):
    worker = SchedulerWorker()
    worker.scheduler = MagicMock()
    added: list[str] = []
    monkeypatch.setattr(
        worker, "_add_job", lambda name, interval: added.append(name)
    )
    monkeypatch.setattr(worker, "_is_scheduler_enabled", lambda name, db: True)
    monkeypatch.setattr(worker, "_get_interval", lambda name, info, db: 3600)
    monkeypatch.setattr(
        "app.services.scheduler.worker.SessionLocal", lambda: MagicMock()
    )

    worker._load_and_schedule_jobs()

    assert "system_reboot" not in added
    assert "raid_scrub" in added  # Gegenprobe: alles andere läuft weiter


def test_worker_writes_no_heartbeat_row_for_system_reboot(monkeypatch):
    """Sonst zeigt die Dashboard-Karte einen erfundenen Gesundheitszustand."""
    worker = SchedulerWorker()
    worker.scheduler = MagicMock()
    worker.scheduler.get_job.return_value = None

    seen: list[str] = []

    class _Query:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    class _DB:
        def query(self, *a, **k):
            return _Query()

        def add(self, obj):
            seen.append(obj.scheduler_name)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("app.services.scheduler.worker.SessionLocal", lambda: _DB())
    monkeypatch.setattr(
        "app.services.scheduler.worker.commit_with_retry", lambda db: None, raising=False
    )

    worker._update_all_heartbeats()

    assert "system_reboot" not in seen


def test_service_reports_system_reboot_disabled_without_config(db_session):
    from app.services.scheduler.service import SchedulerService

    service = SchedulerService(db_session)
    assert service._check_scheduler_enabled("system_reboot") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_scheduler_reboot_registry.py -v`
Expected: FAIL — `KeyError: 'system_reboot'`

- [ ] **Step 3: Add the registry entry**

In `backend/app/schemas/scheduler.py`, in `SCHEDULER_REGISTRY` ergänzen:

```python
    "system_reboot": {
        "display_name": "Geplanter Neustart",
        "description": "Startet das System zu einem festen Wochentermin vollständig neu",
        "config_key": None,
        "default_interval": 604800,  # Formalie; die Anzeige kommt aus extra_config
        "can_run_manually": False,
        # KEIN APScheduler-Job: die Ausführung liegt im Power-Layer
        # (services/power/scheduled_reboot.py). Ohne dieses Flag würde der
        # Worker einen Sieben-Tage-Intervalljob registrieren, der eine
        # Phantom-Execution "erfolgreich" plus Push erzeugt.
        "worker_job": False,
    },
```

- [ ] **Step 4: Teach the worker to respect the flag**

`backend/app/services/scheduler/worker.py` — drei Stellen.

In `_load_and_schedule_jobs()`, als erste Zeile im `for`-Rumpf:

```python
            for name, info in SCHEDULER_REGISTRY.items():
                if not info.get("worker_job", True):
                    # Ausführung liegt außerhalb des Workers (system_reboot).
                    continue
                is_enabled = self._is_scheduler_enabled(name, db)
```

In `_check_config_changes()`, ebenso als erste Zeile im `for`-Rumpf:

```python
            for name, info in SCHEDULER_REGISTRY.items():
                if not info.get("worker_job", True):
                    continue
                new_enabled = self._is_scheduler_enabled(name, db)
```

In `_update_all_heartbeats()` — diese Schleife läuft über `SCHEDULER_REGISTRY`
direkt, ohne `info`:

```python
            for name, info in SCHEDULER_REGISTRY.items():
                if not info.get("worker_job", True):
                    # Kein Worker-Job -> keine erfundene Heartbeat-Zeile. Der
                    # Status kommt aus SchedulerService (Task 11).
                    continue
                is_running = self._enabled_cache.get(name, False)
```

- [ ] **Step 5: Add the default-off branches**

In `backend/app/services/scheduler/service.py`, in `_check_scheduler_enabled()`,
vor dem abschließenden `return True`:

```python
        elif name == "system_reboot":
            # Default AUS. Ohne diesen Zweig greift `return True` und das
            # Feature wäre ab Installation scharf.
            return False
```

In `backend/app/services/scheduler/worker.py`, in `_is_scheduler_enabled()`, an
derselben Stelle dasselbe:

```python
        elif name == "system_reboot":
            return False
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_scheduler_reboot_registry.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 7: Run the existing scheduler tests for regressions**

Run: `cd backend && python -m pytest tests/ -k scheduler -v`
Expected: PASS — kein bestehender Scheduler verliert seinen Job.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/scheduler.py backend/app/services/scheduler/ \
        backend/tests/services/test_scheduler_reboot_registry.py
git commit -m "feat(reboot): Registry-Eintrag system_reboot ohne APScheduler-Job"
```

---

## Task 4: Gates

**Files:**
- Create: `backend/app/services/power/scheduled_reboot.py` (nur die Gate-Funktionen)
- Test: `backend/tests/services/test_reboot_gates.py`

**Interfaces:**
- Consumes: `PHASE_*` und `get_state` aus Task 2.
- Produces:
  - Gate-Konstanten `SKIP_CORE_UPTIME`, `SKIP_DISPLAYS`, `SKIP_SCHEDULER_JOB`, `SKIP_NOT_IDLE`
  - Nicht-Gate-Gründe, die Task 7 und 9 brauchen: `SKIP_REBOOT_FAILED`, `SKIP_STALE`
  - `displays_block() -> bool`
  - `gates_blocking(db, sleep_service, own_execution_id: Optional[int]) -> Optional[str]`
  - `SKIP_REASON_LABELS: dict[str, str]` (deutscher Klartext für die Notification, deckt alle sechs Gründe ab)

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_gates.py`:

```python
"""Die vier Gates des geplanten Systemneustarts."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.power import scheduled_reboot
from app.services.power.scheduled_reboot import (
    SKIP_CORE_UPTIME,
    SKIP_DISPLAYS,
    SKIP_NOT_IDLE,
    SKIP_REASON_LABELS,
    SKIP_SCHEDULER_JOB,
    gates_blocking,
)


def _sleep_service(*, in_core=False, idle=True):
    svc = MagicMock()
    svc._load_config.return_value = SimpleNamespace(idle_cpu_threshold=5.0)
    svc._load_core_uptime.return_value = (in_core, [])
    svc._is_system_idle.return_value = idle
    svc._get_activity_metrics.return_value = SimpleNamespace()
    return svc


@pytest.fixture(autouse=True)
def _displays_off(monkeypatch):
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: False)


def test_all_gates_open(db_session):
    assert gates_blocking(db_session, _sleep_service(), None) is None


def test_core_uptime_blocks(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.core_uptime_helpers.is_in_core_uptime",
        lambda now, windows: (True, object()),
    )
    svc = _sleep_service()
    svc._load_core_uptime.return_value = (True, [object()])
    assert gates_blocking(db_session, svc, None) == SKIP_CORE_UPTIME


def test_displays_block(db_session, monkeypatch):
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    assert gates_blocking(db_session, _sleep_service(), None) == SKIP_DISPLAYS


def test_running_scheduler_job_blocks(db_session):
    db_session.add(
        SchedulerExecution(
            scheduler_name="backup",
            trigger_type="scheduled",
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.RUNNING.value,
        )
    )
    db_session.commit()
    assert gates_blocking(db_session, _sleep_service(), None) == SKIP_SCHEDULER_JOB


def test_own_execution_row_does_not_block(db_session):
    """Die eigene 'running'-Zeile darf sich nicht selbst blockieren."""
    own = SchedulerExecution(
        scheduler_name="system_reboot",
        trigger_type="scheduled",
        started_at=datetime.now(timezone.utc),
        status=SchedulerStatus.RUNNING.value,
    )
    db_session.add(own)
    db_session.commit()
    assert gates_blocking(db_session, _sleep_service(), own.id) is None


def test_busy_system_blocks(db_session):
    """Gate 4 ist _is_system_idle, nicht nur active_uploads — ein SMB-Transfer
    schlägt über den Disk-I/O-Wert an und würde sonst durchrutschen."""
    assert gates_blocking(db_session, _sleep_service(idle=False), None) == SKIP_NOT_IDLE


def test_gate_order_core_uptime_wins(db_session, monkeypatch):
    """Erster Treffer gewinnt — die Reihenfolge ist Teil der Meldung."""
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    svc = _sleep_service(idle=False)
    svc._load_core_uptime.return_value = (True, [object()])
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.core_uptime_helpers.is_in_core_uptime",
        lambda now, windows: (True, object()),
    )
    assert gates_blocking(db_session, svc, None) == SKIP_CORE_UPTIME


def test_every_reason_has_a_label():
    for reason in (SKIP_CORE_UPTIME, SKIP_DISPLAYS, SKIP_SCHEDULER_JOB, SKIP_NOT_IDLE):
        assert SKIP_REASON_LABELS[reason]


def test_displays_block_is_false_in_dev_mode(monkeypatch):
    """gaming_presence.displays_on() liefert im Dev-Mode hart True. Würden wir
    die Funktion hier wiederverwenden, wäre das Feature lokal nie auslösbar."""
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.settings.is_dev_mode", True, raising=False
    )
    assert scheduled_reboot.displays_block() is False


def test_displays_block_is_true_when_unreadable(monkeypatch):
    """Unwissen blockiert — Gegenrichtung zum Gaming-Gate, weil ein Neustart
    die eingreifendere Aktion ist."""
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.settings.is_dev_mode", False, raising=False
    )

    def _boom():
        raise OSError("kein DRM")

    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.get_active_display_count_sync", _boom
    )
    assert scheduled_reboot.displays_block() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.power.scheduled_reboot'`

- [ ] **Step 3: Write the gate implementation**

`backend/app/services/power/scheduled_reboot.py` (erste Fassung — Automat und
Ausführung kommen in Task 7 und 8 dazu):

```python
"""Geplanter Systemneustart: Gates, Zustandsautomat, Ausführung.

Angestoßen vom 60-Sekunden-Tick in `SleepManagerService._schedule_check_loop()`.
Warum hier und nicht im Scheduler-Worker: Kernbetriebszeit, Display-Erkennung,
`enter_true_suspend()` und die `wake_at`-Klemmung liegen alle im Power-Layer,
und der Worker ist ein eigener Prozess ohne `SleepManagerService`.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.power import core_uptime as core_uptime_helpers
from app.services.power.gpu.display_detector import get_active_display_count_sync

logger = logging.getLogger(__name__)

SKIP_CORE_UPTIME = "core_uptime"
SKIP_DISPLAYS = "displays_on"
SKIP_SCHEDULER_JOB = "scheduler_job_running"
SKIP_NOT_IDLE = "system_busy"
SKIP_REBOOT_FAILED = "reboot_command_failed"
SKIP_STALE = "reboot_outcome_unknown"

SKIP_REASON_LABELS: dict[str, str] = {
    SKIP_CORE_UPTIME: "Kernbetriebszeit aktiv",
    SKIP_DISPLAYS: "Displays aktiv",
    SKIP_SCHEDULER_JOB: "ein Wartungsjob läuft",
    SKIP_NOT_IDLE: "das System ist ausgelastet",
    SKIP_REBOOT_FAILED: "der Neustart-Befehl schlug fehl",
    SKIP_STALE: "der Ausgang des Neustarts ist unbekannt",
}


def displays_block() -> bool:
    """Ob ein eingeschaltetes Display den Neustart verhindert.

    Bewusst NICHT `gaming_presence.displays_on()`: die liefert im Dev-Mode
    hart `True`. Für das Gaming-Gate ist das die harmlose Richtung (es lässt
    einen Suspend durch), hier wäre es die fatale — das Feature wäre lokal nie
    auslösbar.

    Unlesbare Angaben zählen hier als „Display an" und blockieren. Auch das ist
    die Gegenrichtung zum Gaming-Gate: ein Neustart ist die eingreifendere
    Aktion, bei Unwissen wird er verschoben statt durchgezogen.
    """
    if settings.is_dev_mode:
        return False
    try:
        return get_active_display_count_sync() > 0
    except Exception as exc:
        logger.warning("Display-Zustand unlesbar — Neustart wird verschoben: %s", exc)
        return True


def _another_scheduler_job_running(db: Session, own_execution_id: Optional[int]) -> bool:
    query = db.query(SchedulerExecution).filter(
        SchedulerExecution.status == SchedulerStatus.RUNNING.value
    )
    if own_execution_id is not None:
        query = query.filter(SchedulerExecution.id != own_execution_id)
    return query.first() is not None


def gates_blocking(
    db: Session,
    sleep_service,
    own_execution_id: Optional[int],
) -> Optional[str]:
    """Der erste Grund, der den Neustart verhindert — oder `None`.

    Die Reihenfolge ist Teil des Vertrags: sie bestimmt, welcher Grund in der
    Skip-Meldung landet, und sortiert vom „grundsätzlich verboten" zum
    „gerade ungünstig".
    """
    # 1) Kernbetriebszeit — Verfügbarkeitszusage. Ein Neustart kappt SMB,
    #    Sync und Uploads auch dann, wenn kein Monitor an ist.
    try:
        master, windows = sleep_service._load_core_uptime()
        if master:
            in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
            if in_core:
                return SKIP_CORE_UPTIME
    except Exception as exc:
        # Fail-closed: wer die Kernbetriebszeit nicht lesen kann, startet nicht neu.
        logger.warning("Kernbetriebszeit nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_CORE_UPTIME

    # 2) Display an — jemand sitzt an der Box.
    if displays_block():
        return SKIP_DISPLAYS

    # 3) Laufender Wartungsjob — ein halbes Backup ist schlimmer als ein
    #    verschobener Neustart.
    try:
        if _another_scheduler_job_running(db, own_execution_id):
            return SKIP_SCHEDULER_JOB
    except Exception as exc:
        logger.warning("Scheduler-Zustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_SCHEDULER_JOB

    # 4) System nicht idle — deckt CPU, Disk-I/O (und damit SMB), Uploads und
    #    HTTP-Rate mit denselben Schwellen ab, die über den Auto-Suspend
    #    entscheiden.
    try:
        config = sleep_service._load_config()
        if config is not None and not sleep_service._is_system_idle(
            config, sleep_service._get_activity_metrics()
        ):
            return SKIP_NOT_IDLE
    except Exception as exc:
        logger.warning("Idle-Zustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_NOT_IDLE

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_gates.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/scheduled_reboot.py backend/tests/services/test_reboot_gates.py
git commit -m "feat(reboot): vier Gates gegen einen unpassenden Neustart"
```

---

## Task 5: Notifications

**Files:**
- Modify: `backend/app/services/notifications/events.py`
- Modify: `backend/app/services/notifications/lifecycle_helpers.py`
- Test: `backend/tests/services/test_reboot_notifications.py`

**Interfaces:**
- Consumes: `SKIP_REASON_LABELS` aus Task 4.
- Produces:
  - `EventType.REBOOT_SCHEDULED/STARTED/COMPLETED/SKIPPED`
  - `emit_reboot_scheduled_sync(due_at_human: str)`
  - `emit_reboot_started_sync()`
  - `emit_reboot_completed_sync(downtime_seconds: Optional[float])`
  - `emit_reboot_skipped_sync(reason_label: str)`

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_notifications.py`:

```python
"""Die vier Meldungen des geplanten Systemneustarts."""
from unittest.mock import MagicMock, patch

from app.services.notifications.events import (
    EVENT_CONFIGS,
    EventType,
    emit_reboot_completed_sync,
    emit_reboot_scheduled_sync,
    emit_reboot_skipped_sync,
    emit_reboot_started_sync,
)


def test_all_four_event_types_are_configured():
    for event in (
        EventType.REBOOT_SCHEDULED,
        EventType.REBOOT_STARTED,
        EventType.REBOOT_COMPLETED,
        EventType.REBOOT_SKIPPED,
    ):
        config = EVENT_CONFIGS[event]
        assert config.category == "lifecycle"
        assert config.title_template
        assert config.message_template


def test_no_cooldown_configured():
    """Ein geplanter Neustart muss immer melden — wie shutdown/startup."""
    from app.services.notifications.events import _COOLDOWN_SECONDS

    for event in (
        EventType.REBOOT_SCHEDULED,
        EventType.REBOOT_STARTED,
        EventType.REBOOT_COMPLETED,
        EventType.REBOOT_SKIPPED,
    ):
        assert event.value not in _COOLDOWN_SECONDS


def test_emitters_pass_their_placeholders():
    emitter = MagicMock()
    with patch("app.services.notifications.events.get_event_emitter", return_value=emitter):
        emit_reboot_scheduled_sync("Sonntag, 04:00")
        emit_reboot_started_sync()
        emit_reboot_completed_sync(downtime_seconds=132.0)
        emit_reboot_skipped_sync("Displays aktiv")

    calls = emitter.emit_for_admins_sync.call_args_list
    assert len(calls) == 4
    assert calls[0].kwargs["due_at_human"] == "Sonntag, 04:00"
    assert calls[2].kwargs["downtime_human"] == "2min 12s"
    assert calls[3].kwargs["reason_label"] == "Displays aktiv"


def test_templates_render_with_the_supplied_placeholders():
    """Fängt einen Platzhalter, den kein Emitter liefert."""
    cases = {
        EventType.REBOOT_SCHEDULED: {"due_at_human": "Sonntag, 04:00"},
        EventType.REBOOT_STARTED: {},
        EventType.REBOOT_COMPLETED: {"downtime_human": "2min"},
        EventType.REBOOT_SKIPPED: {"reason_label": "Displays aktiv"},
    }
    for event, placeholders in cases.items():
        config = EVENT_CONFIGS[event]
        config.title_template.format(**placeholders)
        config.message_template.format(**placeholders)


def test_trigger_label_exists():
    from app.services.notifications.lifecycle_helpers import german_trigger_label

    assert german_trigger_label("scheduled_reboot") == "geplanter Neustart"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_notifications.py -v`
Expected: FAIL — `AttributeError: REBOOT_SCHEDULED`

- [ ] **Step 3: Add the event types**

In `backend/app/services/notifications/events.py`, in `class EventType`, hinter
den Desktop-Power-Events:

```python
    # Geplanter Systemneustart
    REBOOT_SCHEDULED = "lifecycle.reboot_scheduled"
    REBOOT_STARTED = "lifecycle.reboot_started"
    REBOOT_COMPLETED = "lifecycle.reboot_completed"
    REBOOT_SKIPPED = "lifecycle.reboot_skipped"
```

- [ ] **Step 4: Add the event configs**

In `EVENT_CONFIGS`, hinter `EventType.SYSTEM_STARTUP`:

```python
    EventType.REBOOT_SCHEDULED: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="Geplanter Neustart steht an",
        message_template="Der NAS startet um {due_at_human} planmäßig neu.",
        action_url="/admin/schedulers",
    ),
    EventType.REBOOT_STARTED: EventConfig(
        priority=2,
        category="lifecycle",
        notification_type="warning",
        title_template="Wartungsneustart läuft",
        message_template="Der NAS startet jetzt planmäßig neu und ist kurz nicht erreichbar.",
        action_url="/admin/schedulers",
    ),
    EventType.REBOOT_COMPLETED: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="Wartungsneustart abgeschlossen",
        message_template="Der geplante Neustart ist durch. Ausfallzeit: {downtime_human}.",
        action_url="/",
    ),
    EventType.REBOOT_SKIPPED: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="Geplanter Neustart verschoben",
        message_template="Der Neustart wurde nicht ausgeführt: {reason_label}.",
        action_url="/admin/schedulers",
    ),
```

Kein Eintrag in `_COOLDOWN_SECONDS` — bewusst, wie bei shutdown/startup.

- [ ] **Step 5: Add the emitters**

In `backend/app/services/notifications/events.py`, hinter `emit_system_startup`:

```python
# ---------------------------------------------------------------------------
# Geplanter Systemneustart
# ---------------------------------------------------------------------------


def emit_reboot_scheduled_sync(due_at_human: str) -> None:
    """Vorwarnung. Wird nur gesendet, wenn die Box zu dem Zeitpunkt wach ist."""
    get_event_emitter().emit_for_admins_sync(
        EventType.REBOOT_SCHEDULED,
        due_at_human=due_at_human,
    )


def emit_reboot_started_sync() -> None:
    """Unmittelbar vor `systemctl reboot`."""
    get_event_emitter().emit_for_admins_sync(EventType.REBOOT_STARTED)


def emit_reboot_completed_sync(downtime_seconds: Optional[float]) -> None:
    """Beim Boot, anstelle von `lifecycle.startup`."""
    from app.services.notifications.lifecycle_helpers import format_duration_human

    get_event_emitter().emit_for_admins_sync(
        EventType.REBOOT_COMPLETED,
        downtime_seconds=downtime_seconds,
        downtime_human=format_duration_human(downtime_seconds),
    )


def emit_reboot_skipped_sync(reason_label: str) -> None:
    """Bei Fristablauf, Ausführungsfehler oder unklarem Ausgang."""
    get_event_emitter().emit_for_admins_sync(
        EventType.REBOOT_SKIPPED,
        reason_label=reason_label,
    )
```

- [ ] **Step 6: Add the trigger label**

In `backend/app/services/notifications/lifecycle_helpers.py`, in
`_TRIGGER_LABELS_DE`:

```python
    "scheduled_reboot": "geplanter Neustart",
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_notifications.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/notifications/ backend/tests/services/test_reboot_notifications.py
git commit -m "feat(reboot): vier Notifications für den geplanten Neustart"
```

---

## Task 6: Reboot-Ausführung und sudoers

**Files:**
- Modify: `backend/app/services/power/scheduled_reboot.py`
- Modify: `deploy/install/templates/sudoers-baluhost-power`
- Test: `backend/tests/services/test_reboot_execution.py`

**Interfaces:**
- Consumes: nichts Neues.
- Produces: `run_reboot_command() -> tuple[bool, str]`

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_execution.py`:

```python
"""Der eigentliche Neustart-Befehl."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from app.services.power import scheduled_reboot


def test_dev_mode_does_not_reboot(monkeypatch):
    called = []
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", True, raising=False)
    monkeypatch.setattr(
        scheduled_reboot.subprocess, "run",
        lambda *a, **k: called.append(a) or MagicMock(returncode=0),
    )
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is True
    assert "dev" in detail.lower()
    assert called == []


def test_prod_calls_systemctl_reboot_with_list_args(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scheduled_reboot.subprocess, "run", _run)
    ok, _ = scheduled_reboot.run_reboot_command()
    assert ok is True
    assert seen["cmd"] == ["sudo", "systemctl", "reboot"]
    assert seen["kwargs"].get("shell") in (None, False)  # niemals shell=True


def test_nonzero_exit_reports_stderr(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)
    monkeypatch.setattr(
        scheduled_reboot.subprocess, "run",
        lambda *a, **k: MagicMock(returncode=1, stdout="", stderr="sudo: no entry"),
    )
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is False
    assert "sudo: no entry" in detail


def test_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=30)

    monkeypatch.setattr(scheduled_reboot.subprocess, "run", _boom)
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is False
    assert "timeout" in detail.lower()


def test_sudoers_template_has_exactly_one_reboot_line():
    """Ein Verb, keine Argumente, keine Wildcards."""
    template = Path(__file__).resolve().parents[3] / (
        "deploy/install/templates/sudoers-baluhost-power"
    )
    lines = [
        line.strip()
        for line in template.read_text(encoding="utf-8").splitlines()
        if "reboot" in line and not line.strip().startswith("#")
    ]
    assert lines == [
        "@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl reboot"
    ]
```

> Falls `parents[3]` nicht die Repo-Wurzel trifft, den Index anpassen — die
> Testdatei liegt unter `backend/tests/services/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_execution.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'run_reboot_command'`

- [ ] **Step 3: Implement the command**

In `backend/app/services/power/scheduled_reboot.py`, `import subprocess`
ergänzen und hinter `gates_blocking` einfügen:

```python
_REBOOT_CMD = ["sudo", "systemctl", "reboot"]


def run_reboot_command() -> tuple[bool, str]:
    """Startet das System neu. Rückgabe `(ok, detail)`.

    Im Dev-Mode passiert nichts — der Aufrufer simuliert den Boot-Übergang
    (siehe `tick`), damit der Automat lokal durchlaufbar bleibt.

    Der sudoers-Eintrag dafür steht in
    `deploy/install/templates/sudoers-baluhost-power` und erreicht eine
    bestehende Box NUR über einen `SYNC_PERMISSIONS=1`-Deploy. Fehlt er,
    scheitert der Aufruf sauber und der Automat meldet den Grund.
    """
    if settings.is_dev_mode:
        logger.warning("DEV-MODE: `sudo systemctl reboot` wird NICHT ausgeführt")
        return True, "dev-mode: simulierter Neustart"

    try:
        result = subprocess.run(
            _REBOOT_CMD, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout nach 30s"
    except Exception as exc:  # pragma: no cover - defensiv
        return False, str(exc)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"rc={result.returncode}"
    return True, "ok"
```

- [ ] **Step 4: Add the sudoers line**

Am Ende von `deploy/install/templates/sudoers-baluhost-power`:

```
# BaluHost: geplanter Wartungsneustart.
# Ausgelöst von backend/app/services/power/scheduled_reboot.py, hinter
# Admin-Gate, Default-Aus und vier Gates. Genau ein Verb, keine Argumente,
# keine Wildcards — dieser Eintrag beendet jeden Dienst auf der Box und ist
# damit der weitreichendste in dieser Datei.
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_execution.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/scheduled_reboot.py \
        deploy/install/templates/sudoers-baluhost-power \
        backend/tests/services/test_reboot_execution.py
git commit -m "feat(reboot): systemctl-reboot-Aufruf und eng gefasster sudoers-Eintrag"
```

---

## Task 7: Der Zustandsautomat

**Files:**
- Modify: `backend/app/services/power/scheduled_reboot.py`
- Modify: `backend/app/services/power/reboot_state.py` (Hilfsfunktionen für Executions)
- Test: `backend/tests/services/test_reboot_automaton.py`

**Interfaces:**
- Consumes: alles aus Task 1, 2, 4, 5, 6.
- Produces:
  - `tick(db, sleep_service, awake: bool) -> None`
  - `on_boot(db) -> Optional[str]` — `"completed"`, `"stale"` oder `None`
  - `reset_before_suspend(db) -> None`
  - `should_defer_suspend(db, sleep_service) -> bool`
  - `resuspend_target(db) -> tuple[bool, Optional[datetime]]`
  - Konstanten `STALE_EXECUTING_AFTER`, `RESUSPEND_TIMEOUT`
  - in `reboot_state.py`: `open_execution(db) -> int`, `close_execution(db, execution_id, status, *, error=None, result=None)`

**Import-Block, den `scheduled_reboot.py` in diesem Task bekommt** — die Emitter
müssen als Modulnamen importiert werden, sonst greifen die
`patch("app.services.power.scheduled_reboot.emit_...")`-Aufrufe der Tests ins Leere:

```python
from datetime import datetime, timedelta, timezone

from app.models.scheduler_history import SchedulerStatus
from app.services.audit.logger_db import get_audit_logger_db
from app.services.notifications.events import (
    emit_reboot_scheduled_sync,
    emit_reboot_skipped_sync,
    emit_reboot_started_sync,
)
from app.services.power.reboot_schedule import due_occurrence, next_weekday_occurrence
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_EXECUTING,
    PHASE_IDLE,
    PHASE_RESUSPEND_PENDING,
    close_execution,
    get_state,
    load_enabled_config,
    open_execution,
    reset_to_idle,
    to_local,
    to_utc,
)
```

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_automaton.py`:

```python
"""Zustandsautomat des geplanten Systemneustarts.

Der wichtigste Test hier ist `test_no_reboot_loop_after_boot`. Ohne die
Wiederholungssperre würde die Box sechs Stunden lang alle drei Minuten neu
starten.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.scheduler_history import SchedulerConfig, SchedulerExecution, SchedulerStatus
from app.services.power import scheduled_reboot
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_EXECUTING,
    PHASE_IDLE,
    PHASE_RESUSPEND_PENDING,
    get_state,
    to_utc,
)

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)


def _enable(db, **overrides):
    extra = {"weekday": 6, "time": "04:00", "retry_window_hours": 6,
             "warning_lead_minutes": 10}
    extra.update(overrides)
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config=json.dumps(extra),
    ))
    db.commit()


def _sleep_service():
    svc = MagicMock()
    svc._load_config.return_value = SimpleNamespace(idle_cpu_threshold=5.0)
    svc._load_core_uptime.return_value = (False, [])
    svc._is_system_idle.return_value = True
    svc._get_activity_metrics.return_value = SimpleNamespace()
    return svc


@pytest.fixture(autouse=True)
def _gates_open_and_no_real_reboot(monkeypatch):
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: False)
    monkeypatch.setattr(scheduled_reboot, "run_reboot_command", lambda: (True, "test"))
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)


def _at(db, now, awake=True):
    with patch("app.services.power.scheduled_reboot._now_local", return_value=now):
        scheduled_reboot.tick(db, _sleep_service(), awake=awake)


# --- armen ---------------------------------------------------------------

def test_disabled_never_arms(db_session):
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_IDLE


def test_arms_and_executes_when_due_and_gates_open(db_session):
    _enable(db_session)
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_EXECUTING
    assert state.execution_id is not None


def test_does_not_arm_before_the_time(db_session):
    _enable(db_session)
    _at(db_session, SUNDAY_0400 - timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_IDLE


# --- Wiederholungssperre -------------------------------------------------

def test_no_reboot_loop_after_boot(db_session):
    """DER Test. Nach dem Boot liegt derselbe Termin noch in der Frist."""
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    with patch("app.services.power.scheduled_reboot._now_local",
               return_value=SUNDAY_0400 + timedelta(minutes=3)):
        assert scheduled_reboot.on_boot(db_session) == "completed"

    reboots = []
    with patch.object(scheduled_reboot, "run_reboot_command",
                      side_effect=lambda: reboots.append(1) or (True, "x")):
        for minute in (4, 10, 60, 300):
            _at(db_session, SUNDAY_0400 + timedelta(minutes=minute))

    assert reboots == []
    assert get_state(db_session).phase == PHASE_IDLE


def test_repeat_lock_set_on_deadline_expiry(db_session):
    _enable(db_session, retry_window_hours=1)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=1))
    db_session.commit()

    _at(db_session, SUNDAY_0400 + timedelta(hours=1, minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert state.last_completed_due_at is not None


def test_repeat_lock_set_on_command_failure(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(
        scheduled_reboot, "run_reboot_command", lambda: (False, "sudo: no entry")
    )
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert state.last_completed_due_at is not None


def test_failed_command_marks_execution_failed(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(
        scheduled_reboot, "run_reboot_command", lambda: (False, "sudo: no entry")
    )
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    row = db_session.query(SchedulerExecution).filter(
        SchedulerExecution.scheduler_name == "system_reboot"
    ).first()
    assert row.status == SchedulerStatus.FAILED.value
    assert "sudo: no entry" in (row.error_message or "")


# --- Gates und Nachholen -------------------------------------------------

def test_blocked_stays_armed_and_records_reason(db_session, monkeypatch):
    _enable(db_session)
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    state = get_state(db_session)
    assert state.phase == PHASE_ARMED
    assert state.last_skip_reason == scheduled_reboot.SKIP_DISPLAYS


def test_retries_when_gate_opens_within_the_window(db_session, monkeypatch):
    _enable(db_session)
    blocked = {"value": True}
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: blocked["value"])

    _at(db_session, SUNDAY_0400 + timedelta(minutes=1))
    assert get_state(db_session).phase == PHASE_ARMED

    blocked["value"] = False
    _at(db_session, SUNDAY_0400 + timedelta(hours=2))
    assert get_state(db_session).phase == PHASE_EXECUTING


# --- Vorwarnung ----------------------------------------------------------

def test_warning_sent_once_when_awake(db_session):
    _enable(db_session)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=5))
        _at(db_session, SUNDAY_0400 - timedelta(minutes=4))
    assert len(sent) == 1


def test_no_warning_when_suspended(db_session):
    _enable(db_session)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=5), awake=False)
    assert sent == []


def test_lead_zero_disables_the_warning(db_session):
    _enable(db_session, warning_lead_minutes=0)
    sent = []
    with patch("app.services.power.scheduled_reboot.emit_reboot_scheduled_sync",
               side_effect=lambda human: sent.append(human)):
        _at(db_session, SUNDAY_0400 - timedelta(minutes=1))
    assert sent == []


# --- Boot-Übergabe -------------------------------------------------------

def test_on_boot_without_pending_reboot_returns_none(db_session):
    assert scheduled_reboot.on_boot(db_session) is None


def test_on_boot_schedules_resuspend_when_woken_for_reboot(db_session):
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = to_utc(datetime(2026, 9, 13, 8, 0))
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    assert get_state(db_session).phase == PHASE_RESUSPEND_PENDING


def test_on_boot_resuspends_even_without_a_wake_time(db_session):
    """resuspend_wake_at=None ist gültig: Suspend ohne RTC-Alarm."""
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    assert get_state(db_session).phase == PHASE_RESUSPEND_PENDING


def test_on_boot_stays_awake_when_not_woken_for_reboot(db_session):
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = False
    state.phase_entered_at = datetime.now(timezone.utc)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "completed"
    assert get_state(db_session).phase == PHASE_IDLE


def test_on_boot_treats_stale_executing_as_failure(db_session):
    """Kein Wieder-Suspend bei unklarem Ausgang — sonst kommt niemand mehr dran."""
    state = get_state(db_session)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = True
    state.resuspend_wake_at = to_utc(datetime(2026, 9, 13, 8, 0))
    state.phase_entered_at = datetime.now(timezone.utc) - timedelta(hours=5)
    db_session.commit()

    assert scheduled_reboot.on_boot(db_session) == "stale"
    assert get_state(db_session).phase == PHASE_IDLE


# --- Suspend-Wechselwirkung ----------------------------------------------

def test_should_defer_suspend_only_when_gates_open(db_session):
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    db_session.commit()

    assert scheduled_reboot.should_defer_suspend(db_session, _sleep_service()) is True

    with patch.object(scheduled_reboot, "displays_block", return_value=True):
        assert scheduled_reboot.should_defer_suspend(db_session, _sleep_service()) is False


def test_reset_before_suspend_clears_armed_state(db_session):
    _enable(db_session)
    state = get_state(db_session)
    state.phase = PHASE_ARMED
    state.due_at = to_utc(SUNDAY_0400)
    state.deadline_at = to_utc(SUNDAY_0400 + timedelta(hours=6))
    db_session.commit()

    scheduled_reboot.reset_before_suspend(db_session)
    state = get_state(db_session)
    assert state.phase == PHASE_IDLE
    assert state.last_completed_due_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_automaton.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'tick'`

- [ ] **Step 3: Add the execution helpers to `reboot_state.py`**

```python
def open_execution(db: Session) -> int:
    """Legt die `scheduler_executions`-Zeile für einen fälligen Termin an."""
    from app.models.scheduler_history import (
        SchedulerExecution,
        SchedulerStatus,
        TriggerType,
    )

    row = SchedulerExecution(
        scheduler_name=SCHEDULER_NAME,
        trigger_type=TriggerType.SCHEDULED.value,
        started_at=datetime.now(timezone.utc),
        status=SchedulerStatus.RUNNING.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def close_execution(
    db: Session,
    execution_id: Optional[int],
    status: str,
    *,
    error: Optional[str] = None,
    result: Optional[str] = None,
) -> None:
    """Schließt die Execution ab. Fehlt die Zeile, passiert nichts."""
    from app.models.scheduler_history import SchedulerExecution

    if execution_id is None:
        return
    row = db.query(SchedulerExecution).filter(
        SchedulerExecution.id == execution_id
    ).first()
    if row is None:
        return
    completed = datetime.now(timezone.utc)
    row.status = status
    row.completed_at = completed
    row.error_message = error
    row.result_summary = result
    started = row.started_at
    if started is not None:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        row.duration_ms = int((completed - started).total_seconds() * 1000)
    db.commit()
```

- [ ] **Step 4: Write the automaton**

In `backend/app/services/power/scheduled_reboot.py` ergänzen (Imports oben
erweitern um `timedelta`, `timezone`, die `reboot_state`-Namen, die vier
Emitter und `get_audit_logger_db`):

```python
# Ein `executing`, das länger als das hier zurückliegt, gilt als gescheitert.
# Großzügig gegenüber einem normalen Boot (unter zwei Minuten), eng genug,
# dass die Fehlmeldung nicht Tage später kommt.
STALE_EXECUTING_AFTER = timedelta(minutes=30)

# Kommt der Wieder-Suspend in dieser Zeit nicht zustande, übernimmt die
# normale Auto-Idle-Mechanik.
RESUSPEND_TIMEOUT = timedelta(minutes=30)

_WEEKDAY_NAMES_DE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
]


def _now_local() -> datetime:
    """Server-lokale naive Zeit. Eigene Funktion, damit Tests sie ersetzen können."""
    return datetime.now()


def _human_due(due_local: datetime) -> str:
    return f"{_WEEKDAY_NAMES_DE[due_local.weekday()]}, {due_local:%H:%M}"


def _audit_reboot(due_local: datetime, execution_id: Optional[int]) -> None:
    try:
        get_audit_logger_db().log_event(
            event_type="system",
            user=None,
            action="scheduled_reboot",
            resource="system_reboot",
            details={
                "due_at": due_local.isoformat(),
                "execution_id": execution_id,
                "gates": "open",
            },
            success=True,
        )
    except Exception as exc:  # pragma: no cover - Audit darf nie blockieren
        logger.warning("Audit-Eintrag für den Neustart fehlgeschlagen: %s", exc)


def tick(db: Session, sleep_service, awake: bool) -> None:
    """Ein Schritt des Automaten. Wird alle 60 Sekunden aufgerufen.

    `awake` sagt, ob die Box gerade wach ist — davon hängt nur die Vorwarnung ab.
    Wirft nie; der Aufrufer ist der Sleep-Loop und darf nicht abreißen.
    """
    try:
        state = get_state(db)
        if state.phase == PHASE_RESUSPEND_PENDING:
            _tick_resuspend(db, state)
            return
        if state.phase == PHASE_EXECUTING:
            # Der Neustart läuft; nach dem Boot übernimmt `on_boot`.
            return

        config = load_enabled_config(db)
        if config is None:
            if state.phase != PHASE_IDLE:
                reset_to_idle(db, state)
            return

        now = _now_local()
        if state.phase == PHASE_ARMED:
            _tick_armed(db, state, config, sleep_service, now)
            return

        _tick_idle(db, state, config, sleep_service, now, awake)
    except Exception as exc:
        logger.warning("Neustart-Tick fehlgeschlagen (Zustand unverändert): %s", exc)


def _tick_idle(db, state, config, sleep_service, now, awake) -> None:
    retry = timedelta(hours=config.retry_window_hours)

    # Vorwarnung — nur wach, nur einmal pro Termin.
    if awake and config.warning_lead_minutes > 0:
        upcoming = next_weekday_occurrence(now, config.weekday, config.time)
        lead = timedelta(minutes=config.warning_lead_minutes)
        already = (
            state.warned_for_due_at is not None
            and to_local(state.warned_for_due_at) == upcoming
        )
        if not already and upcoming - now <= lead:
            emit_reboot_scheduled_sync(_human_due(upcoming))
            state.warned_for_due_at = to_utc(upcoming)
            db.commit()

    due = due_occurrence(now, config.weekday, config.time, retry)
    if due is None:
        return

    # Wiederholungssperre. `due_occurrence` kann „Zustand ging verloren" und
    # „Termin ist erledigt" nicht unterscheiden; ohne diese Prüfung startet
    # die Box nach dem Neustart in einer Schleife erneut neu.
    if state.last_completed_due_at is not None and to_local(
        state.last_completed_due_at
    ) == due:
        return

    state.phase = PHASE_ARMED
    state.due_at = to_utc(due)
    state.deadline_at = to_utc(due + retry)
    state.execution_id = open_execution(db)
    state.last_skip_reason = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Geplanter Neustart gearmt für %s (Frist bis %s)", due, due + retry)

    _tick_armed(db, state, config, sleep_service, now)


def _tick_armed(db, state, config, sleep_service, now) -> None:
    due_local = to_local(state.due_at) if state.due_at else now

    if state.deadline_at is not None and now > to_local(state.deadline_at):
        reason = state.last_skip_reason or SKIP_NOT_IDLE
        close_execution(
            db, state.execution_id, SchedulerStatus.CANCELLED.value,
            error=SKIP_REASON_LABELS.get(reason, reason),
        )
        emit_reboot_skipped_sync(SKIP_REASON_LABELS.get(reason, reason))
        reset_to_idle(db, state, completed_due_at=to_utc(due_local))
        logger.info("Geplanter Neustart verfallen (%s)", reason)
        return

    blocking = gates_blocking(db, sleep_service, state.execution_id)
    if blocking is not None:
        if state.last_skip_reason != blocking:
            state.last_skip_reason = blocking
            db.commit()
        logger.info("Geplanter Neustart wartet: %s", SKIP_REASON_LABELS.get(blocking))
        return

    _execute(db, state, due_local)


def _execute(db, state, due_local: datetime) -> None:
    _audit_reboot(due_local, state.execution_id)

    try:
        emit_reboot_started_sync()
    except Exception as exc:
        logger.warning("Startmeldung fehlgeschlagen — Neustart läuft trotzdem: %s", exc)

    # Diese Zeile MUSS vor dem Befehl committet sein. Nach dem Neustart ist sie
    # der einzige Beweis, dass es ein geplanter war.
    state.phase = PHASE_EXECUTING
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()

    ok, detail = run_reboot_command()
    if not ok:
        logger.error("Geplanter Neustart fehlgeschlagen: %s", detail)
        close_execution(
            db, state.execution_id, SchedulerStatus.FAILED.value, error=detail,
        )
        emit_reboot_skipped_sync(
            f"{SKIP_REASON_LABELS[SKIP_REBOOT_FAILED]} ({detail})"
        )
        reset_to_idle(db, state, completed_due_at=to_utc(due_local))
        return

    if settings.is_dev_mode:
        # Kein echter Neustart — den Boot-Übergang direkt simulieren, sonst
        # bliebe der Automat lokal für immer auf `executing` stehen.
        logger.info("DEV-MODE: simuliere den Boot-Übergang")
        on_boot(db)


def _tick_resuspend(db, state) -> None:
    """Timeout-Wache. Der eigentliche Suspend passiert im Sleep-Loop (Task 8)."""
    entered = state.phase_entered_at
    if entered is None:
        reset_to_idle(db, state)
        return
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - entered > RESUSPEND_TIMEOUT:
        logger.info(
            "Wieder-Suspend nach dem Neustart kam nicht zustande — "
            "die normale Auto-Idle-Mechanik übernimmt"
        )
        reset_to_idle(db, state)


def on_boot(db: Session) -> Optional[str]:
    """Wertet die Phase nach einem Boot aus. Von `lifespan` aufgerufen.

    Rückgabe:
      "completed" — geplanter Neustart erfolgreich; Folgephase gesetzt
      "stale"     — `executing` zu alt, als gescheitert gewertet
      None        — kein geplanter Neustart im Spiel
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_EXECUTING:
            return None

        due_utc = state.due_at
        entered = state.phase_entered_at
        if entered is not None and entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)

        stale = (
            entered is None
            or datetime.now(timezone.utc) - entered > STALE_EXECUTING_AFTER
        )

        if stale:
            close_execution(
                db, state.execution_id, SchedulerStatus.FAILED.value,
                error=SKIP_REASON_LABELS[SKIP_STALE],
            )
            # Kein Wieder-Suspend: bei unklarem Ausgang darf die Box nicht
            # wieder schlafen gehen, sonst kommt niemand mehr dran.
            reset_to_idle(db, state, completed_due_at=due_utc)
            return "stale"

        close_execution(
            db, state.execution_id, SchedulerStatus.COMPLETED.value,
            result='{"rebooted": true}',
        )

        if state.woke_for_reboot:
            state.phase = PHASE_RESUSPEND_PENDING
            state.execution_id = None
            state.due_at = None
            state.deadline_at = None
            state.last_completed_due_at = due_utc
            state.phase_entered_at = datetime.now(timezone.utc)
            db.commit()
        else:
            reset_to_idle(db, state, completed_due_at=due_utc)
        return "completed"
    except Exception as exc:
        logger.warning("Boot-Auswertung des Neustarts fehlgeschlagen: %s", exc)
        return None


def should_defer_suspend(db: Session, sleep_service) -> bool:
    """Ob ein automatischer Suspend zugunsten eines scharfen Neustarts ausfällt.

    Nur wenn die Gates offen sind — sonst würde ein blockierter Termin die Box
    bis zum Ablauf der Frist wachhalten und Strom verbrennen.
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_ARMED:
            return False
        return gates_blocking(db, sleep_service, state.execution_id) is None
    except Exception as exc:
        logger.warning("Suspend-Verdrängung nicht prüfbar: %s", exc)
        return False


def reset_before_suspend(db: Session) -> None:
    """Vor einem Suspend, der trotz `armed` stattfindet, aufräumen.

    Sonst stünde `phase=armed` mit einem `due_at` von gestern da, während die
    Weckzeit schon auf den Termin nächster Woche zeigt.
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_ARMED:
            return
        reason = state.last_skip_reason or SKIP_NOT_IDLE
        close_execution(
            db, state.execution_id, SchedulerStatus.CANCELLED.value,
            error=SKIP_REASON_LABELS.get(reason, reason),
        )
        reset_to_idle(db, state, completed_due_at=state.due_at)
    except Exception as exc:
        logger.warning("Zurücksetzen vor dem Suspend fehlgeschlagen: %s", exc)


def resuspend_target(db: Session) -> tuple[bool, Optional[datetime]]:
    """`(ist ein Wieder-Suspend fällig, wake_at)` für den Sleep-Loop."""
    try:
        state = get_state(db)
        if state.phase != PHASE_RESUSPEND_PENDING:
            return False, None
        return True, state.resuspend_wake_at
    except Exception:
        return False, None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_automaton.py -v`
Expected: PASS (20 Tests). `test_no_reboot_loop_after_boot` muss grün sein — er ist der Grund für die ganze Wiederholungssperre.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/scheduled_reboot.py \
        backend/app/services/power/reboot_state.py \
        backend/tests/services/test_reboot_automaton.py
git commit -m "feat(reboot): Zustandsautomat mit Wiederholungssperre"
```

---

## Task 8: Verdrahtung im Sleep-Manager

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Modify: `backend/app/services/power/reboot_state.py` (`claim_wakeup`)
- Modify: `backend/app/schemas/sleep.py`
- Test: `backend/tests/services/test_reboot_sleep_integration.py`

**Interfaces:**
- Consumes: `tick`, `should_defer_suspend`, `reset_before_suspend`, `resuspend_target` aus Task 7.
- Produces:
  - `SleepTrigger.SCHEDULED_REBOOT = "scheduled_reboot"`
  - `reboot_state.claim_wakeup(db, regular_utc, now_local) -> Optional[datetime]`
  - `SleepManagerService._next_scheduled_wakeup(now_local) -> Optional[datetime]`

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_reboot_sleep_integration.py`:

```python
"""Wechselwirkung zwischen Neustart-Automat und Sleep-Manager."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.scheduler_history import SchedulerConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power import scheduled_reboot
from app.services.power.reboot_state import (
    PHASE_ARMED, claim_wakeup, get_state, to_utc,
)
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)
SUNDAY_0800 = datetime(2026, 9, 13, 8, 0)


def _enable(db):
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True, interval_seconds=604800,
        extra_config=json.dumps({"weekday": 6, "time": "04:00"}),
    ))
    db.commit()


def test_trigger_value_exists():
    assert SleepTrigger.SCHEDULED_REBOOT.value == "scheduled_reboot"


def test_claim_wakeup_takes_the_earlier_reboot_and_remembers_the_regular(db_session):
    _enable(db_session)
    regular = to_utc(SUNDAY_0800)
    claimed = claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0))
    assert claimed == to_utc(SUNDAY_0400)
    state = get_state(db_session)
    assert state.woke_for_reboot is True
    assert state.resuspend_wake_at == regular


def test_claim_wakeup_leaves_an_earlier_regular_alone(db_session):
    _enable(db_session)
    regular = to_utc(datetime(2026, 9, 13, 2, 0))  # vor dem Termin
    claimed = claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0))
    assert claimed == regular
    assert get_state(db_session).woke_for_reboot is False


def test_claim_wakeup_with_no_regular_wake_time(db_session):
    """Keine Kernbetriebszeit konfiguriert -> resuspend_wake_at bleibt None."""
    _enable(db_session)
    claimed = claim_wakeup(db_session, None, datetime(2026, 9, 13, 1, 0))
    assert claimed == to_utc(SUNDAY_0400)
    state = get_state(db_session)
    assert state.woke_for_reboot is True
    assert state.resuspend_wake_at is None


def test_claim_wakeup_without_the_feature_is_a_no_op(db_session):
    regular = to_utc(SUNDAY_0800)
    assert claim_wakeup(db_session, regular, datetime(2026, 9, 13, 1, 0)) == regular
    assert get_state(db_session).woke_for_reboot is False


@pytest.mark.asyncio
async def test_auto_suspend_is_refused_while_a_reboot_is_armed():
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.AWAKE
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()):
        ok = await svc.enter_true_suspend("test", SleepTrigger.AUTO_IDLE, wake_at=None)

    assert ok is False
    assert backend_called == []


@pytest.mark.asyncio
async def test_manual_suspend_is_never_refused():
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.SOFT_SLEEP
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=None)

    assert ok is True
    assert len(backend_called) == 1


@pytest.mark.asyncio
async def test_blocked_reboot_does_not_prevent_a_normal_suspend():
    """Gates zu -> kein Aufschub, sonst hält ein blockierter Termin die Box wach."""
    svc = SleepManagerService(DevSleepBackend())
    svc._current_state = SleepState.SOFT_SLEEP
    backend_called = []

    async def _suspend(wake_at=None):
        backend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=_suspend), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=False), \
         patch("app.services.power.sleep.scheduled_reboot.reset_before_suspend"), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("idle", SleepTrigger.AUTO_IDLE, wake_at=None)

    assert ok is True
    assert len(backend_called) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_reboot_sleep_integration.py -v`
Expected: FAIL — `AttributeError: SCHEDULED_REBOOT`

- [ ] **Step 3: Add the trigger**

In `backend/app/schemas/sleep.py`, in `class SleepTrigger`, hinter
`CORE_UPTIME_EXIT`:

```python
    SCHEDULED_REBOOT = "scheduled_reboot"
```

- [ ] **Step 4: Add `claim_wakeup` to `reboot_state.py`**

```python
def claim_wakeup(
    db: Session,
    regular_utc: Optional[datetime],
    now_local: datetime,
) -> Optional[datetime]:
    """Der Neustart-Termin stiehlt die Weckzeit — und legt die gestohlene daneben.

    Liegt der nächste Neustart-Termin vor `regular_utc`, wird er zurückgegeben,
    `woke_for_reboot` gesetzt und `regular_utc` als `resuspend_wake_at`
    hinterlegt. Genau das ist „bis zum regulären Aufwachzeitpunkt": nicht ein
    nach dem Neustart neu geratener Wert, sondern derselbe, der ohne den
    Neustart gegolten hätte. `regular_utc` darf `None` sein.

    Schreibt bewusst in die Datenbank — der Aufrufer steht unmittelbar vor dem
    Suspend, und danach gibt es keine Gelegenheit mehr dazu.
    """
    due_local = next_reboot_due(db, now_local)
    if due_local is None:
        return regular_utc

    due_utc = to_utc(due_local)
    if regular_utc is not None:
        regular_aware = regular_utc
        if regular_aware.tzinfo is None:
            regular_aware = regular_aware.replace(tzinfo=timezone.utc)
        if regular_aware <= due_utc:
            return regular_utc

    state = get_state(db)
    state.woke_for_reboot = True
    state.resuspend_wake_at = regular_utc
    db.commit()
    logger.info(
        "Weckzeit auf den Neustart-Termin %s vorgezogen (regulär war %s)",
        due_local, regular_utc,
    )
    return due_utc


def clear_wakeup_claim(db: Session) -> None:
    """Nach einem gescheiterten Suspend: das Flag wieder abräumen."""
    state = get_state(db)
    if state.woke_for_reboot:
        state.woke_for_reboot = False
        state.resuspend_wake_at = None
        db.commit()
```

- [ ] **Step 5: Wire the tick into the schedule loop**

In `backend/app/services/power/sleep.py`, oben importieren:

```python
from app.services.power import scheduled_reboot
from app.services.power import reboot_state
```

In `_schedule_check_loop()`, **direkt nach** dem Suspend-on-Exit-Block und
**vor** der Zeile `if not config or not config.schedule_enabled: continue`:

```python
                # Geplanter Systemneustart. Bewusst vor dem
                # `schedule_enabled`-Abbruch: das Feature hängt nicht am
                # Sleep-Zeitplan.
                try:
                    db = SessionLocal()
                    try:
                        scheduled_reboot.tick(
                            db, self,
                            awake=self._current_state == SleepState.AWAKE,
                        )
                        due, wake_at = scheduled_reboot.resuspend_target(db)
                    finally:
                        db.close()
                except Exception as exc:
                    logger.warning("Neustart-Tick fehlgeschlagen: %s", exc)
                    due, wake_at = False, None

                if (
                    due
                    and self._current_state == SleepState.AWAKE
                    and config is not None
                    and not self._is_always_awake(config)
                    and not self._is_user_present(config)
                    and not self._is_gaming_active(config)
                    and self._foreign_inhibitor("sleep") is None
                    and self._is_system_idle(config, self._get_activity_metrics())
                ):
                    logger.info("Wieder-Suspend nach geplantem Neustart")
                    await self.enter_true_suspend(
                        "scheduled_reboot_resuspend",
                        SleepTrigger.SCHEDULED_REBOOT,
                        wake_at=wake_at,
                    )
```

- [ ] **Step 6: Add the deferral guard and the claim to `enter_true_suspend`**

In `enter_true_suspend()`, hinter dem Foreign-Inhibitor-Guard:

```python
        # Ein scharfer Neustart verdrängt einen automatischen Suspend. Die
        # Regel sitzt hier und nicht in einer der drei Schleifen, weil alle
        # drei suspendieren können. Sie LEHNT AB, statt selbst neu zu starten —
        # der nächste 60s-Tick führt den Neustart aus.
        if trigger != SleepTrigger.MANUAL:
            db = SessionLocal()
            try:
                if scheduled_reboot.should_defer_suspend(db, self):
                    logger.info(
                        "enter_true_suspend abgelehnt: geplanter Neustart ist scharf "
                        "(trigger=%s, reason=%s)", trigger.value, reason,
                    )
                    return False
                # Findet trotzdem ein Suspend statt, während ein Termin scharf
                # aber blockiert ist, muss der Automat zurückgesetzt werden —
                # sonst zeigt `due_at` auf gestern und die Weckzeit auf
                # nächste Woche.
                scheduled_reboot.reset_before_suspend(db)
            finally:
                db.close()
```

Und die Klemmung: die vorhandene Zeile mit `next_core_uptime_start` bleibt, das
Ergebnis wird danach durch `claim_wakeup` geschickt. Direkt **vor** dem
`ok = await self._backend.suspend_system(wake_at=wake_at)`:

```python
        # Der Neustart-Termin darf die Weckzeit übernehmen — und merkt sich
        # dabei die verdrängte. Muss unmittelbar vor dem Backend-Aufruf
        # stehen, weil es danach keine Gelegenheit zum Schreiben mehr gibt.
        try:
            db = SessionLocal()
            try:
                wake_at = reboot_state.claim_wakeup(db, wake_at, datetime.now())
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Weckzeit-Klemmung auf den Neustart fehlgeschlagen: %s", exc)
```

Und unmittelbar nach dem Backend-Aufruf, im Fehlerfall:

```python
        if not ok:
            # Der Suspend kam nicht zustande — ein gesetztes woke_for_reboot
            # wäre gelogen und würde nach dem Neustart einen unnötigen
            # Wieder-Suspend auslösen.
            try:
                db = SessionLocal()
                try:
                    reboot_state.clear_wakeup_claim(db)
                finally:
                    db.close()
            except Exception:
                pass
```

- [ ] **Step 7: Point the RTC guard at the same claim**

In `_next_core_start_for_guard()` den Rückgabewert durch `claim_wakeup`
schicken, damit auch ein von PowerDevil ausgelöster Suspend den Termin trifft:

```python
    def _next_core_start_for_guard(self) -> Optional[datetime]:
        """Provider für den CoreUptimeRtcGuard.

        Berücksichtigt den Neustart-Termin: sonst verschläft die Box ihn genau
        dann, wenn nicht BaluHost, sondern PowerDevil suspendiert hat — auf
        einer KDE-Gaming-Box kein Randfall.
        """
        try:
            master, windows = self._load_core_uptime()
            next_core = None
            if master:
                next_core = core_uptime_helpers.next_core_uptime_start(
                    datetime.now(), windows
                )
            next_core_utc = (
                next_core.astimezone(timezone.utc) if next_core is not None else None
            )
            db = SessionLocal()
            try:
                claimed = reboot_state.claim_wakeup(db, next_core_utc, datetime.now())
            finally:
                db.close()
            if claimed is None:
                return None
            return claimed.astimezone().replace(tzinfo=None)
        except Exception as exc:
            logger.warning("RTC guard provider failed: %s", exc)
            return None
```

> Der Guard reicht den Wert an `rtcwake -t <unix_ts>` weiter und ruft dafür
> `.timestamp()` auf. Ein naiver lokaler Wert ist dort korrekt — genau das
> lieferte die Funktion vorher auch.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_reboot_sleep_integration.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 9: Run the existing sleep tests for regressions**

Run: `cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py tests/test_lifecycle_notifications.py -v`
Expected: PASS — kein bestehender Suspend-Pfad verändert sich.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/power/sleep.py backend/app/services/power/reboot_state.py \
        backend/app/schemas/sleep.py backend/tests/services/test_reboot_sleep_integration.py
git commit -m "feat(reboot): Weckzeit-Klemmung, Suspend-Verdrängung und Wieder-Suspend"
```

---

## Task 9: Boot-Übergabe im Lifespan

**Files:**
- Modify: `backend/app/core/lifespan.py`
- Test: `backend/tests/test_reboot_lifespan.py`

**Interfaces:**
- Consumes: `on_boot` und `get_state` aus Task 7/2.
- Produces: keine neuen Signaturen; `_emit_lifecycle_startup()` und `_emit_lifecycle_shutdown()` verhalten sich bei `phase == executing` anders.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reboot_lifespan.py`:

```python
"""Boot-Übergabe des geplanten Neustarts.

Die Tests laufen DIREKT gegen die Lifespan-Funktionen, nicht über den
TestClient: `conftest` setzt SKIP_APP_INIT=1, `_startup()` läuft in Tests nie,
und ein TestClient-Test wäre grün, ohne dass die Verdrahtung existiert.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core import lifespan as lifespan_mod
from app.services.power.reboot_state import (
    PHASE_EXECUTING, PHASE_IDLE, get_state, to_utc,
)

SUNDAY_0400 = datetime(2026, 9, 13, 4, 0)


def _mark_executing(db, *, entered_minutes_ago=1, woke=False):
    state = get_state(db)
    state.phase = PHASE_EXECUTING
    state.due_at = to_utc(SUNDAY_0400)
    state.woke_for_reboot = woke
    state.phase_entered_at = datetime.now(timezone.utc) - timedelta(
        minutes=entered_minutes_ago
    )
    db.commit()


@pytest.mark.asyncio
async def test_startup_sends_reboot_completed_instead_of_generic(db_session, monkeypatch):
    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    generic = AsyncMock()
    specific = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=generic), \
         patch("app.services.notifications.events.emit_reboot_completed", new=specific):
        await lifespan_mod._emit_lifecycle_startup()

    generic.assert_not_awaited()
    specific.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_sends_the_generic_message_without_a_planned_reboot(
    db_session, monkeypatch
):
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)
    generic = AsyncMock()
    specific = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=generic), \
         patch("app.services.notifications.events.emit_reboot_completed", new=specific):
        await lifespan_mod._emit_lifecycle_startup()

    generic.assert_awaited_once()
    specific.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_executing_sends_skipped_and_leaves_the_box_awake(
    db_session, monkeypatch
):
    _mark_executing(db_session, entered_minutes_ago=300, woke=True)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    skipped = AsyncMock()
    with patch("app.services.notifications.events.emit_system_startup", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_reboot_completed", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_reboot_skipped", new=skipped):
        await lifespan_mod._emit_lifecycle_startup()

    skipped.assert_awaited_once()
    assert get_state(db_session).phase == PHASE_IDLE


@pytest.mark.asyncio
async def test_shutdown_push_is_suppressed_during_a_planned_reboot(
    db_session, monkeypatch
):
    """Der Automat hat `reboot_started` schon gesendet — zwei Meldungen wären
    genau die Verwirrung, die das Feature vermeiden soll."""
    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    generic = AsyncMock()
    with patch("app.services.notifications.events.emit_system_shutdown", new=generic):
        await lifespan_mod._emit_lifecycle_shutdown(trigger="signal")

    generic.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_still_writes_its_lifecycle_row(db_session, monkeypatch):
    """Die Zeile bleibt — aus ihr berechnet der nächste Start die Downtime."""
    from app.models.system_lifecycle import SystemLifecycleEvent

    _mark_executing(db_session)
    monkeypatch.setattr(lifespan_mod, "IS_PRIMARY_WORKER", True, raising=False)

    with patch("app.services.notifications.events.emit_system_shutdown", new=AsyncMock()):
        await lifespan_mod._emit_lifecycle_shutdown(trigger="signal")

    rows = db_session.query(SystemLifecycleEvent).filter(
        SystemLifecycleEvent.event_type == "shutdown"
    ).all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reboot_lifespan.py -v`
Expected: FAIL — `emit_reboot_completed` existiert nicht als async Wrapper.

- [ ] **Step 3: Add the async wrappers**

In `backend/app/services/notifications/events.py`, hinter den `_sync`-Emittern
aus Task 5:

```python
async def emit_reboot_completed(downtime_seconds: Optional[float]) -> None:
    """Async-Wrapper — genutzt in `_emit_lifecycle_startup()`."""
    emit_reboot_completed_sync(downtime_seconds)


async def emit_reboot_skipped(reason_label: str) -> None:
    """Async-Wrapper — genutzt in `_emit_lifecycle_startup()`."""
    emit_reboot_skipped_sync(reason_label)
```

- [ ] **Step 4: Hand over at boot**

In `backend/app/core/lifespan.py`, in `_emit_lifecycle_startup()`, den Block der
die Meldung sendet ersetzen. Die Zeilen-Inserts bleiben unverändert:

```python
        # Geplanter Neustart? Dann tritt seine Meldung an die Stelle der
        # generischen — sonst liest sich ein Wartungsneustart wie ein Absturz.
        outcome = None
        try:
            from app.services.power.scheduled_reboot import on_boot
            with SessionLocal() as db:
                outcome = on_boot(db)
        except Exception as exc:
            logger.warning("Neustart-Auswertung beim Boot fehlgeschlagen: %s", exc)

        try:
            if outcome == "completed":
                from app.services.notifications.events import emit_reboot_completed
                await emit_reboot_completed(downtime_seconds=downtime_seconds)
            elif outcome == "stale":
                from app.services.notifications.events import emit_reboot_skipped
                from app.services.power.scheduled_reboot import (
                    SKIP_REASON_LABELS, SKIP_STALE,
                )
                await emit_reboot_skipped(SKIP_REASON_LABELS[SKIP_STALE])
            else:
                await emit_system_startup(downtime_seconds=downtime_seconds)
        except Exception as exc:
            logger.warning("Lifecycle startup push failed: %s", exc)
```

- [ ] **Step 5: Suppress the generic shutdown push**

In `_emit_lifecycle_shutdown()`, den Push-Teil bedingt machen. Der
Row-Insert davor bleibt **unverändert**:

```python
        # 2. Push (best effort, max 3s) — beim geplanten Neustart entfällt er:
        #    der Automat hat `reboot_started` bereits gesendet, und zwei
        #    Meldungen wären genau die Verwirrung, die das Feature vermeidet.
        planned = False
        try:
            from app.services.power.reboot_state import PHASE_EXECUTING, get_state
            with SessionLocal() as db:
                planned = get_state(db).phase == PHASE_EXECUTING
        except Exception:
            planned = False

        if planned:
            logger.info("Shutdown-Push unterdrückt: geplanter Neustart läuft")
            return

        try:
            await asyncio.wait_for(
                emit_system_shutdown(trigger=trigger),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Lifecycle shutdown push timed out after 3s — continuing shutdown")
        except Exception as exc:
            logger.warning("Lifecycle shutdown push failed: %s — continuing shutdown", exc)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reboot_lifespan.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 7: Run the lifecycle regression tests**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/lifespan.py backend/app/services/notifications/events.py \
        backend/tests/test_reboot_lifespan.py
git commit -m "feat(reboot): Boot-Übergabe und Verdrängung der generischen Meldungen"
```

---

## Task 10: Statusanzeige, Validierung und Preview-Route

**Files:**
- Modify: `backend/app/services/scheduler/service.py`
- Modify: `backend/app/api/routes/schedulers.py`
- Modify: `backend/app/schemas/scheduler.py` (`RebootPreviewResponse`)
- Test: `backend/tests/api/test_reboot_scheduler_api.py`

**Interfaces:**
- Consumes: `RebootScheduleConfig`, `next_reboot_due`, `get_state`.
- Produces:
  - `RebootPreviewResponse`
  - `SchedulerService.get_reboot_preview() -> RebootPreviewResponse`
  - `GET /api/schedulers/system_reboot/preview`

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_reboot_scheduler_api.py`:

```python
"""API-Oberfläche des geplanten Systemneustarts."""
import json

from app.models.scheduler_history import SchedulerConfig
from app.models.sleep import CoreUptimeWindow


def _enable(db, **extra):
    payload = {"weekday": 6, "time": "04:00", "retry_window_hours": 6}
    payload.update(extra)
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config=json.dumps(payload),
    ))
    db.commit()


def test_config_rejects_an_invalid_weekday(admin_client):
    resp = admin_client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 9, "time": "04:00"}},
    )
    assert resp.status_code == 422


def test_config_rejects_an_invalid_time(admin_client):
    resp = admin_client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 6, "time": "25:00"}},
    )
    assert resp.status_code == 422


def test_config_accepts_valid_values(admin_client):
    resp = admin_client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 2, "time": "03:30",
                               "retry_window_hours": 4, "warning_lead_minutes": 15}},
    )
    assert resp.status_code == 200


def test_other_schedulers_keep_their_free_extra_config(admin_client):
    """Die Validierung gilt nur für system_reboot."""
    resp = admin_client.put(
        "/api/schedulers/backup/config",
        json={"extra_config": {"backup_type": "incremental"}},
    )
    assert resp.status_code == 200


def test_preview_requires_admin(user_client):
    assert user_client.get("/api/schedulers/system_reboot/preview").status_code == 403


def test_preview_reports_no_collision(admin_client, db_session):
    _enable(db_session)
    body = admin_client.get("/api/schedulers/system_reboot/preview").json()
    assert body["enabled"] is True
    assert body["in_core_uptime"] is False
    assert body["reachable"] is True
    assert body["next_due_at"] is not None


def test_preview_reports_an_unreachable_collision(admin_client, db_session):
    """Termin im Fenster, Fenster endet nach der Frist -> läuft nie."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=6)
    db_session.add(CoreUptimeWindow(
        enabled=True, label="Wochentags", start_time="08:00",
        end_time="22:00", weekdays="0,1,2,3,4",
    ))
    db_session.commit()

    body = admin_client.get("/api/schedulers/system_reboot/preview").json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is False
    assert body["window_label"] == "Wochentags"


def test_preview_reports_a_reachable_collision(admin_client, db_session):
    """Fenster endet innerhalb der Frist -> wird nachgeholt."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=12)
    db_session.add(CoreUptimeWindow(
        enabled=True, label="Vormittag", start_time="08:00",
        end_time="12:00", weekdays="0,1,2,3,4",
    ))
    db_session.commit()

    body = admin_client.get("/api/schedulers/system_reboot/preview").json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is True


def test_status_has_a_next_run_without_any_worker_state(admin_client, db_session):
    _enable(db_session)
    body = admin_client.get("/api/schedulers/system_reboot").json()
    assert body["next_run_at"] is not None
    assert body["worker_healthy"] is None
    assert "04:00" in body["interval_display"]


def test_status_has_no_next_run_when_disabled(admin_client):
    body = admin_client.get("/api/schedulers/system_reboot").json()
    assert body["is_enabled"] is False
    assert body["next_run_at"] is None
```

> Die Fixtures `admin_client` und `user_client` existieren in
> `backend/tests/conftest.py`. Vor dem Schreiben mit
> `sed -n '/admin_client/,+8p' backend/tests/conftest.py` die genauen Namen prüfen
> und übernehmen statt neue anzulegen.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_reboot_scheduler_api.py -v`
Expected: FAIL — 404 auf `/preview`, 200 statt 422 bei ungültiger Konfiguration.

- [ ] **Step 3: Add the preview schema**

In `backend/app/schemas/scheduler.py`, hinter `RebootScheduleConfig`:

```python
class RebootPreviewResponse(BaseModel):
    """Vorschau auf den nächsten Neustart-Termin, inklusive Kollisionsprüfung.

    Serverseitig gerechnet, weil die Kollisionsregel dieselbe sein muss wie im
    Tick. Zwei Implementierungen derselben Regel driften auseinander.
    """

    enabled: bool
    next_due_at: Optional[datetime] = None
    in_core_uptime: bool = False
    window_label: Optional[str] = None
    window_ends_at: Optional[datetime] = None
    retry_deadline_at: Optional[datetime] = None
    reachable: bool = True
```

- [ ] **Step 4: Add the status branch and the preview to the service**

In `backend/app/services/scheduler/service.py`, in `_get_scheduler_status()`,
unmittelbar vor dem abschließenden `return SchedulerStatusResponse(...)`:

```python
        # system_reboot hat keinen Worker-Job und damit keine scheduler_state-
        # Zeile. Ohne diesen Zweig zeigt die Karte "nicht laufend, kein
        # nächster Lauf". worker_healthy bleibt None — dieser Eintrag hängt
        # nicht am Worker, und eine erfundene Angabe wäre schlechter als keine.
        if name == "system_reboot":
            from app.services.power.reboot_state import (
                PHASE_ARMED, PHASE_EXECUTING, get_state, next_reboot_due, to_utc,
            )

            due_local = next_reboot_due(self.db, datetime.now()) if is_enabled else None
            next_run_at = to_utc(due_local) if due_local is not None else None
            phase = get_state(self.db).phase
            is_running = phase in (PHASE_ARMED, PHASE_EXECUTING)
            worker_healthy = None
            if extra_config:
                weekday = int(extra_config.get("weekday", 6))
                names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                         "Freitag", "Samstag", "Sonntag"]
                interval_label = f"{names[weekday]} {extra_config.get('time', '04:00')}"
            else:
                interval_label = "Sonntag 04:00"
            return SchedulerStatusResponse(
                name=name,
                display_name=info["display_name"],
                description=info["description"],
                is_running=is_running,
                is_enabled=is_enabled,
                interval_seconds=interval,
                interval_display=interval_label,
                last_run_at=last_run_at,
                next_run_at=next_run_at,
                last_status=last_status,
                last_error=last_error,
                last_duration_ms=last_duration,
                config_key=info.get("config_key"),
                can_run_manually=info.get("can_run_manually", True),
                extra_config=extra_config,
                worker_healthy=worker_healthy,
            )
```

Und als neue Methode auf `SchedulerService`:

```python
    def get_reboot_preview(self) -> "RebootPreviewResponse":
        """Nächster Termin plus Kollision mit der Kernbetriebszeit."""
        from app.models.sleep import CoreUptimeWindow
        from app.schemas.scheduler import RebootPreviewResponse
        from app.services.power import core_uptime as cu
        from app.services.power.reboot_state import load_enabled_config, to_utc
        from app.services.power.reboot_schedule import next_weekday_occurrence

        config = load_enabled_config(self.db)
        if config is None:
            return RebootPreviewResponse(enabled=False)

        due = next_weekday_occurrence(datetime.now(), config.weekday, config.time)
        deadline = due + timedelta(hours=config.retry_window_hours)

        windows = self.db.query(CoreUptimeWindow).all()
        in_core, window = cu.is_in_core_uptime(due, windows)
        if not in_core:
            return RebootPreviewResponse(
                enabled=True,
                next_due_at=to_utc(due),
                in_core_uptime=False,
                retry_deadline_at=to_utc(deadline),
                reachable=True,
            )

        window_end = cu.current_window_end(due, window)
        return RebootPreviewResponse(
            enabled=True,
            next_due_at=to_utc(due),
            in_core_uptime=True,
            window_label=window.label,
            window_ends_at=to_utc(window_end),
            retry_deadline_at=to_utc(deadline),
            # Erreichbar nur, wenn das Fenster noch innerhalb der Frist endet.
            reachable=window_end <= deadline,
        )
```

`from datetime import timedelta` oben in `service.py` ergänzen, falls nicht
bereits importiert.

- [ ] **Step 5: Validate and audit in the route**

In `backend/app/api/routes/schedulers.py`, in `update_scheduler_config()`, vor
dem Aufruf von `service.update_scheduler_config`:

```python
    if name == "system_reboot" and config.extra_config is not None:
        # Für diesen einen Scheduler ist extra_config kein freies Dict.
        # Pydantic wirft ValidationError -> FastAPI antwortet 422.
        from app.schemas.scheduler import RebootScheduleConfig

        try:
            validated = RebootScheduleConfig(**config.extra_config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        config = config.model_copy(update={"extra_config": validated.model_dump()})

        get_audit_logger_db().log_event(
            event_type="admin",
            user=current_user.username,
            action="update_reboot_schedule",
            resource="system_reboot",
            details=validated.model_dump(),
            success=True,
        )
```

Dazu oben in der Datei ergänzen:

```python
from pydantic import ValidationError

from app.services.audit.logger_db import get_audit_logger_db
```

Ebenso in `toggle_scheduler()`, vor dem `return`:

```python
    if name == "system_reboot":
        get_audit_logger_db().log_event(
            event_type="admin",
            user=current_user.username,
            action="toggle_reboot_schedule",
            resource="system_reboot",
            details={"enabled": body.enabled},
            success=True,
        )
```

- [ ] **Step 6: Add the preview route**

In `backend/app/api/routes/schedulers.py`. **Die Route muss VOR
`@router.get("/{name}")` stehen**, sonst fängt der Platzhalter sie ab:

```python
@router.get("/system_reboot/preview", response_model=RebootPreviewResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_reboot_preview(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Nächster Neustart-Termin und seine Kollision mit der Kernbetriebszeit.

    `reachable: false` heißt: der Termin liegt in einem Kernbetriebszeit-Fenster,
    das erst NACH Ablauf der Nachholfrist endet — der Neustart läuft so nie.
    """
    return get_scheduler_service(db).get_reboot_preview()
```

`RebootPreviewResponse` in den Import-Block aus `app.schemas.scheduler`
aufnehmen.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_reboot_scheduler_api.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/scheduler/service.py backend/app/api/routes/schedulers.py \
        backend/app/schemas/scheduler.py backend/tests/api/test_reboot_scheduler_api.py
git commit -m "feat(reboot): Statusanzeige, Konfigurationsvalidierung, Audit und Preview-Route"
```

---

## Task 11: Frontend

**Files:**
- Modify: `client/src/api/schedulers.ts`
- Modify: `client/src/components/scheduler/SchedulerConfigModal.tsx`
- Modify: `client/src/i18n/locales/de/scheduler.json`, `client/src/i18n/locales/en/scheduler.json`
- Test: `client/src/components/scheduler/__tests__/SchedulerConfigModal.reboot.test.tsx`
- Test: `client/src/i18n/__tests__/reboot-placeholders.test.ts`

**Interfaces:**
- Consumes: `GET /api/schedulers/system_reboot/preview`, `PUT /api/schedulers/system_reboot/config`.
- Produces: `RebootPreview`-Typ und `getRebootPreview()` in `client/src/api/schedulers.ts`.

- [ ] **Step 1: Write the failing tests**

`client/src/components/scheduler/__tests__/SchedulerConfigModal.reboot.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { SchedulerConfigModal } from '../SchedulerConfigModal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key} ${JSON.stringify(opts)}` : key }),
}));

const getRebootPreview = vi.fn();
vi.mock('../../../api/schedulers', () => ({
  getRebootPreview: (...args: unknown[]) => getRebootPreview(...args),
}));

const rebootScheduler = {
  name: 'system_reboot',
  display_name: 'Geplanter Neustart',
  description: '',
  is_running: false,
  is_enabled: true,
  interval_seconds: 604800,
  interval_display: 'Sonntag 04:00',
  can_run_manually: false,
  extra_config: { weekday: 6, time: '04:00', retry_window_hours: 6, warning_lead_minutes: 10 },
} as never;

describe('SchedulerConfigModal — system_reboot', () => {
  beforeEach(() => {
    getRebootPreview.mockReset();
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-13T02:00:00Z', in_core_uptime: false,
      window_label: null, window_ends_at: null,
      retry_deadline_at: '2026-09-13T08:00:00Z', reachable: true,
    });
  });

  it('shows weekday and time instead of the interval controls', async () => {
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    expect(await screen.findByTestId('reboot-weekday')).toBeInTheDocument();
    expect(screen.getByTestId('reboot-time')).toBeInTheDocument();
    expect(screen.queryByTestId('interval-value')).not.toBeInTheDocument();
  });

  it('renders no warning without a collision', async () => {
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    await waitFor(() => expect(getRebootPreview).toHaveBeenCalled());
    expect(screen.queryByTestId('reboot-core-uptime-warning')).not.toBeInTheDocument();
  });

  it('warns that the reboot will never run when the window outlasts the retry window', async () => {
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Wochentags', window_ends_at: '2026-09-14T20:00:00Z',
      retry_deadline_at: '2026-09-14T14:00:00Z', reachable: false,
    });
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    const warning = await screen.findByTestId('reboot-core-uptime-warning');
    expect(warning.textContent).toContain('configModal.reboot.warningNever');
  });

  it('warns more mildly when the reboot is caught up after the window', async () => {
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Vormittag', window_ends_at: '2026-09-14T10:00:00Z',
      retry_deadline_at: '2026-09-14T20:00:00Z', reachable: true,
    });
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    const warning = await screen.findByTestId('reboot-core-uptime-warning');
    expect(warning.textContent).toContain('configModal.reboot.warningDeferred');
  });
});
```

`client/src/i18n/__tests__/reboot-placeholders.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import de from '../locales/de/scheduler.json';
import en from '../locales/en/scheduler.json';

/**
 * Der react-i18next-Mock erfindet Interpolation — ein fehlender
 * {{platzhalter}} in der Locale-Datei fällt in Komponententests nicht auf.
 * Deshalb hier ein Vertragstest gegen die JSON-Dateien selbst.
 */
const REQUIRED: Record<string, string[]> = {
  'configModal.reboot.warningNever': ['window', 'windowEnds', 'retryHours'],
  'configModal.reboot.warningDeferred': ['window', 'windowEnds'],
};

function at(source: Record<string, unknown>, path: string): string {
  return path.split('.').reduce<unknown>(
    (acc, part) => (acc as Record<string, unknown>)?.[part], source,
  ) as string;
}

describe('scheduler locales — reboot warnings', () => {
  for (const [key, placeholders] of Object.entries(REQUIRED)) {
    for (const [name, bundle] of Object.entries({ de, en })) {
      it(`${name}: ${key} carries ${placeholders.join(', ')}`, () => {
        const value = at(bundle as Record<string, unknown>, key);
        expect(typeof value).toBe('string');
        for (const placeholder of placeholders) {
          expect(value).toContain(`{{${placeholder}}}`);
        }
      });
    }
  }
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/scheduler src/i18n`
Expected: FAIL — `getRebootPreview` existiert nicht, Locale-Schlüssel fehlen.

- [ ] **Step 3: Add the API client function**

In `client/src/api/schedulers.ts`:

```ts
export interface RebootPreview {
  enabled: boolean;
  next_due_at: string | null;
  in_core_uptime: boolean;
  window_label: string | null;
  window_ends_at: string | null;
  retry_deadline_at: string | null;
  /** false = Termin liegt in einem Fenster, das erst nach der Frist endet -> läuft nie. */
  reachable: boolean;
}

export async function getRebootPreview(): Promise<RebootPreview> {
  const { data } = await api.get<RebootPreview>('/schedulers/system_reboot/preview');
  return data;
}
```

Den vorhandenen Import-/`api`-Stil der Datei übernehmen.

- [ ] **Step 4: Add the reboot branch to the modal**

In `SchedulerConfigModal.tsx`. Zustand und Vorschau, oben bei den vorhandenen
`useState`-Aufrufen:

```tsx
const isReboot = scheduler?.name === 'system_reboot';
const [weekday, setWeekday] = useState(6);
const [time, setTime] = useState('04:00');
const [retryHours, setRetryHours] = useState(6);
const [leadMinutes, setLeadMinutes] = useState(10);
const [preview, setPreview] = useState<RebootPreview | null>(null);
```

Im bestehenden `useEffect`, das das Formular initialisiert, im `if (scheduler)`-Block:

```tsx
      if (scheduler.name === 'system_reboot') {
        const extra = scheduler.extra_config ?? {};
        setWeekday(Number(extra.weekday ?? 6));
        setTime(String(extra.time ?? '04:00'));
        setRetryHours(Number(extra.retry_window_hours ?? 6));
        setLeadMinutes(Number(extra.warning_lead_minutes ?? 10));
      }
```

Vorschau laden — neu, direkt darunter:

```tsx
useEffect(() => {
  if (!isOpen || !isReboot) { setPreview(null); return; }
  let cancelled = false;
  getRebootPreview()
    .then((value) => { if (!cancelled) setPreview(value); })
    .catch(() => { if (!cancelled) setPreview(null); });
  return () => { cancelled = true; };
}, [isOpen, isReboot, weekday, time, retryHours]);
```

> Die Vorschau zeigt den **gespeicherten** Termin, nicht den gerade getippten —
> sie kommt vom Server, und der kennt nur die persistierte Konfiguration. Nach
> dem Speichern lädt der Effekt neu. Das ist bewusst so: die Kollisionsregel
> serverseitig zu halten war die Entscheidung in Abschnitt 8 der Spec, und eine
> zweite Rechnung im Client wäre genau die Dopplung, die driftet.

Die Formularfelder — für `system_reboot` **anstelle** der Intervall-Steuerung.
Den vorhandenen Intervall-Block in `{!isReboot && ( ... )}` einwickeln und
daneben setzen:

```tsx
{isReboot && (
  <div className="space-y-4">
    <label className="block">
      <span className="mb-1 block text-sm text-slate-300">
        {t('configModal.reboot.weekday')}
      </span>
      <select
        data-testid="reboot-weekday"
        value={weekday}
        onChange={(e) => setWeekday(Number(e.target.value))}
        className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2"
      >
        {[0, 1, 2, 3, 4, 5, 6].map((day) => (
          <option key={day} value={day}>{t(`weekdays.${day}`)}</option>
        ))}
      </select>
    </label>

    <label className="block">
      <span className="mb-1 block text-sm text-slate-300">
        {t('configModal.reboot.time')}
      </span>
      <input
        data-testid="reboot-time"
        type="time"
        value={time}
        onChange={(e) => setTime(e.target.value)}
        className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2"
      />
    </label>

    <label className="block">
      <span className="mb-1 block text-sm text-slate-300">
        {t('configModal.reboot.retryHours')}
      </span>
      <input
        data-testid="reboot-retry"
        type="number" min={1} max={24}
        value={retryHours}
        onChange={(e) => setRetryHours(Number(e.target.value))}
        className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2"
      />
    </label>

    <label className="block">
      <span className="mb-1 block text-sm text-slate-300">
        {t('configModal.reboot.leadMinutes')}
      </span>
      <input
        data-testid="reboot-lead"
        type="number" min={0} max={120}
        value={leadMinutes}
        onChange={(e) => setLeadMinutes(Number(e.target.value))}
        className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2"
      />
    </label>
  </div>
)}
```

> Die Tailwind-Klassen sind die des bestehenden Intervall-Blocks. Weichen sie
> dort ab, die vorhandenen übernehmen statt diese — das Modal soll einheitlich
> aussehen. `weekdays.0..6` muss in beiden Locale-Dateien existieren; falls der
> Namespace die Wochentage noch nicht hat, in Schritt 5 mit anlegen.

Der Warnblock, nicht blockierend:

```tsx
{isReboot && preview?.in_core_uptime && (
  <div data-testid="reboot-core-uptime-warning" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
    {preview.reachable
      ? t('configModal.reboot.warningDeferred', {
          window: preview.window_label ?? '',
          windowEnds: formatTime(preview.window_ends_at),
        })
      : t('configModal.reboot.warningNever', {
          window: preview.window_label ?? '',
          windowEnds: formatTime(preview.window_ends_at),
          retryHours,
        })}
  </div>
)}
```

Der Speicherpfad schickt für `system_reboot` `extra_config` statt
`interval_seconds`:

```tsx
const config: SchedulerConfigUpdate = isReboot
  ? { is_enabled: isEnabled, extra_config: {
      weekday, time, retry_window_hours: retryHours, warning_lead_minutes: leadMinutes,
    } }
  : { interval_seconds: intervalSeconds, is_enabled: isEnabled, ...(/* bestehender Zweig */) };
```

- [ ] **Step 5: Add the locale strings**

Zusätzlich zu den Blöcken unten braucht der Namespace `weekdays.0` bis
`weekdays.6` (Montag…Sonntag bzw. Monday…Sunday) auf oberster Ebene — die
Wochentagsauswahl greift darauf zu. Erst prüfen, ob es sie schon gibt:
`sed -n '/weekdays/,+9p' client/src/i18n/locales/de/scheduler.json`.

`client/src/i18n/locales/de/scheduler.json`, unter `configModal`:

```json
"reboot": {
  "weekday": "Wochentag",
  "time": "Uhrzeit",
  "retryHours": "Nachholfrist (Stunden)",
  "leadMinutes": "Vorwarnung (Minuten, 0 = aus)",
  "warningDeferred": "Dieser Termin liegt in der Kernbetriebszeit „{{window}}\". Der Neustart wird übersprungen und um {{windowEnds}} nachgeholt.",
  "warningNever": "Dieser Termin liegt in der Kernbetriebszeit „{{window}}\". Das Fenster endet erst um {{windowEnds}} und damit außerhalb der Nachholfrist von {{retryHours}} Stunden. Der Neustart läuft so nie."
}
```

`client/src/i18n/locales/en/scheduler.json`, unter `configModal`:

```json
"reboot": {
  "weekday": "Weekday",
  "time": "Time",
  "retryHours": "Catch-up window (hours)",
  "leadMinutes": "Advance warning (minutes, 0 = off)",
  "warningDeferred": "This time falls inside core operating hours \"{{window}}\". The reboot will be skipped and caught up at {{windowEnds}}.",
  "warningNever": "This time falls inside core operating hours \"{{window}}\". The window only ends at {{windowEnds}}, which is outside the {{retryHours}}-hour catch-up window. The reboot will never run."
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/scheduler src/i18n`
Expected: PASS

- [ ] **Step 7: Run the CI gates**

Run: `cd client && npx eslint . && npm run build`
Expected: 0 ESLint-Fehler, Build grün. `npm run build` ist `tsc -b` über die
Projekte app/node/TEST — ein reines `tsc --noEmit` deckt das nicht ab.

- [ ] **Step 8: Commit**

```bash
git add client/src/api/schedulers.ts client/src/components/scheduler/ client/src/i18n/
git commit -m "feat(reboot): Wochentag-Konfiguration und Kernbetriebszeit-Warnung im UI"
```

---

## Task 12: Dokumentation

**Files:**
- Modify: `.claude/rules/ci-cd-security.md`
- Modify: `.claude/rules/architecture.md`
- Modify: `CLAUDE.md`
- Modify: `docs/TECHNICAL_DOCUMENTATION.md`

- [ ] **Step 1: Document the sudoers entry as an accepted risk**

In `.claude/rules/ci-cd-security.md`, unter „Known Gaps & Accepted Risks", als
Punkt 11:

```markdown
11. **`baluhost` user may run `systemctl reboot` as root** — Added in
    `deploy/install/templates/sudoers-baluhost-power` for the scheduled
    maintenance reboot (`backend/app/services/power/scheduled_reboot.py`).
    Exactly one verb, no arguments, no wildcards. This is the widest entry in
    the file — it terminates every service on the box — so the compensating
    controls matter: the feature is **off by default** (no `scheduler_configs`
    row means disabled, enforced by an explicit `system_reboot` branch in both
    `_is_enabled` paths), only an admin can configure or enable it, and four
    gates (core uptime, displays on, running scheduler job, system not idle)
    must all be open before it fires. Every configuration change and every
    actual reboot is written to the audit log. Reaching an installed box needs
    a `SYNC_PERMISSIONS=1` deploy; until then the reboot fails closed.
```

- [ ] **Step 2: Add the scheduler to the architecture rules**

In `.claude/rules/architecture.md`, in der Scheduler-Liste unter
„Service submodules" bzw. bei den API-Routen ergänzen:

```markdown
- `power/scheduled_reboot.py` - Geplanter Wochenneustart (Gates, Automat,
  Ausführung); Termin und Historie über den Scheduler-Eintrag `system_reboot`,
  Ausführung im Power-Layer, weil dort Kernbetriebszeit, Display-Erkennung und
  die `wake_at`-Klemmung liegen
```

- [ ] **Step 3: Add the finding aid to CLAUDE.md**

In `CLAUDE.md`, in „Quick Reference: Finding Things":

```markdown
**Geplanter Systemneustart**: `backend/app/services/power/scheduled_reboot.py` (Automat + Gates), `reboot_schedule.py` (Terminmathematik), `reboot_state.py` (Zustand über den Reboot hinweg); Design: `docs/superpowers/specs/2026-09-12-scheduled-system-reboot-design.md`
```

- [ ] **Step 4: Document the feature for users**

In `docs/TECHNICAL_DOCUMENTATION.md` einen Abschnitt „Geplanter
Systemneustart" ergänzen: Konfiguration (Wochentag, Uhrzeit, Nachholfrist,
Vorwarnung), die vier Gates mit ihren Gründen, das Weck-/Wieder-Suspend-Verhalten,
die vier Notifications und den einmaligen `SYNC_PERMISSIONS=1`-Deploy-Schritt.
Den vorhandenen Aufbau und Ton der Nachbarabschnitte übernehmen.

- [ ] **Step 5: Commit**

```bash
git add .claude/rules/ CLAUDE.md docs/TECHNICAL_DOCUMENTATION.md
git commit -m "docs(reboot): sudoers-Risiko, Architekturverweise und Nutzerdoku"
```

---

## Abschluss vor dem PR

- [ ] **Backend-Tests der neuen Dateien**

```bash
cd backend && python -m pytest \
  tests/services/test_reboot_schedule.py \
  tests/services/test_reboot_state.py \
  tests/services/test_reboot_gates.py \
  tests/services/test_reboot_execution.py \
  tests/services/test_reboot_automaton.py \
  tests/services/test_reboot_sleep_integration.py \
  tests/services/test_scheduler_reboot_registry.py \
  tests/api/test_reboot_scheduler_api.py \
  tests/test_reboot_lifespan.py -v
```

- [ ] **Regressionen in den berührten Bereichen**

```bash
cd backend && python -m pytest tests/ -k "sleep or scheduler or lifecycle" -v
```

- [ ] **Genau ein Alembic-Head**

```bash
cd backend && python -m alembic heads
```
Erwartet: **eine** Zeile.

- [ ] **Frontend-Gates**

```bash
cd client && npx eslint . && npm run build && npx vitest run
```

- [ ] **Die volle Backend-Suite gehört der CI** — auf Windows hängt sie.

- [ ] **PR-Beschreibung** muss den einmaligen Ops-Schritt nennen: nach dem Merge
      einen `SYNC_PERMISSIONS=1`-Deploy fahren, sonst schlägt der erste Neustart
      mit „sudo: no entry" fehl (fail-closed, mit Notification).
