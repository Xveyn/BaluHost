# System Permissions: Rename + Desktop-Toggle Permission — Design

**Date:** 2026-06-04
**Status:** Approved
**Author:** Sven (Xveyn) + Claude

## Problem

Admins grant per-user "Power Permissions" in the User-Management edit modal
(`PowerPermissionsSection`) — four delegated power actions (Soft Sleep, Wake,
Suspend, Wake-on-LAN) that non-admin users may invoke from client apps (Mobile,
later BaluDesk). Two gaps:

1. **Naming.** The concept now covers more than power actions. The user-facing
   name should be **"System Permissions / Systemberechtigungen"**.
2. **Missing capability.** The KDE desktop toggle (DPMS displays on/off, a recent
   feature) is **admin-only**. There is no way to delegate it to a non-admin the
   way sleep/suspend/WoL already are.

Additionally, the existing `PowerPermissionsSection` is **hardcoded German with no
i18n** — it must be internationalized as part of the rename.

## What already exists (reused)

- **Table** `user_power_permissions` — bools `can_soft_sleep`, `can_wake`,
  `can_suspend`, `can_wol` + `granted_by`/`granted_at`/`updated_at`
  (`backend/app/models/power_permissions.py`).
- **Service** `services/power_permissions.py` — `get_permissions`,
  `update_permissions` (implication logic + `power_permission_changed` audit
  event), `check_permission(db, user_id, action)` driven by `_ACTION_FIELD_MAP`.
- **Schemas** `schemas/power_permissions.py` — `UserPowerPermissionsResponse`,
  `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse`.
- **Admin endpoints** `GET/PUT /api/users/{user_id}/power-permissions`
  (`get_current_admin`).
- **Self endpoint** `GET /api/system/sleep/my-permissions` (`get_current_user`),
  consumed by the Mobile app to decide which buttons to show.
- **Sleep delegation dependencies** in `deps.py` — `_make_power_dependency(action)`
  factory + `require_power_soft_sleep` / `_wake` / `_suspend` / `_wol`. Each calls
  `check_permission(db, user.id, action)`; admins pass unconditionally; failures
  are audit-logged and return 403.
- **Desktop feature** `routes/desktop.py` + `services/power/desktop*.py`:
  `GET /api/system/sleep/desktop/status` (`get_current_user`),
  `POST .../enable` and `POST .../disable` (**`get_current_admin`**, rate-limited,
  audit-logged `POWER`/`desktop_enable|disable`). `disable` = `kscreen-doctor
  --dpms off` (displays off so the dGPU deep-idles); `enable` = displays on. Dev
  backend toggles in-memory.
- **Frontend** `PowerPermissionsSection.tsx` rendered in `UserFormModal`
  (namespace `admin`, keys `users.*`). API client `api/powerPermissions.ts`.

## Decisions (locked)

1. **Rename scope: UI + i18n only.** Backend identifiers (`user_power_permissions`
   table, `/power-permissions` API path, `power_permissions.py` files, schema/class
   names) stay unchanged — no migration risk, no breaking change for Mobile/BaluDesk.
   Add a clarifying note in the relevant backend CLAUDE.md files recording that the
   user-facing name is "System Permissions" while backend identifiers stay
   `power_permissions`.
2. **Desktop permission: a single `can_toggle_desktop`** covering enable AND
   disable. Desktop on/off is symmetric — no separate "wake" counterpart like
   sleep — so one column / one switch. **No implication logic.**
3. **Backend gating: yes.** The desktop `enable`/`disable` endpoints switch from
   admin-only to **admin OR `can_toggle_desktop`**, consistent with the existing
   sleep delegation model. A granted non-admin can then toggle the desktop from the
   Mobile app.

## Architecture

### Backend

**1. Model** (`backend/app/models/power_permissions.py`)
Add column, mirroring the existing bool columns:
```python
can_toggle_desktop: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0"
)
```

**2. Alembic migration**
Add `can_toggle_desktop` to `user_power_permissions` (`server_default="0"`,
not null). **Chain `down_revision` onto the real `alembic heads`** (run
`alembic heads` first — do NOT assume the stale dev-DB head; multi-head chains
broke a prior prod deploy). `upgrade` = `op.add_column(...)`; `downgrade` =
`op.drop_column(...)`.

