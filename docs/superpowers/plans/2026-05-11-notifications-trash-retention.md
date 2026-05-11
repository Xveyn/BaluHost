# Notifications Trash + Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `is_dismissed` (bool) with `deleted_at` (timestamp) to model a real trash with auto-expiry, add per-user retention (1–7 days), and surface a Trash tab with Restore / Permanent-Delete on the notifications page.

**Architecture:** Single source of truth for trash state is `notifications.deleted_at`. A user-configurable `notification_preferences.trash_retention_days` (1–7, default 7) drives an hourly cleanup job that hard-deletes expired rows. System notifications (`user_id IS NULL`) use a fixed 7-day retention. The `_user_filter()` helper already covers admin vs user scoping for system notifications; we reuse it for the new endpoints.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic (with `batch_alter_table` for SQLite portability), Pydantic v2, APScheduler. Frontend: React 18, TypeScript, Tailwind CSS, lucide-react, react-hot-toast, i18next, axios via `apiClient`.

**Spec:** `docs/superpowers/specs/2026-05-11-notifications-trash-retention-design.md`

---

## File Map

**Backend — modify:**
- `backend/app/models/notification.py` — Notification: replace `is_dismissed` with `deleted_at`; NotificationPreferences: add `trash_retention_days`
- `backend/app/schemas/notification.py` — `NotificationResponse`: drop `is_dismissed`, add `deleted_at`; `NotificationPreferences*`: add `trash_retention_days`
- `backend/app/services/notifications/service.py` — swap all `is_dismissed` filters to `deleted_at`; rewrite `dismiss`/`dismiss_all`; add `restore`/`delete_permanently`/`empty_trash`/`cleanup_expired_trash`; remove `cleanup_old_notifications`; swap `include_dismissed` parameter for `trashed_only`
- `backend/app/services/notifications/scheduler.py` — add hourly `notification_trash_cleanup` job; relocate scheduler creation so cleanup runs without Firebase
- `backend/app/api/routes/notifications.py` — update existing dismiss docstrings; remove `include_dismissed` query param; add 4 new endpoints (GET `/trash`, POST `/{id}/restore`, DELETE `/{id}`, DELETE `/trash`)

**Backend — create:**
- `backend/alembic/versions/<rev>_notification_trash_retention.py` — schema migration
- `backend/tests/migrations/test_notification_trash_retention.py` — migration backfill tests

**Backend — modify (tests):**
- `backend/tests/services/test_notification_service.py` — add trash tests, fix existing dismiss test
- `backend/tests/test_notifications_routes.py` — add trash route tests (file may need to be created if it doesn't exist; check first)

**Frontend — modify:**
- `client/src/api/notifications.ts` — type `Notification.is_dismissed` → `deleted_at`; type `NotificationPreferences` add `trash_retention_days`; add `getTrashNotifications`, `restoreNotification`, `deleteNotificationPermanently`, `emptyTrash`
- `client/src/contexts/NotificationContext.tsx` — context filter (no behavior change beyond field rename); existing `dismiss` semantics now move-to-trash, no code change in context
- `client/src/pages/NotificationsArchivePage.tsx` — replace `readFilter` with Inbox/Trash tabs; trash tab gets restore + delete-forever row icons and "Papierkorb leeren" button
- `client/src/pages/NotificationPreferencesPage.tsx` — add retention slider section
- `client/src/i18n/locales/de/notifications.json` + `client/src/i18n/locales/en/notifications.json` — new keys
- `client/src/__tests__/lib/notificationGrouping.test.ts` — fixture `is_dismissed: false` → `deleted_at: null`

---

## Task 1: Migration + Model

**Files:**
- Create: `backend/alembic/versions/<rev>_notification_trash_retention.py`
- Modify: `backend/app/models/notification.py`
- Create: `backend/tests/migrations/test_notification_trash_retention.py`

- [ ] **Step 1: Find the current Alembic head**

Run: `cd backend && alembic heads`
Expected: One revision ID, e.g. `1a2b3c4d5e6f (head)`. Note this — you'll need it as `down_revision`.

- [ ] **Step 2: Create the migration stub**

Run: `cd backend && alembic revision -m "notification trash retention"`
Expected: A new file `backend/alembic/versions/<auto-id>_notification_trash_retention.py`. Note the path.

- [ ] **Step 3: Replace migration body**

Open the new file. Keep the `revision` and `down_revision` lines exactly as generated. Replace the `upgrade()` and `downgrade()` bodies with:

```python
"""notification trash retention

Revision ID: <leave the generated id>
Revises: <leave the generated down_revision>
Create Date: <leave generated>

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, as used by Alembic.
# (leave the auto-generated revision/down_revision lines untouched)


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_notifications_deleted_at", ["deleted_at"])

    # Backfill: existing soft-dismissed rows start their retention now.
    op.execute(
        "UPDATE notifications SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE is_dismissed"
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("is_dismissed")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "trash_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="7",
            )
        )
        batch_op.create_check_constraint(
            "ck_trash_retention_1_7",
            "trash_retention_days BETWEEN 1 AND 7",
        )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_dismissed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
    op.execute(
        "UPDATE notifications SET is_dismissed = "
        "(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END)"
    )
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.drop_constraint("ck_trash_retention_1_7", type_="check")
        batch_op.drop_column("trash_retention_days")
```

- [ ] **Step 4: Apply migration to dev DB**

Run: `cd backend && alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, notification trash retention`. No errors.

- [ ] **Step 5: Update the SQLAlchemy model**

In `backend/app/models/notification.py`:

Replace the `is_dismissed` line (currently line 69):

```python
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

with:

```python
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )
```

In the `to_dict` method of `Notification`, replace the `"is_dismissed"` entry (currently line 94) with:

```python
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
```

In the `NotificationPreferences` class, add after `min_priority` (currently line 126):

```python
    trash_retention_days: Mapped[int] = mapped_column(
        Integer, default=7, nullable=False
    )
```

In the `NotificationPreferences.to_dict` method, add a key before the closing `}` (currently line 145):

```python
            "trash_retention_days": self.trash_retention_days,
