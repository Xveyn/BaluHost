# Notification Preferences Admin Filter Design

**Date:** 2026-04-12
**Status:** Approved

## Problem

The user-facing notification preferences page (`NotificationPreferencesPage.tsx`) currently shows all 8 notification categories (RAID, SMART, Backup, Scheduler, System, Security, Sync, VPN) hardcoded via `ALL_CATEGORIES`, regardless of what an admin has assigned to the user via the Notification Routing feature.

Non-admin users can therefore toggle delivery channels for categories they will never actually receive system notifications for, which is confusing and misleading. The existing read-only "Zugewiesene System-Benachrichtigungen" badge section above the table duplicates the information imperfectly and adds visual noise.

## Solution

Filter the "Category Settings" table so that non-admin users only see and configure the categories an admin has explicitly routed to them. Remove the redundant badge section. Show an empty-state message when a non-admin user has no assigned categories. Admin users continue to see all 8 categories unchanged (they implicitly receive everything).

## Requirements

- Non-admin users with ≥1 routed category see only their routed categories in the Category Settings table.
- Non-admin users with 0 routed categories see an empty-state message instead of the table.
- Admin users see all 8 categories in the Category Settings table (unchanged).
- The existing read-only badge section ("Zugewiesene System-Benachrichtigungen") is removed.
- Stored `category_preferences` remain untouched: hiding a category does not delete or modify saved preferences; if an admin re-enables a category later, the user's prior settings for it reappear.
- Priority Filter and Quiet Hours sections remain visible for all users regardless of routing state.
- If `getMyNotificationRouting()` fails (network/backend error), non-admin users are treated as having 0 categories → empty state. Admins are unaffected.

## Design

### 1. Scope

Frontend-only change, single file:

- `client/src/pages/NotificationPreferencesPage.tsx`

Plus i18n strings:

- `client/src/i18n/locales/de/notifications.json`
- `client/src/i18n/locales/en/notifications.json`

No backend changes. No API changes. No new files.

### 2. Admin Detection

Detect the current user's role via the existing auth context (`useAuth()` hook or equivalent — the concrete hook name will be confirmed during implementation). Derive:

```ts
const isAdmin = user?.role === 'admin';
```

### 3. Visible Categories Derivation

Add a derived constant inside the component:

```ts
const visibleCategories: NotificationCategory[] = isAdmin
  ? ALL_CATEGORIES
  : ALL_CATEGORIES.filter(
      (cat) => routing?.[`receive_${cat}` as keyof MyNotificationRouting] === true
    );
```

`routing === null` (initial load or error) naturally yields `visibleCategories = []` for non-admins → empty state.

### 4. Badge Section Removal

Delete the block currently at `NotificationPreferencesPage.tsx:310-335` (the "Zugewiesene System-Benachrichtigungen" read-only chips section).

### 5. Category Settings Section Behavior

Replace the current unconditional table render with a conditional:

- **If `!isAdmin && visibleCategories.length === 0`:** render an empty-state card in place of the table. The card has the same outer wrapper styling (`rounded-xl border border-slate-800 bg-slate-900/50 p-6`) and contains:
  - Heading: `t('categories.title')`
  - Body text: `t('categories.noneAssigned')` (new i18n string)
- **Otherwise:** render the existing table, but iterate over `visibleCategories` instead of `ALL_CATEGORIES` in the row loop (currently line 376).

### 6. Stored Data Preservation

No changes to `categoryPrefs` state handling or the `handleSave()` payload. The full `categoryPrefs` object is still saved via `updatePreferences()`. Hidden categories retain whatever values they previously had. This guarantees:

- Admin revokes → user's old prefs stay in DB.
- Admin re-grants → old prefs reappear in the UI with the original values.

### 7. i18n Strings

New keys in the `notifications` namespace:

| Key | German | English |
|---|---|---|
| `categories.noneAssigned` | "Dir wurden noch keine System-Benachrichtigungen zugewiesen. Wende dich an einen Administrator." | "No system notifications have been assigned to you yet. Please contact an administrator." |

### 8. Testing

Manual verification in the dev environment:

- **Admin user:** all 8 rows visible, table works as before.
- **Non-admin user, 0 routed:** empty-state card visible, no table, Priority Filter and Quiet Hours still functional.
- **Non-admin user, 3 routed:** only those 3 rows visible in the table, toggle and save work.
- **Non-admin user, admin revokes a category mid-session:** after reload, the row disappears; previously saved preferences for that category are preserved in the DB (verify via backend query or by re-granting and confirming old values return).
- **Routing API error simulation:** force `getMyNotificationRouting()` to reject → empty state appears for non-admin.

Existing automated tests (if any) for this page should still pass — no changed test contracts.

## Files to Modify

- `client/src/pages/NotificationPreferencesPage.tsx` — add admin detection, derive `visibleCategories`, remove badge block, add empty-state branch, iterate `visibleCategories` in the table.
- `client/src/i18n/locales/de/notifications.json` — add `categories.noneAssigned`.
- `client/src/i18n/locales/en/notifications.json` — add `categories.noneAssigned`.

## Non-Goals

- Backend changes to `user_notification_routing` or notification preferences schema.
- Filtering the stored `category_preferences` payload on save.
- Per-channel (error/success/mobile/desktop) gating based on routing — routing is per-category only.
- Changes to the admin-facing `NotificationRoutingSection.tsx`.
- Real-time updates when an admin changes routing while the user has the preferences page open (requires page reload, acceptable).
- Changes to Priority Filter or Quiet Hours behavior.
