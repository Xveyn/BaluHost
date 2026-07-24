# Steam-Session-Historie + Dashboard-Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Steam-Sessions werden in einer eigenen Tabelle verbucht, das Dashboard zeigt die letzten fünf als admin-only Panel, und der direkte Spielwechsel X→Y wird gebucht **und** gemeldet (schließt #462).

**Architecture:** Die offene Session in der DB (`ended_at IS NULL`) **ist** der Zustand des Pollers — kein `_last_app_id`, kein `_initialized`-Flag mehr. Ein neues Modul `ledger.py` übersetzt eine Detektor-Beobachtung in Buchungen und gibt zurück, was zu melden ist; der Poller detektiert, ruft den Ledger und feuert danach die Events. Das Panel liest dieselbe Tabelle über den bereits vorhandenen `status`-Renderer.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (`Mapped[...]`/`mapped_column`), Alembic, pytest (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/specs/2026-07-24-steam-session-history-dashboard-panel-design.md`
**Branch:** `feat/steam-session-history-panel` (existiert bereits, Spec ist dort committed)

## Global Constraints

- **Arbeitsverzeichnis für alle Kommandos:** `backend/` (`cd "D:/Programme (x86)/Baluhost/backend"`). Testpfade im Plan sind relativ dazu.
- **Kein `&&` in Kommandos** (PowerShell 5.1 kennt es nicht) — mit `;` trennen oder `if ($?) { … }`.
- **Commit-Nachrichten ASCII-only** (keine Umlaute) und einzeilig via `-m`; Zeilenumbrüche über mehrere `-m`-Flags. Jede Commit-Nachricht endet mit `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` als eigenes `-m`.
- **Type Hints auf allen Funktionen**, Docstrings auf allen öffentlichen Funktionen/Klassen (`.claude/rules/backend/coding-style.md`).
- **Die Migration setzt auf `down_revision = '71fe791d28d6'`** — das ist der einzige echte Head im `alembic/versions`-Verzeichnis (verifiziert 2026-07-24, 115 Revisionen). **Niemals** den Head der lokalen Dev-DB verwenden (#123 → #124).
- **Tests laufen mit `NAS_MODE=dev`** (`tests/conftest.py:23`) — `settings.is_dev_mode` ist in der Suite **True**. Deshalb darf die Dev-Mode-Ersatzerkennung nicht in `detector.py`/`names.py` landen (das würde die bestehenden Detektor-Tests brechen), sondern kommt in ein eigenes Modul `detection.py` (Task 8).
- **Konstanten aus der Spec, wörtlich:** `STALE_AFTER_SECONDS = 60.0`, `ADOPT_WINDOW_SECONDS = 600.0`, `RETENTION_DAYS = 365`, Panel-Zeilen = 5, Poll-Intervall bleibt 30 s.
- **Reihenfolge im Tick, verbindlich:** erst buchen **und committen**, dann melden.
- **Kein Frontend-Diff.** `PluginDashboardPanel.tsx` löst Panel-Icons dynamisch aus lucide auf (kebab→Pascal, Fallback `Plug`), `StatusPanel.tsx` rendert `label`/`value`/`tone`. Wer in `client/` etwas ändern will, hat den Plan verlassen.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `app/models/steam_session.py` (neu) | Nur das ORM-Modell `SteamSession` |
| `alembic/versions/<rev>_add_steam_sessions_table.py` (neu) | Tabelle anlegen/entfernen |
| `app/plugins/installed/steam_gaming/ledger.py` (neu) | Flanken- und Lückenregeln, Retention, Dauerberechnung. Kennt die DB, kennt **keine** Notifications |
| `app/plugins/installed/steam_gaming/detection.py` (neu) | Eine Quelle für „läuft ein Spiel" (Pill, Ledger, Panel), inkl. Dev-Mode-Ersatz |
| `app/plugins/installed/steam_gaming/poller.py` (ändern) | Detektieren → Ledger → melden. Kein eigener Zustand mehr |
| `app/plugins/installed/steam_gaming/__init__.py` (ändern) | Panel-Spec + Panel-Daten + Formatierung; Pill nutzt `detection.py` |
| `app/plugins/base.py` (ändern) | `DashboardPanelSpec.admin_only` |
| `app/api/routes/dashboard.py` (ändern) | Gate: `admin_only` → `is_privileged` |
| `app/services/websocket_manager.py` (ändern) | `broadcast_typed(..., admins_only=False)` |
| `app/services/dashboard_panel_bridge.py` (ändern) | Broadcast admin-only-Panels nur an Admins |
| `tests/plugins/test_steam_gaming_ledger.py` (neu) | Ledger-Regeln |
| `tests/plugins/test_steam_gaming_panel.py` (neu) | Panel-Spec, Formatierung, Gate |
| `tests/plugins/test_steam_gaming_poller.py` (ändern) | Poller gegen den Ledger |

**Warum ein Sicherheits-Task, der nicht in der Spec steht (Task 7):** Beim Planen gefunden — `dashboard_panel_ws_bridge()` broadcastet Panel-Daten mit `broadcast_typed()` an **alle** verbundenen WebSocket-Clients. Ein `admin_only`-Gate allein in der REST-Route wäre wirkungslos, sobald der Bridge feuert (er triggert auf Smart-Device-SHM-Änderungen, und Tapo-Geräte laufen auf dieser Box). Ohne Task 7 leakt das Panel die Spielnamen an jeden angemeldeten Nutzer — genau das, was `admin_only` verhindern soll.

---

## Task 1: Modell + Migration

**Files:**
- Create: `app/models/steam_session.py`
- Create: `alembic/versions/<generiert>_add_steam_sessions_table.py`
- Modify: `app/models/__init__.py`
- Test: `tests/plugins/test_steam_gaming_ledger.py`

**Interfaces:**
- Produces: `app.models.steam_session.SteamSession` mit den Feldern `id: int`, `app_id: str`, `game_name: Optional[str]`, `started_at: datetime`, `last_seen_at: datetime`, `ended_at: Optional[datetime]`.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/plugins/test_steam_gaming_ledger.py`:

```python
"""Steam session ledger: persisted play sessions (Teilprojekt 4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.steam_session import SteamSession

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


class TestModel:
    def test_open_session_round_trips(self, db_session):
        db_session.add(SteamSession(
            app_id="1449560",
            game_name="Metro Exodus Enhanced Edition",
            started_at=T0,
            last_seen_at=T0,
        ))
        db_session.commit()

        row = db_session.query(SteamSession).one()
        assert row.app_id == "1449560"
        assert row.game_name == "Metro Exodus Enhanced Edition"
        assert row.ended_at is None

    def test_game_name_is_optional(self, db_session):
        db_session.add(SteamSession(
            app_id="999", game_name=None, started_at=T0, last_seen_at=T0,
        ))
        db_session.commit()

        assert db_session.query(SteamSession).one().game_name is None

    def test_ended_session_stores_its_end(self, db_session):
        end = T0 + timedelta(hours=1)
        db_session.add(SteamSession(
            app_id="1", started_at=T0, last_seen_at=end, ended_at=end,
        ))
        db_session.commit()

        assert db_session.query(SteamSession).one().ended_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.steam_session'`

- [ ] **Step 3: Write the model**

Neue Datei `app/models/steam_session.py`:

```python
"""Steam play sessions recorded by the steam_gaming plugin (Teilprojekt 4/4).

The table lives in app/models/ rather than in the plugin because Alembic's
autogenerate only sees what is attached to Base.metadata — same reason
smart_device.py sits here for the Tapo plugin.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SteamSession(Base):
    """One play session. ``ended_at IS NULL`` means it is still running.

    The duration is deliberately NOT stored: it is derived from
    ``ended_at - started_at``. A stored value would be a second truth that can
    drift when a session is adopted across a backend restart.
    """

    __tablename__ = "steam_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    app_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    game_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SteamSession(app_id='{self.app_id}', started_at={self.started_at})>"
```

- [ ] **Step 4: Register the model**

In `app/models/__init__.py` direkt nach der Zeile
`from app.models.status_bar import StatusBarPillConfig, StatusBarSettings` einfügen:

```python
from app.models.steam_session import SteamSession
```

und in der `__all__`-Liste direkt nach `"StatusBarSettings",` einfügen:

```python
    "SteamSession",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: PASS (3 passed) — die `db_session`-Fixture legt die Tabelle über `Base.metadata.create_all()` an.

- [ ] **Step 6: Generate the migration skeleton**

Run: `python -m alembic revision -m "add steam_sessions table"`
Expected: `Generating …/alembic/versions/<rev>_add_steam_sessions_table.py ... done`

**Sofort prüfen:** In der erzeugten Datei muss `down_revision` auf `'71fe791d28d6'` stehen. Steht dort etwas anderes, von Hand korrigieren — das ist der einzige echte Head.

- [ ] **Step 7: Fill in the migration body**

`upgrade()` und `downgrade()` in der neuen Datei komplett ersetzen durch:

```python
def upgrade() -> None:
    """Create steam_sessions (play history for the steam_gaming plugin)."""
    op.create_table(
        'steam_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.String(length=32), nullable=False),
        sa.Column('game_name', sa.String(length=200), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_steam_sessions_id', 'steam_sessions', ['id'])
    op.create_index('ix_steam_sessions_app_id', 'steam_sessions', ['app_id'])
    op.create_index('ix_steam_sessions_started_at', 'steam_sessions', ['started_at'])


def downgrade() -> None:
    """Drop steam_sessions. Loses the play history — dev/rollback path only."""
    op.drop_index('ix_steam_sessions_started_at', table_name='steam_sessions')
    op.drop_index('ix_steam_sessions_app_id', table_name='steam_sessions')
    op.drop_index('ix_steam_sessions_id', table_name='steam_sessions')
    op.drop_table('steam_sessions')
```

Der Docstring am Dateikopf (von Alembic erzeugt) bleibt; ergänze darunter einen Satz:
`Teilprojekt 4/4 — siehe docs/superpowers/specs/2026-07-24-steam-session-history-dashboard-panel-design.md`

- [ ] **Step 8: Verify the migration applies and reverts**

Run: `python -m alembic upgrade head`
Expected: `Running upgrade 71fe791d28d6 -> <rev>, add steam_sessions table`

Run: `python -m alembic downgrade -1`
Expected: `Running downgrade <rev> -> 71fe791d28d6, add steam_sessions table`

Run: `python -m alembic upgrade head`
Expected: erneut `Running upgrade …` (wieder oben)

Run: `python -m alembic heads`
Expected: **genau eine** Zeile, die auf `<rev> (head)` endet.

- [ ] **Step 9: Commit**

```bash
git add app/models/steam_session.py app/models/__init__.py alembic/versions tests/plugins/test_steam_gaming_ledger.py
git commit -m "feat(steam-gaming): steam_sessions table for the play history" -m "Model in app/models/ so Alembic autogenerate sees it; duration stays derived, never stored." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Ledger — Flanken im Live-Fall

**Files:**
- Create: `app/plugins/installed/steam_gaming/ledger.py`
- Test: `tests/plugins/test_steam_gaming_ledger.py`

**Interfaces:**
- Consumes: `SteamSession` (Task 1)
- Produces:
  - `LedgerEvent(event_id: str, app_id: str, game: str)` — frozen dataclass
  - `record(db: Session, app_id: Optional[str], *, now: datetime, resolve_name: Callable[[str], Optional[str]]) -> List[LedgerEvent]` — bucht **und committet**, gibt die zu meldenden Events zurück
  - `as_utc(value: datetime) -> datetime` — hängt UTC an naive Werte (SQLite)
  - Konstanten `EVENT_STARTED = "session_started"`, `EVENT_ENDED = "session_ended"`, `STALE_AFTER_SECONDS = 60.0`, `ADOPT_WINDOW_SECONDS = 600.0`

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_steam_gaming_ledger.py` anhängen:

```python
from app.plugins.installed.steam_gaming import ledger


def _names(app_id: str):
    """Stand-in for names.resolve_name()."""
    return {"111": "Metro", "222": "Cyberpunk"}.get(app_id)


def _record(db, app_id, now):
    return ledger.record(db, app_id, now=now, resolve_name=_names)


class TestLiveEdges:
    def test_nothing_open_and_nothing_running_books_nothing(self, db_session):
        events = _record(db_session, None, T0)

        assert events == []
        assert db_session.query(SteamSession).count() == 0

    def test_game_appears_opens_a_session_and_announces_it(self, db_session):
        events = _record(db_session, "111", T0)

        row = db_session.query(SteamSession).one()
        assert row.app_id == "111"
        assert row.game_name == "Metro"
        assert row.started_at is not None
        assert row.ended_at is None
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_STARTED, "111", "Metro")
        ]

    def test_same_game_next_tick_only_moves_the_heartbeat(self, db_session):
        _record(db_session, "111", T0)
        events = _record(db_session, "111", T0 + timedelta(seconds=30))

        row = db_session.query(SteamSession).one()
        assert events == []
        assert ledger.as_utc(row.last_seen_at) == T0 + timedelta(seconds=30)
        assert row.ended_at is None

    def test_game_disappears_closes_at_now_and_announces_the_end(self, db_session):
        _record(db_session, "111", T0)
        end = T0 + timedelta(seconds=30)
        events = _record(db_session, None, end)

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == end
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_ENDED, "111", "Metro")
        ]

    def test_direct_switch_closes_x_opens_y_and_announces_both(self, db_session):
        """#462: X->Y without a pause was swallowed in TP3."""
        _record(db_session, "111", T0)
        switch = T0 + timedelta(seconds=30)
        events = _record(db_session, "222", switch)

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == switch
        assert rows[1].app_id == "222" and rows[1].ended_at is None
        assert [(e.event_id, e.app_id, e.game) for e in events] == [
            (ledger.EVENT_ENDED, "111", "Metro"),
            (ledger.EVENT_STARTED, "222", "Cyberpunk"),
        ]

    def test_unresolved_name_falls_back_to_the_app_id_in_the_event(self, db_session):
        events = _record(db_session, "999", T0)

        assert db_session.query(SteamSession).one().game_name is None
        assert events[0].game == "999"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'ledger'`

- [ ] **Step 3: Write the ledger**

Neue Datei `app/plugins/installed/steam_gaming/ledger.py`:

```python
"""Steam session ledger: turn detector observations into persisted sessions.

The open session in the database IS the poller's state - there is no in-process
last_app_id and no initialization flag. That is what makes a restart mid-session
harmless: the gap between `now` and the open session's last_seen_at says what
happened while the process was away (see the gap rules in Task 3).

This module knows the database and nothing about notifications: it returns what
is worth announcing and lets the caller deliver it, after the booking is
committed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.models.steam_session import SteamSession

logger = logging.getLogger(__name__)

EVENT_STARTED = "session_started"
EVENT_ENDED = "session_ended"

# Two poll intervals: within this, the poller was there continuously, so `now`
# is a truthful end time and the edge is live news worth announcing.
STALE_AFTER_SECONDS = 60.0
# The same game across a gap this short is one session (a deploy mid-game).
ADOPT_WINDOW_SECONDS = 600.0


@dataclass(frozen=True)
class LedgerEvent:
    """A notification the caller should fire once the booking is committed."""

    event_id: str
    app_id: str
    game: str


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes even for DateTime(timezone=True)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _label(session: SteamSession) -> str:
    """Name for a notification; the AppID is the honest fallback."""
    return session.game_name or session.app_id


def _open(
    db: Session,
    app_id: str,
    now: datetime,
    resolve_name: Callable[[str], Optional[str]],
) -> SteamSession:
    """Start a new session. Announcing it is the caller's decision."""
    session = SteamSession(
        app_id=app_id,
        game_name=resolve_name(app_id),
        started_at=now,
        last_seen_at=now,
    )
    db.add(session)
    return session


