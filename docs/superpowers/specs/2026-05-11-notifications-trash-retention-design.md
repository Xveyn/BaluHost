# Notifications Trash + Retention

**Date:** 2026-05-11
**Status:** Approved

## Problem

The notifications page (`/notifications`) currently exposes two destructive-looking actions ("Alle löschen" header button, X icon per row) that internally call `POST /notifications/dismiss-all` / `POST /notifications/{id}/dismiss`. These set `is_dismissed=TRUE` — a soft-hide. Rows stay in the DB forever, surfaceable via the `include_dismissed=true` filter. There is:

- No real "deleted" state and no recovery UI for accidental dismissals
- No retention/cleanup — `cleanup_old_notifications(retention_days=90)` exists in the service but is wired to no background job
- No user-facing way to control how long deleted notifications stick around
- A UX inconsistency: the button reads "Alle löschen" but the row-icon tooltip reads "Ausblenden"

## Solution

Replace the boolean `is_dismissed` with a `deleted_at: DateTime | None` timestamp that doubles as both the trash-marker and the retention start. Add a per-user retention setting (1–7 days, default 7). Auto-purge expired trash via an hourly background job. Expose a dedicated Trash tab on the existing archive page with Restore / Permanent-Delete actions.

## Requirements

- Dismissing a notification (X icon, "Alle löschen") moves it to the trash, not just hides it
- The trash is a separate, browsable view with the same filters as the inbox
- Each user configures retention between 1 and 7 days (default 7); system notifications (`user_id=NULL`) use a fixed 7-day retention
- Restore returns a notification to the inbox (clears `deleted_at`)
- Permanent delete is irreversible; "Papierkorb leeren" wipes the current user's trash entirely
- After retention expires, the background job hard-deletes rows
- No information about other users' notifications leaks via 403 vs 404 (use 404 uniformly)

## Design

### 1. Schema

#### `notifications` table

| Change | Detail |
|---|---|
| Drop column | `is_dismissed BOOLEAN` |
| Add column | `deleted_at TIMESTAMPTZ NULL` |
| Add index | `ix_notifications_deleted_at ON (deleted_at)` |

#### `notification_preferences` table

| Change | Detail |
|---|---|
| Add column | `trash_retention_days INTEGER NOT NULL DEFAULT 7` |
| Add check | `CHECK (trash_retention_days BETWEEN 1 AND 7)` |

#### Semantics

- `deleted_at IS NULL` → active (inbox)
- `deleted_at IS NOT NULL` → in trash, retention starts at `deleted_at`
- Cleanup deletes rows where `NOW() - deleted_at > retention`

### 2. Migration

Single Alembic revision. Uses `batch_alter_table` so the migration works against both PostgreSQL (prod) and SQLite (dev). `CURRENT_TIMESTAMP` and the truthy-bareword `WHERE is_dismissed` are portable across both engines.

```python
def upgrade():
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "ix_notifications_deleted_at", ["deleted_at"]
        )

    # Backfill: existing soft-dismissed rows start their retention now.
    op.execute(
        "UPDATE notifications SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE is_dismissed"
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("is_dismissed")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.add_column(
            sa.Column("trash_retention_days", sa.Integer(),
                      nullable=False, server_default="7")
        )
        batch_op.create_check_constraint(
            "ck_trash_retention_1_7",
            "trash_retention_days BETWEEN 1 AND 7"
        )


def downgrade():
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("is_dismissed", sa.Boolean(),
                      nullable=False, server_default=sa.text("0"))
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

Existing dismissed rows get a fresh retention clock starting at migration time. On a production DB with O(thousands) rows the `UPDATE` + `DROP COLUMN` finish in under a second; Postgres performs both atomically inside the migration transaction.

### 3. Backend

#### Model (`backend/app/models/notification.py`)

```python
class Notification(Base):
    # ... existing fields except is_dismissed ...
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            # ... existing fields ...
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class NotificationPreferences(Base):
    # ... existing fields ...
    trash_retention_days: Mapped[int] = mapped_column(
        Integer, default=7, nullable=False
    )
