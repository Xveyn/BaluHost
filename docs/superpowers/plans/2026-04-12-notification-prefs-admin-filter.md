# Notification Preferences Admin Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter the user-facing notification preferences table so non-admin users only see and configure categories an admin has routed to them, with an empty-state when no categories are assigned.

**Architecture:** Frontend-only change in `NotificationPreferencesPage.tsx`. Derive `visibleCategories` from existing `MyNotificationRouting` state plus `useAuth().isAdmin`. Remove redundant badge block. Swap table for empty-state card when a non-admin has zero routed categories. Stored `category_preferences` remain untouched — hiding a category never mutates state.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, i18next, existing `useAuth()` context, existing `notificationRouting` API client.

**Spec:** `docs/superpowers/specs/2026-04-12-notification-prefs-admin-filter-design.md`

---

## File Structure

**Modified files:**

- `client/src/pages/NotificationPreferencesPage.tsx` — add admin detection via `useAuth()`, derive `visibleCategories`, remove badge block, add empty-state branch, iterate `visibleCategories` in the table.
- `client/src/i18n/locales/de/notifications.json` — add `categories.noneAssigned`.
- `client/src/i18n/locales/en/notifications.json` — add `categories.noneAssigned`.

**No new files. No backend changes.**

---

## Task 1: Add i18n strings for empty state

**Files:**
- Modify: `client/src/i18n/locales/de/notifications.json`
- Modify: `client/src/i18n/locales/en/notifications.json`

- [ ] **Step 1: Add German string**

In `client/src/i18n/locales/de/notifications.json`, inside the `categories` object, add the `noneAssigned` key after `desktopClientDimmed`:

```json
  "categories": {
    "title": "Kategorie-Einstellungen",
    "description": "Konfiguriere Benachrichtigungen für einzelne Kategorien",
    "type": "Typ",
    "error": "Fehler",
    "errorDesc": "Bei Fehlern und Warnungen benachrichtigen",
    "success": "Erfolg",
    "successDesc": "Bei erfolgreichen Vorgängen benachrichtigen",
    "mobileApp": "Mobile App",
    "mobileAppDimmed": "Keine Mobile App verbunden",
    "desktopClient": "Desktop Client",
    "desktopClientDimmed": "Kein Desktop Client verbunden",
    "noneAssigned": "Dir wurden noch keine System-Benachrichtigungen zugewiesen. Wende dich an einen Administrator."
  },
```

- [ ] **Step 2: Add English string**

In `client/src/i18n/locales/en/notifications.json`, add the same key inside the `categories` object:

```json
    "noneAssigned": "No system notifications have been assigned to you yet. Please contact an administrator."
```

(Place it as the last key inside `categories`, preserving the existing sibling keys.)

- [ ] **Step 3: Verify JSON validity**

Run:
```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/notifications.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/notifications.json','utf8')); console.log('ok')"
```
Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/notifications.json client/src/i18n/locales/en/notifications.json
git commit -m "feat(i18n): add notification categories.noneAssigned string"
```

---

## Task 2: Import useAuth and derive admin flag

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

**Context:** `useAuth()` lives in `client/src/contexts/AuthContext.tsx` and exposes `isAdmin: boolean` (computed as `user?.role === 'admin'`).

- [ ] **Step 1: Add the import**

In `client/src/pages/NotificationPreferencesPage.tsx`, add this import near the other context/hook imports at the top of the file (after the existing `react-router-dom` import on line 9):

```tsx
import { useAuth } from '../contexts/AuthContext';
```

- [ ] **Step 2: Call the hook inside the component**

Inside `NotificationPreferencesPage`, immediately after the existing `const navigate = useNavigate();` line (around line 57), add:

```tsx
const { isAdmin } = useAuth();
```

- [ ] **Step 3: Typecheck**

```bash
cd client && npx tsc --noEmit
```
Expected: no errors related to this file.

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "refactor(notifications): read isAdmin in preferences page"
```

---

## Task 3: Derive visibleCategories and remove badge section

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

**Context:** `MyNotificationRouting` has 8 boolean fields of the form `receive_<category>`. `routing` is `null` while loading or on fetch error.

- [ ] **Step 1: Derive `visibleCategories`**

Below the existing `const getCategoryPref = ...` helper (around line 167–169), add:

```tsx
const visibleCategories: NotificationCategory[] = isAdmin
  ? ALL_CATEGORIES
  : ALL_CATEGORIES.filter(
      (cat) => routing?.[`receive_${cat}` as keyof MyNotificationRouting] === true
    );
```

- [ ] **Step 2: Remove the read-only badge block**

Delete lines 310–335 in the current file — the whole JSX block starting with `{/* Admin-assigned routing (read-only) */}` and ending with its closing `)}`. The block to remove looks like this (delete all of it):

