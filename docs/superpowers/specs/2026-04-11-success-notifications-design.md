# Success Notifications & Category Settings Redesign

**Date:** 2026-04-11
**Status:** Approved

## Problem

BaluHost's notification system is event-driven but only emits notifications for failures and one success case (backup completed). After 5 days of production uptime with a healthy system, the admin only sees daily backup notifications — no confirmation that SMART checks, RAID scrubs, or scheduler jobs completed successfully.

Additionally, the current Category Settings UI uses "Push / In-App" columns which conflate *what* events to receive with *where* to receive them.

## Solution

1. **Add opt-in success notifications** — Admins can enable notifications for successful events per category
2. **Redesign Category Settings table** — Separate *what* (Fehler/Erfolg) from *where* (Mobile App/Desktop Client)
3. **Emit missing success events** — Wire up defined-but-unused EventTypes in the scheduler worker and other services
4. **Remove global channel toggles** — Per-category channel control replaces the global Push/In-App master switches

## Requirements

- Admins can toggle error and success notifications independently per category
- Admins can toggle Mobile App and Desktop Client delivery independently per category
- Web app bell always shows all notifications (if Fehler or Erfolg is active)
- Mobile App / Desktop Client columns visually dim when user has no registered devices, but remain functional
- Status indicator per category: green check if at least one of Fehler/Erfolg active, red X if neither
- No behavior change for existing users — error notifications stay on, success notifications default off
- Backup success notifications default to on (preserving current behavior)
- Priority Filter and Quiet Hours sections remain unchanged

## Design

### 1. Data Model

The existing `category_preferences` JSON field in `NotificationPreferences` changes structure:

**Current:** `{ "raid": { "push": true, "in_app": true }, ... }`

**New:** `{ "raid": { "error": true, "success": false, "mobile": true, "desktop": false }, ... }`

**Defaults** (when no entry exists for a category):

| Field | Default | Rationale |
|---|---|---|
| `error` | `true` | Preserve existing behavior |
| `success` | `false` | Opt-in, no change for existing users |
| `mobile` | `true` | Preserve existing push behavior |
| `desktop` | `false` | BaluDesk push is new, opt-in |

**Exception:** Backup category defaults `success: true` to preserve the existing backup-completed notification behavior.

**Migration strategy:** No DB migration needed (JSON field). The service layer handles backwards compatibility:
- Old format `{ "push": bool, "in_app": bool }` detected by presence of `push` key
- Auto-mapped: `push → mobile`, `in_app → error` (= "I want this category")
- New format written on next save

**Deprecation:** Global `push_enabled` and `in_app_enabled` fields on `NotificationPreferences` are deprecated — kept in DB but no longer read by the notification gate logic.

### 2. Backend Event Emission

#### New success event emissions

Events that are defined in `EventType` but never emitted today:

| Event | Emit location | Category |
|---|---|---|
| `SCHEDULER_COMPLETED` | `scheduler/worker.py` after successful job | scheduler |
| `RAID_SYNC_STARTED` | `raid/dev_backend.py` + `mdadm_backend.py` | raid |
| `RAID_SYNC_COMPLETE` | `raid/dev_backend.py` + `mdadm_backend.py` | raid |
| `SERVICE_RESTORED` | `jobs.py` when service recovers | system |

Convenience functions to add in `events.py`:
- `emit_scheduler_completed_sync(scheduler_name: str)`
- `emit_raid_sync_started_sync(array_name: str)`
- `emit_raid_sync_complete_sync(array_name: str)`
- `emit_service_restored_sync(service_name: str)`

Events that already emit and just need the new gate logic:
- `BACKUP_COMPLETED` (backup/service.py)
- `RAID_REBUILT` (raid/api.py, dev_backend.py, mdadm_backend.py)
- `RAID_SCRUB_COMPLETE` (raid/scrub.py)
- `SYNC_COMPLETED` (mobile.py)

#### Gate logic in `emit_sync()`

**Creation gate** — before inserting the notification into the database:

1. Determine event class: success (`priority == 0 AND notification_type == "info"`) or error (`notification_type in ("warning", "critical")`)
2. For system/admin notifications (`user_id=None`): query all admins' `category_preferences`, check if **at least one** admin has the corresponding flag enabled (`success` or `error`) for this event's category
3. If zero admins want it → skip notification creation entirely (saves DB rows)
4. If at least one wants it → create the notification with `user_id=None` as today
5. For user-specific notifications: check that user's own preferences

**Query-time filter** — in `get_user_notifications()`:

System notifications (`user_id=None`) are visible to all admins today. With the new model, the bell query should respect the admin's preferences: if Admin B has `error: false` for RAID, RAID error notifications are filtered out of their bell results. This is a lightweight post-query filter applied after fetching, using the requesting user's `category_preferences`.

**Delivery gate** — after notification creation, per recipient:

1. Check recipient's `mobile` flag for this category → send Firebase push (existing `_send_push_sync`)
2. Check recipient's `desktop` flag → send BaluDesk push (future, prepared but not wired)
3. Web app bell → controlled by query-time filter above

The gate reads the acting user's `category_preferences` from `NotificationPreferences`. Helper method:

```python
def _get_category_pref(self, prefs, category: str) -> dict:
    """Get category preference with backwards compatibility."""
    if not prefs or not prefs.category_preferences:
        defaults = {"error": True, "success": False, "mobile": True, "desktop": False}
        if category == "backup":
            defaults["success"] = True
        return defaults
    
    cat = prefs.category_preferences.get(category, {})
    
    # Old format detection
    if "push" in cat and "error" not in cat:
        return {
            "error": cat.get("in_app", True),
            "success": False,
            "mobile": cat.get("push", True),
            "desktop": False,
        }
    
    defaults = {"error": True, "success": category == "backup", "mobile": True, "desktop": False}
    return {**defaults, **cat}
```

### 3. New API Endpoint

**`GET /api/notifications/delivery-status`**

Returns device availability for the current user to control column dimming in the frontend:

```json
{
  "has_mobile_devices": true,
  "has_desktop_clients": false
}
```

Implementation: Query `MobileDevice` for active devices with push tokens, and `desktop_pairings` for active desktop clients.

Auth: `Depends(get_current_user)`, rate limit: `get_limit("read_operations")`.

### 4. Frontend — Category Settings Table

#### Table structure

| Typ | Fehler | Erfolg | Mobile App | Desktop Client |
|---|---|---|---|---|
| [CatIcon] RAID [StatusIcon] | [x] | [ ] | [x] | [ ] |
| [CatIcon] SMART [StatusIcon] | [x] | [ ] | [x] | [ ] |
| [CatIcon] Backup [StatusIcon] | [x] | [x] | [x] | [ ] |
| [CatIcon] Scheduler [StatusIcon] | [ ] | [ ] | [x] | [ ] |
| [CatIcon] System [StatusIcon] | [x] | [ ] | [ ] | [ ] |
| [CatIcon] Security [StatusIcon] | [x] | [ ] | [x] | [ ] |
| [CatIcon] Sync [StatusIcon] | [x] | [ ] | [ ] | [ ] |
| [CatIcon] VPN [StatusIcon] | [x] | [ ] | [ ] | [ ] |

#### Column headers

| Column | Icon | Color |
|---|---|---|
| Typ | — | — |
| Fehler | `AlertTriangle` | text-amber-400 |
| Erfolg | `CircleCheck` | text-emerald-400 |
| Mobile App | `Smartphone` | text-slate-400 |
| Desktop Client | `Monitor` | text-slate-400 |

#### Status indicator (in Typ column)

- **Green check** (`Check` icon, `text-emerald-400`): at least one of `error` or `success` is true
- **Red X** (`X` icon, `text-red-400`): neither `error` nor `success` is true

#### Column dimming

- "Mobile App" column header + checkboxes: `opacity-50` when `has_mobile_devices === false`
- "Desktop Client" column header + checkboxes: `opacity-50` when `has_desktop_clients === false`
- Checkboxes remain clickable (not disabled) — user can pre-configure before pairing a device

#### Removed sections

- "Notification Channels" (global Push / In-App toggles) — removed entirely
- Priority Filter — stays
- Quiet Hours — stays

#### Data flow

- `CategoryPreference` type changes from `{ push: boolean, in_app: boolean }` to `{ error: boolean, success: boolean, mobile: boolean, desktop: boolean }`
- `handleCategoryChange` updated for new field names
- New `useEffect` to fetch `/api/notifications/delivery-status` on mount
- Save continues to use `PUT /api/notifications/preferences` with the new JSON structure

### 5. i18n Keys

New keys in `notifications` namespace:

```json
{
  "categories": {
    "type": "Typ",
    "error": "Fehler",
    "errorDesc": "Bei Fehlern und Warnungen benachrichtigen",
    "success": "Erfolg",
    "successDesc": "Bei erfolgreichen Vorgängen benachrichtigen",
    "mobileApp": "Mobile App",
    "mobileAppDimmed": "Keine Mobile App verbunden",
    "desktopClient": "Desktop Client",
    "desktopClientDimmed": "Kein Desktop Client verbunden"
  }
}
```

## File Change Summary

| File | Change | Description |
|---|---|---|
| `backend/app/services/notifications/events.py` | Modify | Add convenience functions for new success emits |
| `backend/app/services/notifications/events.py` | Modify | Gate logic: check error/success flags before creating notification |
| `backend/app/services/notifications/service.py` | Modify | `_get_category_pref()` helper with backwards compat, deprecate global toggles |
| `backend/app/services/scheduler/worker.py` | Modify | Add `emit_scheduler_completed_sync()` after successful job |
| `backend/app/services/jobs.py` | Modify | Add `emit_service_restored_sync()` when service recovers |
| `backend/app/api/routes/notifications.py` | Add endpoint | `GET /api/notifications/delivery-status` |
| `backend/app/schemas/notifications.py` | Modify | Update `CategoryPreference` schema fields |
| `client/src/api/notifications.ts` | Modify | Update `CategoryPreference` type, add `getDeliveryStatus()` |
| `client/src/pages/NotificationPreferencesPage.tsx` | Modify | Redesign table, remove global toggles, add status indicator |
| `client/src/i18n/locales/de/notifications.json` | Modify | Add new keys |
| `client/src/i18n/locales/en/notifications.json` | Modify | Add new keys |

## No Changes Required

| File | Reason |
|---|---|
| `notification_preferences` DB table | JSON field, no schema change |
| `NotificationPreferences` model | JSON field, no column change |
| `notification_routing.py` | Routing is orthogonal to preferences |
| `firebase.py` | Push delivery unchanged |
| Quiet Hours logic | Unchanged |
| Priority Filter logic | Unchanged |