```

- [ ] **Step 6: Sanity-check model imports**

Run: `cd backend && python -c "from app.models.notification import Notification, NotificationPreferences; print(Notification.__table__.columns.keys()); print(NotificationPreferences.__table__.columns.keys())"`
Expected: `deleted_at` appears in Notification columns; `trash_retention_days` appears in NotificationPreferences; **`is_dismissed` is NOT in Notification columns**.

- [ ] **Step 7: Write migration backfill test**

Create `backend/tests/migrations/__init__.py` if it doesn't exist (empty file).

Create `backend/tests/migrations/test_notification_trash_retention.py`:

```python
"""Test the notification trash retention migration backfills dismissed rows."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.notification import Notification


def test_existing_notifications_in_inbox_have_deleted_at_null(db_session):
    """After migration, notifications without deleted_at remain in the inbox."""
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Active",
        message="Still in inbox",
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    assert n.deleted_at is None


def test_can_write_and_query_deleted_at(db_session):
    """Migration created the column and index; writes round-trip."""
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Trashed",
        message="In trash",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    assert n.deleted_at is not None


def test_trash_retention_days_defaults_to_7(db_session):
    """New preferences rows default to 7-day retention."""
    from app.models.notification import NotificationPreferences
    prefs = NotificationPreferences(user_id=999999)
    db_session.add(prefs)
    db_session.commit()
    db_session.refresh(prefs)
    assert prefs.trash_retention_days == 7


def test_trash_retention_days_rejects_out_of_range(db_session):
    """CHECK constraint rejects values outside 1..7."""
    from app.models.notification import NotificationPreferences
    from sqlalchemy.exc import IntegrityError

    prefs = NotificationPreferences(user_id=999998, trash_retention_days=0)
    db_session.add(prefs)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
```

- [ ] **Step 8: Run migration tests**

Run: `cd backend && python -m pytest tests/migrations/test_notification_trash_retention.py -v`
Expected: 4 passed.

- [ ] **Step 9: Smoke-test downgrade then upgrade**

Run:
```
cd backend && alembic downgrade -1 && alembic upgrade head
```
Expected: Two successful runs, no errors. (This verifies the downgrade path works.)

- [ ] **Step 10: Commit**

```bash
git add backend/alembic/versions/*_notification_trash_retention.py backend/app/models/notification.py backend/tests/migrations/
git commit -m "feat(notifications): migrate is_dismissed → deleted_at with 1-7d retention"
```

---

## Task 2: Schemas

**Files:**
- Modify: `backend/app/schemas/notification.py`

- [ ] **Step 1: Update `NotificationResponse`**

In `backend/app/schemas/notification.py`, replace line 63 `is_dismissed: bool = False` with:

```python
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when notification was moved to trash (null = active)"
    )
```

In `NotificationResponse.from_db()` (the `return cls(...)` block starting at line 95), replace the line `is_dismissed=notification.is_dismissed,` (line 105) with:

```python
            deleted_at=notification.deleted_at,
```

- [ ] **Step 2: Update preferences schemas**

In `NotificationPreferencesBase` (starting line 167), add a new field after `category_preferences` (after line 199):

```python
    trash_retention_days: int = Field(
        default=7,
        ge=1,
        le=7,
        description="Days to retain notifications in trash before auto-purge"
    )
```

In `NotificationPreferencesUpdate` (starting line 202), add after `category_preferences`:

```python
    trash_retention_days: Optional[int] = Field(default=None, ge=1, le=7)
```

In `NotificationPreferencesResponse.from_db()` (the `return cls(...)` block starting at line 225), add after `category_preferences=prefs.category_preferences,`:

```python
            trash_retention_days=prefs.trash_retention_days,
```

- [ ] **Step 3: Verify schemas import cleanly**

Run: `cd backend && python -c "from app.schemas.notification import NotificationResponse, NotificationPreferencesResponse, NotificationPreferencesUpdate; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/notification.py
git commit -m "feat(notifications): expose deleted_at + trash_retention_days in schemas"
```

---

## Task 3: Service — switch dismiss/internal filters to deleted_at

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Update existing dismiss test**

In `backend/tests/services/test_notification_service.py`, find `test_dismiss_notification` (around line 216) and replace the final assertion block:

```python
        result = notification_service.dismiss(
            db_session, notification.id, test_user.id
        )

        assert result is not None
        assert result.is_dismissed is True
        assert result.is_read is True
```

with:

```python
        result = notification_service.dismiss(
            db_session, notification.id, test_user.id
        )

        assert result is not None
        assert result.deleted_at is not None
        assert result.is_read is True
```

Also find the assertion `assert notification.is_dismissed is False` (around line 63) and replace with:

```python
        assert notification.deleted_at is None
```

- [ ] **Step 2: Add new dismiss test**

Append to `backend/tests/services/test_notification_service.py`:

```python
class TestTrashSemantics:
    """Tests for trash-based dismiss/restore/delete behavior."""

    def test_dismiss_sets_deleted_at(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)

        before = n.deleted_at
        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert before is None
        assert n.deleted_at is not None
        assert n.is_read is True

    def test_dismiss_idempotent_on_already_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()

        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        first = n.deleted_at

        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        # Second dismiss must not overwrite the original timestamp
        assert n.deleted_at == first
```

- [ ] **Step 3: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v`
Expected: FAIL — `dismiss` does not yet set `deleted_at` (still uses `is_dismissed`).

- [ ] **Step 4: Update service filters and `dismiss`/`dismiss_all`**

In `backend/app/services/notifications/service.py`:

Add `func` to the existing SQLAlchemy import (around line 12 — confirm it's already imported via `from sqlalchemy import desc, and_, func, or_`; if not, add `func`).

Find every occurrence of `Notification.is_dismissed == False` and replace with `Notification.deleted_at.is_(None)`. The current locations are lines 470, 537, 578, 617, 747. Use a single replace_all in the file.

Replace the body of `dismiss` (around line 697–727) with:

```python
    def dismiss(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Notification]:
        """Move a notification to trash (idempotent on already-trashed rows)."""
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            self._user_filter(user_id, is_admin),
        ).first()

        if notification and notification.deleted_at is None:
            notification.deleted_at = datetime.now(timezone.utc)
            notification.is_read = True
            db.commit()
            db.refresh(notification)
            logger.debug(f"Moved notification {notification_id} to trash")

        return notification
```

Replace the body of `dismiss_all` (around line 729–757) with:

```python
    def dismiss_all(
        self,
        db: Session,
        user_id: int,
        is_admin: bool = False,
    ) -> int:
        """Move all active notifications for a user to trash."""
        query = db.query(Notification).filter(
            self._user_filter(user_id, is_admin),
            Notification.deleted_at.is_(None),
        )

        count = query.update({
            Notification.deleted_at: datetime.now(timezone.utc),
            Notification.is_read: True,
        })
        db.commit()

        logger.info(f"Moved {count} notifications to trash for user {user_id}")
        return count
```

- [ ] **Step 5: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -v -k "dismiss or Trash"`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): dismiss now writes deleted_at timestamp"
```

---

## Task 4: Service — `restore` method

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write failing tests**

Append to `TestTrashSemantics` class in `backend/tests/services/test_notification_service.py`:

```python
    def test_restore_clears_deleted_at(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert n.deleted_at is not None

        result = notification_service.restore(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert result is not None
        assert n.deleted_at is None

    def test_restore_idempotent_on_active(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()

        result = notification_service.restore(db_session, n.id, test_user.id)
        assert result is not None
        assert result.deleted_at is None

    def test_restore_returns_none_for_unknown_id(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        result = notification_service.restore(db_session, 9999999, test_user.id)
        assert result is None
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k restore`
Expected: FAIL — `restore` is not defined.

- [ ] **Step 3: Implement `restore`**

In `backend/app/services/notifications/service.py`, add this method immediately after `dismiss_all` (around line 758):

```python
    def restore(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Notification]:
        """Restore a notification from trash (idempotent on already-active rows)."""
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            self._user_filter(user_id, is_admin),
        ).first()

        if notification and notification.deleted_at is not None:
            notification.deleted_at = None
            db.commit()
            db.refresh(notification)
            logger.debug(f"Restored notification {notification_id} from trash")

        return notification
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k restore`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): add restore() to bring a row back from trash"
```

---

## Task 5: Service — `delete_permanently`

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write failing test**

Append to `TestTrashSemantics`:

```python
    def test_delete_permanently_removes_row(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        notification_id = n.id

        deleted = notification_service.delete_permanently(
            db_session, notification_id, test_user.id
        )
        assert deleted is True
        assert (
            db_session.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
            is None
        )

    def test_delete_permanently_returns_false_for_unknown_id(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        deleted = notification_service.delete_permanently(
            db_session, 9999999, test_user.id
        )
        assert deleted is False
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k delete_permanently`
Expected: FAIL — method not defined.

- [ ] **Step 3: Implement**

In `backend/app/services/notifications/service.py`, add after the `restore` method:

```python
    def delete_permanently(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> bool:
        """Hard-delete a single notification (any state). Returns True if deleted."""
        count = (
            db.query(Notification)
            .filter(
                Notification.id == notification_id,
                self._user_filter(user_id, is_admin),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        if count:
            logger.debug(f"Hard-deleted notification {notification_id}")
        return count > 0
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k delete_permanently`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): add delete_permanently() for hard delete"
```

---

## Task 6: Service — `empty_trash`

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write failing test**

Append to `TestTrashSemantics`:

```python
    def test_empty_trash_removes_only_trashed_rows(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        count = notification_service.empty_trash(db_session, test_user.id)

        assert count == 1
        remaining = db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].title == "active"

    def test_empty_trash_isolates_users(
        self,
        notification_service,
        db_session,
        test_user,
        test_admin,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        user_trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="user-trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        other_trashed = Notification(
            user_id=test_admin.id,
            category="system",
            notification_type="info",
            title="admin-trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([user_trashed, other_trashed])
        db_session.commit()

        notification_service.empty_trash(db_session, test_user.id, is_admin=False)

        # User's trash gone; admin's trash untouched (non-admin scope)
        assert db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).count() == 0
        assert db_session.query(Notification).filter(
            Notification.user_id == test_admin.id
        ).count() == 1
```

Note: this test requires a `test_admin` fixture. If it does not yet exist in `backend/tests/conftest.py` or the same test file, check `conftest.py` for an existing admin fixture (likely `admin_user` or `test_admin`). If missing, add one:

```python
@pytest.fixture
def test_admin(db_session):
    """Create an admin user for tests that need admin scope isolation."""
    from app.models.user import User
    user = User(
        username="admin_for_trash",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
```

(Adjust password field name if the User model differs — check the existing `test_user` fixture for the pattern.)

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k empty_trash`
Expected: FAIL — `empty_trash` not defined.

- [ ] **Step 3: Implement**

In `backend/app/services/notifications/service.py`, add after `delete_permanently`:

```python
    def empty_trash(
        self,
        db: Session,
        user_id: int,
        is_admin: bool = False,
    ) -> int:
        """Hard-delete every trashed notification visible to this user."""
        count = (
            db.query(Notification)
            .filter(
                self._user_filter(user_id, is_admin),
                Notification.deleted_at.is_not(None),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(f"Emptied trash for user {user_id}: {count} rows")
        return count
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k empty_trash`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py backend/tests/conftest.py
git commit -m "feat(notifications): add empty_trash() for bulk hard-delete"
```

---

## Task 7: Service — `cleanup_expired_trash` (remove `cleanup_old_notifications`)

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write failing tests**

Append to `TestTrashSemantics`:

```python
    def test_cleanup_expired_trash_respects_user_retention(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification, NotificationPreferences
        from datetime import datetime, timezone, timedelta

        # 3-day retention for this user
        prefs = NotificationPreferences(user_id=test_user.id, trash_retention_days=3)
        db_session.add(prefs)

        now = datetime.now(timezone.utc)
        old = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="old",
            message="m",
            deleted_at=now - timedelta(days=5),
        )
        recent = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="recent",
            message="m",
            deleted_at=now - timedelta(days=1),
        )
        db_session.add_all([old, recent])
        db_session.commit()

        count = notification_service.cleanup_expired_trash(db_session)

        assert count == 1
        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id == test_user.id)
            .all()
        ]
        assert titles == ["recent"]

    def test_cleanup_expired_trash_default_when_no_prefs(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        too_old = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="too_old",
            message="m",
            deleted_at=now - timedelta(days=8),
        )
        within = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="within",
            message="m",
            deleted_at=now - timedelta(days=6),
        )
        db_session.add_all([too_old, within])
        db_session.commit()

        count = notification_service.cleanup_expired_trash(db_session)

        assert count == 1
        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id == test_user.id)
            .all()
        ]
        assert titles == ["within"]

    def test_cleanup_expired_trash_system_notifications_fixed_7d(
        self,
        notification_service,
        db_session,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        old_system = Notification(
            user_id=None,
            category="system",
            notification_type="info",
            title="old_sys",
            message="m",
            deleted_at=now - timedelta(days=10),
        )
        fresh_system = Notification(
            user_id=None,
            category="system",
            notification_type="info",
            title="fresh_sys",
            message="m",
            deleted_at=now - timedelta(days=3),
        )
        db_session.add_all([old_system, fresh_system])
        db_session.commit()

        notification_service.cleanup_expired_trash(db_session)

        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id.is_(None))
            .all()
        ]
        assert titles == ["fresh_sys"]
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k cleanup_expired_trash`
Expected: FAIL — `cleanup_expired_trash` not defined.

- [ ] **Step 3: Implement and remove old cleanup**

In `backend/app/services/notifications/service.py`, replace the entire `cleanup_old_notifications` method (the `async def cleanup_old_notifications(...)` block, around lines 867–891) with:

```python
    def cleanup_expired_trash(self, db: Session) -> int:
        """Hard-delete trashed notifications past their retention.

        Per-user retention comes from NotificationPreferences.trash_retention_days
        (default 7 if no prefs row). System notifications (user_id IS NULL) use
        a fixed 7-day retention.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        users_with_trash = (
            db.query(Notification.user_id)
            .filter(
                Notification.deleted_at.is_not(None),
                Notification.user_id.is_not(None),
            )
            .distinct()
            .all()
        )

        total = 0
        for (user_id,) in users_with_trash:
            prefs = self.get_user_preferences(db, user_id)
            retention_days = prefs.trash_retention_days if prefs else 7
            cutoff = now - timedelta(days=retention_days)
            count = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.deleted_at.is_not(None),
                    Notification.deleted_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
            total += count

        # System notifications use fixed 7-day retention
        sys_cutoff = now - timedelta(days=7)
        total += (
            db.query(Notification)
            .filter(
                Notification.user_id.is_(None),
                Notification.deleted_at.is_not(None),
                Notification.deleted_at < sys_cutoff,
            )
            .delete(synchronize_session=False)
        )

        db.commit()
        if total:
            logger.info(f"Expired trash cleanup: deleted {total} notifications")
        return total
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k cleanup_expired_trash`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "feat(notifications): cleanup_expired_trash respects per-user retention"
```