```tsx
{/* Admin-assigned routing (read-only) */}
{routing && Object.values(routing).some((v) => v === true) && (
  <div className="border border-slate-700 rounded-lg p-4 mb-6">
    <h3 className="text-sm font-medium text-slate-300 mb-2">
      Zugewiesene System-Benachrichtigungen
    </h3>
    <p className="text-xs text-slate-500 mb-3">
      Diese Kategorien wurden dir von einem Administrator zugewiesen.
    </p>
    <div className="flex flex-wrap gap-2">
      {(Object.entries(routing) as [string, boolean][])
        .filter(([_, enabled]) => enabled)
        .map(([key]) => {
          const category = key.replace('receive_', '') as NotificationCategory;
          return (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20"
            >
              {getCategoryName(category)}
            </span>
          );
        })}
    </div>
  </div>
)}
```

- [ ] **Step 3: Typecheck**

```bash
cd client && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "refactor(notifications): derive visibleCategories, drop badge block"
```

---

## Task 4: Gate the Category Settings section on visibleCategories

**Files:**
- Modify: `client/src/pages/NotificationPreferencesPage.tsx`

**Context:** The Category Settings section currently starts around line 338 with `<div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">` and renders an unconditional table. We want:

1. If `!isAdmin && visibleCategories.length === 0` → render an empty-state card in place of the table wrapper.
2. Else → render the existing table, but iterate `visibleCategories` instead of `ALL_CATEGORIES`.

- [ ] **Step 1: Wrap the section in a conditional**

Replace the entire existing Category Settings block (the outer `<div>` with `rounded-xl border border-slate-800 bg-slate-900/50 p-6` that begins at the `{/* Category Settings */}` comment, through its closing `</div>`) with the following:

```tsx
{/* Category Settings */}
{!isAdmin && visibleCategories.length === 0 ? (
  <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
    <h2 className="mb-2 text-lg font-semibold text-slate-100">{t('categories.title')}</h2>
    <p className="text-sm text-slate-400">{t('categories.noneAssigned')}</p>
  </div>
) : (
  <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
    <h2 className="mb-4 text-lg font-semibold text-slate-100">{t('categories.title')}</h2>
    <p className="mb-4 text-sm text-slate-400">
      {t('categories.description')}
    </p>

    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-slate-800 text-left text-sm text-slate-400">
            <th className="pb-3 pr-4">{t('categories.type')}</th>
            <th className="pb-3 px-4 text-center">
              <div className="flex items-center justify-center gap-1">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                <span>{t('categories.error')}</span>
              </div>
            </th>
            <th className="pb-3 px-4 text-center">
              <div className="flex items-center justify-center gap-1">
                <CircleCheck className="h-4 w-4 text-emerald-400" />
                <span>{t('categories.success')}</span>
              </div>
            </th>
            <th className={`pb-3 px-4 text-center${!deliveryStatus.has_mobile_devices ? ' opacity-50' : ''}`}>
              <div className="flex items-center justify-center gap-1">
                <Smartphone className="h-4 w-4" />
                <span>{t('categories.mobileApp')}</span>
              </div>
            </th>
            <th className={`pb-3 pl-4 text-center${!deliveryStatus.has_desktop_clients ? ' opacity-50' : ''}`}>
              <div className="flex items-center justify-center gap-1">
                <Monitor className="h-4 w-4" />
                <span>{t('categories.desktopClient')}</span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {visibleCategories.map((category) => {
            const pref = getCategoryPref(category);
            const isActive = pref.error || pref.success;
            return (
              <tr key={category} className="text-sm">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{getCategoryIcon(category)}</span>
                    <span className="font-medium text-slate-100">
                      {getCategoryName(category)}
                    </span>
                    {isActive ? (
                      <Check className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <X className="h-4 w-4 text-rose-400" />
                    )}
                  </div>
                </td>
                <td className="py-3 px-4 text-center">
                  <input
                    type="checkbox"
                    checked={pref.error}
                    onChange={(e) =>
                      handleCategoryChange(category, 'error', e.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                  />
                </td>
                <td className="py-3 px-4 text-center">
                  <input
                    type="checkbox"
                    checked={pref.success}
                    onChange={(e) =>
                      handleCategoryChange(category, 'success', e.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                  />
                </td>
                <td className={`py-3 px-4 text-center${!deliveryStatus.has_mobile_devices ? ' opacity-50' : ''}`}>
                  <input
                    type="checkbox"
                    checked={pref.mobile}
                    onChange={(e) =>
                      handleCategoryChange(category, 'mobile', e.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                  />
                </td>
                <td className={`py-3 pl-4 text-center${!deliveryStatus.has_desktop_clients ? ' opacity-50' : ''}`}>
                  <input
                    type="checkbox"
                    checked={pref.desktop}
                    onChange={(e) =>
                      handleCategoryChange(category, 'desktop', e.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  </div>
)}
```

The only functional difference from the original table JSX is `{visibleCategories.map(...)}` instead of `{ALL_CATEGORIES.map(...)}` and the new `!isAdmin && visibleCategories.length === 0` branch wrapping it.

