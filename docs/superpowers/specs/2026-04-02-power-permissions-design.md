# Power Permissions Delegation Design

**Date:** 2026-04-02
**Status:** Approved

## Problem

Power actions (Soft Sleep, Suspend, Wake, WoL) are admin-only. Admins are meant for administration, not as regular users with mobile apps. Normal users with registered mobile devices need a way to control power — but only if explicitly granted by an admin.

## Solution

Granular per-user power permissions that admins configure in the User management UI. Permissions are consumed by client apps (Mobile, later BaluDesk). Web-UI remains admin-only for power. Default: all denied.

## Permissions Model

Four permissions with implication logic:

| Permission | Description | Implies |
|---|---|---|
| `can_soft_sleep` | Enter soft sleep mode | `can_wake` |
| `can_wake` | Exit soft sleep mode | — |
| `can_suspend` | System suspend (S3) | `can_wol` |
| `can_wol` | Send Wake-on-LAN packet | — |

**Implication rules (enforced in service layer):**
- Setting `can_soft_sleep = true` → `can_wake` automatically set to `true`
- Setting `can_suspend = true` → `can_wol` automatically set to `true`
- Setting `can_wake = false` → `can_soft_sleep` automatically set to `false`
- Setting `can_wol = false` → `can_suspend` automatically set to `false`

A user with no entry in the table has no permissions (default deny).

## Data Model

New table `user_power_permissions`:

| Column | Type | Default | Description |
|---|---|---|---|
| `id` | Integer PK | auto | Primary key |
| `user_id` | Integer FK → users.id | — | Unique, ON DELETE CASCADE |
| `can_soft_sleep` | Boolean | `false` | Soft sleep permission |
| `can_wake` | Boolean | `false` | Wake permission |
| `can_suspend` | Boolean | `false` | Suspend permission |
| `can_wol` | Boolean | `false` | Wake-on-LAN permission |
| `granted_by` | Integer FK → users.id | — | Admin who last changed permissions |
| `granted_at` | DateTime(tz) | `now()` | When last granted |
| `updated_at` | DateTime(tz) | `now()` | Last modification |

## API Design

### Admin Endpoints (existing users router)

**GET `/api/users/{user_id}/power-permissions`**
- Auth: `get_current_admin`
- Returns: `UserPowerPermissions` (4 booleans + granted_by, granted_at)
- No entry in DB → return default object with all `false`

**PUT `/api/users/{user_id}/power-permissions`**
- Auth: `get_current_admin`
- Body: `UserPowerPermissionsUpdate` (4 optional booleans)
- Applies implication logic before saving
- Sets `granted_by` to current admin
- Audit log: `power_permission_changed` security event

### Modified Sleep Endpoints

Endpoints `/api/sleep/soft`, `/wake`, `/suspend`, `/wol` change auth dependency:

```
get_current_admin → get_power_authorized_user
```

New dependency `get_power_authorized_user`:
1. User is admin? → allowed (unchanged behavior)
2. User is not admin? → check `user_power_permissions` table for matching permission
3. No permission? → 403 Forbidden

### User Self-Query Endpoint

**GET `/api/sleep/my-permissions`**
- Auth: `get_current_user` (not admin-only)
- Returns: 4 booleans for the logged-in user
- Mobile app calls this to determine which buttons to show

## Service Layer

New service `backend/app/services/power_permissions.py`:

- `get_permissions(db, user_id) → UserPowerPermissions` — read from DB, default object if no entry
- `update_permissions(db, user_id, update, granted_by) → UserPowerPermissions` — write/update, apply implications
- `check_permission(db, user_id, action: str) → bool` — single check for dependency

## Audit Logging

Two audit event types:

1. **Permission changes** (in `update_permissions`):
   - Event type: `SECURITY`
   - Action: `power_permission_changed`
   - Details: admin username, target user, old/new permissions

2. **Delegated power actions** (in sleep endpoints):
   - Event type: `SECURITY`
   - Action: `delegated_power_action`
   - Details: user, action performed, success/failure

## Frontend Changes

### Admin: User Edit (SettingsPage → Users)

New section "Power Permissions" in user edit dialog:
- 4 toggle switches: Soft Sleep, Wake, Suspend, WoL
- Implication logic reflected in UI (activating Soft Sleep auto-activates Wake, shown as locked/disabled toggle with tooltip)
- Reverse: deactivating Wake also deactivates Soft Sleep
- Hint text: "Erlaubt diesem User, Power-Aktionen ueber die Mobile App auszufuehren"
- Shows `granted_by` and `granted_at`
- Only shown for non-admin users
- Info note if user has no registered mobile device

### No Web-UI Power Controls for Users

Power buttons in web UI remain admin-only. Permissions are only consumed by client apps.

## New Files

| File | Purpose |
|---|---|
| `backend/app/models/power_permissions.py` | SQLAlchemy model `UserPowerPermission` |
| `backend/app/schemas/power_permissions.py` | Pydantic schemas (response, update) |
| `backend/app/services/power_permissions.py` | Service with implication logic + audit |
| `alembic/versions/xxx_add_user_power_permissions.py` | DB migration |
| `client/src/api/powerPermissions.ts` | API client module |

## Modified Files

| File | Change |
|---|---|
| `backend/app/models/__init__.py` | Register model |
| `backend/app/api/routes/sleep.py` | New dependency + `/my-permissions` endpoint |
| `backend/app/api/deps.py` | New `get_power_authorized_user` dependency |
| `backend/app/api/routes/users.py` | 2 new endpoints (GET/PUT power-permissions) |
| `client/src/pages/SettingsPage.tsx` (or user edit component) | Power permissions UI section |

## Not in Scope

- Web-UI power buttons for normal users
- BaluDesk integration (future)
- Notification to user when permission is granted
- Power permissions for the `/api/power/*` endpoints (CPU frequency etc.) — only sleep/wake/suspend/wol