def _current_session(db: Session) -> Optional[SteamSession]:
    """The newest open session, if any."""
    return (
        db.query(SteamSession)
        .filter(SteamSession.ended_at.is_(None))
        .order_by(SteamSession.started_at.desc())
        .first()
    )


def record(
    db: Session,
    app_id: Optional[str],
    *,
    now: datetime,
    resolve_name: Callable[[str], Optional[str]],
) -> List[LedgerEvent]:
    """Book one detector observation; return the events worth announcing.

    Commits on success. Never raises: a database failure rolls back, logs and
    yields no events, so the next tick simply tries again.

    Args:
        db: SQLAlchemy session, owned by the caller.
        app_id: AppID of the running game, or None when nothing is running.
        now: Current time (injected so tests control the clock).
        resolve_name: AppID -> display name, or None when unresolvable.

    Returns:
        Events to deliver, in order.
    """
    events: List[LedgerEvent] = []
    try:
        current = _current_session(db)

        if current is None:
            if app_id is not None:
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))
        elif app_id == current.app_id:
            current.last_seen_at = now
        else:
            current.ended_at = now
            events.append(LedgerEvent(EVENT_ENDED, current.app_id, _label(current)))
            if app_id is not None:
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))

        db.commit()
    except Exception:  # broad on purpose: a booking failure must not kill the poller
        db.rollback()
        logger.warning("steam ledger: booking failed", exc_info=True)
        return []

    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/plugins/installed/steam_gaming/ledger.py tests/plugins/test_steam_gaming_ledger.py
