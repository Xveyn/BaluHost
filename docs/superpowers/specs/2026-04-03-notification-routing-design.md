# Notification Routing Design

**Date:** 2026-04-03
**Status:** Approved

## Problem

System notifications (RAID, SMART, temperature, login failures, etc.) are currently hardcoded to only reach admin-role users. Non-admin users with mobile devices never receive push notifications or in-app alerts for system events, even when they should be informed. The admin has no way to configure which users receive which notification categories.

## Solution

Admin-configurable notification routing: admins can assign notification categories to non-admin users via toggles in the user edit dialog. Follows the established Power Permissions pattern (dedicated table, sub-resource API, toggle UI).

## Requirements

- Admins can assign notification categories per non-admin user (8 categories: RAID, SMART, Backup, Scheduler, System, Security, Sync, VPN)
- Admin users always receive all categories (not configurable, implicit)
- Routed users receive notifications via both Push (Firebase) and In-App (WebSocket)
- User's own NotificationPreferences (opt-out, quiet hours, channel toggles) are respected after admin routing
- Users can see their assigned categories read-only in their notification settings
- No row in routing table = no system notifications (all categories false by default)

## Design

### 1. Data Model

New table `user_notification_routing`, one row per user:

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | Integer, PK | auto | |
| `user_id` | Integer, FK → users.id | — | unique, not null |
| `receive_raid` | Boolean | false | |
| `receive_smart` | Boolean | false | |
| `receive_backup` | Boolean | false | |
| `receive_scheduler` | Boolean | false | |
| `receive_system` | Boolean | false | |
| `receive_security` | Boolean | false | |
| `receive_sync` | Boolean | false | |
| `receive_vpn` | Boolean | false | |
| `granted_by` | Integer, FK → users.id | null | Which admin made the change |
| `granted_at` | DateTime(tz) | null | |
| `updated_at` | DateTime(tz) | auto | server_onupdate=func.now() |

File: `backend/app/models/notification_routing.py`

### 2. API Endpoints

**Admin endpoints** (in `backend/app/api/routes/users.py`):

- `GET /api/users/{user_id}/notification-routing` — read routing for a user (returns defaults if no row)
- `PUT /api/users/{user_id}/notification-routing` — update routing (partial update, all fields optional)

Both require `Depends(get_current_admin)` + rate limiting via `@user_limiter.limit(get_limit("admin_operations"))`.

**User endpoint** (in `backend/app/api/routes/notifications.py`):

- `GET /api/notifications/my-routing` — read-only view of own assigned categories

### 3. Service Layer

New service `backend/app/services/notification_routing.py` with:

- `get_routing(db, user_id)` — returns routing row or default (all false)
- `update_routing(db, user_id, update, granted_by)` — upsert with audit logging
- `check_routing(db, user_id, category)` — returns bool for a specific category
- `get_routed_user_ids(db, category)` — returns list of non-admin user IDs with `receive_{category}=True`

### 4. Routing Logic Changes

**Gate sequence for system notifications (user_id=None):**

1. Admin users → always receive (unchanged)
2. Non-admin users with `receive_{category}=True` in `user_notification_routing` → check user's `NotificationPreferences` (quiet hours, push_enabled, category opt-out) → send or skip

**Files modified:**

- `events.py: _send_push_sync()` — after admin device query, also query routed non-admin user devices for the notification's category. Check each user's NotificationPreferences before sending.
- `service.py: _send_push_to_admins()` → rename to `_send_push_to_recipients()` — same extension as above.
- `service.py: _broadcast_to_admins()` → rename to `_broadcast_to_recipients()` — also broadcast via WebSocket to routed non-admin users.
- `service.py: dispatch()` — update calls to use renamed methods.

### 5. Schemas

New file `backend/app/schemas/notification_routing.py`:

- `NotificationRoutingResponse` — full response with all 8 category booleans + `granted_by_username` + `granted_at`
- `NotificationRoutingUpdate` — all 8 category booleans as `Optional[bool]` for partial updates
- `MyNotificationRoutingResponse` — user-facing read-only (no admin metadata)

### 6. Frontend

**A) Admin: NotificationRoutingSection**

New component `client/src/components/user-management/NotificationRoutingSection.tsx`:

- Rendered in `UserFormModal.tsx` below PowerPermissionsSection (only for non-admin users in edit mode)
- 8 toggle rows, one per category, with lucide-react icons + category name
- Immediate save on toggle click (optimistic update, like PowerPermissionsSection)
- Footer: "Zuletzt geaendert von {admin} am {datum}"

**B) User: Read-only display**

In the user's notification preferences page, add a section:

- Heading: "Zugewiesene System-Benachrichtigungen"
- Active categories displayed as read-only badges/chips
- Note: "Wird von einem Administrator verwaltet"
- Hidden when no categories are assigned

**C) API module**

New `client/src/api/notificationRouting.ts`:

- `getUserNotificationRouting(userId)` → `GET /api/users/{userId}/notification-routing`
- `updateUserNotificationRouting(userId, update)` → `PUT /api/users/{userId}/notification-routing`
- `getMyNotificationRouting()` → `GET /api/notifications/my-routing`

### 7. Testing

- **Model tests:** CRUD for `UserNotificationRouting`, default behavior when no row exists
- **Service tests:** `get_routing()`, `update_routing()`, `check_routing()`, `get_routed_user_ids()`
- **API tests:** Admin GET/PUT endpoints (auth, validation), user read-only endpoint, 403 for non-admin write attempts
- **Routing integration:** Non-admin with `receive_raid=True` receives push + WebSocket; user's own preferences (opt-out, quiet hours) still respected after routing
- **Edge cases:** Admin user ignores routing table, user without mobile device, user with push disabled

### 8. Migration

Alembic migration: `alembic revision --autogenerate -m "add user_notification_routing table"`

## Files to Create

- `backend/app/models/notification_routing.py`
- `backend/app/services/notification_routing.py`
- `backend/app/schemas/notification_routing.py`
- `client/src/api/notificationRouting.ts`
- `client/src/components/user-management/NotificationRoutingSection.tsx`
- `backend/tests/test_notification_routing.py`

## Files to Modify

- `backend/app/models/__init__.py` — register new model
- `backend/app/api/routes/users.py` — add GET/PUT notification-routing endpoints
- `backend/app/api/routes/notifications.py` — add GET my-routing endpoint
- `backend/app/services/notifications/events.py` — extend `_send_push_sync()` to include routed users
- `backend/app/services/notifications/service.py` — extend `_send_push_to_admins()` and `_broadcast_to_admins()` to include routed users
- `client/src/components/user-management/UserFormModal.tsx` — add NotificationRoutingSection
- User notification preferences page — add read-only routing display

## Non-Goals

- Per-event-type granularity (only per-category)
- Admin routing configuration for admin-role users (always receive all)
- New notification categories (uses existing 8)
- Changes to user's self-service NotificationPreferences