---

## Task 8: Service — `trashed_only` parameter on list/count

**Files:**
- Modify: `backend/app/services/notifications/service.py`
- Modify: `backend/tests/services/test_notification_service.py`

- [ ] **Step 1: Write failing tests**

Append to `TestTrashSemantics`:

```python
    def test_get_user_notifications_inbox_excludes_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        results = notification_service.get_user_notifications(
            db_session, test_user.id
        )
        titles = [n.title for n in results]
        assert "active" in titles
        assert "trashed" not in titles

    def test_get_user_notifications_trashed_only_returns_trash(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        results = notification_service.get_user_notifications(
            db_session, test_user.id, trashed_only=True
        )
        titles = [n.title for n in results]
        assert titles == ["trashed"]

    def test_get_unread_count_ignores_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        unread = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="unread",
            message="m",
        )
        unread_in_trash = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="unread_in_trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([unread, unread_in_trash])
        db_session.commit()

        count = notification_service.get_unread_count(db_session, test_user.id)
        assert count == 1
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py::TestTrashSemantics -v -k "inbox or trashed_only or unread_count"`
Expected: FAIL — `trashed_only` parameter unknown; the trashed row still appears.

- [ ] **Step 3: Refactor `get_user_notifications` and `count_user_notifications`**

In `backend/app/services/notifications/service.py`, change the signature of `get_user_notifications` (around line 423) and `count_user_notifications` (around line 489):

**Replace the parameter** `include_dismissed: bool = False,` (present in both signatures) with:

```python
        trashed_only: bool = False,
```

**Replace the filter block** in both methods. Find this in `get_user_notifications` (around line 469):