**3. Schemas** (`backend/app/schemas/power_permissions.py`)
- `UserPowerPermissionsResponse`: `can_toggle_desktop: bool = False`
- `UserPowerPermissionsUpdate`: `can_toggle_desktop: Optional[bool] = Field(default=None, description="Allow toggling the desktop (DPMS on/off)")`
- `MyPowerPermissionsResponse`: `can_toggle_desktop: bool = False`

**4. Service** (`backend/app/services/power_permissions.py`)
- `_ACTION_FIELD_MAP`: add `"toggle_desktop": "can_toggle_desktop"`.
- `get_permissions`: include `can_toggle_desktop` in the returned response.
- `update_permissions`: apply explicit `update.can_toggle_desktop` when not None;
  include the field in the `old_values`/`new_values` audit dicts. **No implication**
  — it is independent of the sleep/suspend chains (the existing `_apply_implications`
  is untouched).

**5. Sleep route** (`backend/app/api/routes/sleep.py` → `get_my_power_permissions`)
Include `can_toggle_desktop` in `MyPowerPermissionsResponse`: `True` for admins,
else from `get_permissions(...)`.

**6. Desktop delegation dependency** (`backend/app/api/deps.py`)
Add next to the existing power dependencies:
```python
require_power_toggle_desktop = _make_power_dependency("toggle_desktop")
```
(If `_make_power_dependency`/the `require_power_*` names differ from the design's
assumption, match whatever is actually in `deps.py` — verify at implementation.)

**7. Desktop route** (`backend/app/api/routes/desktop.py`)
`desktop_enable` and `desktop_disable`: change
`current_user = Depends(get_current_admin)` →
`current_user = Depends(require_power_toggle_desktop)`. `desktop_status` stays
`get_current_user`. Rate-limiting + audit logging unchanged. Update the imports.

### Frontend

**8. API client** (`client/src/api/powerPermissions.ts`)
Add `can_toggle_desktop: boolean` to `UserPowerPermissions` and `MyPowerPermissions`;
`can_toggle_desktop?: boolean` to `UserPowerPermissionsUpdate`.

**9. Component** (`client/src/components/user-management/PowerPermissionsSection.tsx`)
- **Keep the filename** (preserves git history, stays backend-aligned; invisible
  to users).
- Internationalize fully via `useTranslation('admin')` — replace every hardcoded
  German string with `t('users.systemPermissions.*')`.
- Heading → System Permissions (i18n). Description → i18n.
- Restructure `PERMISSION_TOGGLES` so each entry carries a stable `i18nKey`
  (`softSleep`, `wake`, `suspend`, `wol`, `toggleDesktop`) used to look up
  `items.<i18nKey>.label` / `.desc`; keep `key` (the API field), `icon`,
  `impliedBy`/`implies`.
- Add the 5th toggle: `key: 'can_toggle_desktop'`, `i18nKey: 'toggleDesktop'`,
  `icon: <MonitorOff className="h-4 w-4" />` (matches the PowerMenu desktop-disable
  action), no `implies`/`impliedBy`.
- Loading text, success toast, error toast, and the "last changed by" line all use
  i18n (with `{{name}}`/`{{date}}` interpolation). The `impliedBy` tooltip uses
  `t('users.systemPermissions.impliedBy', { name })`.

