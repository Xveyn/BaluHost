# Dashboard.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-11
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/pages/Dashboard.tsx` — currently **716 lines**.

## Goal

Behavior-preserving decomposition of the remaining inline blocks in
`Dashboard.tsx`. The page's child widgets were already extracted into
`components/dashboard/*` (ActivityFeed, AlertBanner, ConnectedDevicesWidget,
CpuGpuPanel, LiveActivities, NetworkWidget, NextMaintenanceWidget,
PluginDashboardPanel, PluginsPanel, ServicesPanel). What remains inline is the
stat/delta derivation logic, the alert generation memo, and four large
presentational blocks (quick-stat cards, the SMART disk panel, the RAID summary
card, the system-health card).

**Non-goals:** no change to data fetching, endpoints, polling, i18n keys, copy,
Tailwind styling, or any computed value. No TanStack changes. The page file stays
at its path (`pages/Dashboard.tsx`, default export) so routing/imports are
untouched. Assessment **F6 (sessionStorage cache) is already resolved** — the page
uses `useSystemTelemetry` (query-backed); there is no cache to migrate.

## Constraints

- Every extracted value must be **byte-identical** in behavior to the current
  inline code: same formulas, same clamps, same i18n keys, same fallback order.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching, no navigation ownership (the page passes `onClick` handlers).
- Extracted derivation hooks are **pure**: they take already-fetched data as
  input and call `useTranslation('dashboard')` internally; they do **not** fetch
  (no duplicate telemetry subscription).
- Tests are T7-conform: assert on role/text/title/`aria`, **never** on Tailwind
  class strings. Fixtures are complete objects of the real API types, not partial
  `as X` casts.

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| `SystemStats`/`StorageStats` interfaces + derivations, `memoryPercent`, `cpuDelta`, `memoryDelta`, `storageDelta`, `formatDelta`, `cpuFrequency`, `cpuTemperature`, `cpuModel`, `memorySpeedType`, `cpuStatBase` | 30–177, 256–270 | `hooks/useDashboardStats.ts` |
| `alerts` `useMemo` | 180–254 | `hooks/useDashboardAlerts.ts` |
| 4 inline SVG icons in `quickStats` | ~284–331 | `components/dashboard/statIcons.tsx` |
| quick-stat card `.map` body (delta-tone switch, click affordance, card markup) | 370–422 | `components/dashboard/QuickStatCard.tsx` |
| SMART per-device usage math (RAID-member / proportional / zero fallback) | 484–509 | `components/dashboard/computeSmartDeviceUsage.ts` (pure) |
| SMART disk panel (header + mode toggle + status badge + device list) | 440–585 | `components/dashboard/SmartHealthPanel.tsx` + `SmartDeviceCard.tsx` |
| RAID summary card | 593–644 | `components/dashboard/RaidSummaryCard.tsx` |
| system-health checks card | 646–703 | `components/dashboard/SystemHealthCard.tsx` |

The `quickStats` **array** itself stays assembled in `Dashboard.tsx` (uses the
hook's derived values + icons from `statIcons`); only the per-card *rendering*
moves into `QuickStatCard`.

## New units & interfaces

### `hooks/useDashboardStats.ts`

```ts
import type { SystemInfoResponse, TelemetryHistory } from '../api/system';
import type { SmartStatusResponse } from '../api/smart';

export type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';
export interface Delta { label: string; tone: DeltaTone; }

export interface SystemStats {
  cpuUsage: number; cpuCores: number;
  memoryUsed: number; memoryTotal: number;
  uptime: number; systemUptime: number;
}
export interface StorageStats {
  used: number; total: number; available: number; percent: number;
}
export interface CpuStatBase {
  vendor: ReturnType<typeof import('../components/dashboard/CpuGpuPanel').detectCpuVendor>;
  usagePercent: number;
  meta: string;
  submeta?: string;
  delta: Delta;
  tempC: number | null;
}

export interface UseDashboardStatsInput {
  systemInfo: SystemInfoResponse | null;
  // storageInfo is the normalised storage from useSystemTelemetry (has .total/.used numbers)
  storageInfo: { total: number; used: number } | null;
  smartData: SmartStatusResponse | null;
  history: TelemetryHistory;
}
export interface UseDashboardStatsResult {
  systemStats: SystemStats;
  storageStats: StorageStats;
  memoryPercent: number;
  memorySpeedType: string | null;
  cpuStatBase: CpuStatBase;
  memoryDelta: Delta;   // pre-formatted (formatDelta(memoryDeltaRaw))
  storageDelta: Delta;  // pre-formatted (formatDelta(null) => {label:'Live',tone:'live'})
}

export function useDashboardStats(input: UseDashboardStatsInput): UseDashboardStatsResult;
```

`formatDelta`, `cpuFrequency`, `cpuTemperature`, `cpuModel` are internal to the
hook (module-private). Logic copied verbatim from the current memos, including:
`cpuUsage` clamp to `[0,100]`, storage `smartData` fallback summation, percent
clamps, the `cpuStatBase.meta`/`submeta` `t(...)` branches, `detectCpuVendor(cpuModel)`.

### `hooks/useDashboardAlerts.ts`

```ts
import type { Alert } from '../components/dashboard';
import type { SmartStatusResponse } from '../api/smart';
import type { RaidStatusResponse } from '../api/raid';
import type { SchedulerStatus } from '../api/schedulers';
import type { ServiceStatus } from '../api/service-status';

export interface UseDashboardAlertsInput {
  smartData: SmartStatusResponse | null;
  raidData: RaidStatusResponse | null;
  allSchedulers: SchedulerStatus[];
  services: ServiceStatus[];
  isAdmin: boolean;
}
export function useDashboardAlerts(input: UseDashboardAlertsInput): Alert[];
```

Body is the current `alerts` memo verbatim (SMART FAILED→critical /
UNKNOWN→warning split, RAID degraded, scheduler `failed` admin-gated, service
`error` admin-gated), calling `useTranslation('dashboard')` internally.

### `components/dashboard/computeSmartDeviceUsage.ts` (pure, no React)

```ts
import type { SmartDevice } from '../../api/smart';

export function computeSmartDeviceUsage(
  device: SmartDevice,
  allDevices: SmartDevice[],
  storageUsed: number,
): { usedBytes: number; usagePercent: number };
```

Verbatim logic from lines 485–509: start from `device.used_percent ?? 0` and
`device.used_bytes ?? 0`; if `usedBytes === 0 && storageUsed > 0`, apply the
RAID-member branch (full mirror) or the proportional-over-non-RAID branch.

### `components/dashboard/statIcons.tsx`

Named `ReactNode` constants `cpuIcon`, `memoryIcon`, `storageIcon`, `uptimeIcon`
— the four inline `<svg>` blocks moved verbatim.

### `components/dashboard/QuickStatCard.tsx`

```ts
import type { Delta } from '../../hooks/useDashboardStats';
export interface QuickStat {
  id: string; title: string; value: string;
  meta: string; submeta?: string;
  delta: Delta; accent: string; progress: number;
  icon: React.ReactNode;
}
interface QuickStatCardProps { stat: QuickStat; onClick?: () => void; }
```

Owns the `deltaToneClass` switch (verbatim tone→class mapping) and the
`cursor-pointer`/`active:scale` affordance; markup verbatim from 388–421.

### `components/dashboard/SmartDeviceCard.tsx`

Presentational. Props: the `SmartDevice` plus the **already-computed**
`usedBytes` and `usagePercent` (SmartHealthPanel computes them via the helper).
Renders the device row: icon, model/name/serial, status/capacity/temperature/
first-critical-attribute grid, and the conic-gradient usage ring. Markup
verbatim from 516–575.

### `components/dashboard/SmartHealthPanel.tsx`

```ts
interface SmartHealthPanelProps {
  smartData: SmartStatusResponse | null;
  smartLoading: boolean;
  smartError: string | null;
  smartMode: string | null;
  smartModeLoading: boolean;
  onToggleSmartMode: () => void;
  storageUsed: number;   // storageStats.used, for the usage fallback
}
```

Renders the full card (440–585): header, dev-only mode toggle button, status
badge, loading/error/empty states, and the device list (maps devices,
`computeSmartDeviceUsage(device, smartData.devices, storageUsed)` per device →
`SmartDeviceCard`).

### `components/dashboard/RaidSummaryCard.tsx`

```ts
interface RaidSummaryCardProps {
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
}
```

Verbatim RAID config card (593–644): per-array status pill (the full status→class
chain), device counts, resync progress bar.

### `components/dashboard/SystemHealthCard.tsx`

```ts
interface SystemHealthCardProps {
  smartData: SmartStatusResponse | null;
  smartLoading: boolean;
  smartError: string | null;
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
  storagePercent: number;   // storageStats.percent
}
```

Verbatim health-checks list (646–703): SMART row, RAID status row, physical
drives count, total capacity, avg temp, storage used %.

### `components/dashboard/index.ts`

Add exports for `QuickStatCard` (+ `QuickStat` type), `SmartHealthPanel`,
`SmartDeviceCard`, `RaidSummaryCard`, `SystemHealthCard`. `statIcons` and
`computeSmartDeviceUsage` are imported directly (not necessarily via barrel).

### `pages/Dashboard.tsx` (after)

Keeps all page-level data hooks and navigation. Calls `useDashboardStats` and
`useDashboardAlerts`. Builds the `quickStats` array from hook values + `statIcons`.
Composes: header, `AlertBanner`, error, `QuickStatCard` grid (with `CpuGpuPanel`
when `hasGpu`), the four dashboard panels, `LiveActivities`, `SmartHealthPanel`,
`ActivityFeed`, `RaidSummaryCard`, `SystemHealthCard`, `ConnectedDevicesWidget`,
`NextMaintenanceWidget`. Target: **~150–180 lines** (from 716).

## Testing

Broad + page integration (Vitest, T7-conform):

- **`computeSmartDeviceUsage`** — unit tests for: direct backend values
  (`used_bytes`/`used_percent` present), RAID-member fallback (full mirror),
  proportional non-RAID fallback, and the `storageUsed === 0` no-op. *The core
  risk of this decomposition.*
- **`useDashboardStats`** — `renderHook`: cpu clamp, storage primary vs SMART
  fallback, memoryPercent, delta formatting (increase/decrease/steady/live),
  `cpuStatBase.meta`/`submeta` branches, `memorySpeedType` variants.
- **`useDashboardAlerts`** — each branch (SMART failed/unknown, RAID degraded,
  scheduler failed admin-gated, service error admin-gated), plus the
  non-admin suppression.
- **QuickStatCard** — renders value/meta/submeta, delta-tone rendering, click
  fires `onClick`; no click affordance when `onClick` absent.
- **SmartHealthPanel** — loading, error, empty, and populated device list;
  mode-toggle button visibility + click; status badge states.
- **SmartDeviceCard** — renders model/serial/status/usage %.
- **RaidSummaryCard** — loading, empty, array with/without resync.
- **SystemHealthCard** — SMART ok/warn/error rows, RAID rows, counts/capacity/temp.
- **Page integration** (`__tests__/pages/Dashboard.test.tsx`) — mock the data
  hooks; assert the composed page renders title, a quick-stat value, and the
  SMART panel; that an alert surfaces when smartData has a FAILED device.

## Verification gates

- `Dashboard.tsx` < 500 lines (target ~150–180).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green.
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved value against the original).
