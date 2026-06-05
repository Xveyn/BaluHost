# Consolidate Sync Schedules into `/devices` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/devices` → tab "Schedules" the single home for sync-schedule management; migrate bandwidth limits and sleep-window awareness; remove the redundant `/sync` page and its dead code.

**Architecture:** The newer `DeviceManagement` page (`/devices`) already manages the same `sync_schedules` backend more completely than the old `/sync` page. We extend its hook (`useDeviceManagement`) and `SchedulesTab` with the two features worth keeping, add `?tab=` deep-linking so the Scheduler button can land directly on the Schedules tab, then delete the `/sync` route, `SyncSettings`, `useSyncSettings`, and three `sync-settings/` components plus the now-orphaned `api/sync` functions.

**Tech Stack:** React 18 + TypeScript, React Router v6 (`useSearchParams`), `react-i18next`, Tailwind, axios via `apiClient`, `react-hot-toast`.

**Verification note (read before starting):** The frontend has **no component test harness** — `npm run test` is a placeholder (see `client/package.json` / `development.md`). Per "follow existing patterns", this plan uses `npx tsc --noEmit` as the compile gate plus explicit manual verification in dev mode, rather than introducing a new test framework. Do not scaffold vitest for this work.

**Branch:** `refactor/consolidate-sync-into-devices` (already created off `main`; the spec doc is already committed there).

---

## File Structure

**Modified:**
- `client/src/pages/DeviceManagement.tsx` — `?tab=` deep-link support; pass new props to `SchedulesTab`
- `client/src/hooks/useDeviceManagement.ts` — load bandwidth + sleep preflight; add `handleSaveBandwidth`
- `client/src/components/device-management/SchedulesTab.tsx` — sleep-window awareness + bandwidth panel
- `client/src/components/device-management/index.ts` — export `BandwidthLimitsPanel`
- `client/src/pages/SchedulerDashboard.tsx` — repoint button to `/devices?tab=schedules`
- `client/src/App.tsx` — remove `/sync` lazy import + route
- `client/src/api/sync.ts` — remove orphaned device/folder/VPN functions + types
- `client/src/i18n/locales/{de,en}/devices.json` — new schedule keys (bandwidth, sleep)
- `client/src/i18n/locales/{de,en}/scheduler.json` — reworded button/description
- `client/src/i18n/locales/{de,en}/settings.json` — remove orphaned `sync.*` block (guarded)

**Created:**
- `client/src/components/device-management/BandwidthLimitsPanel.tsx` — moved from `sync-settings/`

**Deleted:**
- `client/src/components/SyncSettings.tsx`
- `client/src/hooks/useSyncSettings.ts`
- `client/src/components/sync-settings/` (whole directory: `ScheduleList.tsx`, `ScheduleFormFields.tsx`, `RegisteredDevicesPanel.tsx`, `BandwidthLimitsPanel.tsx`, `index.ts`)

---

## Task 1: Deep-link `?tab=` support in DeviceManagement

**Files:**
- Modify: `client/src/pages/DeviceManagement.tsx`

- [ ] **Step 1: Add a tab-parse helper and init `activeTab` from the URL**

In `DeviceManagement.tsx`, find:

```tsx
type Tab = 'devices' | 'register' | 'schedules';

export default function DeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<Tab>('devices');
```

Replace with:

```tsx
type Tab = 'devices' | 'register' | 'schedules';

const VALID_TABS: Tab[] = ['devices', 'register', 'schedules'];

function parseTab(value: string | null): Tab {
  return value && (VALID_TABS as string[]).includes(value) ? (value as Tab) : 'devices';
}

export default function DeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<Tab>(() => parseTab(searchParams.get('tab')));

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    if (tab === 'devices') next.delete('tab');
    else next.set('tab', tab);
    setSearchParams(next, { replace: true });
  };
```

- [ ] **Step 2: Preserve `?tab=` when clearing the `?pair=1` param**

Find:

```tsx
  useEffect(() => {
    if (searchParams.get('pair') === '1') {
      setShowPairingDialog(true);
      setSearchParams({}, { replace: true });
    }
  }, []);
```

Replace with:

```tsx
  useEffect(() => {
    if (searchParams.get('pair') === '1') {
      setShowPairingDialog(true);
      const next = new URLSearchParams(searchParams);
      next.delete('pair');
      setSearchParams(next, { replace: true });
    }
  }, []);
```

- [ ] **Step 3: Route the three tab buttons through `handleTabChange`**

Find the three tab buttons:

