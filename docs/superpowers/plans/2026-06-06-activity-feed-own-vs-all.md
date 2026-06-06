# Activity Feed own-vs-all + leak-fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-point the Dashboard "Recent Activity" widget from the leaky audit-log endpoint to the user-scoped `/api/activity` API, give admins an all-users view, and close the existing data-disclosure in `/api/logging/file-access`.

**Architecture:** Backend — add an `all_users` branch to `FileActivityService.get_recent_activities` (joins `users` for attribution) exposed via a `scope=mine|all` query param on `GET /api/activity/recent` (admin-gated for `all`); harden `GET /api/logging/file-access` so non-admins are forced to their own username. Frontend — a new typed `api/activity.ts` client, `useActivityFeed` re-pointed at it with action-type→icon/i18n-title mapping, and `ActivityFeed.tsx` passing `allUsers={isAdmin}` plus admin-gating the "View System Logs" button.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pytest (backend); React + TypeScript + axios + Vitest + i18next (frontend).

**Reference spec:** `docs/superpowers/specs/2026-06-06-activity-feed-own-vs-all-design.md`

---

## File Structure

Backend:
- `backend/app/schemas/file_activity.py` — add `user_id`, `username` to `ActivityItem`.
- `backend/app/services/file_activity.py` — `all_users` branch + join + `_to_activity_item(username=…)`.
- `backend/app/api/routes/activity.py` — `scope` param + admin gate.
- `backend/app/api/routes/logging.py` — non-admin self-scoping in `get_file_access_logs`.
- `backend/tests/test_file_activity.py` — service + route admin-scope tests.
- `backend/tests/test_logging_file_access_scope.py` (new) — leak-fix test.

Frontend:
- `client/src/api/activity.ts` (new) — typed client.
- `client/src/i18n/locales/de/dashboard.json`, `client/src/i18n/locales/en/dashboard.json` — action titles.
- `client/src/hooks/useActivityFeed.ts` — re-point + mapping + i18n.
- `client/src/components/dashboard/ActivityFeed.tsx` — `allUsers` + admin-gated button.
- `client/src/__tests__/hooks/useActivityFeed.test.ts` (new) — mapping tests.
- `client/src/__tests__/components/dashboard/ActivityFeed.test.tsx` (new) — admin-button gating.

---

## Task 1: Backend — extend `ActivityItem` + service `all_users` branch

**Files:**
- Modify: `backend/app/schemas/file_activity.py` (class `ActivityItem`, ~line 32-47)
- Modify: `backend/app/services/file_activity.py` (`get_recent_activities` ~line 132-174, `_to_activity_item` ~line 277-298)
- Test: `backend/tests/test_file_activity.py`

- [ ] **Step 1: Write the failing service tests**

Append to `backend/tests/test_file_activity.py` (inside `class TestFileActivityService`):

```python
    def test_get_recent_activities_sets_user_id_and_no_username_for_mine(self, db_session: Session):
        svc = self._make_service(db_session)
        svc.record(7, "file.upload", "u7/a.txt", "a.txt")
        db_session.commit()

        items, total = svc.get_recent_activities(user_id=7, limit=10)
        assert total == 1
        assert items[0].user_id == 7
        assert items[0].username is None

    def test_get_recent_activities_all_users_returns_cross_user_with_username(self, db_session: Session):
        from app.models.user import User

        alice = User(username="alice", email="alice@example.com", hashed_password="x", role="user")
        bob = User(username="bob", email="bob@example.com", hashed_password="x", role="user")
        db_session.add_all([alice, bob])
        db_session.commit()

        svc = self._make_service(db_session)
        svc.record(alice.id, "file.upload", "alice/a.txt", "a.txt")
        svc.record(bob.id, "file.download", "bob/b.txt", "b.txt")
        db_session.commit()

        # Scoped: alice sees only her own
        mine, mine_total = svc.get_recent_activities(user_id=alice.id, limit=10)
        assert mine_total == 1
        assert {i.file_name for i in mine} == {"a.txt"}

        # All users: both, each with the acting username populated
        everyone, total = svc.get_recent_activities(user_id=alice.id, limit=10, all_users=True)
        assert total == 2
        names = {i.file_name: i.username for i in everyone}
        assert names == {"a.txt": "alice", "b.txt": "bob"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_file_activity.py -k "all_users or user_id_and_no_username" -v`