- [ ] **Step 2: Typecheck**

```bash
cd client && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Verify `MyNotificationRouting` import**

Confirm that `MyNotificationRouting` is already imported at the top of `NotificationPreferencesPage.tsx`. It is imported on line 35:

```tsx
import { getMyNotificationRouting, type MyNotificationRouting } from '../api/notificationRouting';
```

No action needed — this is just a verification. If for any reason the import is missing, add it.

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/NotificationPreferencesPage.tsx
git commit -m "feat(notifications): show only admin-routed categories to users"
```

---

## Task 5: Manual verification in dev environment

**Files:** none — runtime verification only.

**Context:** Dev backend seeds `admin/DevMode2024` and `user/User123`. The user's notification routing can be changed via the admin UI (`User Management` → edit user → Notification Routing section) or directly via `PUT /api/users/{id}/notification-routing`.

- [ ] **Step 1: Start dev environment**

```bash
python start_dev.py
```

Wait for `Backend started on port 3001` and `Frontend ready at http://localhost:5173`.

- [ ] **Step 2: Verify admin user sees all 8 categories**

1. Open `http://localhost:5173`, log in as `admin / DevMode2024`.
2. Navigate to Settings → Notifications.
3. Confirm: Category Settings table lists all 8 rows (RAID, SMART, Backup, Scheduler, System, Security, Sync, VPN).
4. Confirm: The old "Zugewiesene System-Benachrichtigungen" badge block is gone.

- [ ] **Step 3: Verify non-admin user with 0 routed categories sees empty state**

1. In a second browser/incognito window, log in as `user / User123`.
2. Navigate to Settings → Notifications.
3. Confirm: Priority Filter and Quiet Hours sections are visible.
4. Confirm: In place of the category table, a card shows the heading "Kategorie-Einstellungen" and the text "Dir wurden noch keine System-Benachrichtigungen zugewiesen. Wende dich an einen Administrator."
5. Confirm: No table is rendered.

- [ ] **Step 4: Verify non-admin user with partial routing**

1. In the admin window, go to User Management, open the non-admin user's edit modal, enable `RAID` and `Backup` under Notification Routing. Save.
2. In the user window, reload the Notification Preferences page.
3. Confirm: The category table now shows exactly two rows — RAID and Backup — and the four channel columns (Error, Success, Mobile App, Desktop Client) render for each.
4. Toggle one of the checkboxes (e.g., RAID → Mobile), click Save, confirm the success toast.

- [ ] **Step 5: Verify preference preservation on revoke → re-grant**

1. In the admin window, revoke RAID routing for the user. Save.
2. In the user window, reload the Preferences page. Confirm RAID row disappears; Backup row remains.
3. In the admin window, re-enable RAID routing. Save.
4. In the user window, reload. Confirm RAID row reappears and the previously toggled checkbox (e.g., Mobile) still reflects the saved value.

- [ ] **Step 6: Verify routing load failure falls back to empty state for non-admins**

Simulate by temporarily stopping the backend process and reloading the user's Notification Preferences page. Since `getMyNotificationRouting()` will reject, `routing` stays `null`, and a non-admin user should see the empty-state card (not a crash, not the table). Restart the backend afterward.

Alternatively, leave the backend running and instead block the specific endpoint in the browser devtools' Network tab (Request blocking → `/api/notifications/my-routing`), then reload.

- [ ] **Step 7: Stop the dev environment**

Press `Ctrl+C` in the terminal running `start_dev.py` to stop both processes.

- [ ] **Step 8: Final commit if any fixes were needed**

If the manual verification surfaced a bug, fix it, amend with a fresh commit (do NOT use `git commit --amend`), and re-run the relevant steps. If everything passed, no commit is needed for this task.

---

## Self-Review

**Spec coverage:**

- Non-admin users see only routed categories → Task 3 (`visibleCategories`) + Task 4 (iterate `visibleCategories`).
- Non-admin users with 0 routed see empty state → Task 1 (i18n) + Task 4 (conditional branch).
- Admin users see all 8 categories → Task 3 (`isAdmin ? ALL_CATEGORIES : ...`).
- Badge section removed → Task 3 Step 2.
- Stored `category_preferences` untouched → No task modifies save logic; `handleCategoryChange` and `handleSave` remain as-is.
- Priority Filter and Quiet Hours remain visible → No task modifies those sections.
- Routing load failure → non-admin sees empty state → `routing === null` naturally yields `visibleCategories = []` (verified in Task 5 Step 6).

All requirements covered.

**Type consistency:**

- `MyNotificationRouting` field names use `receive_<category>` prefix — matches the TS interface in `client/src/api/notificationRouting.ts`.
- `NotificationCategory` type comes from `api/notifications.ts` and is already imported in the page.
- `visibleCategories` is typed as `NotificationCategory[]` — same as `ALL_CATEGORIES`, so the downstream `.map(...)` and `getCategoryPref` calls type-check.
