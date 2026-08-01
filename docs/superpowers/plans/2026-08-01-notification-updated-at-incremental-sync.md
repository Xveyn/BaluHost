# Notification `updated_at` + inkrementelle Abfrage — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notifications bekommen einen monotonen Änderungs-Zeitstempel und eine `updated_after`-Abfrage, damit die Android-App (BaluApp) den Bestand inkrementell und konfliktauflösbar abgleichen kann.

**Architecture:** Eine Spalte `updated_at` auf `notifications` mit `onupdate=func.now()` — SQLAlchemy stempelt damit sowohl ORM-Zuweisungen (`dismiss`, `restore`, `mark_as_read`, `snooze`) als auch die beiden Bulk-Updates (`mark_all_as_read`, `dismiss_all`); beides wurde gegen SQLite nachgemessen. Der Stempel wandert in `to_dict()` (WebSocket) und `NotificationResponse` (REST) und wird über einen neuen `updated_after`-Filter auf den zwei Listen-Endpunkten abfragbar.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, Pydantic v2, pytest.

## Global Constraints

- Umsetzt werden **Punkte 1–3** aus [#504](https://github.com/Xveyn/BaluHost/issues/504). Punkt 4 (Grabsteine) wird in Task 5 **dokumentiert entschieden**, nicht gebaut.
- **`is_read` bekommt keinen eigenen Zeitstempel.** Das Feld ist monoton (kein Endpunkt setzt auf ungelesen zurück, im gesamten Backend gibt es keine Zuweisung `is_read = False`) — nichts hinzufügen, was nicht gebraucht wird.
- **Bestehendes Verhalten bleibt unangetastet:** Sortierung der Listen bleibt `created_at DESC`, bestehende Filter (`unread_only`, `category`, `notification_type`, `created_after`, `created_before`) bleiben unverändert.
- **Alembic:** Die neue Migration setzt auf `down_revision = "dcabe4cc2ebc"` (aktueller `alembic heads` am 2026-08-01). Niemals auf den Stand der lokalen Dev-DB raten — mehrere Heads brechen den Prod-Deploy (#123 → #124).
- **Zeitzonen:** Spalte ist `DateTime(timezone=True)`. psycopg2 liefert *aware*, SQLite (Dev/Test) *naive* — Tests müssen mit beidem umgehen, Vergleiche nie auf `tzinfo` verlassen (#470).
- **Keine `time.sleep()`-Trenner in Tests.** Zeitabhaengige Faelle werden durch explizites Ruecksetzen des Stempels entschieden, nicht durch Warten - Wallclock-Trenner sind als Determinismus-Risiko gefuehrt (TQ5/#362) und koennen "bewegt" und "nicht bewegt" bei Sekundenaufloesung ohnehin nicht unterscheiden.
- **Coverage-Gate:** `--cov-fail-under=65` auf `app/`. Neue Zweige brauchen Tests, sonst fällt CI.
- Kommentare und Docstrings auf **Englisch** (Backend-Konvention), Plan und PR-Text auf Deutsch.

---

## File Structure

| Datei | Rolle |
|---|---|
| `backend/app/models/notification.py` | Spalte `updated_at` + Ausgabe in `to_dict()` (WebSocket-Nutzlast) |
| `backend/alembic/versions/<rev>_add_notification_updated_at.py` | Spalte anlegen, Index, **Backfill** aus `COALESCE(deleted_at, created_at)` |
| `backend/app/schemas/notification.py` | `updated_at` in `NotificationResponse` + `from_db()` |
| `backend/app/services/notifications/service.py` | `updated_after`-Filter in `get_user_notifications` und `count_user_notifications` |
| `backend/app/api/routes/notifications.py` | `updated_after`-Query auf `GET /api/notifications` und `GET /api/notifications/trash` |
| `backend/tests/migrations/test_notification_updated_at.py` | neu — Spalte schreibbar, Default gesetzt |
| `backend/tests/services/test_notification_service.py` | ergänzt — Stempel-Semantik + Filter |
| `backend/tests/test_notifications_routes.py` | ergänzt — Query-Parameter End-to-End |
| `docs/api/NOTIFICATION_SYNC.md` | neu — der Sync-Kontrakt inkl. dokumentierter Grabstein-Entscheidung |

---

### Task 1: Spalte `updated_at` + Migration

**Files:**
- Modify: `backend/app/models/notification.py:74-76` (nach `snoozed_until`), `:84-100` (`to_dict`)
- Create: `backend/alembic/versions/<rev>_add_notification_updated_at.py`
- Test: `backend/tests/migrations/test_notification_updated_at.py`

**Interfaces:**
- Produces: `Notification.updated_at: Mapped[datetime]`, im `to_dict()` unter dem Schlüssel `"updated_at"` als ISO-String oder `None`.

- [ ] **Step 1: Write the failing test**

Neue Datei `backend/tests/migrations/test_notification_updated_at.py`:

```python
"""The updated_at stamp exists, is written on creation, and moves on change."""
from datetime import datetime, timezone

from app.models.notification import Notification


def _make(db_session, **over) -> Notification:
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Probe",
        message="Body",
        **over,
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    return n


def test_new_notification_gets_a_stamp(db_session):
    n = _make(db_session)

    assert n.updated_at is not None


def test_stamp_is_exposed_in_to_dict(db_session):
    """The WebSocket payload carries the same stamp as the REST response."""
    n = _make(db_session)

    payload = n.to_dict()

    assert "updated_at" in payload
    assert payload["updated_at"] is not None


def test_stamp_survives_an_explicit_value(db_session):
    """A caller-supplied value round-trips — the migration backfill relies on it."""
    fixed = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    n = _make(db_session, updated_at=fixed)

    assert n.updated_at.year == 2026
    assert n.updated_at.month == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/migrations/test_notification_updated_at.py -q --no-cov`
Expected: FAIL — `TypeError: 'updated_at' is an invalid keyword argument for Notification`

- [ ] **Step 3: Add the column to the model**

In `backend/app/models/notification.py` direkt nach dem `snoozed_until`-Block (Zeile 74-76) einfügen:

```python
    # Monotonic write stamp for incremental sync (#504). SQLAlchemy fills it on
    # INSERT via server_default and on every UPDATE via onupdate - measured to
    # fire for bulk Query.update() as well, which is what mark_all_as_read and
    # dismiss_all use. A no-op call writes nothing and therefore does NOT bump
    # the stamp, which is what keeps an incremental fetch small.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
```

- [ ] **Step 4: Expose it in `to_dict()`**

In `backend/app/models/notification.py` in `to_dict()` nach der `created_at`-Zeile (Zeile 88) einfügen:

```python
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/migrations/test_notification_updated_at.py -q --no-cov`
Expected: PASS (3 Tests)

- [ ] **Step 6: Create the migration**

Run: `cd backend && python -m alembic revision -m "add notification updated_at"`

Die erzeugte Datei so füllen (Revision-ID aus dem Dateinamen übernehmen, `down_revision` **exakt** wie unten):

```python
"""add notification updated_at

Revision ID: <aus dem Dateinamen>
Revises: dcabe4cc2ebc
Create Date: <generiert>

Backfills from COALESCE(deleted_at, created_at) rather than letting the
server_default stamp every existing row with "now". A fresh now() would claim
a change that never happened and make the first incremental sync after deploy
return the entire history.
"""
from alembic import op
import sqlalchemy as sa

revision = "<aus dem Dateinamen>"
down_revision = "dcabe4cc2ebc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE notifications SET updated_at = COALESCE(deleted_at, created_at)"
    )
    op.alter_column(
        "notifications",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    op.create_index(
        "ix_notifications_updated_at", "notifications", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_updated_at", table_name="notifications")
    op.drop_column("notifications", "updated_at")
```

- [ ] **Step 7: Verify the migration chain has exactly one head**

Run: `cd backend && python -m alembic heads`
Expected: genau **eine** Zeile, die auf die neue Revision zeigt (`... (head)`). Mehr als eine Zeile = falsches `down_revision`, sofort korrigieren.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/notification.py backend/alembic/versions/ backend/tests/migrations/test_notification_updated_at.py
git commit -m "feat(notifications): add updated_at write stamp (#504)"
```

---

### Task 2: `updated_at` in der REST-Antwort

**Files:**
- Modify: `backend/app/schemas/notification.py:70` (Felder), `:108-123` (`from_db`)
- Test: `backend/tests/services/test_notification_service.py` (anhängen)

**Interfaces:**
- Consumes: `Notification.updated_at` aus Task 1.
- Produces: `NotificationResponse.updated_at: datetime` — nicht optional, die Spalte ist `nullable=False`.

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_notification_service.py` anhängen:

```python
class TestUpdatedAtInResponse:
    """The stamp has to reach the client, or the sync cannot use it (#504)."""

    def test_response_carries_the_stamp(self, db_session):
        from app.models.notification import Notification
        from app.schemas.notification import NotificationResponse

        n = Notification(
            user_id=None, category="system", notification_type="info",
            title="T", message="M",
        )
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)

        response = NotificationResponse.from_db(n)

        assert response.updated_at is not None
        assert response.updated_at == n.updated_at
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -q --no-cov -k UpdatedAtInResponse`
Expected: FAIL — `AttributeError: 'NotificationResponse' object has no attribute 'updated_at'`

- [ ] **Step 3: Add the field**

In `backend/app/schemas/notification.py` direkt nach `created_at: datetime` (Zeile 70):

```python
    updated_at: datetime = Field(
        description="Monotonic write stamp; moves on every state change (#504)"
    )
```

- [ ] **Step 4: Map it in `from_db`**

In `backend/app/schemas/notification.py` in `from_db()` nach `created_at=notification.created_at,` (Zeile 110):

```python
            updated_at=notification.updated_at,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -q --no-cov -k UpdatedAtInResponse`
Expected: PASS

- [ ] **Step 6: Run the whole notification suite for regressions**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py tests/test_notifications_routes.py -q --no-cov`
Expected: PASS — schlägt hier etwas fehl, baut ein Test eine `NotificationResponse` von Hand und braucht das neue Pflichtfeld.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/notification.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): expose updated_at in the API response (#504)"
```

---

### Task 3: Stempel-Semantik absichern

**Files:**
- Test: `backend/tests/services/test_notification_service.py` (anhängen)

**Interfaces:**
- Consumes: `NotificationService.mark_all_as_read`, `.dismiss_all`, `.dismiss`, `.restore`, `.mark_as_read`.
- Produces: nichts — reine Regressionswächter für den Sync-Kontrakt.

Diese Task hat **keine Implementierung**. Sie hält die zwei Eigenschaften fest, auf denen der Client-Abgleich ruht und die man versehentlich kaputtmachen kann.

- [ ] **Step 1: Write the tests**

An `backend/tests/services/test_notification_service.py` anhängen:

```python
class TestUpdatedAtSemantics:
    """Two properties the incremental sync depends on (#504).

    No sleeps: the stamp is backdated explicitly before each action, so
    "moved" and "did not move" are decidable regardless of clock resolution.
    Wall-clock separators are a determinism risk (TQ5/#362) and cannot even
    tell the two outcomes apart when a write lands in the same second.
    """

    OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def _make(cls, db_session, **over):
        """A notification whose stamp is old enough to be unmistakable."""
        from app.models.notification import Notification
        n = Notification(
            user_id=1, category="system", notification_type="info",
            title="T", message="M", **over,
        )
        db_session.add(n)
        db_session.commit()
        # Backdate in a separate statement so the starting point is explicit.
        db_session.query(Notification).filter_by(id=n.id).update(
            {"updated_at": cls.OLD}, synchronize_session=False
        )
        db_session.commit()
        db_session.expire_all()
        return db_session.get(Notification, n.id)

    @staticmethod
    def _stamp(db_session, row_id):
        from app.models.notification import Notification
        db_session.expire_all()
        return db_session.get(Notification, row_id).updated_at

    @staticmethod
    def _is_backdated(stamp) -> bool:
        """Comparison that survives naive (SQLite) and aware (psycopg2) values."""
        return stamp.year == 2020

    def test_bulk_dismiss_all_stamps_every_row(self, db_session):
        """dismiss_all writes via Query.update(); onupdate must still fire, or
        a mass action would be invisible to an incremental fetch."""
        from app.services.notifications.service import NotificationService

        a = self._make(db_session)
        b = self._make(db_session)

        NotificationService().dismiss_all(db_session, user_id=1)

        assert not self._is_backdated(self._stamp(db_session, a.id))
        assert not self._is_backdated(self._stamp(db_session, b.id))

    def test_bulk_mark_all_as_read_stamps_every_row(self, db_session):
        from app.services.notifications.service import NotificationService

        a = self._make(db_session)

        NotificationService().mark_all_as_read(db_session, user_id=1)

        assert not self._is_backdated(self._stamp(db_session, a.id))

    def test_a_no_op_dismiss_does_not_move_the_stamp(self, db_session):
        """Dismissing an already-trashed row changes nothing - stamping it
        would drag the row into every later incremental fetch."""
        from app.services.notifications.service import NotificationService

        n = self._make(db_session, deleted_at=datetime.now(timezone.utc))

        NotificationService().dismiss(db_session, n.id, user_id=1)

        assert self._is_backdated(self._stamp(db_session, n.id))

    def test_a_no_op_restore_does_not_move_the_stamp(self, db_session):
        from app.services.notifications.service import NotificationService

        n = self._make(db_session)  # already active

        NotificationService().restore(db_session, n.id, user_id=1)

        assert self._is_backdated(self._stamp(db_session, n.id))

    def test_restore_moves_the_stamp_when_it_actually_restores(self, db_session):
        """The case the whole issue is about: without a stamp the client cannot
        tell a restore-after-dismiss from a stale server view."""
        from app.models.notification import Notification
        from app.services.notifications.service import NotificationService

        n = self._make(db_session, deleted_at=datetime.now(timezone.utc))

        NotificationService().restore(db_session, n.id, user_id=1)

        db_session.expire_all()
        restored = db_session.get(Notification, n.id)
        assert restored.deleted_at is None
        assert not self._is_backdated(restored.updated_at)
```

Die Datei braucht oben `from datetime import datetime, timezone` - falls dort noch nicht importiert, ergaenzen.

- [ ] **Step 2: Run the tests**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -q --no-cov -k UpdatedAtSemantics`
Expected: PASS (5 Tests). Schlägt einer der Bulk-Tests fehl, feuert `onupdate` auf diesem SQLAlchemy-Stand **nicht** bei `Query.update()` — dann in `mark_all_as_read` und `dismiss_all` `Notification.updated_at: datetime.now(timezone.utc)` explizit ins Update-Dict aufnehmen und die Tests erneut laufen lassen.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/test_notification_service.py
git commit -m "test(notifications): pin the updated_at stamp semantics (#504)"
```

---

### Task 4: `updated_after`-Filter im Service

**Files:**
- Modify: `backend/app/services/notifications/service.py:421-434` (Signatur), `:479-483` (Filter), `:490-501` (Signatur `count_user_notifications`), `:549-550` (Filter)
- Test: `backend/tests/services/test_notification_service.py` (anhängen)

**Interfaces:**
- Consumes: `Notification.updated_at` aus Task 1.
- Produces: `get_user_notifications(..., updated_after: Optional[datetime] = None, ...)` und `count_user_notifications(..., updated_after: Optional[datetime] = None, ...)` — Parameter jeweils **nach** `created_before` einfügen, damit bestehende Positionsaufrufe nicht verrutschen.

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_notification_service.py` anhängen:

```python
class TestUpdatedAfterFilter:
    """Problem 2 from #504: created_* filters cannot see a state change.

    Same backdating as TestUpdatedAtSemantics - no sleeps, no clock resolution
    to trip over.
    """

    OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)
    CUTOFF = datetime(2023, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def _make(cls, db_session, title, backdate=False):
        from app.models.notification import Notification
        n = Notification(
            user_id=1, category="system", notification_type="info",
            title=title, message="M",
        )
        db_session.add(n)
        db_session.commit()
        if backdate:
            db_session.query(Notification).filter_by(id=n.id).update(
                {"updated_at": cls.OLD}, synchronize_session=False
            )
            db_session.commit()
        db_session.expire_all()
        return db_session.get(Notification, n.id)

    def test_returns_only_rows_changed_after_the_cutoff(self, db_session):
        from app.services.notifications.service import NotificationService

        svc = NotificationService()
        self._make(db_session, "alt", backdate=True)
        self._make(db_session, "neu")

        rows = svc.get_user_notifications(
            db_session, user_id=1, updated_after=self.CUTOFF)

        assert [r.title for r in rows] == ["neu"]

    def test_a_state_change_pulls_an_old_row_back_into_the_window(self, db_session):
        """The whole point: a three-week-old notification that was just read
        must show up, which created_after can never do."""
        from app.services.notifications.service import NotificationService

        svc = NotificationService()
        old = self._make(db_session, "alt", backdate=True)

        svc.mark_as_read(db_session, old.id, user_id=1)

        titles = [r.title for r in svc.get_user_notifications(
            db_session, user_id=1, updated_after=self.CUTOFF)]
        assert titles == ["alt"]

    def test_count_applies_the_same_filter(self, db_session):
        from app.services.notifications.service import NotificationService

        svc = NotificationService()
        self._make(db_session, "alt", backdate=True)
        self._make(db_session, "neu")

        assert svc.count_user_notifications(
            db_session, user_id=1, updated_after=self.CUTOFF) == 1

    def test_without_the_filter_nothing_changes(self, db_session):
        from app.services.notifications.service import NotificationService

        svc = NotificationService()
        self._make(db_session, "a", backdate=True)
        self._make(db_session, "b")

        assert len(svc.get_user_notifications(db_session, user_id=1)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -q --no-cov -k UpdatedAfterFilter`
Expected: FAIL — `TypeError: get_user_notifications() got an unexpected keyword argument 'updated_after'`

- [ ] **Step 3: Add the parameter to `get_user_notifications`**

In `backend/app/services/notifications/service.py` in der Signatur nach `created_before: Optional[datetime] = None,` (Zeile 430):

```python
        updated_after: Optional[datetime] = None,
```

Im Docstring nach der `created_before`-Zeile:

```python
            updated_after: Only return notifications whose state changed at or
                after this time (incremental sync, #504)
```

Und nach dem `created_before`-Filter (Zeile 482-483):

```python
        if updated_after:
            query = query.filter(Notification.updated_at >= updated_after)
```

- [ ] **Step 4: Add the same to `count_user_notifications`**

In der Signatur (nach Zeile 499) `updated_after: Optional[datetime] = None,` ergänzen und nach dem dortigen `created_after`-Filterblock (Zeile 549-550):

```python
        if updated_after:
            query = query.filter(Notification.updated_at >= updated_after)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -q --no-cov -k UpdatedAfterFilter`
Expected: PASS (4 Tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): filter lists by updated_after (#504)"
```

---

### Task 5: `updated_after` auf den Routen + Sync-Kontrakt dokumentieren

**Files:**
- Modify: `backend/app/api/routes/notifications.py:42-43` + `:63-64` + `:79-80` (Inbox), `:429-430` + `:447-448` + `:460-461` (Trash)
- Create: `docs/api/NOTIFICATION_SYNC.md`
- Test: `backend/tests/test_notifications_routes.py` (anhängen)

**Interfaces:**
- Consumes: `updated_after` aus Task 4.
- Produces: Query-Parameter `updated_after` auf `GET /api/notifications` und `GET /api/notifications/trash`.

- [ ] **Step 1: Write the failing test**

An `backend/tests/test_notifications_routes.py` anhängen (Import-Stil und Fixtures der Datei übernehmen):

```python
class TestUpdatedAfterQuery:
    """#504 problem 2, end to end."""

    def test_inbox_accepts_updated_after(self, client, auth_headers):
        response = client.get(
            "/api/notifications",
            params={"updated_after": "2020-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200

    def test_trash_accepts_updated_after(self, client, auth_headers):
        response = client.get(
            "/api/notifications/trash",
            params={"updated_after": "2020-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200

    def test_every_item_carries_the_stamp(self, client, auth_headers):
        response = client.get("/api/notifications", headers=auth_headers)

        assert response.status_code == 200
        for item in response.json()["notifications"]:
            assert item["updated_at"] is not None

    def test_a_far_future_cutoff_returns_nothing(self, client, auth_headers):
        """Guards against the parameter being silently ignored — a filter that
        does nothing would let the client think it is fully synced."""
        response = client.get(
            "/api/notifications",
            params={"updated_after": "2999-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["notifications"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py -q --no-cov -k UpdatedAfterQuery`
Expected: FAIL — `test_a_far_future_cutoff_returns_nothing` liefert Einträge, weil FastAPI den unbekannten Parameter verwirft

- [ ] **Step 3: Add the parameter to the inbox route**

In `backend/app/api/routes/notifications.py` nach Zeile 43:

```python
    updated_after: Optional[datetime] = Query(None, description="Only return notifications changed at or after this time (incremental sync)"),
```

und in **beiden** Service-Aufrufen dieser Route (Zeilen 63-64 und 79-80, Liste und Count) jeweils nach `created_before=created_before,`:

```python
        updated_after=updated_after,
```

- [ ] **Step 4: Add the parameter to the trash route**

Dasselbe in der Trash-Route: nach Zeile 430 den `Query(None, ...)`-Parameter, und in beiden Service-Aufrufen (Zeilen 447-448 und 460-461) `updated_after=updated_after,` ergänzen.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py -q --no-cov -k UpdatedAfterQuery`
Expected: PASS (4 Tests)

- [ ] **Step 6: Write the sync contract document**

Neue Datei `docs/api/NOTIFICATION_SYNC.md`:

```markdown
# Notification-Abgleich für Clients

Gilt für Clients mit lokalem Bestand (BaluApp). Die Webapp braucht das nicht —
sie wird vom Server ausgeliefert und hat ohne ihn ohnehin keine Daten.

## Zeitstempel

| Feld | Bedeutung |
|---|---|
| `created_at` | Erstellung. Ändert sich nie. |
| `updated_at` | **Letzte Zustandsänderung.** Bewegt sich bei Lesen, Wegklicken, Wiederherstellen und Snooze — auch bei den Massenaktionen. |
| `deleted_at` | Zeitpunkt des Wegklickens, `null` = aktiv. |

Ein folgenloser Aufruf (etwa Wegklicken einer bereits weggeklickten Zeile)
schreibt nichts und bewegt `updated_at` deshalb **nicht**. Das ist Absicht:
sonst zöge jede Massenaktion den kompletten Bestand in jeden weiteren
inkrementellen Abruf.

## Inkrementell abfragen

`GET /api/notifications?updated_after=<ISO-8601>` und dasselbe auf
`/api/notifications/trash`. Der Client merkt sich das höchste gesehene
`updated_at` und schickt es beim nächsten Mal.

Paginierung: die Sortierung ist `created_at DESC`. Kommen während einer
Seitenfolge neue Notifications an, verschieben sich die Offsets. Wer sauber
durchblättern will, setzt zusätzlich `created_before` auf den Startzeitpunkt
des Durchlaufs.

## Konfliktauflösung

`is_read` ist **monoton** — es gibt keinen Endpunkt, der auf ungelesen
zurücksetzt. Zusammenführen per ODER: irgendwo gelesen ⇒ gelesen.

Für den Papierkorb-Zustand gilt Last-Write-Wins über `updated_at`.

## Endgültig gelöschte Zeilen (bewusste Entscheidung)

**Es gibt keine Grabsteine.** Hard-Deletes hinterlassen keine Spur, und das
bleibt so. Begründung:

1. **Der häufigste Fall ist vorhersagbar.** `cleanup_expired_trash()` löscht
   Papierkorb-Zeilen nach Ablauf der Retention — pro Nutzer 1–7 Tage aus
   `NotificationPreferences.trash_retention_days`, für System-Notifications
   fix 7 Tage. Eine Zeile, die der Client zuletzt mit `deleted_at = T` gesehen
   hat, ist nach `T + retention` weg. Der Client kann dieselbe Regel lokal
   anwenden; `trash_retention_days` liefert
   `GET /api/notifications/preferences`.
2. **Der Rest ist selten und nutzerinitiiert.** Übrig bleiben
   `DELETE /api/notifications/{id}` und `DELETE /api/notifications/trash` —
   bewusste Aktionen, typischerweise von einem verbundenen Gerät.

**Der Client muss deshalb periodisch einen Vollabgleich fahren**, um solche
Löschungen zu bemerken. Empfehlung: bei jedem Kaltstart, sonst täglich.

Diese Festlegung ersetzt Punkt 4 aus #504. Wird sie zu teuer — etwa weil der
Bestand pro Nutzer stark wächst — ist eine Grabstein-Tabelle die nächste
Ausbaustufe.
```

- [ ] **Step 7: Run the full notification suite**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py tests/test_notifications_routes.py tests/migrations/test_notification_updated_at.py tests/api/test_notification_plugin_category.py -q --no-cov`
Expected: PASS

- [ ] **Step 8: Run ruff**

Run: `cd backend && python -m ruff check app/ tests/`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/test_notifications_routes.py docs/api/NOTIFICATION_SYNC.md
git commit -m "feat(notifications): updated_after query + documented sync contract (#504)"
```

---

## Abschluss

- [ ] **Volle Backend-Suite** (auf Windows kann sie hängen — dann CI entscheiden lassen):
  `cd backend && python -m pytest -q`
- [ ] **PR öffnen**, im Text: die drei umgesetzten Punkte, die Grabstein-Entscheidung mit Begründung, der Backfill aus `COALESCE(deleted_at, created_at)` und der Hinweis, dass `Xveyn/BaluApp` diesen Kontrakt konsumiert.
- [ ] **#504 nach dem Merge kommentieren**, nicht schließen: Punkt 4 ist entschieden und dokumentiert, aber wer das Issue schließt, sollte das explizit tun.
