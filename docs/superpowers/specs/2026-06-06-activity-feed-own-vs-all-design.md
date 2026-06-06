# Activity Feed: own-vs-all + data-leak fix — Design

> Status: approved (2026-06-06). Next step: implementation plan via writing-plans.

## Goal

The Dashboard already shows a "Recent Activity" widget, but it is wired to the
**wrong data source** and leaks data:

- `components/dashboard/ActivityFeed.tsx` → `hooks/useActivityFeed.ts` →
  `loggingApi.getFileAccessLogs()` → `GET /api/logging/file-access` (the audit
  log), **not** the purpose-built `/api/activity/*` (file-activity) API.
- That logging endpoint is `Depends(get_current_user)` (any authenticated user)
  and calls the non-filtering `AuditLoggerDB.get_logs()` with no user scoping.
  The widget passes no `user` filter, so **every authenticated user sees every
  other user's file activity** — real usernames and full file paths
  (e.g. `alice • /private/steuer2025.pdf downloaded`).

Desired behaviour:

- **Normal user** → sees only their **own** recent file activity.
- **Admin** → sees **all users'** activity, with the acting user shown per entry.

The dedicated `file_activity` service is already user-scoped and built for exactly
this (retention, dedup, client reporting). Re-pointing the widget at it both
delivers the feature and removes the widget's dependency on the leaky endpoint.
We additionally harden the logging endpoint itself so the leak is closed for any
direct caller, not just hidden from the widget.

Decision (2026-06-06): do it properly — include the endpoint hardening and the
i18n cleanup; no separate GitHub issue (the leak is fixed within this work).

## Scope

In scope:

1. Make `GET /api/activity/recent` admin-capable (`scope=mine|all`).
2. Harden `GET /api/logging/file-access` so non-admins only see their own entries.
3. Re-point the Dashboard widget to `/api/activity/recent`.
4. Move the hard-coded English action titles into i18n (de/en).
5. Backend + frontend tests.

Out of scope (YAGNI):

- No dedicated `/activity` page, no filter UI on the widget.
- No avatars — acting user shown as plain username text.
- `GET /api/activity/recent-files` stays user-scoped (unchanged).
- No change to `get_logs_paginated` / the `/logging` page (already role-filtered).

## Design

### 1. Backend — `/api/activity/recent` admin-capable

**Schema** (`backend/app/schemas/file_activity.py`)
- `ActivityItem` gains:
  - `user_id: int` — always populated.
  - `username: Optional[str] = None` — populated only in the admin/all view.

**Service** (`backend/app/services/file_activity.py`)
- `get_recent_activities(..., all_users: bool = False)`:
  - `all_users=False` (default): unchanged — filtered by `user_id`,
    `username` left `None`.
  - `all_users=True`: drop the `user_id == ...` filter; `JOIN users` to fetch
    `username`; all other filters (action_types, file_type, since, path_prefix),
    ordering, pagination and `total` count behave identically.
- `_to_activity_item` carries `user_id`; an `all_users` path also sets `username`
  from the joined row.