git commit -m "feat(steam-gaming): ledger books sessions from detector edges" -m "The open DB session is the state; X->Y now closes X and opens Y (#462)." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Ledger — Lückenregeln

**Files:**
- Modify: `app/plugins/installed/steam_gaming/ledger.py`
- Test: `tests/plugins/test_steam_gaming_ledger.py`

**Interfaces:**
- Consumes: `record()`, `as_utc()`, `STALE_AFTER_SECONDS`, `ADOPT_WINDOW_SECONDS` (Task 2)
- Produces: unveränderte Signatur von `record()` — nur das Verhalten bei Lücken kommt dazu.

Die drei Regeln aus der Spec:
1. `ended_at = now`, wenn die Lücke ≤ `STALE_AFTER_SECONDS` — sonst `ended_at = last_seen_at`.
2. Nach einer Lücke wird nur gebucht, **nie** gemeldet.
3. Dasselbe Spiel über eine Lücke ≤ `ADOPT_WINDOW_SECONDS` führt die Session fort, darüber wird gesplittet.

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_steam_gaming_ledger.py` anhängen:

```python
class TestGapRules:
    def test_stale_end_is_booked_at_the_last_heartbeat(self, db_session):
        """The process was away: `now` would book the outage as playtime."""
        _record(db_session, "111", T0)
        _record(db_session, "111", T0 + timedelta(seconds=30))  # last heartbeat

        _record(db_session, None, T0 + timedelta(hours=2))

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.ended_at) == T0 + timedelta(seconds=30)

    def test_stale_end_is_not_announced(self, db_session):
        """A deploy must not push 'session ended' for a game that ended hours ago."""
        _record(db_session, "111", T0)

        events = _record(db_session, None, T0 + timedelta(hours=2))

        assert events == []

    def test_stale_switch_books_both_but_announces_nothing(self, db_session):
        _record(db_session, "111", T0)

        events = _record(db_session, "222", T0 + timedelta(hours=2))

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == T0
        assert rows[1].app_id == "222" and rows[1].ended_at is None
        assert events == []

    def test_same_game_across_a_short_gap_continues_the_session(self, db_session):
        """A deploy mid-game is the normal case on this box."""
        _record(db_session, "111", T0)
        resumed = T0 + timedelta(minutes=5)

        events = _record(db_session, "111", resumed)

        row = db_session.query(SteamSession).one()
        assert ledger.as_utc(row.started_at) == T0
        assert ledger.as_utc(row.last_seen_at) == resumed
        assert row.ended_at is None
        assert events == []

    def test_same_game_across_a_long_gap_splits_into_two_sessions(self, db_session):
        """Off overnight and restarted in the morning is not a 14h session."""
        _record(db_session, "111", T0)
        next_day = T0 + timedelta(hours=14)

        events = _record(db_session, "111", next_day)

        rows = db_session.query(SteamSession).order_by(SteamSession.started_at).all()
        assert len(rows) == 2
        assert ledger.as_utc(rows[0].ended_at) == T0
        assert ledger.as_utc(rows[1].started_at) == next_day
        assert rows[1].ended_at is None
        assert events == []

    def test_the_adopt_window_boundary_still_continues(self, db_session):
        _record(db_session, "111", T0)

        _record(db_session, "111", T0 + timedelta(seconds=ledger.ADOPT_WINDOW_SECONDS))

        assert db_session.query(SteamSession).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -k GapRules -v --no-cov`
Expected: FAIL — u. a. `test_stale_end_is_booked_at_the_last_heartbeat` (bucht noch `now`) und `test_same_game_across_a_long_gap_splits_into_two_sessions` (erzeugt nur eine Zeile)

- [ ] **Step 3: Add the gap rules**

In `ledger.py` die Hilfsfunktion ergänzen (direkt unter `_current_session`):

```python
def _gap_seconds(session: SteamSession, now: datetime) -> float:
    """How long the poller was away, measured from the session's last heartbeat."""
    return (now - as_utc(session.last_seen_at)).total_seconds()
```

und den `try`-Block in `record()` ersetzen durch:

```python
        current = _current_session(db)

        if current is None:
            if app_id is not None:
                # Nothing open: either nothing was running, or this is the very
                # first tick after deploying the ledger. Both look identical
                # here - see the accepted deviation in the design doc.
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))
        else:
            gap = _gap_seconds(current, now)
            live = gap <= STALE_AFTER_SECONDS

            if app_id == current.app_id:
                if gap <= ADOPT_WINDOW_SECONDS:
                    current.last_seen_at = now
                else:
                    # Same game, but far too long ago to be one session.
                    current.ended_at = as_utc(current.last_seen_at)
                    _open(db, app_id, now, resolve_name)  # after a gap: book, never announce
            else:
                # `now` is only a truthful end time while the poller was there.
                current.ended_at = now if live else as_utc(current.last_seen_at)
                if live:
                    events.append(LedgerEvent(EVENT_ENDED, current.app_id, _label(current)))
                if app_id is not None:
                    opened = _open(db, app_id, now, resolve_name)
                    if live:
                        events.append(
                            LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened))
                        )

        db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: PASS (15 passed) — die Live-Tests aus Task 2 bleiben grün, weil dort alle Lücken ≤ 30 s sind.

- [ ] **Step 5: Commit**

```bash
git add app/plugins/installed/steam_gaming/ledger.py tests/plugins/test_steam_gaming_ledger.py
git commit -m "feat(steam-gaming): gap rules make restarts and suspend harmless" -m "Stale ends book at last_seen_at and stay silent; the same game across a short gap continues, across a long one splits." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Ledger — Waisen aufräumen, Namen nachtragen, Dauer

**Files:**
- Modify: `app/plugins/installed/steam_gaming/ledger.py`
- Test: `tests/plugins/test_steam_gaming_ledger.py`

**Interfaces:**
- Produces: `duration_seconds(session: SteamSession, now: datetime) -> float` (vom Panel in Task 8 benutzt)

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_steam_gaming_ledger.py` anhängen:

```python
class TestHousekeeping:
    def test_orphaned_open_sessions_are_closed_silently(self, db_session):
        """The invariant says one open session; a crash can still leave more."""
        db_session.add_all([
            SteamSession(app_id="111", started_at=T0, last_seen_at=T0),
            SteamSession(
                app_id="222",
                started_at=T0 + timedelta(hours=1),
                last_seen_at=T0 + timedelta(hours=1),
            ),
        ])
        db_session.commit()

        events = _record(db_session, "222", T0 + timedelta(hours=1, seconds=30))

        older = db_session.query(SteamSession).filter_by(app_id="111").one()
        newer = db_session.query(SteamSession).filter_by(app_id="222").one()
        assert ledger.as_utc(older.ended_at) == T0
        assert newer.ended_at is None
        assert events == []

    def test_missing_game_name_is_resolved_on_a_later_heartbeat(self, db_session):
        """A game started during its own install has no appmanifest yet."""
        ledger.record(db_session, "111", now=T0, resolve_name=lambda _app_id: None)
        assert db_session.query(SteamSession).one().game_name is None

        _record(db_session, "111", T0 + timedelta(seconds=30))

        assert db_session.query(SteamSession).one().game_name == "Metro"

    def test_a_resolved_name_is_not_overwritten(self, db_session):
        _record(db_session, "111", T0)

        ledger.record(
            db_session, "111", now=T0 + timedelta(seconds=30), resolve_name=lambda _a: None
        )

        assert db_session.query(SteamSession).one().game_name == "Metro"


class TestDuration:
    def test_closed_session_duration(self, db_session):
        session = SteamSession(
            app_id="111",
            started_at=T0,
            last_seen_at=T0 + timedelta(minutes=90),
            ended_at=T0 + timedelta(minutes=90),
        )

        assert ledger.duration_seconds(session, T0 + timedelta(hours=5)) == 5400.0

    def test_open_session_counts_up_to_now(self, db_session):
        session = SteamSession(app_id="111", started_at=T0, last_seen_at=T0)

        assert ledger.duration_seconds(session, T0 + timedelta(minutes=12)) == 720.0

    def test_clock_stepping_backwards_clamps_at_zero(self, db_session):
        """An NTP step backwards must not produce a negative duration."""
        session = SteamSession(app_id="111", started_at=T0, last_seen_at=T0)

        assert ledger.duration_seconds(session, T0 - timedelta(minutes=5)) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -k "Housekeeping or Duration" -v --no-cov`
Expected: FAIL — `AttributeError: module 'app.plugins.installed.steam_gaming.ledger' has no attribute 'duration_seconds'` sowie ein offener Waisen-Datensatz

- [ ] **Step 3: Implement housekeeping and duration**

In `ledger.py` `_current_session()` ersetzen durch:

```python
def _claim_current_session(db: Session) -> Optional[SteamSession]:
    """The newest open session; any older open one is an orphan and gets closed.

    The invariant is "at most one open session". A crash at the wrong moment can
    still leave more behind, so every tick cleans up instead of trusting it.
    """
    open_sessions = (
        db.query(SteamSession)
        .filter(SteamSession.ended_at.is_(None))
        .order_by(SteamSession.started_at.desc())
        .all()
    )
    for orphan in open_sessions[1:]:
        orphan.ended_at = as_utc(orphan.last_seen_at)
        logger.warning("steam ledger: closed orphaned session id=%s", orphan.id)
    return open_sessions[0] if open_sessions else None
```

In `record()` den Aufruf anpassen:

```python
        current = _claim_current_session(db)
```

und im Heartbeat-Zweig den Namen nachtragen — aus

```python
                if gap <= ADOPT_WINDOW_SECONDS:
                    current.last_seen_at = now
```

wird

```python
                if gap <= ADOPT_WINDOW_SECONDS:
                    current.last_seen_at = now
                    if current.game_name is None:
                        # A game started during its own install has no manifest
                        # yet; resolve_name() retries misses after 60s anyway.
                        current.game_name = resolve_name(app_id)
```

Am Ende der Datei ergänzen:

```python
def duration_seconds(session: SteamSession, now: datetime) -> float:
    """Seconds played. An open session counts up to *now*.

    Clamped at 0: an NTP step backwards would otherwise produce a negative
    duration, which is worse in the panel than a flattering zero.
    """
    end = as_utc(session.ended_at) if session.ended_at is not None else now
    return max(0.0, (end - as_utc(session.started_at)).total_seconds())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: PASS (21 passed)

- [ ] **Step 5: Commit**

```bash
git add app/plugins/installed/steam_gaming/ledger.py tests/plugins/test_steam_gaming_ledger.py
git commit -m "feat(steam-gaming): close orphans, backfill names, derive duration" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Ledger — Retention

**Files:**
- Modify: `app/plugins/installed/steam_gaming/ledger.py`
- Test: `tests/plugins/test_steam_gaming_ledger.py`

