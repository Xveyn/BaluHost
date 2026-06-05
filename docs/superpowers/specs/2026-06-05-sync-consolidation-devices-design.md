# Sync Consolidation into `/devices` — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorming)
**Branch:** `refactor/consolidate-sync-into-devices`

## Problem

Sync-schedule management exists twice, against the **same** backend (`sync_schedules`):

- `/sync` → `SyncSettings.tsx` (older, hook `useSyncSettings`, `components/sync-settings/`)
- `/devices` → tab "Schedules" → `SchedulesTab.tsx` (newer, "unified device management", hook `useDeviceManagement`, `components/device-management/`)

The `/devices` Schedules tab is the more complete one (it adds enable, delete, `auto_vpn`, device reassignment, relative next-run). The `/sync` page carries three features the devices tab lacks: **bandwidth limits**, **sleep-window awareness**, and a read-only **registered-devices folder list + VPN revoke**.

This was surfaced after PR #163 fixed the Scheduler dashboard's "Go to Settings" button to point at `/sync` — which then turned out to be redundant.

## Goal

One home for sync schedules: `/devices` → tab "Schedules". Remove `/sync` and its duplicate code. Migrate the two features worth keeping (bandwidth limits, sleep-window awareness). Drop the rest.

## Decisions

| Question | Decision |
|---|---|
| Which page survives | `/devices` (DeviceManagement) |
| Migrate sleep-window awareness | **Yes** |
| Migrate bandwidth limits | **Yes** |
| Migrate registered-devices folders / VPN revoke | **No** (VPN revoke already exists at `/vpn` for admins; folder list dropped) |
| Old `/sync` route | **Remove entirely** (no redirect; old direct links fall through to the app's fallback route) |
| Move `BandwidthLimitsPanel` | **Yes** → into `components/device-management/`, namespace `devices` |
| Orphaned `api/sync` functions | Clean up in the same PR **if** no remaining users (verified by search) |

## Architecture Changes

### 1. Deep-link support in `DeviceManagement.tsx`
Read a `?tab=` query param to initialize `activeTab` (validated against `'devices' | 'register' | 'schedules'`, fallback `'devices'`). Writing the active tab back to the URL on tab change, mirroring `SettingsPage.handleTabChange`. Keep the existing `?pair=1` handling.

Side effect: this fixes the already-broken `/sync-prototype` → `/devices?tab=desktop` redirect (`App.tsx:231`) — `desktop` is not a valid tab and currently silently lands on `devices`; after this change it still resolves to `devices` via the validated fallback, but a real `?tab=schedules` now works.

### 2. Extend `useDeviceManagement`
Additionally load and expose:
- `bandwidth` + `handleSaveBandwidth` — via `getBandwidthLimits` / `saveBandwidthLimits` from `api/sync`
- `sleepSchedule` — via `getSyncPreflight` → `preflight.sleep_schedule`

Follows the hook's existing `useAsyncData` + `useCallback`/`toast`/`handleApiError` patterns.

### 3. Enrich `SchedulesTab.tsx`
- **Sleep-window awareness**: a warning banner plus submit-disable in the create form when `timeOfDay` falls inside the sleep window (`isTimeInSleepWindow` from `lib/sleep-utils`); a "Sleep" badge on affected schedules in the list. Mirrors the logic that lived in `SyncSettings` + `ScheduleList`.
- **Bandwidth limits**: render the migrated `BandwidthLimitsPanel`, wired to `bandwidth` / `handleSaveBandwidth` from the hook.

### 4. Move `BandwidthLimitsPanel`
From `components/sync-settings/` to `components/device-management/`. It is already a clean props-only unit (`initialUpload`, `initialDownload`, `onSave`); the only change beyond the move is switching its `useTranslation('settings')` + `sync.*` keys to the `devices` namespace.

## Deletions (the actual consolidation)
- Route `/sync` + its lazy import in `App.tsx`
- `components/SyncSettings.tsx`
- `hooks/useSyncSettings.ts`
- `components/sync-settings/`: `ScheduleList.tsx`, `ScheduleFormFields.tsx`, `RegisteredDevicesPanel.tsx` (adjust/remove `index.ts`)
- Orphaned `api/sync` functions (`getSyncDevices`, `getDeviceFolders`, `revokeVpnClient`) — only if a repo-wide search confirms no other users

## Explicitly NOT migrated
- Read-only per-device sync-folder list → dropped
- VPN revoke from the sync page → dropped here; remains available at `/vpn` (admin)

## Adjustments (not deletions)
- **Scheduler button** (`SchedulerDashboard.tsx:259`): `to="/sync"` → `to="/devices?tab=schedules"`
- i18n `scheduler.json` (de + en): `syncTab.goToSettings` → "Zu Sync-Zeitplänen" / "Go to Sync Schedules"; `syncTab.description` reworded to point at the Devices page

## i18n
Add the needed `settings.sync.*` strings (bandwidth labels, sleep warning, "Sleep" badge) to the `devices` namespace (de + en). Remove orphaned `settings.sync.*` keys that no surviving component uses.

## Out of Scope
- Backend changes (all endpoints already exist and are unchanged)
- Redesign of the Devices/Register tabs
- VPN management changes

## Testing / Verification
- `npx tsc --noEmit` passes
- Manual (dev mode):
  - `/devices?tab=schedules` opens the Schedules tab directly
  - Creating a schedule with a time inside the sleep window → submit disabled + warning banner; existing in-window schedules show the "Sleep" badge
  - Bandwidth limits save and reload correctly
  - Old `/sync` URL falls through to the fallback route (no crash)
  - Scheduler dashboard "Go to Sync Schedules" button lands on `/devices?tab=schedules`