```

#### Schemas (`backend/app/schemas/notification.py`)

- `NotificationResponse`: replace `is_dismissed: bool = False` with `deleted_at: Optional[datetime] = None`. `from_db` maps directly.
- `NotificationPreferencesResponse` + `NotificationPreferencesUpdate`: add `trash_retention_days: int = Field(default=7, ge=1, le=7)`.

#### Service (`backend/app/services/notifications/service.py`)

All existing filters change `Notification.is_dismissed == False` → `Notification.deleted_at.is_(None)`.

Method changes:

| Method | Behavior |
|---|---|
| `dismiss(id, user_id, is_admin)` | Sets `deleted_at = func.now()`, `is_read = True`. Idempotent if already trashed (no-op). |
| `dismiss_all(user_id, is_admin)` | Bulk update over `deleted_at IS NULL`. |
| `restore(id, user_id, is_admin)` *(new)* | Sets `deleted_at = None`. Idempotent for already-active rows. Returns the notification or `None` if not found. |
| `delete_permanently(id, user_id, is_admin)` *(new)* | Hard `DELETE` with ownership filter. Returns `True` if a row was deleted, `False` otherwise. |
| `empty_trash(user_id, is_admin)` *(new)* | `DELETE WHERE deleted_at IS NOT NULL AND <user_filter>`. Returns count. |
| `cleanup_expired_trash(db)` *(new, replaces `cleanup_old_notifications`)* | Two-step delete: (a) for each user-owned row: `now - deleted_at > prefs.trash_retention_days` (default 7 if no prefs row); (b) for `user_id IS NULL` rows: fixed 7-day cutoff. Returns total deleted count. |
| `get_user_notifications(...)` | New parameter `trashed_only: bool = False`. Removes `include_dismissed` parameter (callers updated). Inbox: `deleted_at IS NULL`. Trash: `deleted_at IS NOT NULL`. |
| `count_user_notifications(...)` | Same parameter change as above. |
| `get_unread_count(s)` | Adds `deleted_at IS NULL` filter (trashed items don't count as unread). |

Delete the unused `cleanup_old_notifications` method — no current caller exists.

Implementation sketch for `cleanup_expired_trash`:

```python
def cleanup_expired_trash(self, db: Session) -> int:
    now = datetime.now(timezone.utc)

    # Per-user retention via JOIN with prefs (default 7 if no prefs row)
    users_with_trash = (
        db.query(Notification.user_id)
        .filter(Notification.deleted_at.is_not(None),
                Notification.user_id.is_not(None))
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
            .filter(Notification.user_id == user_id,
                    Notification.deleted_at.is_not(None),
                    Notification.deleted_at < cutoff)
            .delete(synchronize_session=False)
        )
        total += count

    # System notifications (user_id IS NULL): fixed 7-day retention
    sys_cutoff = now - timedelta(days=7)
    total += (
        db.query(Notification)
        .filter(Notification.user_id.is_(None),
                Notification.deleted_at.is_not(None),
                Notification.deleted_at < sys_cutoff)
        .delete(synchronize_session=False)
    )

    db.commit()
    return total