Expected: FAIL — `TypeError: get_recent_activities() got an unexpected keyword argument 'all_users'` (and `ActivityItem` has no `user_id`/`username`).

- [ ] **Step 3: Add the schema fields**

In `backend/app/schemas/file_activity.py`, change `ActivityItem` to add the two fields (keep the rest):

```python
class ActivityItem(BaseModel):
    """Single activity entry in API responses."""

    id: int
    user_id: int
    username: Optional[str] = None
    action_type: str
    file_path: str
    file_name: str
    is_directory: bool
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    source: str
    device_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement the `all_users` branch in the service**

In `backend/app/services/file_activity.py`, replace `get_recent_activities` (the whole method) with:

```python
    def get_recent_activities(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        action_types: Optional[List[str]] = None,
        file_type: Optional[str] = None,
        since: Optional[datetime] = None,
        path_prefix: Optional[str] = None,
        all_users: bool = False,
    ) -> tuple[List[ActivityItem], int]:
        """Query recent activities.

        When ``all_users`` is True, returns activities across every user and
        populates ``ActivityItem.username`` (admin view). Otherwise scoped to
        ``user_id`` with ``username`` left as None.

        Returns (items, total_count).
        """
        from app.models.user import User

        if all_users:
            query = self.db.query(FileActivity, User.username).join(
                User, User.id == FileActivity.user_id
            )
        else:
            query = self.db.query(FileActivity).filter(
                FileActivity.user_id == user_id
            )

        if action_types:
            query = query.filter(FileActivity.action_type.in_(action_types))

        if since:
            query = query.filter(FileActivity.created_at >= since)

        if path_prefix:
            prefix = path_prefix.rstrip("/") + "/"
            query = query.filter(FileActivity.file_path.like(f"{prefix}%"))

        if file_type:
            query = self._apply_file_type_filter(query, file_type)

        total = query.count()

        rows = (
            query.order_by(desc(FileActivity.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        if all_users:
            items = [
                self._to_activity_item(row, username=username)
                for (row, username) in rows
            ]
        else:
            items = [self._to_activity_item(r) for r in rows]
        return items, total
```

- [ ] **Step 5: Update `_to_activity_item` to carry user_id + username**

In `backend/app/services/file_activity.py`, replace `_to_activity_item` with:

```python
    @staticmethod
    def _to_activity_item(
        row: FileActivity, username: Optional[str] = None
    ) -> ActivityItem:
        metadata = None
        if row.metadata_json:
            try:
                metadata = json.loads(row.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass

        return ActivityItem(
            id=row.id,
            user_id=row.user_id,
            username=username,
            action_type=row.action_type,
            file_path=row.file_path,
            file_name=row.file_name,
            is_directory=row.is_directory,
            file_size=row.file_size,
            mime_type=row.mime_type,
            source=row.source,
            device_id=row.device_id,
            metadata=metadata,
            created_at=row.created_at,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_file_activity.py -v`
Expected: PASS (new tests + all pre-existing ones).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/file_activity.py backend/app/services/file_activity.py backend/tests/test_file_activity.py
git commit -m "feat(activity): service all_users view + user attribution on ActivityItem"
```

---

## Task 2: Backend — `scope` param + admin gate on `/api/activity/recent`

**Files:**
- Modify: `backend/app/api/routes/activity.py` (`get_recent_activities` ~line 27-73)
- Test: `backend/tests/test_file_activity.py` (route-level tests)

- [ ] **Step 1: Write the failing route tests**

Append to `backend/tests/test_file_activity.py` (module level, outside the service class):

```python
from app.core.config import settings as app_settings


class TestActivityRouteScope:
    """Route-level tests for scope=mine|all on /api/activity/recent."""

    def _seed_two_users_activity(self, db_session):
        from app.models.user import User
        from app.services.file_activity import FileActivityService

        admin = db_session.query(User).filter(User.username == app_settings.admin_username).first()
        testuser = db_session.query(User).filter(User.username == "testuser").first()

        svc = FileActivityService(db_session)
        svc.record(admin.id, "file.upload", "admin/admin.txt", "admin.txt")
        svc.record(testuser.id, "file.upload", "testuser/user.txt", "user.txt")
        db_session.commit()

    def test_scope_mine_returns_only_own(self, client, db_session, user_headers):
        self._seed_two_users_activity(db_session)
        resp = client.get(
            f"{app_settings.api_prefix}/activity/recent?scope=mine&limit=50",
            headers=user_headers,
        )
        assert resp.status_code == 200
        names = {a["file_name"] for a in resp.json()["activities"]}
        assert names == {"user.txt"}

    def test_scope_all_forbidden_for_regular_user(self, client, db_session, user_headers):
        self._seed_two_users_activity(db_session)
        resp = client.get(
            f"{app_settings.api_prefix}/activity/recent?scope=all&limit=50",
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_scope_all_returns_cross_user_for_admin(self, client, db_session, admin_headers):
        self._seed_two_users_activity(db_session)
        resp = client.get(
            f"{app_settings.api_prefix}/activity/recent?scope=all&limit=50",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        activities = resp.json()["activities"]
        names = {a["file_name"] for a in activities}
        assert names == {"admin.txt", "user.txt"}
        # username is populated in the all-users view
        assert all(a["username"] for a in activities)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_file_activity.py::TestActivityRouteScope -v`
Expected: FAIL — `scope=all` returns 200 for a regular user (no gate yet) / `scope` is ignored.

- [ ] **Step 3: Implement the `scope` param + admin gate**

In `backend/app/api/routes/activity.py`, add the import near the other imports (after line 20):

```python
from app.services.permissions import is_privileged
```

Then replace the `get_recent_activities` handler signature and body up to the service call. The new signature adds `scope`, and the body gates `all`:

```python
@router.get("/recent", response_model=ActivityListResponse)
@user_limiter.limit(get_limit("file_list"))
async def get_recent_activities(
    request: Request,
    response: Response,
    limit: int = 20,
    offset: int = 0,
    action_types: Optional[str] = None,
    file_type: Optional[str] = None,
    since: Optional[datetime] = None,
    path_prefix: Optional[str] = None,
    scope: str = "mine",
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Get recent file activities.

    Args:
        limit: Max items (1-100, default 20).
        offset: Pagination offset.
        action_types: Comma-separated filter, e.g. ``file.open,file.download``.
        file_type: Filter by type: file, directory, image, video, document.
        since: ISO timestamp — only activities after this time.
        path_prefix: Only activities within this directory.
        scope: ``mine`` (own activity, default) or ``all`` (admin only — every
            user's activity, with the acting username populated).
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    all_users = scope == "all"
    if all_users and not is_privileged(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    parsed_types: Optional[List[str]] = None
    if action_types:
        parsed_types = [t.strip() for t in action_types.split(",") if t.strip()]

    svc = FileActivityService(db)
    items, total = svc.get_recent_activities(
        user_id=user.id,
        limit=limit,
        offset=offset,
        action_types=parsed_types,
        file_type=file_type,
        since=since,
        path_prefix=path_prefix,
        all_users=all_users,
    )

    return ActivityListResponse(
        activities=items,
        total=total,
        has_more=(offset + limit) < total,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_file_activity.py::TestActivityRouteScope -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/activity.py backend/tests/test_file_activity.py
git commit -m "feat(activity): scope=all admin view on /api/activity/recent"
```

---

## Task 3: Backend — close the data leak in `/api/logging/file-access`

**Files:**
- Modify: `backend/app/api/routes/logging.py` (`get_file_access_logs` ~line 161-203)
- Test: `backend/tests/test_logging_file_access_scope.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_logging_file_access_scope.py`:

```python
"""Regression test: /api/logging/file-access must not leak other users' activity."""
from app.core.config import settings
from app.services.audit.logger_db import get_audit_logger_db


def _seed_file_access(db_session):
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="FILE_ACCESS", user=settings.admin_username,
        action="download", resource="/admin/secret.pdf", db=db_session,
    )
    audit.log_event(
        event_type="FILE_ACCESS", user="testuser",
        action="upload", resource="/testuser/note.txt", db=db_session,
    )
    db_session.commit()


def test_regular_user_only_sees_own_file_access(client, db_session, user_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100",
        headers=user_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert users == {"testuser"}


def test_regular_user_cannot_widen_with_user_param(client, db_session, user_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100&user={settings.admin_username}",
        headers=user_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert users <= {"testuser"}  # empty or only own — never the admin's


def test_admin_sees_all_file_access(client, db_session, admin_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert {settings.admin_username, "testuser"} <= users
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_logging_file_access_scope.py -v`
Expected: FAIL — `test_regular_user_only_sees_own_file_access` sees `{"admin", "testuser"}` (leak).

- [ ] **Step 3: Implement the self-scoping**

In `backend/app/api/routes/logging.py`, add the import after line 10 (`from app.api.deps import get_current_user, get_db`):

```python
from app.services.permissions import is_privileged
```

In `get_file_access_logs`, immediately before `audit = get_audit_logger_db()` (~line 188), insert:

```python
    # Non-admins may only ever see their own file-access entries — prevent the
    # widget (and any direct caller) from reading other users' paths/usernames.
    if not is_privileged(current_user):
        user = current_user.username
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_logging_file_access_scope.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/logging.py backend/tests/test_logging_file_access_scope.py
git commit -m "fix(logging): scope file-access logs to own user for non-admins"
```

---

## Task 4: Frontend — new typed `api/activity.ts` client

**Files:**
- Create: `client/src/api/activity.ts`

- [ ] **Step 1: Create the client module**

Create `client/src/api/activity.ts`:

```typescript
import { apiClient } from '../lib/api';

export interface ActivityItem {
  id: number;
  user_id: number;
  username?: string | null;
  action_type: string;
  file_path: string;
  file_name: string;
  is_directory: boolean;
  file_size?: number | null;
  mime_type?: string | null;
  source: string;
  device_id?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityListResponse {
  activities: ActivityItem[];
  total: number;
  has_more: boolean;
}

export interface GetRecentActivitiesParams {
  limit?: number;
  offset?: number;
  scope?: 'mine' | 'all';
}

export async function getRecentActivities(
  params: GetRecentActivitiesParams = {},
): Promise<ActivityListResponse> {
  const { limit = 20, offset = 0, scope = 'mine' } = params;
  const { data } = await apiClient.get<ActivityListResponse>('/api/activity/recent', {
    params: { limit, offset, scope },
  });
  return data;
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors from `api/activity.ts`.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/activity.ts
git commit -m "feat(activity): typed api/activity client for /api/activity/recent"
```

---

## Task 5: Frontend — i18n action-title keys (de/en)

**Files:**
- Modify: `client/src/i18n/locales/de/dashboard.json`
- Modify: `client/src/i18n/locales/en/dashboard.json`

- [ ] **Step 1: Add the keys to the English locale**

In `client/src/i18n/locales/en/dashboard.json`, locate the existing `"activity"` object and add an `"actions"` sub-object inside it (alongside `title`, `liveOperations`, etc.):

```json
    "actions": {
      "upload": "File Uploaded",
      "download": "File Downloaded",
      "delete": "File Deleted",
      "edit": "File Edited",
      "open": "File Opened",
      "move": "File Moved",
      "rename": "File Renamed",
      "share": "File Shared",
      "permission": "Permissions Changed",
      "create": "Folder Created",
      "sync": "Sync Triggered",
      "default": "Activity"
    }
```

- [ ] **Step 2: Add the keys to the German locale**

In `client/src/i18n/locales/de/dashboard.json`, add the same `"actions"` sub-object inside `"activity"`:

```json
    "actions": {
      "upload": "Datei hochgeladen",
      "download": "Datei heruntergeladen",
      "delete": "Datei gelöscht",
      "edit": "Datei bearbeitet",
      "open": "Datei geöffnet",
      "move": "Datei verschoben",
      "rename": "Datei umbenannt",
      "share": "Datei geteilt",
      "permission": "Berechtigungen geändert",
      "create": "Ordner erstellt",
      "sync": "Synchronisierung gestartet",
      "default": "Aktivität"
    }
```

- [ ] **Step 3: Validate JSON**

Run: `cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/dashboard.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/dashboard.json','utf8')); console.log('ok')"`
Expected: prints `ok` (both files parse).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/dashboard.json client/src/i18n/locales/en/dashboard.json
git commit -m "i18n(activity): action-title keys for the dashboard activity feed (de/en)"
```

---

## Task 6: Frontend — re-point `useActivityFeed` + action mapping

**Files:**
- Modify: `client/src/hooks/useActivityFeed.ts` (full rewrite of data source + mapping)
- Test: `client/src/__tests__/hooks/useActivityFeed.test.ts` (new)

Note: confirm `ActivityFeed.tsx` is the only importer before rewriting. Run a vectordb search for `useActivityFeed` usages (`mcp__vectordb-search__search_code`, query "useActivityFeed import usage", `projectPath D:/Programme (x86)/Baluhost`). Only `components/dashboard/ActivityFeed.tsx` should consume it; Task 7 updates that caller.

- [ ] **Step 1: Write the failing hook test**

Create `client/src/__tests__/hooks/useActivityFeed.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useActivityFeed } from '../../hooks/useActivityFeed';
import type { ActivityListResponse } from '../../api/activity';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../lib/errorHandling', () => ({
  getApiErrorMessage: (_e: unknown, fallback: string) => fallback,
}));

vi.mock('../../api/activity', () => ({
  getRecentActivities: vi.fn(),
}));

import { getRecentActivities } from '../../api/activity';

const adminResponse: ActivityListResponse = {
  total: 2,
  has_more: false,
  activities: [
    {
      id: 1, user_id: 5, username: 'alice', action_type: 'file.upload',
      file_path: 'alice/report.pdf', file_name: 'report.pdf', is_directory: false,
      file_size: 2048, mime_type: 'application/pdf', source: 'server',
      device_id: null, metadata: null, created_at: new Date().toISOString(),
    },
    {
      id: 2, user_id: 6, username: 'bob', action_type: 'folder.create',
      file_path: 'bob/photos', file_name: 'photos', is_directory: true,
      file_size: null, mime_type: null, source: 'server',
      device_id: null, metadata: null, created_at: new Date().toISOString(),
    },
  ],
};

describe('useActivityFeed', () => {
  beforeEach(() => {
    vi.mocked(getRecentActivities).mockResolvedValue(adminResponse);
  });
  afterEach(() => vi.restoreAllMocks());

  it('requests scope=all when allUsers is true and maps action types', async () => {
    const { result } = renderHook(() => useActivityFeed({ limit: 5, allUsers: true }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getRecentActivities).toHaveBeenCalledWith({ limit: 5, scope: 'all' });
    expect(result.current.activities).toHaveLength(2);
    // action_type → icon key (prefix stripped; folder.create → create)
    expect(result.current.activities[0].icon).toBe('upload');
    expect(result.current.activities[1].icon).toBe('create');
    // title resolved via i18n key (mocked t returns the key)
    expect(result.current.activities[0].title).toBe('activity.actions.upload');
    expect(result.current.activities[1].title).toBe('activity.actions.create');
    // admin view includes the acting username in the detail line
    expect(result.current.activities[0].detail).toContain('alice');
  });

  it('requests scope=mine when allUsers is false and omits username in detail', async () => {
    vi.mocked(getRecentActivities).mockResolvedValue({
      total: 1, has_more: false,
      activities: [{
        id: 9, user_id: 5, username: null, action_type: 'file.download',
        file_path: 'me/a.txt', file_name: 'a.txt', is_directory: false,
        file_size: null, mime_type: null, source: 'server',
        device_id: null, metadata: null, created_at: new Date().toISOString(),
      }],
    });

    const { result } = renderHook(() => useActivityFeed({ limit: 5 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getRecentActivities).toHaveBeenCalledWith({ limit: 5, scope: 'mine' });
    expect(result.current.activities[0].icon).toBe('download');
    expect(result.current.activities[0].detail).toBe('a.txt');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/hooks/useActivityFeed.test.ts`
Expected: FAIL — current hook calls `loggingApi.getFileAccessLogs`, not `getRecentActivities`; `allUsers` option unsupported.

- [ ] **Step 3: Rewrite the hook**

Replace the entire contents of `client/src/hooks/useActivityFeed.ts` with:

```typescript
/**
 * Hook for fetching the dashboard activity feed from the user-scoped
 * /api/activity API. Admins may request all users' activity (scope=all).
 */
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { getRecentActivities, type ActivityItem as ApiActivityItem } from '../api/activity';
import { formatBytes } from '../lib/formatters';
import { getApiErrorMessage } from '../lib/errorHandling';

export interface ActivityItem {
  id: string;
  title: string;
  detail: string;
  ago: string;
  icon: string;
  timestamp: Date;
  success: boolean;
}

interface UseActivityFeedOptions {
  limit?: number;
  allUsers?: boolean;
  refreshInterval?: number;
}

interface UseActivityFeedReturn {
  activities: ActivityItem[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// Map a dotted action_type (e.g. "file.upload", "folder.create") to an icon key
// understood by ActivityFeed's ActivityIcon and to an i18n title sub-key.
const ACTION_MAP: Record<string, { icon: string; titleKey: string }> = {
  'file.upload': { icon: 'upload', titleKey: 'upload' },
  'file.download': { icon: 'download', titleKey: 'download' },
  'file.delete': { icon: 'delete', titleKey: 'delete' },
  'file.edit': { icon: 'file', titleKey: 'edit' },
  'file.open': { icon: 'file', titleKey: 'open' },
  'file.move': { icon: 'move', titleKey: 'move' },
  'file.rename': { icon: 'move', titleKey: 'rename' },
  'file.share': { icon: 'share', titleKey: 'share' },
  'file.permission': { icon: 'share', titleKey: 'permission' },
  'folder.create': { icon: 'create', titleKey: 'create' },
  'sync.triggered': { icon: 'file', titleKey: 'sync' },
};

export function mapActionType(actionType: string): { icon: string; titleKey: string } {
  return ACTION_MAP[actionType] ?? { icon: 'file', titleKey: 'default' };
}

// Format relative time
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return date.toLocaleDateString();
}

export function useActivityFeed(options: UseActivityFeedOptions = {}): UseActivityFeedReturn {
  const { limit = 5, allUsers = false, refreshInterval = 30000 } = options;
  const { t } = useTranslation('dashboard');

  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const toViewItem = useCallback(
    (item: ApiActivityItem): ActivityItem => {
      const { icon, titleKey } = mapActionType(item.action_type);
      const timestamp = new Date(item.created_at);

      let detail = item.file_name;
      if (item.username) detail = `${item.username} • ${detail}`;
      if (item.file_size) detail += ` (${formatBytes(item.file_size)})`;

      return {
        id: String(item.id),
        title: t(`activity.actions.${titleKey}`),
        detail,
        ago: formatRelativeTime(timestamp),
        icon,
        timestamp,
        success: true,
      };
    },
    [t],
  );

  const loadData = useCallback(async () => {
    try {
      const response = await getRecentActivities({ limit, scope: allUsers ? 'all' : 'mine' });
      setActivities(response.activities.map(toViewItem));
      setError(null);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to load activity feed'));
    }
  }, [limit, allUsers, toViewItem]);

  useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [loadData]);

  useEffect(() => {
    if (refreshInterval <= 0) return;
    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, loadData]);

  return { activities, loading, error, refetch: loadData };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/hooks/useActivityFeed.test.ts`
Expected: PASS (both cases).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useActivityFeed.ts client/src/__tests__/hooks/useActivityFeed.test.ts
git commit -m "feat(activity): re-point useActivityFeed to /api/activity with action mapping"
```

---

## Task 7: Frontend — wire `ActivityFeed.tsx` (allUsers + admin button gate)

**Files:**
- Modify: `client/src/components/dashboard/ActivityFeed.tsx` (~line 1-67)
- Test: `client/src/__tests__/components/dashboard/ActivityFeed.test.tsx` (new)

- [ ] **Step 1: Write the failing component test**

Create `client/src/__tests__/components/dashboard/ActivityFeed.test.tsx`:

```tsx
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityFeed } from '../../../components/dashboard/ActivityFeed';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockUseActivityFeed = vi.fn();
vi.mock('../../../hooks/useActivityFeed', () => ({
  useActivityFeed: (opts: unknown) => mockUseActivityFeed(opts),
}));

afterEach(() => vi.clearAllMocks());

function setup(isAdmin: boolean) {
  mockUseAuth.mockReturnValue({ isAdmin });
  mockUseActivityFeed.mockReturnValue({ activities: [], loading: false, error: null });
  render(<ActivityFeed limit={5} />);
}

describe('ActivityFeed admin gating', () => {
  it('passes allUsers=true and shows the system-logs button for admins', () => {
    setup(true);
    expect(mockUseActivityFeed).toHaveBeenCalledWith(
      expect.objectContaining({ allUsers: true }),
    );
    expect(screen.getByText('dashboard:activity.viewSystemLogs')).toBeInTheDocument();
  });

  it('passes allUsers=false and hides the system-logs button for regular users', () => {
    setup(false);
    expect(mockUseActivityFeed).toHaveBeenCalledWith(
      expect.objectContaining({ allUsers: false }),
    );
    expect(screen.queryByText('dashboard:activity.viewSystemLogs')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/dashboard/ActivityFeed.test.tsx`
Expected: FAIL — component does not use `useAuth`, button is always rendered, and `allUsers` is not passed.

- [ ] **Step 3: Update the component**

In `client/src/components/dashboard/ActivityFeed.tsx`:

(a) Add the `useAuth` import after the existing `useActivityFeed` import (after line 8):

```typescript
import { useAuth } from '../../contexts/AuthContext';
```

(b) Replace the hook wiring (the `const { activities, loading, error } = ...` line, ~line 48) with:

```typescript
  const { isAdmin } = useAuth();
  const { activities, loading, error } = useActivityFeed({ limit, allUsers: isAdmin });
```

(c) Gate the "View System Logs" button (the `<button onClick={handleViewLogs} ...>...</button>` block, ~line 61-66) by wrapping it so it only renders for admins:

```tsx
        {isAdmin && (
          <button
            onClick={handleViewLogs}
            className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white"
          >
            {t('dashboard:activity.viewSystemLogs')}
          </button>
        )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/dashboard/ActivityFeed.test.tsx`
Expected: PASS (both cases).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/ActivityFeed.tsx client/src/__tests__/components/dashboard/ActivityFeed.test.tsx
git commit -m "feat(activity): admin all-users feed + admin-only system-logs link"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend — run the touched test modules**

Run: `cd backend && python -m pytest tests/test_file_activity.py tests/test_logging_file_access_scope.py -v`
Expected: all PASS.

- [ ] **Step 2: Frontend — type-check + full unit suite**

Run: `cd client && npx tsc --noEmit && npx vitest run`
Expected: no TS errors; all Vitest tests pass (new activity tests included).

- [ ] **Step 3: Frontend — production build sanity**

Run: `cd client && npm run build`
Expected: build succeeds (no unresolved imports from the removed `loggingApi` usage in the hook).

- [ ] **Step 4: Manual smoke (dev mode)**

Start `python start_dev.py`. Log in as `admin/DevMode2024` → Dashboard "Recent Activity" shows activity for all users with usernames, and the "View System Logs" link is present. Log in as `user/User123` → the widget shows only that user's activity, no other users' paths, and no "View System Logs" link. (If the feed is empty, perform a file upload/download in the File Manager first to generate activity.)

- [ ] **Step 5: Confirm no stale importers**

Verify nothing else still calls the old hook signature: vectordb search for `getFileAccessLogs` should show it only in `api/logging.ts` and any logging-page code — not in `hooks/useActivityFeed.ts`.

---

## Notes for the implementer

- Repo uses `core.autocrlf=true` on Windows — let Git handle line endings; don't fight CRLF warnings.
- Run backend tests from the `backend/` dir; frontend from `client/`.
- Keep commits as laid out (one per task) — the branch is `feat/activity-feed-own-vs-all`.
- The spec is the source of truth: `docs/superpowers/specs/2026-06-06-activity-feed-own-vs-all-design.md`.
</content>