```python
        if not include_dismissed:
            query = query.filter(Notification.is_dismissed == False)
```

Replace with:

```python
        if trashed_only:
            query = query.filter(Notification.deleted_at.is_not(None))
        else:
            query = query.filter(Notification.deleted_at.is_(None))
```

Apply the same replacement in `count_user_notifications` (around line 536):

```python
        if not include_dismissed:
            query = query.filter(Notification.is_dismissed == False)
```

becomes:

```python
        if trashed_only:
            query = query.filter(Notification.deleted_at.is_not(None))
        else:
            query = query.filter(Notification.deleted_at.is_(None))
```

Also update the docstrings of both methods: replace any mention of `include_dismissed` with `trashed_only` and re-describe ("If True, return only trashed notifications; otherwise return only active (inbox) notifications").

(At this point the remaining `is_dismissed` filters in `get_unread_count`/`get_unread_counts` should already read `Notification.deleted_at.is_(None)` from Task 3's replace_all.)

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/services/test_notification_service.py -v`
Expected: All tests in this file pass.

- [ ] **Step 5: Run the full service test suite to catch any caller regression**

Run: `cd backend && python -m pytest tests/services/ -v`
Expected: All previously-passing tests still pass. If something fails citing `include_dismissed`, locate that caller and switch it to `trashed_only`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notifications/service.py backend/tests/services/test_notification_service.py
git commit -m "refactor(notifications): swap include_dismissed for trashed_only"
```

---

## Task 9: Routes — update existing endpoints

**Files:**
- Modify: `backend/app/api/routes/notifications.py`

- [ ] **Step 1: Update existing `GET /notifications` query parameter**

In `backend/app/api/routes/notifications.py`, find the `get_notifications` handler (around line 35). Replace the `include_dismissed` query parameter (line 38) with nothing — remove that whole `include_dismissed: bool = ...` line.

Also remove its reference inside the two service calls (`include_dismissed=include_dismissed,` — appears in `service.get_user_notifications(...)` and `service.count_user_notifications(...)` around lines 56–83). Just delete those lines; the service defaults to `trashed_only=False`.

- [ ] **Step 2: Update docstrings of dismiss endpoints**

Find `dismiss_all_notifications` (around line 190). Replace its docstring with:

```python
    """Move all active notifications for the current user to trash.

    Sets deleted_at=NOW() and is_read=True on all active notifications.
    Items can be restored from the trash view or are auto-purged after the
    user's configured retention period (default 7 days).
    """
```

Find `dismiss_notification` (around line 207). Replace its docstring with:

```python
    """Move a notification to trash.

    The notification is hidden from inbox views and appears in the trash,
    where it can be restored or permanently deleted. Auto-purged after the
    user's configured retention period (default 7 days).
    """
```

- [ ] **Step 3: Verify the API still imports cleanly**

Run: `cd backend && python -c "from app.api.routes.notifications import router; print(len(router.routes))"`
Expected: A positive integer (current number of routes), no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/notifications.py
git commit -m "refactor(notifications): drop include_dismissed param, update dismiss docs"
```

---

## Task 10: Route — `GET /notifications/trash`

**Files:**
- Modify: `backend/app/api/routes/notifications.py`
- Modify (or create): `backend/tests/test_notifications_routes.py`

- [ ] **Step 1: Check whether the route-test file exists**

Run: `cd backend && python -c "import os; print(os.path.exists('tests/test_notifications_routes.py'))"`
Expected: prints `True` or `False`. If `False`, create the file with the minimal scaffolding in the test step below; if `True`, append to it.

- [ ] **Step 2: Write failing test**

Add (or create the file containing) the following test. If the file already exists, append the class; if creating, prepend the file with imports:

```python
"""Integration tests for notification routes."""
from datetime import datetime, timezone

import pytest


class TestTrashRoutes:
    """Tests for trash-specific route endpoints."""

    def test_get_trash_returns_only_trashed(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        resp = client.get("/api/notifications/trash", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        titles = [n["title"] for n in data["notifications"]]
        assert titles == ["trashed"]
```

If `auth_headers` / `test_user` / `client` fixtures don't exist under those names, check `backend/tests/conftest.py` for the project's conventions (often `client`, `auth_headers`, `test_user` exist). Adjust fixture names to match.

- [ ] **Step 3: Run test — expect failure**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes::test_get_trash_returns_only_trashed -v`
Expected: FAIL — 404 Not Found (endpoint doesn't exist).

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/routes/notifications.py`, add this endpoint immediately before the `POST /notifications` create endpoint (around line 357):

```python
@router.get("/trash", response_model=NotificationListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_trash(
    request: Request, response: Response,
    category: Optional[NotificationCategoryEnum] = Query(None),
    notification_type: Optional[str] = Query(None),
    created_after: Optional[datetime] = Query(None),
    created_before: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    """List trashed notifications for the current user, paginated."""
    service = get_notification_service()
    offset = (page - 1) * page_size
    admin = is_privileged(current_user)

    notifications = service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        trashed_only=True,
        category=category,
        notification_type=notification_type,
        created_after=created_after,
        created_before=created_before,
        limit=page_size,
        offset=offset,
        is_admin=admin,
    )

    total = service.count_user_notifications(
        db=db,
        user_id=current_user.id,
        trashed_only=True,
        category=category,
        notification_type=notification_type,
        created_after=created_after,
        created_before=created_before,
        is_admin=admin,
    )

    unread_count = service.get_unread_count(db, current_user.id, is_admin=admin)

    return NotificationListResponse(
        notifications=[NotificationResponse.from_db(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 5: Run test — expect pass**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes::test_get_trash_returns_only_trashed -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/test_notifications_routes.py
git commit -m "feat(notifications): add GET /notifications/trash"
```

---

## Task 11: Route — `POST /notifications/{id}/restore`

**Files:**
- Modify: `backend/app/api/routes/notifications.py`
- Modify: `backend/tests/test_notifications_routes.py`

- [ ] **Step 1: Write failing test**

Append to `TestTrashRoutes`:

```python
    def test_restore_round_trip(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(n)
        db_session.commit()

        resp = client.post(
            f"/api/notifications/{n.id}/restore", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_at"] is None

    def test_restore_unknown_id_returns_404(
        self, client, auth_headers
    ):
        resp = client.post(
            "/api/notifications/99999999/restore", headers=auth_headers
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes -v -k restore`
Expected: FAIL (404 for the round-trip test because the route doesn't exist).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/routes/notifications.py`, add directly after the `snooze_notification` endpoint (around line 252):

```python
@router.post("/{notification_id}/restore", response_model=NotificationResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def restore_notification(
    request: Request, response: Response,
    notification_id: int,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """Restore a notification from trash."""
    service = get_notification_service()
    notification = service.restore(
        db, notification_id, current_user.id, is_admin=is_privileged(current_user)
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return NotificationResponse.from_db(notification)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes -v -k restore`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/test_notifications_routes.py
git commit -m "feat(notifications): add POST /{id}/restore endpoint"
```

---

## Task 12: Route — `DELETE /notifications/{id}`

**Files:**
- Modify: `backend/app/api/routes/notifications.py`
- Modify: `backend/tests/test_notifications_routes.py`

- [ ] **Step 1: Write failing test**

Append to `TestTrashRoutes`:

```python
    def test_delete_permanently_removes_row(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
        )
        db_session.add(n)
        db_session.commit()
        nid = n.id

        resp = client.delete(
            f"/api/notifications/{nid}", headers=auth_headers
        )
        assert resp.status_code == 204
        assert (
            db_session.query(Notification)
            .filter(Notification.id == nid)
            .first()
            is None
        )

    def test_delete_unknown_id_returns_404(
        self, client, auth_headers
    ):
        resp = client.delete(
            "/api/notifications/99999999", headers=auth_headers
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes -v -k delete_permanently`
Expected: FAIL.

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/routes/notifications.py`, add after the restore endpoint:

```python
@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_notification(
    request: Request, response: Response,
    notification_id: int,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Permanently delete a notification (any state)."""
    service = get_notification_service()
    deleted = service.delete_permanently(
        db, notification_id, current_user.id, is_admin=is_privileged(current_user)
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes -v -k delete`
Expected: 2 passed (plus prior tests still green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/test_notifications_routes.py
git commit -m "feat(notifications): add DELETE /{id} for permanent removal"
```

---

## Task 13: Route — `DELETE /notifications/trash`

**Files:**
- Modify: `backend/app/api/routes/notifications.py`
- Modify: `backend/tests/test_notifications_routes.py`

**Route ordering note:** The DELETE for `/trash` MUST be added BEFORE the DELETE for `/{notification_id}`, otherwise FastAPI matches `"trash"` against the `{notification_id}` path parameter and you get a 422.

- [ ] **Step 1: Write failing test**

Append to `TestTrashRoutes`:

```python
    def test_empty_trash_returns_count(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        for i in range(3):
            db_session.add(Notification(
                user_id=test_user.id,
                category="system",
                notification_type="info",
                title=f"t{i}",
                message="m",
                deleted_at=datetime.now(timezone.utc),
            ))
        db_session.commit()

        resp = client.delete("/api/notifications/trash", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"count": 3}
        assert db_session.query(Notification).filter(
            Notification.user_id == test_user.id,
            Notification.deleted_at.is_not(None),
        ).count() == 0
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes::test_empty_trash_returns_count -v`
Expected: FAIL.

- [ ] **Step 3: Add the endpoint BEFORE the `DELETE /{notification_id}` endpoint**

In `backend/app/api/routes/notifications.py`, find the `delete_notification` endpoint added in Task 12. Insert this BEFORE it:

```python
@router.delete("/trash")
@user_limiter.limit(get_limit("admin_operations"))
async def empty_trash(
    request: Request, response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Empty the current user's trash (admins also wipe trashed system notifications)."""
    service = get_notification_service()
    count = service.empty_trash(
        db, current_user.id, is_admin=is_privileged(current_user)
    )
    return {"count": count}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd backend && python -m pytest tests/test_notifications_routes.py::TestTrashRoutes -v`
Expected: All trash route tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/notifications.py backend/tests/test_notifications_routes.py
git commit -m "feat(notifications): add DELETE /trash to empty current user's trash"
```

---

## Task 14: Background job — hourly trash cleanup

**Files:**
- Modify: `backend/app/services/notifications/scheduler.py`

- [ ] **Step 1: Inspect the current scheduler structure**

Open `backend/app/services/notifications/scheduler.py`. Confirm `start_notification_scheduler` (around line 280) currently gates the whole scheduler on `FirebaseService.is_available()` and registers only `device_expiration_check`.

- [ ] **Step 2: Refactor to always-on scheduler, gated device-expiration job**

Replace the entire `start_notification_scheduler` function (lines 280–303 in the current file) with:

```python
def start_notification_scheduler() -> None:
    """Start the notification scheduler background job."""
    global _notification_scheduler
    if _notification_scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed, notification scheduler disabled")
        return

    _notification_scheduler = BackgroundScheduler()

    # Always-on: hourly trash cleanup (independent of Firebase)
    _notification_scheduler.add_job(
        func=_run_trash_cleanup,
        trigger="interval",
        hours=1,
        id="notification_trash_cleanup",
        name="Hard-delete expired trashed notifications",
        replace_existing=True,
    )

    # Firebase-dependent: device expiration warnings
    if FirebaseService.is_available():
        _notification_scheduler.add_job(
            func=NotificationScheduler.run_periodic_check,
            trigger="interval",
            hours=1,
            id="device_expiration_check",
            name="Check and send device expiration warnings",
            replace_existing=True,
        )
    else:
        logger.info("Device expiration check skipped (Firebase not configured)")

    _notification_scheduler.start()
    logger.info("Notification scheduler started (running every hour)")
```

- [ ] **Step 3: Add the trash-cleanup helper**

Immediately above `start_notification_scheduler` in the same file, add:

```python
def _run_trash_cleanup() -> None:
    """Hourly job: hard-delete notifications past their retention."""
    db = SessionLocal()
    try:
        from app.services.notifications.service import get_notification_service
        count = get_notification_service().cleanup_expired_trash(db)
        if count:
            logger.info("Trash cleanup: deleted %d expired notifications", count)
    except Exception:
        logger.exception("Trash cleanup job failed")
    finally:
        db.close()
```

- [ ] **Step 4: Smoke-test import + scheduler startup**

Run: `cd backend && python -c "from app.services.notifications.scheduler import start_notification_scheduler, stop_notification_scheduler; start_notification_scheduler(); stop_notification_scheduler(); print('OK')"`
Expected: `OK`. No traceback.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/scheduler.py
git commit -m "feat(notifications): hourly trash cleanup job (Firebase-independent)"
```

---

## Task 15: Frontend — API client types and functions

**Files:**
- Modify: `client/src/api/notifications.ts`

- [ ] **Step 1: Update the `Notification` interface**

In `client/src/api/notifications.ts`, find the `Notification` interface (around line 10) and replace `is_dismissed: boolean;` with:

```ts
  deleted_at: string | null;
```

- [ ] **Step 2: Update the `NotificationPreferences` interface**

Find the `NotificationPreferences` type definition (search for `interface NotificationPreferences` in the same file). Add (somewhere near the existing fields like `min_priority`):

```ts
  trash_retention_days: number; // 1-7
```

If there's a separate `NotificationPreferencesUpdate` type (for PUT requests), add the same field as `trash_retention_days?: number;`.

- [ ] **Step 3: Add trash API functions**

Append to `client/src/api/notifications.ts` (after the existing `dismissAllNotifications` function):

```ts
export interface GetTrashNotificationsParams {
  category?: NotificationCategory;
  notification_type?: NotificationType;
  created_after?: string;
  created_before?: string;
  page?: number;
  page_size?: number;
}

export const getTrashNotifications = async (
  params: GetTrashNotificationsParams = {}
): Promise<NotificationListResponse> => {
  const { data } = await apiClient.get<NotificationListResponse>(
    "/notifications/trash",
    { params }
  );
  return data;
};

export const restoreNotification = async (
  id: number
): Promise<Notification> => {
  const { data } = await apiClient.post<Notification>(
    `/notifications/${id}/restore`
  );
  return data;
};

export const deleteNotificationPermanently = async (id: number): Promise<void> => {
  await apiClient.delete(`/notifications/${id}`);
};

export const emptyTrash = async (): Promise<{ count: number }> => {
  const { data } = await apiClient.delete<{ count: number }>(
    "/notifications/trash"
  );
  return data;
};
```

Check the existing `getNotifications` function to verify the actual axios import name (`apiClient`, `api`, or similar) and adjust if needed.

- [ ] **Step 4: Run typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: Errors should be limited to call sites in components that still reference the old `is_dismissed` (we'll fix those in Tasks 16 & 19). The new functions themselves should typecheck.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/notifications.ts
git commit -m "feat(notifications): frontend types + trash API functions"
```

---

## Task 16: Frontend — Inbox / Trash tabs

**Files:**
- Modify: `client/src/pages/NotificationsArchivePage.tsx`
- Modify: `client/src/i18n/locales/de/notifications.json`
- Modify: `client/src/i18n/locales/en/notifications.json`

- [ ] **Step 1: Add i18n keys**

In `client/src/i18n/locales/de/notifications.json`, add at the top level of the JSON object (mind the trailing comma on the prior field):

```json
  "tabs": {
    "inbox": "Posteingang",
    "trash": "Papierkorb"
  },
  "trash": {
    "empty": "Papierkorb leeren",
    "emptyConfirm": "Alle {{count}} Einträge endgültig löschen?",
    "restore": "Wiederherstellen",
    "deleteForever": "Endgültig löschen",
    "deleteForeverConfirm": "Diesen Eintrag endgültig löschen?",
    "banner": "Einträge werden nach {{days}} Tag(en) automatisch endgültig gelöscht.",
    "restored": "Wiederhergestellt",
    "deleted": "Endgültig gelöscht",
    "emptied": "Papierkorb geleert"
  }
```

In `client/src/i18n/locales/en/notifications.json`, add the same structure with English values:

```json
  "tabs": {
    "inbox": "Inbox",
    "trash": "Trash"
  },
  "trash": {
    "empty": "Empty trash",
    "emptyConfirm": "Permanently delete all {{count}} items?",
    "restore": "Restore",
    "deleteForever": "Delete forever",
    "deleteForeverConfirm": "Permanently delete this entry?",
    "banner": "Entries are automatically deleted after {{days}} day(s).",
    "restored": "Restored",
    "deleted": "Permanently deleted",
    "emptied": "Trash emptied"
  }
```

- [ ] **Step 2: Rewrite `NotificationsArchivePage` with tabs**

Replace the entire content of `client/src/pages/NotificationsArchivePage.tsx` with:

```tsx
/**
 * Notifications Archive Page
 *
 * Full paginated list of notifications with Inbox / Trash tabs and filters.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Bell, CheckCheck, Settings, Filter, ChevronLeft, ChevronRight, Clock,
  X, Trash2, RotateCcw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNotifications,
  getTrashNotifications,
  restoreNotification,
  deleteNotificationPermanently,
  emptyTrash as apiEmptyTrash,
  getPreferences,
  snoozeNotification,
  getTypeStyle,
  getCategoryIcon,
  getCategoryName,
  getActionLabel,
  type Notification,
  type NotificationCategory,
  type NotificationType,
  type NotificationListResponse,
} from '../api/notifications';
import { useNotifications } from '../contexts/NotificationContext';

const CATEGORIES: NotificationCategory[] = [
  'raid', 'smart', 'backup', 'scheduler', 'system', 'security', 'sync', 'vpn', 'lifecycle',
];

const TYPES: NotificationType[] = ['info', 'warning', 'critical'];

const PAGE_SIZE = 50;

type TabKey = 'inbox' | 'trash';

export default function NotificationsArchivePage() {
  const { t } = useTranslation(['notifications', 'common']);
  const navigate = useNavigate();
  const {
    markAsRead: ctxMarkAsRead,
    markAllAsRead: ctxMarkAllAsRead,
    dismiss: ctxDismiss,
    dismissAll: ctxDismissAll,
    refresh: ctxRefresh,
  } = useNotifications();

  const [tab, setTab] = useState<TabKey>('inbox');
  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [retentionDays, setRetentionDays] = useState<number>(7);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<NotificationCategory | ''>('');
  const [typeFilter, setTypeFilter] = useState<NotificationType | ''>('');
  const [readFilter, setReadFilter] = useState<'' | 'unread'>('');

  // Load retention setting once for the trash banner
  useEffect(() => {
    getPreferences()
      .then((p) => setRetentionDays(p.trash_retention_days ?? 7))
      .catch(() => setRetentionDays(7));
  }, []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        notification_type: typeFilter || undefined,
      };
      const result =
        tab === 'inbox'
          ? await getNotifications({
              ...params,
              unread_only: readFilter === 'unread',
            })
          : await getTrashNotifications(params);
      setData(result);
    } catch {
      toast.error(t('common:toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [tab, page, categoryFilter, typeFilter, readFilter, t]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  // Reset to page 1 whenever the tab or any filter changes
  useEffect(() => {
    setPage(1);
  }, [tab, categoryFilter, typeFilter, readFilter]);

  const handleMarkAllRead = async () => {
    try {
      await ctxMarkAllAsRead();
      toast.success(t('toast.markedAllRead'));
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleDismissAll = async () => {
    if (!data || data.total === 0) return;
    if (!window.confirm(t('toast.confirmDismissAll', { count: data.total }))) return;
    try {
      await ctxDismissAll();
      toast.success(t('toast.movedToTrash'));
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleEmptyTrash = async () => {
    if (!data || data.total === 0) return;
    if (!window.confirm(t('trash.emptyConfirm', { count: data.total }))) return;
    try {
      const { count } = await apiEmptyTrash();
      toast.success(t('trash.emptied'));
      fetchList();
      // Inbox unread badge is unaffected by trash-empty, but a context refresh is cheap insurance
      if (count > 0) ctxRefresh();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleMarkRead = async (n: Notification) => {
    if (n.is_read) return;
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.map((x) =>
        x.id === n.id ? { ...x, is_read: true } : x
      ),
      unread_count: Math.max(0, prev.unread_count - 1),
    }));
    try { await ctxMarkAsRead(n.id); } catch { /* non-critical */ }
  };

  const handleDismiss = async (n: Notification) => {
    // Inbox X = move to trash
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
      unread_count: !n.is_read ? Math.max(0, prev.unread_count - 1) : prev.unread_count,
    }));
    try {
      await ctxDismiss(n.id);
    } catch {
      fetchList();
    }
  };

  const handleRestore = async (n: Notification) => {
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
    }));
    try {
      await restoreNotification(n.id);
      toast.success(t('trash.restored'));
      ctxRefresh();
    } catch {
      toast.error(t('common:toast.error'));
      fetchList();
    }
  };

  const handleDeleteForever = async (n: Notification) => {
    if (!window.confirm(t('trash.deleteForeverConfirm'))) return;
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
    }));
    try {
      await deleteNotificationPermanently(n.id);
      toast.success(t('trash.deleted'));
    } catch {
      toast.error(t('common:toast.error'));
      fetchList();
    }
  };

  const handleSnooze = async (n: Notification, hours: number) => {
    try {
      await snoozeNotification(n.id, hours);
      toast.success(`${hours}h snoozed`);
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{t('title')}</h1>
          <p className="text-sm text-slate-400">
            {data
              ? `${data.total} ${tab === 'inbox' ? t('count.total') : t('count.inTrash')}${tab === 'inbox' ? `, ${data.unread_count} ${t('count.unread')}` : ''}`
              : t('common:loading')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tab === 'inbox' && (
            <>
              <button
                onClick={handleMarkAllRead}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
              >
                <CheckCheck className="h-4 w-4" />
                {t('buttons.markAllRead')}
              </button>
              <button
                onClick={handleDismissAll}
                disabled={!data || data.total === 0}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-rose-500/50 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" />
                {t('buttons.dismissAll')}
              </button>
            </>
          )}
          {tab === 'trash' && (
            <button
              onClick={handleEmptyTrash}
              disabled={!data || data.total === 0}
              className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 px-3 py-2 text-sm text-rose-400 transition hover:border-rose-500 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" />
              {t('trash.empty')}
            </button>
          )}
          <button
            onClick={() => navigate('/settings?tab=notifications')}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            <Settings className="h-4 w-4" />
            {t('buttons.settings')}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-800">
        {(['inbox', 'trash'] as TabKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`relative px-4 py-2 text-sm transition ${
              tab === k
                ? 'text-sky-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t(`tabs.${k}`)}
            {tab === k && (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-sky-500" />
            )}
          </button>
        ))}
      </div>

      {/* Trash banner */}
      {tab === 'trash' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2 text-xs text-amber-300">
          {t('trash.banner', { days: retentionDays })}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <Filter className="h-4 w-4 text-slate-400" />

        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as NotificationCategory | '')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">{t('filters.allCategories')}</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{getCategoryIcon(c)} {getCategoryName(c)}</option>
          ))}
        </select>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as NotificationType | '')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">{t('filters.allTypes')}</option>
          {TYPES.map((tp) => (
            <option key={tp} value={tp}>{tp.charAt(0).toUpperCase() + tp.slice(1)}</option>
          ))}
        </select>

        {tab === 'inbox' && (
          <select
            value={readFilter}
            onChange={(e) => setReadFilter(e.target.value as '' | 'unread')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
          >
            <option value="">{t('filters.default')}</option>
            <option value="unread">{t('filters.unreadOnly')}</option>
          </select>
        )}
      </div>

      {/* List */}
      <div className="space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          </div>
        ) : !data || data.notifications.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Bell className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p>{tab === 'inbox' ? t('empty.inbox') : t('empty.trash')}</p>
          </div>
        ) : (
          data.notifications.map((n) => (
            <NotificationRow
              key={n.id}
              tab={tab}
              notification={n}
              onMarkRead={handleMarkRead}
              onDismiss={handleDismiss}
              onRestore={handleRestore}
              onDeleteForever={handleDeleteForever}
              onSnooze={handleSnooze}
              onNavigate={(url) => navigate(url)}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-slate-700 p-2 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-slate-400">
            {t('pagination.pageOf', { page, total: totalPages })}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded-lg border border-slate-700 p-2 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

/** Individual notification row with actions */
function NotificationRow({
  tab,
  notification: n,
  onMarkRead,
  onDismiss,
  onRestore,
  onDeleteForever,
  onSnooze,
  onNavigate,
}: {
  tab: TabKey;
  notification: Notification;
  onMarkRead: (n: Notification) => void;
  onDismiss: (n: Notification) => void;
  onRestore: (n: Notification) => void;
  onDeleteForever: (n: Notification) => void;
  onSnooze: (n: Notification, hours: number) => void;
  onNavigate: (url: string) => void;
}) {
  const [showSnooze, setShowSnooze] = useState(false);
  const { t } = useTranslation(['notifications']);
  const typeStyle = getTypeStyle(n.notification_type);

  return (
    <div
      className={`group relative flex items-start gap-4 rounded-xl border px-4 py-3 transition ${
        !n.is_read
          ? 'border-slate-700 bg-slate-800/50'
          : 'border-slate-800/50 bg-slate-900/30'
      }`}
    >
      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}>
        <span className="text-lg">{getCategoryIcon(n.category)}</span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm font-medium ${!n.is_read ? 'text-slate-100' : 'text-slate-300'}`}>
            {n.title}
          </p>
          <span className="flex-shrink-0 text-xs text-slate-500">{n.time_ago}</span>
        </div>
        <p className="mt-0.5 text-xs text-slate-400">{n.message}</p>
        <div className="mt-1.5 flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${typeStyle.bgColor} ${typeStyle.color}`}>
            {n.notification_type}
          </span>
          <span className="text-[10px] text-slate-500">{getCategoryName(n.category)}</span>
          {n.snoozed_until && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">
              <Clock className="h-3 w-3" />
              Snoozed bis {new Date(n.snoozed_until).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-shrink-0 items-center gap-1">
        {n.action_url && tab === 'inbox' && (
          <button
            onClick={() => onNavigate(n.action_url!)}
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            {getActionLabel(n.category)}
          </button>
        )}

        {tab === 'inbox' && (
          <>
            <div className="relative">
              <button
                onClick={() => setShowSnooze(!showSnooze)}
                className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
                title="Snooze"
              >
                <Clock className="h-4 w-4" />
              </button>
              {showSnooze && (
                <div className="absolute right-0 top-8 z-10 rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl">
                  {[1, 4, 24].map((h) => (
                    <button
                      key={h}
                      onClick={() => { onSnooze(n, h); setShowSnooze(false); }}
                      className="block w-full px-4 py-1.5 text-left text-xs text-slate-300 transition hover:bg-slate-700"
                    >
                      {h}h
                    </button>
                  ))}
                </div>
              )}
            </div>

            {!n.is_read && (
              <button
                onClick={() => onMarkRead(n)}
                className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
                title={t('buttons.markRead')}
              >
                <CheckCheck className="h-4 w-4" />
              </button>
            )}

            <button
              onClick={() => onDismiss(n)}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
              title={t('buttons.moveToTrash')}
            >
              <X className="h-4 w-4" />
            </button>
          </>
        )}

        {tab === 'trash' && (
          <>
            <button
              onClick={() => onRestore(n)}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-sky-400"
              title={t('trash.restore')}
            >
              <RotateCcw className="h-4 w-4" />
            </button>
            <button
              onClick={() => onDeleteForever(n)}
              className="rounded-lg p-1.5 text-rose-500 transition hover:bg-rose-500/10 hover:text-rose-400"
              title={t('trash.deleteForever')}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add missing i18n keys this component references**

In `client/src/i18n/locales/de/notifications.json`, ensure these keys exist (add any missing — they are referenced by the new component):

```json
  "title": "Benachrichtigungen",
  "count": {
    "total": "gesamt",
    "inTrash": "im Papierkorb",
    "unread": "ungelesen"
  },
  "buttons": {
    "markAllRead": "Alle gelesen",
    "dismissAll": "Alle löschen",
    "settings": "Einstellungen",
    "markRead": "Als gelesen markieren",
    "moveToTrash": "In Papierkorb"
  },
  "filters": {
    "allCategories": "Alle Kategorien",
    "allTypes": "Alle Typen",
    "default": "Standard",
    "unreadOnly": "Nur ungelesen"
  },
  "empty": {
    "inbox": "Keine Benachrichtigungen",
    "trash": "Papierkorb ist leer"
  },
  "pagination": {
    "pageOf": "Seite {{page}} von {{total}}"
  },
  "toast": {
    "markedAllRead": "Alle als gelesen markiert",
    "movedToTrash": "In Papierkorb verschoben",
    "confirmDismissAll": "{{count}} Benachrichtigungen in Papierkorb verschieben?"
  }
```

(Some of these keys may already exist — only add the missing ones. The point is the component now relies on them via `t()`.)

In `client/src/i18n/locales/en/notifications.json`, mirror with English values.

- [ ] **Step 4: Run typecheck and dev server**

Run: `cd client && npx tsc --noEmit`
Expected: No errors related to this file.

Run dev server (`cd client && npm run dev` in another shell) and visit `/notifications`. Verify:
- Tabs switch between Inbox and Trash
- Trash banner displays the correct retention day count
- X icon in inbox moves a notification to the trash (verify by switching tabs)
- Restore icon brings it back
- Delete-forever icon prompts and removes it

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/NotificationsArchivePage.tsx client/src/i18n/locales/de/notifications.json client/src/i18n/locales/en/notifications.json
git commit -m "feat(notifications): Inbox/Trash tabs with restore + delete-forever"
```

---

## Task 17: Frontend — Retention slider in preferences

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`
- Modify: `client/src/i18n/locales/de/notifications.json`
- Modify: `client/src/i18n/locales/en/notifications.json`

- [ ] **Step 1: Add i18n keys**

Add to both notifications.json files (DE and EN), at the top level:

```json
  "retention": {
    "title": "Papierkorb",
    "label": "Aufbewahrung gelöschter Benachrichtigungen",
    "days_one": "{{count}} Tag",
    "days_other": "{{count}} Tage",
    "hint": "Nach Ablauf werden Einträge automatisch endgültig entfernt."
  }
```

English values:

```json
  "retention": {
    "title": "Trash",
    "label": "Retention for deleted notifications",
    "days_one": "{{count}} day",
    "days_other": "{{count}} days",
    "hint": "After the retention period entries are automatically removed."
  }
```

- [ ] **Step 2: Add state and slider section**

In `client/src/pages/NotificationPreferencesPage.tsx`:

After the `const [minPriority, setMinPriority] = useState(0);` line (around line 69), add:

```tsx
  const [trashRetentionDays, setTrashRetentionDays] = useState<number>(7);
```

In the `loadPreferences` function, after `setMinPriority(prefs.min_priority);` (around line 100), add:

```tsx
      setTrashRetentionDays(prefs.trash_retention_days ?? 7);
```

In `handleSave`, change the `updatePreferences` call (around line 139) to include the new field. Replace:

```tsx
      await updatePreferences({
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursEnabled ? quietHoursStart : null,
        quiet_hours_end: quietHoursEnabled ? quietHoursEnd : null,
        min_priority: minPriority,
        category_preferences: categoryPrefs,
      });
```

with:

```tsx
      await updatePreferences({
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursEnabled ? quietHoursStart : null,
        quiet_hours_end: quietHoursEnabled ? quietHoursEnd : null,
        min_priority: minPriority,
        category_preferences: categoryPrefs,
        trash_retention_days: trashRetentionDays,
      });
```

Add the slider section. Place it AFTER the Quiet Hours block (around line 318, after the closing `</div>` of the quiet hours section). Insert this JSX:

```tsx
      {/* Trash Retention */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="mb-3">
          <h2 className="text-lg font-semibold text-slate-100">{t('retention.title')}</h2>
          <p className="text-sm text-slate-400">{t('retention.hint')}</p>
        </div>
        <label className="block text-sm text-slate-300 mb-2">
          {t('retention.label')}: <span className="font-medium text-sky-400">{t('retention.days', { count: trashRetentionDays })}</span>
        </label>
        <input
          type="range"
          min={1}
          max={7}
          step={1}
          value={trashRetentionDays}
          onChange={(e) => setTrashRetentionDays(Number(e.target.value))}
          className="w-full max-w-md accent-sky-500"
        />
        <div className="flex justify-between text-xs text-slate-500 max-w-md mt-1">
          <span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span><span>7</span>
        </div>
      </div>
```

(Note: i18next pluralization picks `days_one` for `count === 1` and `days_other` otherwise — the key `retention.days` resolves correctly.)

- [ ] **Step 3: Typecheck + dev server**

Run: `cd client && npx tsc --noEmit`
Expected: Clean.

In the dev server, navigate to settings → notifications. Verify:
- Retention slider renders with the current value (default 7)
- Moving the slider updates the label
- Clicking "Save" persists and reloading the page keeps the new value

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx client/src/i18n/locales/de/notifications.json client/src/i18n/locales/en/notifications.json
git commit -m "feat(notifications): user-configurable trash retention slider (1-7 days)"
```

---

## Task 18: Frontend — fix `notificationGrouping.test.ts` fixture

**Files:**
- Modify: `client/src/__tests__/lib/notificationGrouping.test.ts`

- [ ] **Step 1: Update the fixture**

In `client/src/__tests__/lib/notificationGrouping.test.ts`, find line 12 (`is_dismissed: false,`) and replace with:

```ts
    deleted_at: null,
```

If there are multiple fixtures in the file with `is_dismissed`, replace all of them in the same manner.

- [ ] **Step 2: Run frontend tests**

Run: `cd client && npm run test`
Expected: All tests pass. If any other test still references `is_dismissed`, update those too.

- [ ] **Step 3: Commit**

```bash
git add client/src/__tests__/lib/notificationGrouping.test.ts
git commit -m "test(notifications): align grouping fixture with deleted_at field"
```

---

## Task 19: Full backend + frontend regression run

**Files:** none (sanity gate before smoketest)

- [ ] **Step 1: Run backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: All previously-passing tests still pass plus the new trash tests added in Tasks 1–13. If anything fails referencing `is_dismissed` or `include_dismissed`, fix the caller in the same style as the service refactor in Task 8.

- [ ] **Step 2: Run frontend typecheck and tests**

Run: `cd client && npx tsc --noEmit`
Expected: No errors.

Run: `cd client && npm run test`
Expected: All tests pass.

- [ ] **Step 3: If issues found, fix and re-run**

If any fix is required, commit each fix with a focused message such as `fix(notifications): <what changed>`.

---

## Task 20: Manual E2E smoketest

**Files:** none (manual verification)

- [ ] **Step 1: Start dev server**

Run: `python start_dev.py`
Expected: Backend on port 3001, frontend on 5173.

- [ ] **Step 2: Click through the user-visible flow**

Log in as admin. Then:

1. Navigate to `/notifications`. Note unread count.
2. Click the X icon on a notification → the row disappears from inbox.
3. Switch to the **Papierkorb** tab → confirm the row is here. Verify the banner shows "Einträge werden nach 7 Tag(en) automatisch endgültig gelöscht."
4. Click **Wiederherstellen** (RotateCcw icon) → row vanishes from trash. Switch back to **Inbox** → row is back.
5. Click X again, switch to **Papierkorb**, click the red trash icon → confirm → row is gone permanently. Switching back to Inbox does NOT show it.
6. Click "Alle löschen" on the Inbox → confirm → all rows go to the trash.
7. In Papierkorb, click "Papierkorb leeren" → confirm → trash is empty.
8. Navigate to **Settings → Notifications**. Set retention slider to 1 day. Click Save.
9. Navigate back to `/notifications` → Papierkorb tab → banner now says "1 Tag".

- [ ] **Step 3: Verify the cleanup job (optional, takes patience or DB poke)**

Either wait an hour for the scheduler tick, or in a Python shell:

```python
from app.core.database import SessionLocal
from app.models.notification import Notification
from datetime import datetime, timezone, timedelta
db = SessionLocal()
# Mark an existing trashed row as 2 days old
n = db.query(Notification).filter(Notification.deleted_at.is_not(None)).first()
n.deleted_at = datetime.now(timezone.utc) - timedelta(days=2)
db.commit()
db.close()
# Trigger cleanup
from app.services.notifications.service import get_notification_service
db = SessionLocal()
print("deleted:", get_notification_service().cleanup_expired_trash(db))
db.close()
```

Expected: Prints `deleted: 1` (or more). Refresh the page; the row is gone.

- [ ] **Step 4: Final commit (if any new fixes during smoketest)**

If issues surfaced during smoketest, fix them, run regression again (Task 19), and commit with focused messages.

---

## Self-Review Checklist

After all tasks above complete:

- [ ] All `is_dismissed` references in production code are gone (`PowerShell: Get-ChildItem backend, client -Recurse -Include *.py, *.ts, *.tsx | Select-String 'is_dismissed' -SimpleMatch` should return only the Alembic file `014_add_notification_tables.py` which is historical)
- [ ] All `include_dismissed` references are gone
- [ ] `cleanup_old_notifications` is gone
- [ ] New endpoints are reachable (`curl http://localhost:3001/docs` shows `/trash`, `/{id}/restore`, `/{id} DELETE`, `/trash DELETE`)
- [ ] Background job is registered (check logs at startup: `Notification scheduler started`)
- [ ] Frontend dev server: tabs render, slider saves, all actions work