```

#### Routes (`backend/app/api/routes/notifications.py`)

Existing routes keep their paths but their semantics shift: `POST /{id}/dismiss` and `POST /dismiss-all` now move to trash instead of soft-hiding. Update docstrings.

New endpoints:

| Method | Path | Returns | Description |
|---|---|---|---|
| `GET` | `/notifications/trash` | `NotificationListResponse` | Paginated trash, same filter params as inbox (category, type, dates, page) |
| `POST` | `/notifications/{id}/restore` | `NotificationResponse` | Move back to inbox; 404 if id not found / not owned |
| `DELETE` | `/notifications/{id}` | `204 No Content` | Hard delete; 404 if not found / not owned |
| `DELETE` | `/notifications/trash` | `{count: int}` | Empty current user's trash |

All four use `Depends(deps.get_current_user)` and `@user_limiter.limit(get_limit("admin_operations"))` to match existing patterns. Ownership uses the existing `_user_filter(user_id, is_admin)` helper.

After every state change, broadcast a new `unread_count` over WebSocket using the existing manager.

#### Background Job (`backend/app/services/notifications/scheduler.py`)

Move the APScheduler setup so the cleanup job runs even when Firebase is unavailable. Add:

```python
_scheduler.add_job(
    func=_run_trash_cleanup,
    trigger="interval", hours=1,
    id="notification_trash_cleanup",
    replace_existing=True,
)

def _run_trash_cleanup() -> None:
    db = SessionLocal()
    try:
        from app.services.notifications.service import get_notification_service
        count = get_notification_service().cleanup_expired_trash(db)
        if count:
            logger.info("Trash cleanup: deleted %d expired notifications", count)
    except Exception:
        logger.exception("Trash cleanup failed")
    finally:
        db.close()
```

The existing `device_expiration_check` job stays where it is (still gated by Firebase availability).

### 4. Frontend

#### API Client (`client/src/api/notifications.ts`)

```ts
export interface Notification {
  // ... existing fields except is_dismissed ...
  deleted_at: string | null;
}

export interface NotificationPreferences {
  // ... existing fields ...
  trash_retention_days: number; // 1-7
}

export const getTrashNotifications = (params: GetNotificationsParams) =>
  apiClient.get<NotificationListResponse>("/notifications/trash", { params });

export const restoreNotification = (id: number) =>
  apiClient.post<Notification>(`/notifications/${id}/restore`);

export const deleteNotificationPermanently = (id: number) =>
  apiClient.delete<void>(`/notifications/${id}`);

export const emptyTrash = () =>
  apiClient.delete<{ count: number }>("/notifications/trash");