```tsx
          <button onClick={() => setActiveTab('devices')} className={tabClass('devices')}>
```
```tsx
          <button onClick={() => setActiveTab('register')} className={tabClass('register')}>
```
```tsx
          <button onClick={() => setActiveTab('schedules')} className={tabClass('schedules')}>
```

Change each `onClick` to use `handleTabChange` instead of `setActiveTab`:

```tsx
          <button onClick={() => handleTabChange('devices')} className={tabClass('devices')}>
```
```tsx
          <button onClick={() => handleTabChange('register')} className={tabClass('register')}>
```
```tsx
          <button onClick={() => handleTabChange('schedules')} className={tabClass('schedules')}>
```

- [ ] **Step 4: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors. (`setActiveTab` is still used internally by `handleTabChange`, so no unused-var warning.)

- [ ] **Step 5: Manual check**

Run `python start_dev.py`, log in (admin/DevMode2024), open `http://localhost:5173/devices?tab=schedules`.
Expected: the Schedules tab is active on load. Clicking other tabs updates the URL (`?tab=register`, or no param for devices). `http://localhost:5173/devices?tab=bogus` falls back to the Devices tab.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/DeviceManagement.tsx
git commit -m "feat(devices): support ?tab= deep-linking into device tabs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Load bandwidth + sleep preflight in `useDeviceManagement`

**Files:**
- Modify: `client/src/hooks/useDeviceManagement.ts`

- [ ] **Step 1: Extend the `api/sync` import**

Find:

```tsx
import {
  createSyncSchedule,
  listSyncSchedules,
  disableSyncSchedule,
  enableSyncSchedule,
  deleteSyncSchedule,
  updateSyncSchedule,
  type CreateScheduleRequest,
} from '../api/sync';
```

Replace with:

```tsx
import {
  createSyncSchedule,
  listSyncSchedules,
  disableSyncSchedule,
  enableSyncSchedule,
  deleteSyncSchedule,
  updateSyncSchedule,
  getBandwidthLimits,
  saveBandwidthLimits,
  getSyncPreflight,
  type CreateScheduleRequest,
} from '../api/sync';
```

- [ ] **Step 2: Fetch bandwidth + preflight**

Find:

```tsx
  const {
    data: schedules,
    loading: schedulesLoading,
    refetch: refetchSchedules,
  } = useAsyncData(listSyncSchedules);

  const { confirm, dialog: confirmDialog } = useConfirmDialog();
```

Replace with:

```tsx
  const {
    data: schedules,
    loading: schedulesLoading,
    refetch: refetchSchedules,
  } = useAsyncData(listSyncSchedules);

  const { data: bandwidth, refetch: refetchBandwidth } = useAsyncData(getBandwidthLimits);
  const { data: preflight } = useAsyncData(getSyncPreflight);

  const { confirm, dialog: confirmDialog } = useConfirmDialog();
```

- [ ] **Step 3: Add the bandwidth save handler**

Find the start of `handleSaveDeviceName`:

```tsx
  const handleSaveDeviceName = useCallback(
```

Insert the following **directly above** that line:

```tsx
  const handleSaveBandwidth = useCallback(
    async (upload: number | null, download: number | null): Promise<boolean> => {
      try {
        await saveBandwidthLimits(upload, download);
        toast.success(t('toast.bandwidthSaved'));
        refetchBandwidth();
        return true;
      } catch {
        toast.error(t('toast.bandwidthSaveFailed'));
        return false;
      }
    },
    [t, refetchBandwidth],
  );

```

- [ ] **Step 4: Expose the new values from the hook**

Find the `return {` block and the line:

```tsx
    schedules: scheduleList,
    schedulesLoading,
    refetchSchedules,
```

Replace with:

```tsx
    schedules: scheduleList,
    schedulesLoading,
    refetchSchedules,
    bandwidth: bandwidth ?? null,
    sleepSchedule: preflight?.sleep_schedule ?? null,
    handleSaveBandwidth,
```

- [ ] **Step 5: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/hooks/useDeviceManagement.ts
git commit -m "feat(devices): load bandwidth limits + sleep preflight in device hook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Move `BandwidthLimitsPanel` into `device-management`

**Files:**
- Create: `client/src/components/device-management/BandwidthLimitsPanel.tsx`
- Modify: `client/src/components/device-management/index.ts`

> The old `components/sync-settings/BandwidthLimitsPanel.tsx` stays in place for now (still imported by the not-yet-deleted `SyncSettings.tsx`); it is removed with the rest of `sync-settings/` in Task 7.

