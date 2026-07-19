# Pages

Top-level route components. Ground truth for routing is `App.tsx` — verify against it directly when in doubt, this table drifts.

## Device Modes

Pages are conditionally included based on `__DEVICE_MODE__` build flag (`lib/features.ts`):
- **Desktop (NAS)**: Full feature set — all `isDesktop`-gated pages loaded (`App.tsx:40-55`)
- **Pi (BaluPi)**: Only `Login`, `Dashboard`, `SystemMonitor` (always loaded, `App.tsx:35-37`) plus `PiDashboard` (loaded when `FEATURES.piDashboard`, `App.tsx:58`) — every desktop-only page is tree-shaken out of the Pi bundle

## Routed Pages

Routes below are children of the single pathless layout route `<Route element={user ? <AppLayout/> : <Navigate to="/login" replace/>}>` (`App.tsx:176-197`), except `Login` (outside it) and `SetupWizard` (not a react-router route at all — see note below). "Admin" = wrapped in `isAdmin ? <X/> : <Navigate to="/"/>`; "Yes" = requires login only, no role check.

| Page | Route | Auth | App.tsx line | Description |
|---|---|---|---|---|
| `Login.tsx` | `/login` | No | 165-167 | Login/register with server profile selection — outside the layout route |
| `Dashboard.tsx` | `/` | Yes | 177 | Main dashboard with widgets, plugin panels — rendered at `/` unless `PiDashboard` is present (Pi build) |
| `PiDashboard.tsx` | `/` (Pi build only) | Yes | 58, 177 | BaluPi-specific compact dashboard; *replaces* `Dashboard` at the same `/` route when `FEATURES.piDashboard` is true — there is no separate `/pi` path |
| `SystemMonitor.tsx` | `/system` | Yes | 178 | CPU/GPU/memory/network/disk-io/power/uptime charts + `services`/`health`/`backend-logs`/`logs`/`activity` tabs (own two-level tab nav, see below) |
| `FileManager.tsx` | `/files` | Yes (desktop only) | 181 | File browser with upload, preview, sharing |
| `UserManagement.tsx` | `/users` | Admin | 182 | User CRUD, roles, 2FA management |
| `AdminDatabase.tsx` | `/admin-db` | Admin | 183 | Database table inspector — thin orchestrator over `components/admin/admin-database/*` (category nav, table browser, browse toolbar, schema strip, owner mapping, analytics content), browse state in `useAdminDatabaseBrowse` (extracted F2/#301) |
| `SchedulerDashboard.tsx` | `/schedulers` | Admin | 184 | Background scheduler status and history |
| `SharesPage.tsx` | `/shares` | Yes | 185 | File share management — composes `components/shares/*` (tables/toolbar/stat-cards, extracted F2) |
| `SettingsPage.tsx` | `/settings` | Yes | 186 | User settings (profile, security, language, storage, vcl, notifications, integrations tabs — see below for the `notifications` tab) |
| `DevicesPage.tsx` | `/devices` | Yes | 187 | Thin wrapper — renders `DeviceManagement.tsx` unconditionally, which owns its own `devices`/`register`/`schedules` tab nav (`?tab=` param, default `devices`) |
| `SystemControlPage.tsx` | `/admin/system-control` | Admin | 188 | Consolidated admin control view — two-level `hardware`/`storage`/`network`/`system` category+tab nav (`?tab=` param); hosts several other `pages/*` files as tab bodies, see below |
| `NotificationsArchivePage.tsx` | `/notifications` | Yes | 189 | Notification history |
| `UserManualPage.tsx` | `/manual` | Yes | 190 | User manual article viewer |
| `PluginsPage.tsx` | `/plugins` | Admin | 191 | Plugin install, toggle, configure — composes `components/plugins/plugin-management/*` (tab nav, list, details sidebar, permission/scope grant modals), state/actions in `usePluginManagement` (extracted F2/#301) |
| `PluginPage.tsx` (`components/PluginPage.tsx`, not `pages/`) | `/plugins/:pluginName/*` | Yes | 192 | Renders a single enabled plugin's UI inside a sandboxed iframe via `PluginSandboxHost` |
| `UpdatePage.tsx` | `/updates` | Admin | 193 | Self-hosted update management |
| `CloudImportPage.tsx` | `/cloud-import` | Yes | 194 | Cloud import (Google Drive, Dropbox, etc.) — note the path is `/cloud-import`, not `/cloud` |
| `PiholePage.tsx` | `/pihole` | Admin | 195 | Pi-hole DNS management |
| `SmartDevicesPage.tsx` | `/smart-devices` | Yes | 196 | Smart device (Tapo) management — **not** admin-gated, despite living under an otherwise admin-heavy set of desktop routes |

`SetupWizard.tsx` has no route path at all: `App.tsx` renders it directly (outside `<Router>`/`<Routes>`) when `getSetupStatus()` reports `setup_required`, before `AuthProvider`/`AppRoutes` ever mount (`App.tsx:303-309`).

## Pages Mounted as Tabs (not directly routed)

These `pages/*` files still exist and are still rendered — just as a tab body inside another page, selected by a `?tab=` query param, not via their own route. Several have a legacy top-level path that now 302s into the tab via a redirect-only route in `App.tsx` (outside the layout route, `App.tsx:199-212`).

| Page | Host page | `?tab=` value | Legacy redirect (still live) |
|---|---|---|---|
| `RaidManagement.tsx` | `SystemControlPage` (`SystemControlPage.tsx:14,196`) | `raid` | `/raid` → `/admin/system-control?tab=raid` (`App.tsx:203`) |
| `PowerManagement.tsx` | `SystemControlPage` (`SystemControlPage.tsx:12,193`) — rendered with `isAdmin={true}` | `energy` | `/power` → `/admin/system-control?tab=energy` (`App.tsx:205`) |
| `FanControl.tsx` | `SystemControlPage` (`SystemControlPage.tsx:13,194`) | `fan` | `/fan-control` → `/admin/system-control?tab=fan` (`App.tsx:206`) |
| `SleepMode.tsx` | `SystemControlPage` (`SystemControlPage.tsx:25,195`) | `sleep` | none — no legacy top-level route redirects to this tab |
| `NotificationPreferencesPage.tsx` | `SettingsPage` (`SettingsPage.tsx:17,362`), rendered as `<NotificationPreferencesPage embedded />` | `notifications` | `/settings/notifications` and `/notifications/settings` → `/settings?tab=notifications` (`App.tsx:200-201`); there is no `/notifications/preferences` route or redirect |

All four `SystemControlPage` tabs above sit behind that page's own `isAdmin` route guard (`App.tsx:188`), so they're still effectively admin-only even though the tab body itself doesn't re-check the role.

Access via `/devices?tab=mobile` and `/devices?tab=desktop` (the targets of the legacy `/mobile-devices` and `/sync-prototype` redirects, `App.tsx:208-209`) does **not** reach `MobileDevicesPage.tsx` or a "desktop" tab — `DeviceManagement.tsx`'s tab parser only recognizes `devices`/`register`/`schedules` and silently falls back to `devices` for any other value (`DeviceManagement.tsx:11-16`). Those two redirects are effectively stale; flagged here for triage, not fixed (docs-only change).

## Dead Files (present in `pages/`, not routed or mounted anywhere)

Verified by exhaustive search — none of these are imported outside their own file / their own test file:

- `AdminHealth.tsx` — superseded by `components/monitoring/HealthTab.tsx`, which the `/system?tab=health` tab actually renders; `HealthTab.tsx`'s own header comment calls itself "an embedded version of AdminHealth" (a separate reimplementation, not a wrapper around this file)
- `Logging.tsx` — superseded the same way by `components/monitoring/LogsTab.tsx` (`/system?tab=logs`); its header comment likewise says "an embedded version of Logging page"
- `BackupPage.tsx` — not imported anywhere; `/admin/system-control?tab=backup` renders `components/BackupSettings.tsx` directly (`SystemControlPage.tsx:15,197`)
- `VpnPage.tsx` — not imported anywhere; `/admin/system-control?tab=vpn` renders `components/VpnManagement.tsx` directly (`SystemControlPage.tsx:16,199`)
- `RemoteServersPage.tsx` — not imported/routed anywhere; its `components/RemoteServers/ServerProfileForm` + `ServerProfileList` building blocks are likewise unused elsewhere (`VpnManagement.tsx` only reuses `VPNProfileList`/`VPNProfileForm` from that same directory)
- `MobileDevicesPage.tsx` — not imported/routed anywhere in production code, only from its own test (`__tests__/pages/MobileDevicesPage.test.tsx`); the `components/mobile-devices/*` subtree it composes is likewise reachable only from its own component tests. Note: `components/CLAUDE.md` still describes this file as live ("`MobileDevicesPage` composes `mobile-devices/*`") — that's drift in a different file, not corrected here (out of scope for this doc)

None of these were deleted or modified — this section exists so a future session doesn't route work to (or route *through*) a page nobody renders.

## Conventions

- Pages compose feature components from `components/` — minimal logic in page files
- Admin pages use `Depends(get_current_admin)` on backend — frontend checks `isAdmin` for nav visibility but backend enforces
- Use `useTranslation(namespace)` for all user-facing strings
- Lazy loading: all pages are still imported via `lazyWithRetry()` in `App.tsx`, but the `<Suspense>` boundary no longer wraps the whole route tree from outside — `App.tsx` uses a single pathless layout route rendering `AppLayout` = `<Layout><Suspense fallback={<LoadingFallback size="inline"/>}><Outlet/></Suspense></Layout>` (`components/layout/AppLayout`), so the boundary sits inside `Layout` and page chunks load without blanking the sidebar/header (F2/#301)