**10. i18n** (`client/src/i18n/locales/en/admin.json` + `de/admin.json`)
Merge a `systemPermissions` block under the existing `users` object (do not
overwrite the files):
```jsonc
"systemPermissions": {
  "title": "System Permissions",                  // DE: "Systemberechtigungen"
  "description": "Allows this user to perform system actions via the mobile app.",
  // DE: "Erlaubt diesem User, System-Aktionen über die Mobile App auszuführen."
  "loading": "Loading system permissions…",        // DE: "Systemberechtigungen werden geladen…"
  "saved": "System permissions updated",           // DE: "Systemberechtigungen aktualisiert"
  "saveError": "Failed to save",                   // DE: "Fehler beim Speichern"
  "lastChangedBy": "Last changed by {{name}} on {{date}}",
  // DE: "Zuletzt geändert von {{name}} am {{date}}"
  "impliedBy": "Implied by {{name}}",              // DE: "Impliziert durch {{name}}"
  "items": {
    "softSleep":     { "label": "Soft Sleep",   "desc": "Put the server into soft sleep" },
    "wake":          { "label": "Wake",         "desc": "Wake the server from soft sleep" },
    "suspend":       { "label": "Suspend",      "desc": "System suspend (S3 sleep)" },
    "wol":           { "label": "Wake-on-LAN",  "desc": "Send a WoL magic packet" },
    "toggleDesktop": { "label": "Desktop",      "desc": "Enable/disable the desktop (saves GPU power)" }
  }
}
```
(German descriptions mirror the current hardcoded strings: "Server in Soft Sleep
versetzen", "Server aus Soft Sleep aufwecken", "System Suspend (S3 Sleep)", "WoL
Magic Packet senden", "Desktop aktivieren/deaktivieren (spart GPU-Strom)".)
The `impliedBy` tooltip replaces the current inline German ternary; pass the
implied-prerequisite's translated label as `name`.

### Docs

**11. CLAUDE.md note** in `backend/app/services/CLAUDE.md`,
`backend/app/schemas/CLAUDE.md`, `backend/app/models/CLAUDE.md`: on the
`power_permissions` line, append a short parenthetical — user-facing name is
"System Permissions / Systemberechtigungen"; backend identifiers remain
`power_permissions` (deliberate, no rename/migration).

## Data flow

```
Admin opens user edit modal
  → PowerPermissionsSection GET /api/users/{id}/power-permissions  (5 bools)
  → admin toggles "Desktop"
  → PUT /api/users/{id}/power-permissions { can_toggle_desktop: true }
      → service writes column, audit "power_permission_changed" (old/new incl. new field)

Granted non-admin (Mobile app)
  → GET /api/system/sleep/my-permissions  → { …, can_toggle_desktop: true }
  → POST /api/system/sleep/desktop/disable
      → require_power_toggle_desktop: admin? no → check_permission("toggle_desktop") → allowed
      → kscreen-doctor --dpms off, audit "desktop_disable"
Ungranted non-admin → 403 (audit authorization_failure)
Admin → unchanged (always allowed)
```

## Error handling

- Missing permission → 403 with audit `authorization_failure` (existing
  `_make_power_dependency` behaviour; no change).
- Permission PUT failures surface via `handleApiError` → toast (existing).
- Migration is additive with a server default → safe on existing rows (all default
  to `false`/denied).

## Testing

- **Backend**
  - Extend power-permissions route/service tests: GET/PUT round-trip including
    `can_toggle_desktop`; `my-permissions` includes the field (admin → True,
    granted user → True, ungranted → False); audit old/new include the field.
  - Update `tests/test_desktop_routes.py`: with the new dependency, a granted
    non-admin gets non-403 on enable/disable, an ungranted non-admin gets 403, an
    admin still succeeds. (Mirror the override pattern already used there.)
  - `python -m pytest` for the touched files, then a broader run for regressions.
- **Frontend**
  - `npm run build` (type-check) — there is no unit harness for this component.
  - Manual dev smoke: open a non-admin user in the edit modal → "System
    Permissions" heading, 5 toggles incl. "Desktop"; toggle persists.

## Security review

- Desktop `enable`/`disable` remain authenticated, rate-limited, and audit-logged;
  the only change is broadening the gate to `admin OR can_toggle_desktop` — a
  deliberate delegation matching the sleep model. Default-deny preserved (no row /
  unset = denied).
- ORM-only; migration adds a column (no raw SQL). New column is a boolean
  permission flag — not sensitive, no `REDACT_PATTERN` impact.
- No new secrets, no subprocess/path surface.

## Out of scope

- Renaming backend table/columns/API/files (explicitly deferred — UI rename only).
- Splitting desktop into separate enable/disable permissions.
- Mobile app UI changes (the app already reads `my-permissions`; surfacing the new
  field is a Mobile-repo task).
- Adding the desktop toggle to the web PowerMenu for delegated users (web stays
  admin-driven for power; the PowerMenu quick-action is a separate feature).
```