- [ ] **Step 1: Create the moved panel (namespace `devices`, restyled to match the tab)**

Create `client/src/components/device-management/BandwidthLimitsPanel.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface BandwidthLimitsPanelProps {
  initialUpload: number | null;
  initialDownload: number | null;
  onSave: (upload: number | null, download: number | null) => Promise<boolean>;
}

const inputClass =
  'w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500';

export function BandwidthLimitsPanel({ initialUpload, initialDownload, onSave }: BandwidthLimitsPanelProps) {
  const { t } = useTranslation('devices');
  const [uploadLimit, setUploadLimit] = useState<number | null>(initialUpload);
  const [downloadLimit, setDownloadLimit] = useState<number | null>(initialDownload);

  useEffect(() => {
    setUploadLimit(initialUpload);
    setDownloadLimit(initialDownload);
  }, [initialUpload, initialDownload]);

  return (
    <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <h3 className="mb-3 text-sm font-medium text-slate-300 flex items-center gap-2">
        <HardDrive className="h-4 w-4" />
        {t('schedules.bandwidthLimits')}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input
          type="number"
          placeholder={t('schedules.uploadLimit')}
          value={uploadLimit ?? ''}
          onChange={(e) => setUploadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className={inputClass}
        />
        <input
          type="number"
          placeholder={t('schedules.downloadLimit')}
          value={downloadLimit ?? ''}
          onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className={inputClass}
        />
        <button
          onClick={() => onSave(uploadLimit, downloadLimit)}
          className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 transition"
        >
          {t('schedules.saveLimits')}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Export it from the barrel**

In `client/src/components/device-management/index.ts`, add after the `QrCodeDialog` export:

```tsx
export { BandwidthLimitsPanel } from './BandwidthLimitsPanel';
```

- [ ] **Step 3: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors. (The new keys `schedules.bandwidthLimits` etc. are added in Task 4; missing i18n keys do not break the type-check — they fall back to the key string at runtime.)

- [ ] **Step 4: Commit**

```bash
git add client/src/components/device-management/BandwidthLimitsPanel.tsx client/src/components/device-management/index.ts
git commit -m "refactor(devices): move BandwidthLimitsPanel into device-management

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: i18n keys for bandwidth + sleep (devices namespace)

**Files:**
- Modify: `client/src/i18n/locales/en/devices.json`
- Modify: `client/src/i18n/locales/de/devices.json`

- [ ] **Step 1: Add schedule keys (English)**

In `client/src/i18n/locales/en/devices.json`, find the `schedules` block ending:

```json
    "autoVpnHint": "When Auto-VPN is enabled, the device will automatically connect via VPN before syncing and disconnect afterwards.",
    "editSchedule": "Edit Schedule"
  },
```

Replace with:

```json
    "autoVpnHint": "When Auto-VPN is enabled, the device will automatically connect via VPN before syncing and disconnect afterwards.",
    "editSchedule": "Edit Schedule",
    "bandwidthLimits": "Bandwidth Limits (bytes/sec)",
    "uploadLimit": "Upload Limit",
    "downloadLimit": "Download Limit",
    "saveLimits": "Save Limits",
    "sleepWarning": "This time falls within the sleep window ({{sleepTime}}–{{wakeTime}}). The sync will not run.",
    "sleepBadge": "Blocked by sleep schedule ({{sleepTime}}–{{wakeTime}})"
  },
```

- [ ] **Step 2: Add toast keys (English)**

In the same file, find the `toast` block line:

```json
    "deviceNameEmpty": "Device name cannot be empty"
  },
```

Replace with:

```json
    "deviceNameEmpty": "Device name cannot be empty",
    "bandwidthSaved": "Bandwidth limits saved",
    "bandwidthSaveFailed": "Failed to save bandwidth limits"
  },
```

- [ ] **Step 3: Add schedule keys (German)**

In `client/src/i18n/locales/de/devices.json`, find:

```json
    "autoVpnHint": "Bei aktiviertem Auto-VPN verbindet sich das Gerät vor dem Sync automatisch per VPN und trennt die Verbindung danach.",
    "editSchedule": "Zeitplan bearbeiten"
  },
```

Replace with:

```json
    "autoVpnHint": "Bei aktiviertem Auto-VPN verbindet sich das Gerät vor dem Sync automatisch per VPN und trennt die Verbindung danach.",
    "editSchedule": "Zeitplan bearbeiten",
    "bandwidthLimits": "Bandbreitenlimits (Bytes/Sek)",
    "uploadLimit": "Upload-Limit",
    "downloadLimit": "Download-Limit",
    "saveLimits": "Limits speichern",
    "sleepWarning": "Dieser Zeitpunkt liegt im Sleep-Fenster ({{sleepTime}}–{{wakeTime}}). Der Sync wird nicht ausgeführt.",
    "sleepBadge": "Durch Sleep-Zeitplan blockiert ({{sleepTime}}–{{wakeTime}})"
  },
```

- [ ] **Step 4: Add toast keys (German)**

In the same German file, find the `toast` block line:

```json
    "deviceNameEmpty": "Gerätename darf nicht leer sein"
  },
```

> If the exact trailing line differs, locate the LAST key inside the `"toast"` object and append after it. Keep valid JSON (comma after the previous line).

Replace with:

```json
    "deviceNameEmpty": "Gerätename darf nicht leer sein",
    "bandwidthSaved": "Bandbreitenlimits gespeichert",
    "bandwidthSaveFailed": "Fehler beim Speichern der Bandbreitenlimits"
  },
```

- [ ] **Step 5: Validate JSON**

```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/devices.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/devices.json','utf8')); console.log('JSON OK')"
```
Expected: `JSON OK`

- [ ] **Step 6: Commit**

```bash
git add client/src/i18n/locales/en/devices.json client/src/i18n/locales/de/devices.json
git commit -m "i18n(devices): add bandwidth + sleep-window schedule strings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Enrich `SchedulesTab` with sleep-awareness + bandwidth panel

**Files:**
- Modify: `client/src/components/device-management/SchedulesTab.tsx`
- Modify: `client/src/pages/DeviceManagement.tsx`

- [ ] **Step 1: Extend imports in `SchedulesTab.tsx`**

Find:

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calendar, Clock, Plus, X, Check, Shield, Pencil, Trash2 } from 'lucide-react';
import { formatRelativeTime } from '../../lib/formatters';
import type { Device } from '../../api/devices';
import type { SyncSchedule, CreateScheduleRequest } from '../../api/sync';
```