```

#### Archive Page (`client/src/pages/NotificationsArchivePage.tsx`)

Replace the existing `readFilter` dropdown ("Standard / Nur ungelesen / Inkl. ausgeblendet") with a tab switcher above the filter bar:

```
┌── Inbox (8) ──┐ ┌── Papierkorb (3) ──┐
└───────────────┘ └─────────────────────┘
```

- Active tab styling matches existing tab patterns (rounded border-bottom emphasis).
- The category/type filter bar stays and applies to both tabs.
- Inbox tab:
  - Header buttons: "Alle gelesen", "Alle löschen", "Einstellungen" (unchanged labels; "Alle löschen" now moves to trash)
  - Row icons: Snooze, Mark-as-read, X ("In Papierkorb")
- Trash tab:
  - Header buttons: "Papierkorb leeren" (rose-500 accent, `window.confirm` first), "Einstellungen"
  - Banner above the list: `"Einträge werden nach {trash_retention_days} Tag(en) automatisch endgültig gelöscht."`
  - Row icons: RotateCcw ("Wiederherstellen"), Trash2 in rose ("Endgültig löschen", confirm)
- Tab counts come from two separate count endpoints / responses (Inbox unread_count + Trash total).

Optimistic updates on Restore / Permanent-Delete mirror the existing dismiss pattern; rollback by refetch on error.

#### Preferences Page (`client/src/pages/NotificationPreferencesPage.tsx`)

Add a new section above the Quiet Hours section:

```
┌─ Papierkorb ─────────────────────────────────────────┐
│ Aufbewahrung gelöschter Benachrichtigungen           │
│ [───●───]  3 Tage                                    │
│ Nach Ablauf werden Einträge automatisch entfernt.    │
└──────────────────────────────────────────────────────┘
```

Slider 1–7 with native HTML `<input type=range>`. Saves via the existing `PUT /notifications/preferences` endpoint (now accepts `trash_retention_days`).

#### Context (`client/src/contexts/NotificationContext.tsx`)

No structural change. The context still tracks active (inbox) notifications. The Trash tab fetches independently and does not feed the context. Optionally expose `restore`, `deletePermanently`, `emptyTrash` from the context so other parts of the UI (e.g., a future bell-dropdown undo toast) can call them — out of scope for this spec but the seam is there.

#### i18n (`client/src/i18n/locales/{de,en}/notifications.json`)

Add keys: `tabs.inbox`, `tabs.trash`, `trash.empty`, `trash.emptyConfirm`, `trash.banner`, `trash.restore`, `trash.deleteForever`, `trash.deleteForeverConfirm`, `preferences.retention.title`, `preferences.retention.label`, `preferences.retention.hint`.

### 5. Edge Cases

| Case | Handling |
|---|---|
| `restore(id)` for a row with `deleted_at IS NULL` | 200 OK, idempotent no-op |
| `restore(id)` / `delete_permanently(id)` for unknown or unowned id | 404 (never 403, to avoid id-enumeration leaks) |
| User has no `NotificationPreferences` row | Default retention 7 days applied in `cleanup_expired_trash` |
| System notifications (`user_id=NULL`) | Fixed 7-day retention regardless of admin prefs (admins have independent prefs that would conflict) |
| Cleanup job error (DB, lock, etc.) | `logger.exception`, swallow; next hourly tick retries |
| Multiple Uvicorn workers | APScheduler is initialized per worker; the cleanup query is idempotent (one transaction commits; others find nothing to delete) — no `IS_PRIMARY_WORKER` gate needed |
| Retention < 1 or > 7 in `PUT /preferences` | Pydantic `Field(ge=1, le=7)` → 422 |
| Existing `is_dismissed=TRUE` rows at migration | Get `deleted_at = NOW()` → visible in trash for 7 more days, then auto-purged |
| WebSocket clients during dismiss/restore/delete | Existing `unread_count` broadcast covers state changes; no new event type required |

### 6. Tests

#### Service (`backend/tests/services/test_notification_service.py`)

| Test | Verifies |
|---|---|
| `test_dismiss_sets_deleted_at` | `dismiss()` populates `deleted_at` with a timestamp ≤ now |
| `test_dismiss_idempotent_on_already_trashed` | Second `dismiss` does not overwrite original `deleted_at` |
| `test_restore_clears_deleted_at` | `restore()` sets `deleted_at` back to `None` |
| `test_restore_idempotent_on_active` | `restore()` on a non-trashed row is a no-op, returns the row |
| `test_delete_permanently_removes_row` | DB row count drops by 1; subsequent `restore` returns `None` |
| `test_empty_trash_removes_only_user_rows` | User B's trash is untouched when user A empties theirs |
| `test_empty_trash_admin_includes_system_notifications` | Admin's empty-trash also hard-deletes `user_id=NULL` trashed rows |
| `test_cleanup_expired_trash_respects_user_retention` | User with 3-day retention has 4-day-old row deleted; user with 7-day retention does not |
| `test_cleanup_expired_trash_default_when_no_prefs` | User without `NotificationPreferences` row uses 7-day default |
| `test_cleanup_expired_trash_system_notifications_fixed_7d` | `user_id=NULL` row older than 7 days is purged regardless of any admin's prefs |
| `test_get_user_notifications_inbox_excludes_trashed` | Default (`trashed_only=False`) filters out `deleted_at IS NOT NULL` |
| `test_get_user_notifications_trash_only_returns_trashed` | `trashed_only=True` returns only trashed |
| `test_get_unread_count_ignores_trashed` | Trashed unread rows do not contribute to count |

#### API (`backend/tests/test_notifications_routes.py`)

| Test | Verifies |
|---|---|
| `test_get_trash_paginated` | `GET /notifications/trash?page=1&page_size=10` returns only trashed, paginated |
| `test_restore_endpoint_round_trip` | After dismiss → restore, GET inbox shows the row again |
| `test_restore_endpoint_404_for_unknown_id` | 404 returned, not 403, for foreign user's id |
| `test_delete_permanently_returns_204` | DELETE returns 204 No Content; row gone from DB |
| `test_empty_trash_returns_count` | Response `{count: N}` matches actual deleted rows |
| `test_trash_retention_validation` | `PUT /preferences {trash_retention_days: 0}` → 422; `8` → 422; `3` → 200 |
| `test_trash_retention_persists` | Round-trip: PUT then GET returns same value |

#### Migration (`backend/tests/migrations/test_notification_trash_retention.py`)

Alembic stairway-style test:
- Seed two rows with `is_dismissed=TRUE` and one with `is_dismissed=FALSE` before upgrade
- Run `upgrade head` → assert dismissed rows now have `deleted_at IS NOT NULL` and within last 5 seconds; active row has `deleted_at IS NULL`
- Run `downgrade -1` → assert `is_dismissed` reflects `deleted_at IS NOT NULL`

#### Frontend (`client/src/__tests__/`)

| Test | Verifies |
|---|---|
| `NotificationsArchivePage.test.tsx :: switches between Inbox and Trash tabs` | Different list endpoints called, counts displayed |
| `NotificationsArchivePage.test.tsx :: restore from trash` | Row disappears from trash list optimistically |
| `NotificationsArchivePage.test.tsx :: empty trash button` | Confirms, then calls `DELETE /notifications/trash`, refetches |
| `NotificationPreferencesPage.test.tsx :: retention slider saves` | Slider change triggers `PUT /preferences` with new value |
| `notificationGrouping.test.ts` (existing) | Fixture updated from `is_dismissed: false` to `deleted_at: null` — existing assertions still pass |

#### E2E Smoketest (manual)

1. `python start_dev.py`
2. Click X on a notification → row vanishes from inbox
3. Switch to Papierkorb tab → row is there, banner shows 7-day notice
4. Click "Wiederherstellen" → row returns to inbox
5. Click X again, switch back to trash, click trash-icon → confirm → row gone
6. Settings → set retention to 1 day
7. (For test: manually `UPDATE notifications SET deleted_at = NOW() - INTERVAL '2 days'` on a trashed row)
8. Wait for next hourly cleanup (or trigger manually) → row physically gone

### 7. Build Order

1. Migration + model + `models/__init__.py` registration
2. Schema updates (`NotificationResponse`, preferences)
3. Service: switch existing filters, add new methods, write unit tests first (TDD)
4. Routes: new endpoints + docstring fixes on existing dismiss routes
5. Background job hook in `notifications/scheduler.py`
6. Frontend API client types + functions
7. `NotificationsArchivePage`: tabs + trash actions
8. `NotificationPreferencesPage`: retention slider
9. i18n keys
10. Smoketest

## Open Questions

None at spec-writing time. The system-notifications retention question raised during design was resolved: fixed 7 days for `user_id IS NULL`, per-user setting for the rest.

## API Compatibility Note

`NotificationResponse.is_dismissed` is removed from the response schema and replaced by `deleted_at`. This is a breaking change for any external consumer (BaluApp Android, BaluDesk) that reads the field. Grep on those repos before release; if either consumer reads `is_dismissed`, ship a coordinated update or keep `is_dismissed` as a computed alias in the schema for one release cycle:

```python
@computed_field
@property
def is_dismissed(self) -> bool:
    return self.deleted_at is not None
```

Default plan: clean break, no alias. Reassess only if downstream usage is found.

## Out of Scope

- Per-category retention overrides
- Bulk restore from trash (only single-row restore via the row icon)
- Admin-facing global trash management
- Surfacing the trash on mobile (BaluApp) or desktop sync (BaluDesk) clients — backend changes are universal but client UI is a separate effort
- Undo-toast pattern after dismiss (the trash itself is the undo affordance)