**Route** (`backend/app/api/routes/activity.py`)
- `get_recent_activities` gains `scope: str = "mine"` query param.
  - `scope == "all"`: require admin. If the caller is not privileged → `403`.
    Calls the service with `all_users=True`.
  - `scope == "mine"` (default) or any other value: current behaviour
    (service called with the caller's `user.id`, `all_users=False`).
- Admin check uses the existing privilege helper / role check used elsewhere in
  routes (consistent with `get_current_admin` semantics) without changing the
  default dependency (endpoint stays `get_current_user` so `scope=mine` works for
  everyone).

### 2. Backend — leak fix in `/api/logging/file-access`

**Route** (`backend/app/api/routes/logging.py:get_file_access_logs`)
- Determine whether `current_user` is privileged (admin).
- Non-admin: force `user = current_user.username` before calling
  `audit.get_logs(...)`, so a non-admin only ever receives their own
  FILE_ACCESS entries (and cannot widen it via the `user` query param).
- Admin: unchanged (may see all, may filter by `user`).
- This closes the disclosure for direct API callers regardless of the widget.

### 3. Frontend — re-point the widget

**New** `client/src/api/activity.ts`
- Interfaces mirroring the backend: `ActivityItem` (incl. `user_id`,
  `username`, `action_type`, `file_path`, `file_name`, `is_directory`,
  `file_size`, `mime_type`, `source`, `device_id`, `created_at`),
  `ActivityListResponse` (`activities`, `total`, `has_more`).
- `getRecentActivities({ limit, offset?, scope? })` → `GET /api/activity/recent`.
- Follows `api/CLAUDE.md` conventions (typed funcs, `apiClient`, return `res.data`).

**Hook** `client/src/hooks/useActivityFeed.ts`
- Fetches from `getRecentActivities` instead of `loggingApi.getFileAccessLogs`.
- Accepts an `allUsers?: boolean` option; passes `scope = allUsers ? 'all' : 'mine'`.
- Maps the dotted `action_type` (`file.upload`, `folder.create`, `sync.triggered`,
  …) → existing icon keys (strip `file.` / `folder.` prefix, map `sync.triggered`).
- Builds `detail` = `file_name` (+ `username • ` prefix when present) (+ size).
- Keeps the existing returned `ActivityItem` view-shape
  (`{ id, title, detail, ago, icon, timestamp, success }`) so the component
  barely changes. `success` defaults to `true` (file_activity has no failure state).
- Action titles come from i18n (see §4), not hard-coded English.

**Component** `client/src/components/dashboard/ActivityFeed.tsx`
- Passes `allUsers={isAdmin}` (from `useAuth`) into the hook.
- "View System Logs" button rendered **only for admins** (the `/logging` route is
  admin-only). Non-admins see the feed without that button.

### 4. i18n

- Add action-title keys to the `dashboard` namespace in
  `client/src/i18n/locales/{de,en}/dashboard.json`
  (upload, download, delete, create/folder.create, move, rename, copy, share,
  edit/open, permission, sync.triggered, generic fallback).
- Hook resolves titles via these keys instead of the hard-coded
  `getActionTitle` English strings.

## Data flow

```
User opens Dashboard
  → ActivityFeed (knows isAdmin via useAuth)
    → useActivityFeed({ limit, allUsers: isAdmin })
      → getRecentActivities({ limit, scope: isAdmin ? 'all' : 'mine' })
        → GET /api/activity/recent?scope=...
          → route: scope=all ⇒ admin-gate ⇒ service(all_users=True)  [join users → username]
                   scope=mine ⇒ service(user.id, all_users=False)
      ← {activities[], total, has_more}
    ← mapped view items (icon, i18n title, detail incl. username for admins, ago)
```

## Error handling

- `scope=all` by a non-admin → `403` (route-level), surfaced by the hook's
  existing error path (`setError`); the widget already renders an error state.
- Empty result → existing empty state ("no recent activity").
- Network/other errors → existing error state via `getApiErrorMessage`.

## Testing

**Backend** (`backend/tests/`)
- Service: `get_recent_activities(all_users=True)` returns entries across users
  with `username` populated; `all_users=False` stays user-scoped with
  `username=None`; existing filters still apply in both modes.
- Route: `scope=all` as admin → cross-user; `scope=all` as normal user → `403`;
  `scope=mine` (and default) → only caller's entries.
- Logging leak fix: a non-admin calling `/api/logging/file-access` receives only
  their own FILE_ACCESS entries even when other users have activity and even when
  passing a `user=` query param; admin still sees all.

**Frontend** (Vitest)
- `useActivityFeed` maps `action_type` → icon + i18n title correctly; admin mode
  includes `username` in `detail`, non-admin does not; `api/activity` mocked.

## Files touched

Backend:
- `app/schemas/file_activity.py` (extend `ActivityItem`)
- `app/services/file_activity.py` (`all_users` branch + join)
- `app/api/routes/activity.py` (`scope` param + admin gate)
- `app/api/routes/logging.py` (non-admin self-scoping)
- `tests/…` (activity admin-scope tests, logging leak-fix test)

Frontend:
- `client/src/api/activity.ts` (new)
- `client/src/hooks/useActivityFeed.ts` (re-point + mapping + i18n)
- `client/src/components/dashboard/ActivityFeed.tsx` (admin button gating, pass allUsers)
- `client/src/i18n/locales/de/dashboard.json`, `…/en/dashboard.json` (action titles)
- `client/src/**/__tests__/…` (useActivityFeed test)
</content>
</invoke>