**Interfaces:**
- Produces: `cleanup_old_sessions(db: Session, *, now: datetime) -> int` (Anzahl gelöschter Zeilen), Konstante `RETENTION_DAYS = 365`

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_steam_gaming_ledger.py` anhängen:

```python
class TestRetention:
    def test_deletes_sessions_older_than_the_retention_window(self, db_session):
        old_start = T0 - timedelta(days=400)
        db_session.add(SteamSession(
            app_id="111",
            started_at=old_start,
            last_seen_at=old_start + timedelta(hours=1),
            ended_at=old_start + timedelta(hours=1),
        ))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 1
        assert db_session.query(SteamSession).count() == 0

    def test_keeps_sessions_inside_the_window(self, db_session):
        recent = T0 - timedelta(days=364)
        db_session.add(SteamSession(
            app_id="111", started_at=recent, last_seen_at=recent, ended_at=recent,
        ))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 0
        assert db_session.query(SteamSession).count() == 1

    def test_never_deletes_an_open_session(self, db_session):
        """An open session has no ended_at - however old, it is the current one."""
        ancient = T0 - timedelta(days=500)
        db_session.add(SteamSession(app_id="111", started_at=ancient, last_seen_at=ancient))
        db_session.commit()

        deleted = ledger.cleanup_old_sessions(db_session, now=T0)

        assert deleted == 0
        assert db_session.query(SteamSession).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -k Retention -v --no-cov`
Expected: FAIL — `AttributeError: … has no attribute 'cleanup_old_sessions'`

- [ ] **Step 3: Implement retention**

In `ledger.py` den Import ergänzen:

```python
from datetime import datetime, timedelta, timezone
```

die Konstante unter `ADOPT_WINDOW_SECONDS` ergänzen:

```python
# Hard-wired on purpose; configurability is tracked in #464.
RETENTION_DAYS = 365
```

und am Dateiende anfügen:

```python
def cleanup_old_sessions(db: Session, *, now: datetime) -> int:
    """Delete ended sessions older than RETENTION_DAYS.

    Deliberately not wired into monitoring/retention_manager.py: that one hangs
    off the MetricType enum and monitoring_config rows, so putting a plugin
    table there would couple the core to a plugin.

    Returns:
        Number of rows deleted; 0 if the delete failed.
    """
    cutoff = now - timedelta(days=RETENTION_DAYS)
    try:
        deleted = (
            db.query(SteamSession)
            .filter(SteamSession.ended_at.isnot(None), SteamSession.ended_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:  # broad on purpose: retention must not kill the poller
        db.rollback()
        logger.warning("steam ledger: retention cleanup failed", exc_info=True)
        return 0
    return deleted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_ledger.py -v --no-cov`
Expected: PASS (24 passed)

- [ ] **Step 5: Commit**

```bash
git add app/plugins/installed/steam_gaming/ledger.py tests/plugins/test_steam_gaming_ledger.py
git commit -m "feat(steam-gaming): retention deletes ended sessions after 365 days" -m "Plugin-local instead of the MetricType-bound retention_manager; configurability tracked in #464." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Poller auf den Ledger umstellen

**Files:**
- Modify: `app/plugins/installed/steam_gaming/poller.py` (komplett ersetzen)
- Modify: `tests/plugins/test_steam_gaming_poller.py` (komplett ersetzen)

**Interfaces:**
- Consumes: `ledger.record()`, `ledger.cleanup_old_sessions()`, `ledger.LedgerEvent` (Tasks 2–5)
- Produces: `SteamSessionPoller(detect=…, resolve=…, emit=…, session_factory=…, clock=…)` mit `async def tick() -> None`. `__init__.py` konstruiert ihn weiterhin ohne Argumente.

Der Poller verliert `_last_app_id` und `_initialized` — der Zustand steht in der DB.

- [ ] **Step 1: Write the failing test**

`tests/plugins/test_steam_gaming_poller.py` **komplett ersetzen** durch:

```python
"""Steam session poller: detect -> book -> announce (Teilprojekt 3+4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.steam_session import SteamSession
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


def _poller(db_session, app_ids, times):
    """A poller whose detector and clock walk the given sequences."""
    detected = iter(app_ids)
    clock_values = iter(times)
    emit = AsyncMock()
    poller = SteamSessionPoller(
        detect=MagicMock(side_effect=lambda *a, **k: next(detected)),
        resolve=MagicMock(side_effect=lambda app_id: f"Game {app_id}"),
        emit=emit,
        session_factory=lambda: db_session,
        clock=lambda: next(clock_values),
    )
    return poller, emit


class TestTick:
    async def test_start_is_booked_and_announced(self, db_session):
        poller, emit = _poller(db_session, ["111"], [T0])

        await poller.tick()

        assert db_session.query(SteamSession).count() == 1
        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", ledger.EVENT_STARTED)
        assert kwargs["entity_id"] == "111"
        assert kwargs["game"] == "Game 111"

    async def test_end_is_announced_on_the_game_that_ended(self, db_session):
        poller, emit = _poller(
            db_session, ["111", None], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        emit.assert_awaited_once()
        args, kwargs = emit.await_args
        assert args[:2] == ("steam_gaming", ledger.EVENT_ENDED)
        assert kwargs["entity_id"] == "111"

    async def test_direct_switch_announces_both_edges(self, db_session):
        """#462 - TP3 swallowed this."""
        poller, emit = _poller(
            db_session, ["111", "222"], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        assert emit.await_count == 2
        first, second = emit.await_args_list
        assert first.args[:2] == ("steam_gaming", ledger.EVENT_ENDED)
        assert first.kwargs["entity_id"] == "111"
        assert second.args[:2] == ("steam_gaming", ledger.EVENT_STARTED)
        assert second.kwargs["entity_id"] == "222"

    async def test_same_game_announces_nothing(self, db_session):
        poller, emit = _poller(
            db_session, ["111", "111"], [T0, T0 + timedelta(seconds=30)]
        )
        await poller.tick()
        emit.reset_mock()

        await poller.tick()

        emit.assert_not_awaited()

    async def test_a_restart_mid_session_announces_nothing(self, db_session):
        """The DB holds the state, so a fresh poller object just picks it up."""
        first, _ = _poller(db_session, ["111"], [T0])
        await first.tick()

        second, emit = _poller(db_session, ["111"], [T0 + timedelta(minutes=5)])
        await second.tick()

        emit.assert_not_awaited()
        assert db_session.query(SteamSession).count() == 1


class TestRetentionSchedule:
    async def test_cleanup_runs_on_the_first_tick(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        poller, _ = _poller(db_session, [None], [T0])

        await poller.tick()

        assert calls == [T0]

    async def test_cleanup_does_not_run_again_the_next_tick(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        poller, _ = _poller(db_session, [None, None], [T0, T0 + timedelta(hours=1)])

        await poller.tick()
        await poller.tick()

        assert calls == [T0]

    async def test_cleanup_runs_again_after_a_day(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ledger, "cleanup_old_sessions", lambda db, *, now: calls.append(now) or 0
        )
        later = T0 + timedelta(hours=25)
        poller, _ = _poller(db_session, [None, None], [T0, later])

        await poller.tick()
        await poller.tick()

        assert calls == [T0, later]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_poller.py -v --no-cov`
Expected: FAIL — `TypeError: SteamSessionPoller.__init__() got an unexpected keyword argument 'session_factory'`

- [ ] **Step 3: Rewrite the poller**

`app/plugins/installed/steam_gaming/poller.py` **komplett ersetzen** durch:

```python
"""Steam session poller: detect, book, announce (Teilprojekt 3+4/4).

Runs as a plugin background task, which thanks to #448 executes primary-only -
so exactly one instance polls. It keeps no state of its own: the open session
in the database is the state (see ledger.py), which is what makes a restart
mid-session harmless.

Order matters: book and commit first, announce afterwards. A failed push must
never roll back a booking.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name
from app.services.notifications.plugin_events import emit_plugin_event

logger = logging.getLogger(__name__)

_PLUGIN = "steam_gaming"
_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60.0


def _utc_now() -> datetime:
    """Indirection so tests can control the clock."""
    return datetime.now(timezone.utc)


class SteamSessionPoller:
    """Books what the detector sees and announces the edges worth announcing."""

    def __init__(
        self,
        detect: Callable[[], Optional[str]] = detect_running_app_id,
        resolve: Callable[[str], Optional[str]] = resolve_name,
        emit=emit_plugin_event,
        session_factory: Callable[[], Session] = SessionLocal,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._detect = detect
        self._resolve = resolve
        self._emit = emit
        self._session_factory = session_factory
        self._clock = clock
        self._last_cleanup: Optional[datetime] = None

    async def tick(self) -> None:
        """One poll: detect, book, then deliver whatever the ledger returned."""
        # Blocking /proc + manifest + DB work stays off the event loop.
        app_id = await asyncio.to_thread(self._detect)
        now = self._clock()
        events = await asyncio.to_thread(self._book, app_id, now)

        for event in events:
            await self._emit(
                _PLUGIN, event.event_id, entity_id=event.app_id, game=event.game
            )

    def _book(self, app_id: Optional[str], now: datetime) -> List[ledger.LedgerEvent]:
        """Blocking: owns the database session for this tick."""
        db = self._session_factory()
        try:
            events = ledger.record(db, app_id, now=now, resolve_name=self._resolve)
            if self._due_for_cleanup(now):
                ledger.cleanup_old_sessions(db, now=now)
                self._last_cleanup = now
            return events
        finally:
            db.close()

    def _due_for_cleanup(self, now: datetime) -> bool:
        """Once a day. The marker lives in the process - a restart costs at most
        one extra DELETE that finds nothing."""
        if self._last_cleanup is None:
            return True
        return (now - self._last_cleanup).total_seconds() >= _CLEANUP_INTERVAL_SECONDS
```

**Kein try/except um `self._detect()`:** Die Spec verlangt „Detector wirft → Tick loggt und endet". Das erledigt bereits der Core-Runner — `PluginManager._run_periodic_task()` (`app/plugins/manager.py:648-668`) fängt jede Exception pro Tick, loggt sie mit `logger.exception` und läuft weiter. Ein zweites `try` im Poller wäre toter Code, der nur die Herkunft des Fehlers verschleiert.

**Wichtig:** Die Tests reichen `session_factory=lambda: db_session` herein — `db.close()` würde die Fixture-Session schließen. Damit die Test-Session das überlebt, ist `_book()` so geschrieben, dass es nur `close()` aufruft; die `db_session`-Fixture nutzt `StaticPool` auf einer In-Memory-DB, deren Verbindung dadurch nicht verworfen wird. Sollte ein Test dennoch an einer geschlossenen Session scheitern, ist die Ursache dort und nicht im Produktionscode.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_poller.py -v --no-cov`
Expected: PASS (8 passed)

- [ ] **Step 5: Run the whole steam suite**

Run: `python -m pytest tests/plugins/ -k steam -v --no-cov`
Expected: PASS — alle Dateien `test_steam_gaming_*` grün (Detector, Names, Launcher, Plugin, Poller, Ledger)

- [ ] **Step 6: Commit**

```bash
git add app/plugins/installed/steam_gaming/poller.py tests/plugins/test_steam_gaming_poller.py
git commit -m "refactor(steam-gaming): poller drops its in-memory state for the ledger" -m "No _last_app_id, no _initialized flag: the open DB session is the state, so a restart mid-session is silent instead of a false alarm." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `admin_only` für Panels — Route **und** WebSocket-Bridge

**Files:**
- Modify: `app/plugins/base.py` (`DashboardPanelSpec`)
- Modify: `app/api/routes/dashboard.py`
- Modify: `app/services/websocket_manager.py` (`broadcast_typed`)
- Modify: `app/services/dashboard_panel_bridge.py`
- Test: `tests/plugins/test_dashboard_panel.py`

**Interfaces:**
- Produces:
  - `DashboardPanelSpec.admin_only: bool = False`
  - `WebSocketManager.broadcast_typed(msg_type: str, payload: dict, admins_only: bool = False) -> int`
  - `_build_panel_update()` liefert zusätzlich den Schlüssel `"admin_only": bool`

**Warum beides:** Das Gate nur in der Route wäre wirkungslos — `dashboard_panel_ws_bridge()` schiebt dieselben Daten per `broadcast_typed()` an **alle** verbundenen Clients.

- [ ] **Step 1: Write the failing test**

An `tests/plugins/test_dashboard_panel.py` anhängen:

```python
class TestAdminOnlyPanels:
    def test_spec_defaults_to_public(self):
        spec = DashboardPanelSpec(panel_type="status", title="Any")
        assert spec.admin_only is False

    def test_spec_can_be_admin_only(self):
        spec = DashboardPanelSpec(panel_type="status", title="Any", admin_only=True)
        assert spec.admin_only is True

    @pytest.mark.asyncio
    async def test_route_hides_an_admin_only_panel_from_a_normal_user(self):
        mock_record = MagicMock()
        mock_record.name = "steam_gaming"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = DashboardPanelSpec(
            panel_type="status", title="Steam Gaming", admin_only=True,
        )
        mock_plugin.get_dashboard_data = AsyncMock(return_value={"items": []})
        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch("app.api.routes.dashboard.user_limiter.enabled", False), patch(
            "app.api.routes.dashboard.PluginManager.get_instance", return_value=mock_pm
        ):
            result = await get_plugin_panel(
                request=MagicMock(),
                response=MagicMock(),
                db=mock_db,
                current_user=MagicMock(role="user"),
            )

        assert result is None
        mock_plugin.get_dashboard_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_serves_an_admin_only_panel_to_an_admin(self):
        mock_record = MagicMock()
        mock_record.name = "steam_gaming"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = DashboardPanelSpec(
            panel_type="status", title="Steam Gaming", admin_only=True,
        )
        mock_plugin.get_dashboard_data = AsyncMock(return_value={"items": []})
        mock_plugin.get_translations.return_value = None
        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch("app.api.routes.dashboard.user_limiter.enabled", False), patch(
            "app.api.routes.dashboard.PluginManager.get_instance", return_value=mock_pm
        ):
            result = await get_plugin_panel(
                request=MagicMock(),
                response=MagicMock(),
                db=mock_db,
                current_user=MagicMock(role="admin"),
            )

        assert result is not None
        assert result.plugin_name == "steam_gaming"


class TestAdminOnlyBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_typed_can_skip_non_admins(self):
        manager = WebSocketManager()
        admin_ws, user_ws = AsyncMock(), AsyncMock()
        await manager.connect(admin_ws, user_id=1, is_admin=True)
        await manager.connect(user_ws, user_id=2, is_admin=False)

        count = await manager.broadcast_typed(
            "dashboard_panel_update", {"data": {}}, admins_only=True
        )

        assert count == 1
        admin_ws.send_json.assert_called_once()
        user_ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_bridge_payload_carries_the_admin_only_flag(self):
        mock_record = MagicMock()
        mock_record.name = "steam_gaming"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = DashboardPanelSpec(
            panel_type="status", title="Steam Gaming", admin_only=True,
        )
        mock_plugin.get_dashboard_data = AsyncMock(return_value={"items": []})
        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch(
            "app.services.dashboard_panel_bridge.PluginManager.get_instance",
            return_value=mock_pm,
        ):
            payload = await _build_panel_update(mock_db)

        assert payload is not None
        assert payload["admin_only"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_dashboard_panel.py -k "AdminOnly" -v --no-cov`
Expected: FAIL — `ValidationError`/`AttributeError` für `admin_only` bzw. `TypeError: broadcast_typed() got an unexpected keyword argument 'admins_only'`

- [ ] **Step 3: Add the spec field**

In `app/plugins/base.py`, in `DashboardPanelSpec` nach dem `accent`-Feld ergänzen:

```python
    admin_only: bool = Field(
        default=False,
        description="Only serve this panel to privileged users",
    )
```

Und den Klassendocstring erweitern:

```python
class DashboardPanelSpec(BaseModel):
    """Specification for a plugin's Dashboard panel.

    ``admin_only`` is enforced by the core - in the REST route and in the
    WebSocket bridge - not by the plugin, so no plugin can get its own gate
    wrong. Same pattern as PluginNavItem.admin_only. (PluginMenuItem
    deliberately has no such field: an action executes something, a panel
    displays something.)
    """
```

- [ ] **Step 4: Gate the route**

In `app/api/routes/dashboard.py` den Import ergänzen:

```python
from app.services.permissions import is_privileged
```

und direkt nach dem bestehenden Block

```python
    spec = plugin.get_dashboard_panel()
    if spec is None:
        return None
```

einfügen:

```python
    if spec.admin_only and not is_privileged(current_user):
        # The game name in the Steam panel is information about the box owner -
        # same privacy call as the status pill. Enforced here so no plugin has
        # to implement its own gate.
        return None
```

- [ ] **Step 5: Add the admin-scoped broadcast**

In `app/services/websocket_manager.py` die Signatur von `broadcast_typed` ändern:

```python
    async def broadcast_typed(
        self, msg_type: str, payload: dict[str, Any], admins_only: bool = False
    ) -> int:
        """Broadcast a typed message to connected users.

        Unlike broadcast_to_all() which wraps in {"type": "notification"},
        this method sends {"type": msg_type, "payload": payload} directly.

        Args:
            msg_type: Message type string (e.g. "dashboard_panel_update").
            payload: Message payload dict.
            admins_only: Skip non-admin connections. Needed for payloads that a
                REST route would gate behind is_privileged() - without it the
                gate would be decorative.

        Returns:
            Number of connections the message was sent to.
        """
```

und in der inneren Schleife als erste Zeile einfügen:

```python
                for conn in connections:
                    if admins_only and not conn.is_admin:
                        continue
```

- [ ] **Step 6: Use it in the bridge**

In `app/services/dashboard_panel_bridge.py` das Rückgabe-Dict von `_build_panel_update()` erweitern:

```python
    return {
        "panel_type": spec.panel_type,
        "plugin_name": record.name,
        "admin_only": spec.admin_only,
        "data": data,
    }
```

und den Broadcast-Aufruf ersetzen:

```python
            ws = get_websocket_manager()
            if ws:
                # An admin_only panel must not reach every socket - the REST
                # gate would be decorative otherwise.
                await ws.broadcast_typed(
                    "dashboard_panel_update",
                    payload,
                    admins_only=bool(payload.get("admin_only")),
                )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_dashboard_panel.py -v --no-cov`
Expected: PASS — die neuen Klassen **und** alle bestehenden Tests der Datei

- [ ] **Step 8: Commit**

```bash
git add app/plugins/base.py app/api/routes/dashboard.py app/services/websocket_manager.py app/services/dashboard_panel_bridge.py tests/plugins/test_dashboard_panel.py
git commit -m "feat(plugins): admin_only dashboard panels, enforced by the core" -m "Gate lives in the REST route AND in the WS bridge: broadcast_typed() pushed panel data to every socket, so a route-only gate would have leaked the payload it was meant to protect." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Steam-Panel + gemeinsame Erkennungsquelle

**Files:**
- Create: `app/plugins/installed/steam_gaming/detection.py`
- Modify: `app/plugins/installed/steam_gaming/__init__.py`
- Modify: `app/plugins/installed/steam_gaming/poller.py` (Defaults auf `detection` umstellen)
- Test: `tests/plugins/test_steam_gaming_panel.py` (neu)

**Interfaces:**
- Consumes: `ledger.duration_seconds()`, `ledger.as_utc()` (Task 4), `SteamSession` (Task 1), `DashboardPanelSpec.admin_only` (Task 7)
- Produces:
  - `detection.current_app_id() -> Optional[str]`, `detection.resolve_game_name(app_id: str) -> Optional[str]`, `detection.DEV_APP_ID = "0"`
  - `SteamGamingPlugin.get_dashboard_panel()`, `SteamGamingPlugin.get_dashboard_data(db)`

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/plugins/test_steam_gaming_panel.py`:

```python
"""Steam gaming dashboard panel: spec, formatting, empty state (TP 4/4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.steam_session import SteamSession
from app.plugins.installed.steam_gaming import SteamGamingPlugin

T0 = datetime(2026, 7, 24, 20, 0, 0, tzinfo=timezone.utc)


class TestPanelSpec:
    def test_panel_is_an_admin_only_status_panel(self):
        spec = SteamGamingPlugin().get_dashboard_panel()

        assert spec is not None
        assert spec.panel_type == "status"
        assert spec.title == "Steam Gaming"
        assert spec.icon == "gamepad-2"
        assert spec.admin_only is True


class TestPanelData:
    async def test_no_sessions_means_no_panel(self, db_session):
        assert await SteamGamingPlugin().get_dashboard_data(db_session) is None

    async def test_running_session_shows_bare_duration_and_ok_tone(self, db_session):
        db_session.add(SteamSession(app_id="111", game_name="Metro", started_at=T0, last_seen_at=T0))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        item = data["items"][0]
        assert item["label"] == "Metro"
        assert item["tone"] == "ok"
        assert item["value"].endswith("m")
        assert "·" not in item["value"]

    async def test_finished_session_shows_date_and_duration(self, db_session):
        db_session.add(SteamSession(
            app_id="222",
            game_name="Cyberpunk",
            started_at=T0,
            last_seen_at=T0 + timedelta(hours=3, minutes=4),
            ended_at=T0 + timedelta(hours=3, minutes=4),
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        item = data["items"][0]
        assert item["tone"] == "neutral"
        assert item["value"] == "24.07. · 3h 04m"

    async def test_unresolved_name_falls_back_to_the_app_id(self, db_session):
        db_session.add(SteamSession(
            app_id="999", game_name=None, started_at=T0, last_seen_at=T0, ended_at=T0,
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert data["items"][0]["label"] == "AppID 999"

    async def test_at_most_five_rows_newest_first(self, db_session):
        for index in range(7):
            start = T0 + timedelta(hours=index)
            db_session.add(SteamSession(
                app_id=str(index), game_name=f"Game {index}",
                started_at=start, last_seen_at=start, ended_at=start,
            ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        labels = [item["label"] for item in data["items"]]
        assert labels == ["Game 6", "Game 5", "Game 4", "Game 3", "Game 2"]

    async def test_sub_hour_duration_has_no_hour_part(self, db_session):
        db_session.add(SteamSession(
            app_id="111", game_name="Metro", started_at=T0,
            last_seen_at=T0 + timedelta(minutes=12), ended_at=T0 + timedelta(minutes=12),
        ))
        db_session.commit()

        data = await SteamGamingPlugin().get_dashboard_data(db_session)

        assert data["items"][0]["value"] == "24.07. · 12m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/test_steam_gaming_panel.py -v --no-cov`
Expected: FAIL — `assert None is not None` (das Plugin hat noch kein Panel)

- [ ] **Step 3: Create the shared detection module**

Neue Datei `app/plugins/installed/steam_gaming/detection.py`:

```python
"""One source of truth for "is a game running" - pill, ledger and panel share it.

The dev-mode stand-in lives HERE and not in detector.py/names.py on purpose:
the test suite runs with NAS_MODE=dev (tests/conftest.py), so a dev branch
inside the pure /proc scan would make the detector tests assert the mock
instead of the real behaviour.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name

# There is no /proc on a Windows dev box, so nothing would ever be detected and
# neither the pill nor the panel would have anything to show locally.
DEV_APP_ID = "0"
DEV_GAME_NAME = "Dev Mode Game"


def current_app_id() -> Optional[str]:
    """AppID of the running game, or None. Blocking - call via asyncio.to_thread."""
    app_id = detect_running_app_id()
    if app_id is None and settings.is_dev_mode:
        return DEV_APP_ID
    return app_id


def resolve_game_name(app_id: str) -> Optional[str]:
    """Display name for *app_id*, or None. Blocking - call via asyncio.to_thread."""
    if settings.is_dev_mode and app_id == DEV_APP_ID:
        return DEV_GAME_NAME
    return resolve_name(app_id)
```

- [ ] **Step 4: Point the poller at it**

In `app/plugins/installed/steam_gaming/poller.py` die beiden Importe

```python
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name
```

ersetzen durch

```python
from app.plugins.installed.steam_gaming.detection import current_app_id, resolve_game_name
```

und die Defaults in `__init__` anpassen:

```python
        detect: Callable[[], Optional[str]] = current_app_id,
        resolve: Callable[[str], Optional[str]] = resolve_game_name,
```

- [ ] **Step 5: Rewrite the plugin's detection helper and add the panel**

In `app/plugins/installed/steam_gaming/__init__.py`:

(a) Importblock — `detector`/`names`-Importe ersetzen und die neuen ergänzen:

```python
from datetime import datetime, timezone

from app.plugins.base import (
    BackgroundTaskSpec,
    DashboardPanelSpec,
    MenuActionResult,
    PluginBase,
    PluginEventSpec,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
    StatusPillSpec,
)
from app.models.steam_session import SteamSession
from app.plugins.dashboard_panel import StatusItem, StatusPanelData
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.detection import current_app_id, resolve_game_name
from app.plugins.installed.steam_gaming.launcher import open_big_picture
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller
from app.services.power.desktop import get_desktop_service
```

(b) `_current_game()` ersetzen durch:

```python
def _current_game() -> Optional[tuple[str, Optional[str]]]:
    """``(app_id, name)`` of the running game, or None. Cached for a few seconds."""
    now = _monotonic()
    checked_at = _CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _CACHE_TTL_SECONDS:
        return _CACHE.get("game")  # type: ignore[return-value]

    app_id = current_app_id()
    game = (app_id, resolve_game_name(app_id)) if app_id else None
    _CACHE["checked_at"] = now
    _CACHE["game"] = game
    return game
```

(c) In `collect_status_pill()` den Dev-Zweig entfernen — aus

```python
        game = await asyncio.to_thread(_current_game)
        if game is None:
            if settings.is_dev_mode:
                # No /proc on a Windows dev box — render something anyway.
                game = ("0", "Dev Mode Game")
            else:
                return None
```

wird

```python
        # The dev-mode stand-in now lives in detection.py, so pill, ledger and
        # panel agree on what is running.
        game = await asyncio.to_thread(_current_game)
        if game is None:
            return None
```

**Und die Zeile `from app.core.config import settings` aus dem Importblock entfernen** — nach dem Wegfall des Dev-Zweigs ist `settings` in dieser Datei unbenutzt und der `eslint`-Äquivalent auf Python-Seite (ruff F401) würde anschlagen.

Prüfen: `python -c "import re; src=open('app/plugins/installed/steam_gaming/__init__.py',encoding='utf-8').read(); print(src.count('settings'))"` → Expected: `0`

(d) Panel-Konstanten neben die vorhandenen setzen:

```python
_PANEL_ROWS = 5
```

(e) Formatierung und Panel-Methoden ergänzen (Modul-Ebene für die Helfer, Methoden in der Klasse nach `run_menu_action`):

```python
def _format_duration(seconds: float) -> str:
    """``3h 04m`` / ``12m`` - digits only, so no string needs translating."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _panel_value(row: SteamSession, now: datetime) -> str:
    """Running sessions show the bare duration; finished ones prepend the date."""
    duration = _format_duration(ledger.duration_seconds(row, now))
    if row.ended_at is None:
        return duration
    return f"{ledger.as_utc(row.started_at):%d.%m.} · {duration}"
```

```python
    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        return DashboardPanelSpec(
            panel_type="status",
            title="Steam Gaming",
            icon="gamepad-2",
            accent="from-indigo-500 to-purple-500",
            # The game name is information about the box owner - same call as
            # the pill's default visibility in Teilprojekt 1.
            admin_only=True,
        )

    async def get_dashboard_data(self, db: Session) -> Optional[dict]:
        """The five newest sessions; the running one sorts to the top.

        Returns None when nothing was ever recorded - a placeholder line would
        be a translatable string, and StatusItem has no key fields.
        """
        rows = (
            db.query(SteamSession)
            .order_by(SteamSession.started_at.desc())
            .limit(_PANEL_ROWS)
            .all()
        )
        if not rows:
            return None

        now = datetime.now(timezone.utc)
        items = [
            StatusItem(
                label=row.game_name or f"AppID {row.app_id}",
                value=_panel_value(row, now),
                tone="ok" if row.ended_at is None else "neutral",
            )
            for row in rows
        ]
        return StatusPanelData(items=items).model_dump()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/plugins/test_steam_gaming_panel.py -v --no-cov`
Expected: PASS (7 passed)

- [ ] **Step 7: Verify nothing else in the plugin broke**

Run: `python -m pytest tests/plugins/ -k steam -v --no-cov`
Expected: PASS — insbesondere `test_steam_gaming_plugin.py` (Pill-Collector, jetzt ohne eigenen Dev-Zweig)

- [ ] **Step 8: Commit**

```bash
git add app/plugins/installed/steam_gaming/ tests/plugins/test_steam_gaming_panel.py
git commit -m "feat(steam-gaming): admin-only dashboard panel with the last five sessions" -m "detection.py becomes the single source pill, ledger and panel share, including the dev-mode stand-in that used to live in the pill collector only." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Doku, Gesamtsuite, Handprobe

**Files:**
- Modify: `app/plugins/CLAUDE.md`
- Modify: `app/models/CLAUDE.md`

- [ ] **Step 1: Document the panel extension point**

In `app/plugins/CLAUDE.md`, im Abschnitt „Creating a Plugin", Punkt 5 (`get_dashboard_panel()`) um diesen Absatz ergänzen:

```markdown
   `DashboardPanelSpec.admin_only=True` beschränkt ein Panel auf privilegierte
   Nutzer. Durchgesetzt wird das **im Core** an zwei Stellen, nicht im Plugin:
   in `api/routes/dashboard.py` (`is_privileged`) und in
   `services/dashboard_panel_bridge.py`, das seinen WebSocket-Broadcast dann
   mit `broadcast_typed(..., admins_only=True)` fährt. Beides ist nötig — der
   Bridge schiebt dieselben Daten unabhängig von der Route an verbundene
   Clients. Panel-Icons werden im Frontend dynamisch aus lucide aufgelöst
   (kebab-case → PascalCase, Fallback `Plug`), ein neues Icon braucht also
   keine Core-Änderung.
```

- [ ] **Step 2: Fix the documented drift**

In `app/plugins/CLAUDE.md` die Passage, die behauptet, der Dashboard-Panel-Endpunkt sei **nicht** an `reconciled_plugin_state` gehängt, korrigieren. Aus

```markdown
   The Dashboard plugin panel (`GET /api/dashboard/plugin-panel`) is **not** one
   of them — it reads `PluginManager.get_plugin()` directly with no DB fallback,
   so it only catches up once some other reconciled route has run on the same
   worker.
```

wird

```markdown
   The Dashboard plugin panel (`GET /api/dashboard/plugin-panel`) is one of them
   as well (`api/routes/dashboard.py`), so it catches up on the same request
   like the other five.
```

**Vorher verifizieren** (die Doku könnte inzwischen wieder stimmen):
Run: `python -c "import re; src=open('app/api/routes/dashboard.py',encoding='utf-8').read(); print('reconciled_plugin_state' in src)"`
Expected: `True` — nur dann diesen Schritt ausführen.

- [ ] **Step 3: Register the model in the models doc**

In `app/models/CLAUDE.md`, Zeile der Gruppe **Plugins & Integrations**, `steam_session.py` ergänzen:

```markdown
**Plugins & Integrations**: `plugin.py`, `plugin_storage.py`, `steam_session.py`, `pihole.py`, `dns_queries.py`, `ad_discovery.py`, `cloud.py`, `cloud_export.py`, `benchmark.py`, `energy_price_config.py`
```

- [ ] **Step 4: Run the full plugin and notification suites**

Run: `python -m pytest tests/plugins/ -v --no-cov`
Expected: PASS — keine Regression in Manager, Sandbox, Tapo, Smart-Device

Run: `python -m pytest tests/ -k "notification or dashboard or websocket" -v --no-cov`
Expected: PASS

- [ ] **Step 5: Verify the migration once more against a fresh database**

Run: `python -c "import os; os.remove('baluhost.db') if os.path.exists('baluhost.db') else None"`

**Achtung:** Das löscht die lokale Dev-DB. Wer sie behalten will, vorher kopieren:
`python -c "import shutil,os; shutil.copy('baluhost.db','baluhost.db.bak') if os.path.exists('baluhost.db') else None"`

Run: `python -m alembic upgrade head`
Expected: läuft von der ersten Revision bis zur neuen durch, ohne Fehler

Run: `python -c "import sqlite3; print([r[0] for r in sqlite3.connect('baluhost.db').execute(\"select name from sqlite_master where type='table' and name='steam_sessions'\")])"`
Expected: `['steam_sessions']`

- [ ] **Step 6: PostgreSQL check (Handarbeit, nicht überspringen)**

CI hat keinen Alembic-Smoke-Test (#450). Gegen eine PostgreSQL-Instanz — lokal oder auf der Box vor dem Merge:

Run: `DATABASE_URL=postgresql://…/baluhost_test python -m alembic upgrade head`
Expected: `Running upgrade 71fe791d28d6 -> <rev>, add steam_sessions table`

Run: `DATABASE_URL=postgresql://…/baluhost_test python -m alembic downgrade -1`
Expected: sauberes `Running downgrade …`, danach existiert `steam_sessions` nicht mehr

Ist keine PostgreSQL-Instanz verfügbar: **im PR ausdrücklich vermerken, dass dieser Schritt offen ist** — nicht stillschweigend überspringen.

- [ ] **Step 7: Commit**

```bash
git add app/plugins/CLAUDE.md app/models/CLAUDE.md
git commit -m "docs(plugins): document admin_only panels and fix the reconcile drift" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Abnahme

Nach Task 9 ist erfüllt:

| Spec-Anforderung | Task |
|---|---|
| Tabelle `steam_sessions` + Migration auf dem echten Head | 1 |
| Flankentabelle (5 Zeilen), Spielwechsel meldet Ende + Start (#462) | 2 |
| Lückenregel 1 — `ended_at = now` vs. `last_seen_at` | 3 |
| Lückenregel 2 — nach einer Lücke nur buchen, nie melden | 3 |
| Lückenregel 3 — Adopt-Fenster 10 min, darüber splitten | 3 |
| Mehrere offene Sessions aufräumen | 4 |
| `game_name` nachtragen | 4 |
| Dauer abgeleitet, bei Uhr-Rücksprung auf 0 geklemmt | 4 |
| Retention 365 Tage, offene Session unangetastet | 5 |
| Poller ohne Eigenzustand, erst buchen+committen, dann melden | 6 |
| Retention einmal je 24 h | 6 |
| `DashboardPanelSpec.admin_only`, Core setzt durch | 7 |
| WS-Bridge leakt admin-only-Panels nicht | 7 (über die Spec hinaus) |
| Panel: `status`, 5 Zeilen, `tone=ok` für laufend, `TT.MM. · Dauer` | 8 |
| Leerer Zustand → kein Panel | 8 |
| Dev-Mock als gemeinsame Quelle | 8 |
| Doku + Doku-Drift | 9 |

**Bewusst nicht im Plan** (Nicht-Ziele der Spec): Big-Picture-Erkennung, Auto-Displays-aus, eigene Steam-Seite, per-Nutzer-Kategorie-Preference, Aggregate über Spielzeit.