Replace with:

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calendar, Clock, Plus, X, Check, Shield, Pencil, Trash2, AlertTriangle } from 'lucide-react';
import { formatRelativeTime } from '../../lib/formatters';
import { isTimeInSleepWindow } from '../../lib/sleep-utils';
import type { Device } from '../../api/devices';
import type { SyncSchedule, CreateScheduleRequest, SleepScheduleInfo, BandwidthLimits } from '../../api/sync';
import { BandwidthLimitsPanel } from './BandwidthLimitsPanel';
```

- [ ] **Step 2: Extend the props interface**

Find:

```tsx
interface SchedulesTabProps {
  devices: Device[];
  schedules: SyncSchedule[];
  schedulesLoading: boolean;
  onCreateSchedule: (data: CreateScheduleRequest) => Promise<boolean>;
  onDisableSchedule: (scheduleId: number) => void;
  onEnableSchedule: (scheduleId: number) => void;
  onDeleteSchedule: (scheduleId: number) => void;
  onUpdateSchedule: (scheduleId: number, data: Record<string, unknown>) => Promise<boolean>;
}
```

Replace with:

```tsx
interface SchedulesTabProps {
  devices: Device[];
  schedules: SyncSchedule[];
  schedulesLoading: boolean;
  sleepSchedule: SleepScheduleInfo | null;
  bandwidth: BandwidthLimits | null;
  onCreateSchedule: (data: CreateScheduleRequest) => Promise<boolean>;
  onDisableSchedule: (scheduleId: number) => void;
  onEnableSchedule: (scheduleId: number) => void;
  onDeleteSchedule: (scheduleId: number) => void;
  onUpdateSchedule: (scheduleId: number, data: Record<string, unknown>) => Promise<boolean>;
  onSaveBandwidth: (upload: number | null, download: number | null) => Promise<boolean>;
}
```

- [ ] **Step 3: Destructure the new props** (props only — do NOT add derived flags here; they go after the form state in Step 4 because they reference `timeOfDay`)

Find:

```tsx
export function SchedulesTab({
  devices,
  schedules,
  schedulesLoading,
  onCreateSchedule,
  onDisableSchedule,
  onEnableSchedule,
  onDeleteSchedule,
  onUpdateSchedule,
}: SchedulesTabProps) {
  const { t } = useTranslation(['devices', 'common']);
```

Replace with:

```tsx
export function SchedulesTab({
  devices,
  schedules,
  schedulesLoading,
  sleepSchedule,
  bandwidth,
  onCreateSchedule,
  onDisableSchedule,
  onEnableSchedule,
  onDeleteSchedule,
  onUpdateSchedule,
  onSaveBandwidth,
}: SchedulesTabProps) {
  const { t } = useTranslation(['devices', 'common']);
```

- [ ] **Step 4: Add the derived sleep flags after the form state**

Find the create-form state block:

```tsx
  // Create form state
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [scheduleType, setScheduleType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number | null>(null);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(null);
  const [autoVpn, setAutoVpn] = useState(false);
```

Replace with:

```tsx
  // Create form state
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [scheduleType, setScheduleType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number | null>(null);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(null);
  const [autoVpn, setAutoVpn] = useState(false);

  const sleepActive = !!sleepSchedule?.enabled;
  const createInSleepWindow =
    sleepActive && isTimeInSleepWindow(timeOfDay, sleepSchedule!.sleep_time, sleepSchedule!.wake_time);
```

- [ ] **Step 5: Add the sleep warning banner + disable the Create button**

Find the Create button block:

```tsx
          <div className="flex items-end">
            <button
              onClick={handleCreate}
              className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-95 flex items-center justify-center gap-2"
            >
              <Plus className="h-4 w-4" />
              {t('buttons.create')}
            </button>
          </div>
        </div>

        <p className="mt-2 text-xs text-slate-500">{t('schedules.autoVpnHint')}</p>
```

Replace with:

```tsx
          <div className="flex items-end">
            <button
              onClick={handleCreate}
              disabled={!selectedDeviceId || createInSleepWindow}
              className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:border-emerald-500/50 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation active:scale-95 flex items-center justify-center gap-2"
            >
              <Plus className="h-4 w-4" />
              {t('buttons.create')}
            </button>
          </div>
        </div>

        {createInSleepWindow && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>
              {t('schedules.sleepWarning', {
                sleepTime: sleepSchedule!.sleep_time,
                wakeTime: sleepSchedule!.wake_time,
              })}
            </span>
          </div>
        )}

        <p className="mt-2 text-xs text-slate-500">{t('schedules.autoVpnHint')}</p>
```

- [ ] **Step 6: Add the "Sleep" badge to in-window schedules in the list**

Find:

```tsx
          {schedules.map((schedule) => {
            const deviceName = resolveDeviceName(devices, schedule.device_id, schedule.device_name);
            const isEnabled = schedule.is_enabled !== false;

            return (
```

Replace with:

```tsx
          {schedules.map((schedule) => {
            const deviceName = resolveDeviceName(devices, schedule.device_id, schedule.device_name);
            const isEnabled = schedule.is_enabled !== false;
            const inSleepWindow =
              sleepActive &&
              isTimeInSleepWindow(schedule.time_of_day, sleepSchedule!.sleep_time, sleepSchedule!.wake_time);

            return (
```

Then find the auto_vpn badge inside the row:

```tsx
                    {schedule.auto_vpn && (
                      <span className="rounded-full px-2.5 py-1 text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-200 flex items-center gap-1">
                        <Shield className="h-3 w-3" />
                        VPN
                      </span>
                    )}
```

Insert **directly above** that block:

```tsx
                    {inSleepWindow && (
                      <span
                        className="rounded-full px-2.5 py-1 text-xs font-medium border border-amber-500/40 bg-amber-500/15 text-amber-200 flex items-center gap-1"
                        title={t('schedules.sleepBadge', {
                          sleepTime: sleepSchedule!.sleep_time,
                          wakeTime: sleepSchedule!.wake_time,
                        })}
                      >
                        <AlertTriangle className="h-3 w-3" />
                        Sleep
                      </span>
                    )}
```

- [ ] **Step 7: Render the bandwidth panel above the schedules list**

Find the closing of the create-form card and the loading/list section start:

```tsx
        <p className="mt-2 text-xs text-slate-500">{t('schedules.autoVpnHint')}</p>
      </div>

      {/* Schedules List */}
      {schedulesLoading ? (
```

Replace with:

```tsx
        <p className="mt-2 text-xs text-slate-500">{t('schedules.autoVpnHint')}</p>
      </div>

      {/* Bandwidth Limits */}
      <BandwidthLimitsPanel
        initialUpload={bandwidth?.upload_speed_limit ?? null}
        initialDownload={bandwidth?.download_speed_limit ?? null}
        onSave={onSaveBandwidth}
      />

      {/* Schedules List */}
      {schedulesLoading ? (
```

- [ ] **Step 8: Pass the new props from `DeviceManagement.tsx`**

In `client/src/pages/DeviceManagement.tsx`, find:

```tsx
      {activeTab === 'schedules' && (
        <SchedulesTab
          devices={dm.devices}
          schedules={dm.schedules}
          schedulesLoading={dm.schedulesLoading}
          onCreateSchedule={dm.handleCreateSchedule}
          onDisableSchedule={dm.handleDisableSchedule}
          onEnableSchedule={dm.handleEnableSchedule}
          onDeleteSchedule={dm.handleDeleteSchedule}
          onUpdateSchedule={dm.handleUpdateSchedule}
        />
      )}
```

Replace with:

```tsx
      {activeTab === 'schedules' && (
        <SchedulesTab
          devices={dm.devices}
          schedules={dm.schedules}
          schedulesLoading={dm.schedulesLoading}
          sleepSchedule={dm.sleepSchedule}
          bandwidth={dm.bandwidth}
          onCreateSchedule={dm.handleCreateSchedule}
          onDisableSchedule={dm.handleDisableSchedule}
          onEnableSchedule={dm.handleEnableSchedule}
          onDeleteSchedule={dm.handleDeleteSchedule}
          onUpdateSchedule={dm.handleUpdateSchedule}
          onSaveBandwidth={dm.handleSaveBandwidth}
        />
      )}
```

- [ ] **Step 9: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 10: Manual check**

In dev mode at `/devices?tab=schedules`:
- Set the create-form time inside the dev sleep window (configure a sleep window at `/sleep` if needed, e.g. 23:00–06:00, then pick 02:00) → the amber warning banner appears and **Create** is disabled.
- Existing schedules whose time is in the window show an amber **Sleep** badge.
- The Bandwidth Limits panel renders; entering values and clicking Save shows the "Bandwidth limits saved" toast; reloading the tab shows the saved values.

- [ ] **Step 11: Commit**

```bash
git add client/src/components/device-management/SchedulesTab.tsx client/src/pages/DeviceManagement.tsx
git commit -m "feat(devices): sleep-window awareness + bandwidth panel in Schedules tab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Repoint the Scheduler dashboard button

**Files:**
- Modify: `client/src/pages/SchedulerDashboard.tsx`
- Modify: `client/src/i18n/locales/en/scheduler.json`
- Modify: `client/src/i18n/locales/de/scheduler.json`

- [ ] **Step 1: Point the button at the Schedules tab**

In `client/src/pages/SchedulerDashboard.tsx`, find:

```tsx
            <Link
              to="/sync"
              className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 transition-colors"
            >
              <Settings className="h-4 w-4" />
              {t('syncTab.goToSettings')}
            </Link>
```

Replace with:

```tsx
            <Link
              to="/devices?tab=schedules"
              className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 transition-colors"
            >
              <Settings className="h-4 w-4" />
              {t('syncTab.goToSettings')}
            </Link>
```

- [ ] **Step 2: Reword the English strings**

In `client/src/i18n/locales/en/scheduler.json`, find:

```json
    "title": "Sync Schedules",
    "description": "User-defined sync schedules can be configured on the Sync page. This section will be enhanced with direct schedule management in a future update.",
    "goToSettings": "Go to Sync"
```

Replace with:

```json
    "title": "Sync Schedules",
    "description": "User-defined sync schedules can be configured on the Devices page under the Schedules tab. This section will be enhanced with direct schedule management in a future update.",
    "goToSettings": "Go to Sync Schedules"
```

- [ ] **Step 3: Reword the German strings**

In `client/src/i18n/locales/de/scheduler.json`, find:

```json
    "title": "Sync-Zeitpläne",
    "description": "Benutzerdefinierte Sync-Zeitpläne können auf der Sync-Seite konfiguriert werden. Dieser Bereich wird in einem zukünftigen Update erweitert.",
    "goToSettings": "Zur Sync-Seite"
```

Replace with:

```json
    "title": "Sync-Zeitpläne",
    "description": "Benutzerdefinierte Sync-Zeitpläne können auf der Geräte-Seite im Tab Zeitpläne konfiguriert werden. Dieser Bereich wird in einem zukünftigen Update erweitert.",
    "goToSettings": "Zu Sync-Zeitplänen"
```

- [ ] **Step 4: Validate JSON + type-check**

```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/scheduler.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/scheduler.json','utf8')); console.log('JSON OK')" && npx tsc --noEmit
```
Expected: `JSON OK`, no type errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/SchedulerDashboard.tsx client/src/i18n/locales/en/scheduler.json client/src/i18n/locales/de/scheduler.json
git commit -m "fix(scheduler): point Sync tab button to /devices?tab=schedules

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Remove `/sync` and dead code

**Files:**
- Modify: `client/src/App.tsx`
- Modify: `client/src/api/sync.ts`
- Modify: `client/src/i18n/locales/{de,en}/settings.json` (guarded)
- Delete: `client/src/components/SyncSettings.tsx`
- Delete: `client/src/hooks/useSyncSettings.ts`
- Delete: `client/src/components/sync-settings/` (whole directory)

- [ ] **Step 1: Remove the lazy import and route in `App.tsx`**

Find and delete this line (around line 53):

```tsx
const SyncSettings = isDesktop ? lazyWithRetry(() => import('./components/SyncSettings')) : null;
```

Find and delete this route line (around line 215):

```tsx
        {SyncSettings && <Route path="/sync" element={user ? <Layout><SyncSettings /></Layout> : <Navigate to="/login" />} />}
```

> Leave the `/sync-prototype` and `/mobile-devices` redirect lines untouched — they point at `/devices?tab=...` and now resolve gracefully via Task 1's validated fallback.

- [ ] **Step 2: Delete the duplicate components and hook**

```bash
cd "D:/Programme (x86)/Baluhost"
git rm client/src/components/SyncSettings.tsx client/src/hooks/useSyncSettings.ts
git rm -r client/src/components/sync-settings
```

- [ ] **Step 3: Remove the now-orphaned `api/sync` functions and types**

In `client/src/api/sync.ts`:

- Delete the `SyncDevice` interface (lines beginning `export interface SyncDevice {` through its closing `}`).
- Delete the `SyncFolderItem` interface (block beginning `export interface SyncFolderItem {`).
- Delete the `mapSyncDevice` function, the `mapMobileDevice` function, the `getSyncDevices` function, and the `getDeviceFolders` function (the entire "Devices & Folders" section).
- Delete the `revokeVpnClient` function (the entire "VPN" section).

Keep everything else: `SyncSchedule`, `CreateScheduleRequest`, `SleepScheduleInfo`, `SyncPreflightResponse`, `BandwidthLimits`, `getSyncPreflight`, all schedule functions, and both bandwidth functions.

> These four functions + two interfaces were verified (repo-wide search) to be used ONLY by the files deleted in Step 2.

- [ ] **Step 4: Type-check (catches any missed reference)**

Run: `cd client && npx tsc --noEmit`
Expected: no errors. If an error reports a missing `SyncDevice`/`getSyncDevices`/etc. import, that file still references the removed symbol — fix that reference before continuing.

- [ ] **Step 5: Guarded removal of orphaned `settings.json` sync block**

First confirm nothing still uses the `settings` namespace `sync.*` keys:

```bash
cd "D:/Programme (x86)/Baluhost"
node -e "const fs=require('fs');const files=require('child_process').execSync('git ls-files client/src',{encoding:'utf8'}).split(/\r?\n/).filter(f=>/\.(tsx?|ts)$/.test(f));const hit=files.filter(f=>/t\(['\"]sync\.|useTranslation\(['\"]settings['\"]/.test(fs.readFileSync(f,'utf8')) && /sync\./.test(fs.readFileSync(f,'utf8')));console.log(hit.length? 'STILL USED:\n'+hit.join('\n') : 'NO REMAINING USERS');"
```

- If output is `NO REMAINING USERS`: delete the entire `"sync": { ... }` block from BOTH `client/src/i18n/locales/en/settings.json` and `client/src/i18n/locales/de/settings.json` (the block starting at `"sync": {` and ending at its matching `},` before `"backup": {`).
- If output lists files: leave the `sync` block in place and note it in the PR description as deferred cleanup.

Then validate JSON (only if you edited the files):

```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/settings.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/settings.json','utf8')); console.log('JSON OK')"
```
Expected: `JSON OK`

- [ ] **Step 6: Type-check again + verify no `/sync` references remain**

```bash
cd client && npx tsc --noEmit
```

Then, from the repo root, confirm no dangling references to the deleted modules remain:

```powershell
Get-ChildItem -Path "client/src" -Recurse -Include *.tsx,*.ts | Select-String -Pattern "SyncSettings|useSyncSettings" | Select-Object Path,LineNumber,Line
```
Expected: no matches. (The type-check in Step 4 already guarantees no dangling `/sync` route import; the only remaining literal `/sync` in the tree is the intentional `/sync-prototype` redirect in `App.tsx`.)

- [ ] **Step 7: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add -A
git commit -m "refactor(sync): remove redundant /sync page and dead code

Removes the /sync route, SyncSettings, useSyncSettings, the sync-settings
components, and the now-orphaned api/sync device/folder/VPN helpers.
Sync schedules now live solely at /devices?tab=schedules.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Final verification + PR

**Files:** none

- [ ] **Step 1: Full type-check + production build**

```bash
cd client && npx tsc --noEmit && npm run build
```
Expected: type-check clean; Vite build succeeds with no unresolved-import or missing-module errors.

- [ ] **Step 2: Manual end-to-end (dev mode)**

Run `python start_dev.py`, log in, then verify:
- Scheduler dashboard (`/schedulers`) → tab "Sync Schedules" → button "Go to Sync Schedules" lands on `/devices?tab=schedules` **without a full page reload**.
- `/devices?tab=schedules` deep-link opens the Schedules tab directly.
- Create a schedule (normal time) → succeeds; enable/disable/edit/delete all work.
- Sleep-window time → warning banner + disabled Create; in-window existing schedule shows the Sleep badge.
- Bandwidth limits save + persist across reload.
- Visiting the old `/sync` URL renders no route (blank within the app) — accepted per design.

- [ ] **Step 3: Push the branch**

```bash
cd "D:/Programme (x86)/Baluhost"
git push -u origin refactor/consolidate-sync-into-devices
```

- [ ] **Step 4: Open the PR to `main`**

Write the body to a temp file (avoid here-string quoting issues) and create the PR:

```bash
cd "D:/Programme (x86)/Baluhost"
cat > /tmp/pr-consolidate-sync.md <<'EOF'
## Summary

Consolidates sync-schedule management into a single home: `/devices` → tab **Schedules**. Removes the redundant `/sync` page (`SyncSettings`) that managed the same `sync_schedules` backend, and migrates the two features worth keeping.

Follow-up to #163, which exposed the redundancy.

## Changes

- **Deep-linking:** `DeviceManagement` now honors `?tab=` (also fixes the previously dead `/sync-prototype` / `/mobile-devices` redirects, which land on the Devices tab via a validated fallback).
- **Migrated into the Schedules tab:** bandwidth limits (panel moved to `device-management/`), and sleep-window awareness (warning + disabled Create when the time is in the window; "Sleep" badge on affected schedules).
- **Scheduler button** now points to `/devices?tab=schedules` (client-side nav).
- **Removed:** `/sync` route, `SyncSettings.tsx`, `useSyncSettings.ts`, the `sync-settings/` components, and the orphaned `api/sync` device/folder/VPN helpers.
- **Not migrated** (per design): the read-only per-device folder list and per-device VPN revoke — VPN revoke remains at `/vpn`.

## Verification

- `npx tsc --noEmit` clean; `npm run build` succeeds.
- Manual dev-mode pass: deep-link, schedule CRUD, sleep warning/badge, bandwidth save/persist, button navigation.

Spec: `docs/superpowers/specs/2026-06-05-sync-consolidation-devices-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
gh pr create --base main --head refactor/consolidate-sync-into-devices --title "refactor(sync): consolidate sync schedules into /devices" --body-file /tmp/pr-consolidate-sync.md
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- `/devices` single home → Tasks 1, 5, 8 ✓
- Deep-link `?tab=` support → Task 1 ✓
- Bandwidth migration → Tasks 2, 3, 4, 5 ✓
- Sleep-window awareness migration → Tasks 2, 4, 5 ✓
- Move `BandwidthLimitsPanel` → Task 3 ✓
- Remove `/sync` route + `SyncSettings` + `useSyncSettings` + `sync-settings/` → Task 7 ✓
- Orphaned `api/sync` cleanup (guarded) → Task 7 Step 3 ✓
- NOT migrating folders/VPN revoke → covered by deletion in Task 7 ✓
- Scheduler button repoint + i18n → Task 6 ✓
- i18n key migration + orphan cleanup → Tasks 4, 7 Step 5 ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type consistency:** Hook exposes `bandwidth` (`BandwidthLimits | null`), `sleepSchedule` (`SleepScheduleInfo | null`), `handleSaveBandwidth(upload, download) => Promise<boolean>`; `SchedulesTab` props and `DeviceManagement` call site match these exactly; `BandwidthLimitsPanel` `onSave` signature matches `handleSaveBandwidth`. ✓
