# Dashboard.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the remaining inline blocks of `client/src/pages/Dashboard.tsx` (716 lines) into pure derivation hooks and presentational dashboard components, behavior-preserving, dropping the page to ~150–180 lines.

**Architecture:** Two pure derivation hooks (`useDashboardStats`, `useDashboardAlerts`) take already-fetched data and derive display values (no fetch; `useTranslation('dashboard')` internally). Presentational cards (`QuickStatCard`, `SmartHealthPanel`+`SmartDeviceCard`, `RaidSummaryCard`, `SystemHealthCard`) receive props + callbacks. One pure helper (`computeSmartDeviceUsage`) holds the SMART usage math. The page composes them.

**Tech Stack:** React 18 + TypeScript (strict), Vite, Tailwind, react-i18next, @tanstack/react-query, lucide-react, Vitest + @testing-library/react.

## Global Constraints

- **Behavior-preserving:** every moved value is byte-identical in behavior — same formulas, clamps, i18n keys, copy, Tailwind classes, fallback order. No TanStack/endpoint/polling changes.
- **Page stays at path:** `pages/Dashboard.tsx`, `export default function Dashboard()`. Routing/imports untouched.
- **Extracted components are presentational:** props in, callbacks in; no fetching, no navigation ownership (page passes `onClick`).
- **Extracted hooks are pure derivation:** inputs are already-fetched data; call `useTranslation('dashboard')` internally; never call `useQuery`/fetch.
- **Tests T7-conform:** assert on role/text/title/`aria`, never Tailwind class strings. Fixtures are complete objects of the real API types (`SmartDevice`, `RaidArray`, `ServiceStatus`, `SchedulerStatus`, `SystemInfoResponse`), not partial `as X` casts.
- **i18n test mock (verbatim across all test files):**
  ```ts
  vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (k: string) => k }),
  }));
  ```
  Assert on the returned i18n key strings.
- **Windows/CRLF:** repo uses `core.autocrlf=true`; the LF→CRLF warning on commit is expected.
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017SpZfCSw8idoeYBoci5rZD
  ```

## Reference: current inline source

All extractions copy from the current `client/src/pages/Dashboard.tsx`. Key line ranges:
- Stat derivations & `formatDelta` & `cpuStatBase`: 30–177, 256–270
- `alerts` memo: 180–254
- `quickStats` array (incl. 4 inline SVGs): 272–333
- quick-stat card `.map` body: 370–422
- SMART panel: 440–585 (per-device usage math 484–509; device card markup 516–575)
- RAID summary card: 593–644
- system-health card: 646–703

## File Structure

- Create `client/src/components/dashboard/computeSmartDeviceUsage.ts`
- Create `client/src/hooks/useDashboardStats.ts`
- Create `client/src/hooks/useDashboardAlerts.ts`
- Create `client/src/components/dashboard/statIcons.tsx`
- Create `client/src/components/dashboard/QuickStatCard.tsx`
- Create `client/src/components/dashboard/SmartDeviceCard.tsx`
- Create `client/src/components/dashboard/SmartHealthPanel.tsx`
- Create `client/src/components/dashboard/RaidSummaryCard.tsx`
- Create `client/src/components/dashboard/SystemHealthCard.tsx`
- Modify `client/src/components/dashboard/index.ts` (barrel)
- Modify `client/src/pages/Dashboard.tsx` (orchestrator rewrite)
- Tests mirror source under `client/src/__tests__/...`
- Docs: `client/src/components/CLAUDE.md`, `client/src/hooks/CLAUDE.md`

---

### Task 1: `computeSmartDeviceUsage` pure helper

**Files:**
- Create: `client/src/components/dashboard/computeSmartDeviceUsage.ts`
- Test: `client/src/__tests__/components/dashboard/computeSmartDeviceUsage.test.ts`

**Interfaces:**
- Consumes: `SmartDevice` from `../../api/smart`.
- Produces: `computeSmartDeviceUsage(device: SmartDevice, allDevices: SmartDevice[], storageUsed: number): { usedBytes: number; usagePercent: number }`

**Logic (verbatim from Dashboard.tsx 485–509):** start `usagePercent = device.used_percent ?? 0`, `usedBytes = device.used_bytes ?? 0`. If `usedBytes === 0 && storageUsed > 0`: let `deviceCapacity = device.capacity_bytes || 0`. If `device.raid_member_of && deviceCapacity > 0` → `usedBytes = storageUsed; usagePercent = (usedBytes / deviceCapacity) * 100`. Else if `deviceCapacity > 0` → sum non-RAID capacities; if `> 0`, `deviceShare = deviceCapacity / nonRaidCapacity; usedBytes = Math.round(storageUsed * deviceShare); usagePercent = (usedBytes / deviceCapacity) * 100`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { computeSmartDeviceUsage } from '../../../components/dashboard/computeSmartDeviceUsage';
import type { SmartDevice } from '../../../api/smart';

function device(overrides: Partial<SmartDevice> = {}): SmartDevice {
  return {
    name: '/dev/sda',
    model: 'Test Disk',
    serial: 'SN-1',
    temperature: 30,
    status: 'PASSED',
    capacity_bytes: 1000,
    used_bytes: null,
    used_percent: null,
    mount_point: null,
    raid_member_of: null,
    last_self_test: null,
    attributes: [],
    ...overrides,
  };
}

describe('computeSmartDeviceUsage', () => {
  it('uses direct backend values when present', () => {
    const d = device({ used_bytes: 400, used_percent: 40 });
    expect(computeSmartDeviceUsage(d, [d], 999)).toEqual({ usedBytes: 400, usagePercent: 40 });
  });

  it('RAID member with no direct usage mirrors full storageUsed', () => {
    const d = device({ capacity_bytes: 2000, raid_member_of: 'md0' });
    expect(computeSmartDeviceUsage(d, [d], 500)).toEqual({ usedBytes: 500, usagePercent: 25 });
  });

  it('non-RAID device gets a proportional share of storageUsed', () => {
    const a = device({ name: '/dev/sda', serial: 'A', capacity_bytes: 1000 });
    const b = device({ name: '/dev/sdb', serial: 'B', capacity_bytes: 3000 });
    // a's share = 1000/4000 = 0.25 -> usedBytes = round(800*0.25)=200, percent = 200/1000*100 = 20
    expect(computeSmartDeviceUsage(a, [a, b], 800)).toEqual({ usedBytes: 200, usagePercent: 20 });
  });

  it('storageUsed 0 leaves zeros', () => {
    const d = device({ capacity_bytes: 1000 });
    expect(computeSmartDeviceUsage(d, [d], 0)).toEqual({ usedBytes: 0, usagePercent: 0 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/dashboard/computeSmartDeviceUsage.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```ts
import type { SmartDevice } from '../../api/smart';

export function computeSmartDeviceUsage(
  device: SmartDevice,
  allDevices: SmartDevice[],
  storageUsed: number,
): { usedBytes: number; usagePercent: number } {
  let usagePercent = device.used_percent ?? 0;
  let usedBytes = device.used_bytes ?? 0;

  if (usedBytes === 0 && storageUsed > 0) {
    const deviceCapacity = device.capacity_bytes || 0;

    if (device.raid_member_of && deviceCapacity > 0) {
      usedBytes = storageUsed;
      usagePercent = (usedBytes / deviceCapacity) * 100;
    } else if (deviceCapacity > 0) {
      const nonRaidCapacity = allDevices
        .filter(d => !d.raid_member_of)
        .reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);

      if (nonRaidCapacity > 0) {
        const deviceShare = deviceCapacity / nonRaidCapacity;
        usedBytes = Math.round(storageUsed * deviceShare);
        usagePercent = (usedBytes / deviceCapacity) * 100;
      }
    }
  }

  return { usedBytes, usagePercent };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/dashboard/computeSmartDeviceUsage.test.ts`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/computeSmartDeviceUsage.ts client/src/__tests__/components/dashboard/computeSmartDeviceUsage.test.ts
git commit -m "feat(dashboard): extract computeSmartDeviceUsage pure helper (#301)"
```

---

### Task 2: `useDashboardStats` derivation hook

**Files:**
- Create: `client/src/hooks/useDashboardStats.ts`
- Test: `client/src/__tests__/hooks/useDashboardStats.test.tsx`

**Interfaces:**
- Consumes: `SystemInfoResponse`, `TelemetryHistory` from `../api/system`; `SmartStatusResponse` from `../api/smart`; `detectCpuVendor` + `Vendor` from `../components/dashboard/CpuGpuPanel`.
- Produces:
  ```ts
  export type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';
  export interface Delta { label: string; tone: DeltaTone; }
  export interface SystemStats { cpuUsage: number; cpuCores: number; memoryUsed: number; memoryTotal: number; uptime: number; systemUptime: number; }
  export interface StorageStats { used: number; total: number; available: number; percent: number; }
  export interface CpuStatBase { vendor: Vendor; usagePercent: number; meta: string; submeta?: string; delta: Delta; tempC: number | null; }
  export interface UseDashboardStatsInput {
    systemInfo: SystemInfoResponse | null;
    storageInfo: { total: number; used: number } | null;
    smartData: SmartStatusResponse | null;
    history: TelemetryHistory;
  }
  export interface UseDashboardStatsResult {
    systemStats: SystemStats; storageStats: StorageStats; memoryPercent: number;
    memorySpeedType: string | null; cpuStatBase: CpuStatBase;
    memoryDelta: Delta; storageDelta: Delta;
  }
  export function useDashboardStats(input: UseDashboardStatsInput): UseDashboardStatsResult;
  ```

**Note:** logic copied verbatim from Dashboard.tsx `systemStats` (72–81), `storageStats` (83–106), `memoryPercent` (108–110), `cpuDelta` (112–120), `memoryDelta` (122–130), `storageDelta = null` (132), `formatDelta` (136–148), `cpuFrequency` (150–154), `cpuTemperature` (156–159), `cpuModel` (161–163), `memorySpeedType` (165–177), `cpuTempC` (256), `cpuStatBase` (257–270). `formatDelta`, `cpuFrequency`, `cpuTemperature`, `cpuModel` are module-private inside the hook. `storageInfo` here is the normalised `storage` object from `useSystemTelemetry` (numeric `.total`/`.used`); the original guard `storageInfo && storageInfo.total > 0` is preserved.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDashboardStats, type UseDashboardStatsInput } from '../../hooks/useDashboardStats';
import type { SystemInfoResponse, TelemetryHistory } from '../../api/system';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const emptyHistory: TelemetryHistory = { cpu: [], memory: [], network: [] };

function sysInfo(overrides: Partial<SystemInfoResponse> = {}): SystemInfoResponse {
  return {
    cpu: { usage: 42, cores: 8, frequency_mhz: 3600, model: 'AMD Ryzen 5 5600GT', temperature_celsius: 55 },
    memory: { total: 16000, used: 8000, free: 8000, speed_mts: 3200, type: 'DDR4' },
    disk: {} as SystemInfoResponse['disk'],
    uptime: 100,
    system_uptime: 200,
    dev_mode: true,
    ...overrides,
  };
}

function baseInput(overrides: Partial<UseDashboardStatsInput> = {}): UseDashboardStatsInput {
  return { systemInfo: sysInfo(), storageInfo: { total: 1000, used: 400 }, smartData: null, history: emptyHistory, ...overrides };
}

describe('useDashboardStats', () => {
  it('derives systemStats with cpu clamp and storage percent', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.systemStats).toEqual({ cpuUsage: 42, cpuCores: 8, memoryUsed: 8000, memoryTotal: 16000, uptime: 100, systemUptime: 200 });
    expect(result.current.storageStats).toEqual({ used: 400, total: 1000, available: 600, percent: 40 });
    expect(result.current.memoryPercent).toBe(50);
  });

  it('clamps cpu usage over 100', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput({ systemInfo: sysInfo({ cpu: { usage: 150, cores: 4 } }) })));
    expect(result.current.systemStats.cpuUsage).toBe(100);
  });

  it('falls back to summed SMART capacity when no storageInfo', () => {
    const smartData = { checked_at: 'x', devices: [
      { name: 'a', model: 'm', serial: 's1', temperature: null, status: 'PASSED', capacity_bytes: 2000, used_bytes: 500, used_percent: null, mount_point: null, raid_member_of: null, last_self_test: null, attributes: [] },
    ] };
    const { result } = renderHook(() => useDashboardStats(baseInput({ storageInfo: null, smartData })));
    expect(result.current.storageStats.total).toBe(2000);
    expect(result.current.storageStats.used).toBe(500);
  });

  it('formats memoryDelta as Live when history < 2 points', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.memoryDelta).toEqual({ label: 'Live', tone: 'live' });
    expect(result.current.storageDelta).toEqual({ label: 'Live', tone: 'live' });
  });

  it('builds cpuStatBase with amd vendor and model meta', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.cpuStatBase.vendor).toBe('amd');
    expect(result.current.cpuStatBase.meta).toBe('AMD Ryzen 5 5600GT');
    expect(result.current.memorySpeedType).toBe('DDR4 @ 3200 MT/s');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/hooks/useDashboardStats.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

Create `client/src/hooks/useDashboardStats.ts`. Port the memos verbatim. Structure:

```ts
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { SystemInfoResponse, TelemetryHistory } from '../api/system';
import type { SmartStatusResponse } from '../api/smart';
import { detectCpuVendor, type Vendor } from '../components/dashboard/CpuGpuPanel';
import { formatNumber } from '../lib/formatters';

export type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';
export interface Delta { label: string; tone: DeltaTone; }
export interface SystemStats { cpuUsage: number; cpuCores: number; memoryUsed: number; memoryTotal: number; uptime: number; systemUptime: number; }
export interface StorageStats { used: number; total: number; available: number; percent: number; }
export interface CpuStatBase { vendor: Vendor; usagePercent: number; meta: string; submeta?: string; delta: Delta; tempC: number | null; }
export interface UseDashboardStatsInput {
  systemInfo: SystemInfoResponse | null;
  storageInfo: { total: number; used: number } | null;
  smartData: SmartStatusResponse | null;
  history: TelemetryHistory;
}
export interface UseDashboardStatsResult {
  systemStats: SystemStats; storageStats: StorageStats; memoryPercent: number;
  memorySpeedType: string | null; cpuStatBase: CpuStatBase;
  memoryDelta: Delta; storageDelta: Delta;
}

function formatDelta(value: number | null, suffix = '%'): Delta {
  if (value === null) return { label: 'Live', tone: 'live' };
  const rounded = Number(value.toFixed(1));
  if (rounded === 0) return { label: `0${suffix}`, tone: 'steady' };
  if (rounded > 0) return { label: `+${rounded}${suffix}`, tone: 'increase' };
  return { label: `${rounded}${suffix}`, tone: 'decrease' };
}

export function useDashboardStats({ systemInfo, storageInfo, smartData, history }: UseDashboardStatsInput): UseDashboardStatsResult {
  const { t } = useTranslation('dashboard');

  const systemStats = useMemo<SystemStats>(() => { /* verbatim 73–80 */ }, [systemInfo]);
  const storageStats = useMemo<StorageStats>(() => { /* verbatim 84–105, guard storageInfo && storageInfo.total > 0 */ }, [storageInfo, smartData]);
  const memoryPercent = useMemo(() => systemStats.memoryTotal ? (systemStats.memoryUsed / systemStats.memoryTotal) * 100 : 0, [systemStats.memoryTotal, systemStats.memoryUsed]);
  const cpuDelta = useMemo(() => { /* verbatim 113–119 */ }, [history.cpu]);
  const memoryDeltaRaw = useMemo(() => { /* verbatim 123–129 */ }, [history.memory]);
  const cpuFrequency = useMemo(() => systemInfo?.cpu?.frequency_mhz ? `${formatNumber(systemInfo.cpu.frequency_mhz / 1000, 2)} GHz` : null, [systemInfo]);
  const cpuTemperature = useMemo(() => { const v = systemInfo?.cpu?.temperature_celsius; return typeof v === 'number' ? `${formatNumber(v, 1)}°C` : null; }, [systemInfo]);
  const cpuModel = useMemo(() => systemInfo?.cpu?.model || null, [systemInfo]);
  const memorySpeedType = useMemo(() => { /* verbatim 166–176 */ }, [systemInfo]);
  const cpuTempC = systemInfo?.cpu?.temperature_celsius ?? null;
  const cpuStatBase = useMemo<CpuStatBase>(() => ({ /* verbatim 258–269, delta: formatDelta(cpuDelta) */ }), [systemStats.cpuUsage, systemStats.cpuCores, cpuModel, cpuFrequency, cpuTemperature, cpuTempC, cpuDelta, t]);

  return {
    systemStats, storageStats, memoryPercent, memorySpeedType, cpuStatBase,
    memoryDelta: formatDelta(memoryDeltaRaw),
    storageDelta: formatDelta(null),
  };
}
```

Fill each `/* verbatim */` with the exact body from the referenced Dashboard.tsx lines. Do **not** alter any formula, clamp, or the `t(...)` key branches in `cpuStatBase.meta`/`submeta`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/hooks/useDashboardStats.test.tsx`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useDashboardStats.ts client/src/__tests__/hooks/useDashboardStats.test.tsx
git commit -m "feat(dashboard): extract useDashboardStats derivation hook (#301)"
```

---

### Task 3: `useDashboardAlerts` derivation hook

**Files:**
- Create: `client/src/hooks/useDashboardAlerts.ts`
- Test: `client/src/__tests__/hooks/useDashboardAlerts.test.tsx`

**Interfaces:**
- Consumes: `Alert` from `../components/dashboard`; `SmartStatusResponse` (`../api/smart`), `RaidStatusResponse` (`../api/raid`), `SchedulerStatus` (`../api/schedulers`), `ServiceStatus` (`../api/service-status`).
- Produces:
  ```ts
  export interface UseDashboardAlertsInput {
    smartData: SmartStatusResponse | null;
    raidData: RaidStatusResponse | null;
    allSchedulers: SchedulerStatus[];
    services: ServiceStatus[];
    isAdmin: boolean;
  }
  export function useDashboardAlerts(input: UseDashboardAlertsInput): Alert[];
  ```

**Note:** body is verbatim from Dashboard.tsx 180–254 (the `alerts` memo), calling `useTranslation('dashboard')` internally. Preserve every branch and every i18n key exactly, including the admin gates (`isAdmin && ...`) on scheduler/service alerts and the SMART FAILED→`critical` / UNKNOWN→`warning` split.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDashboardAlerts } from '../../hooks/useDashboardAlerts';
import type { SmartDevice, SmartStatusResponse } from '../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

function dev(status: string): SmartDevice {
  return { name: 'a', model: 'm', serial: 's-' + status, temperature: null, status, capacity_bytes: 1, used_bytes: 0, used_percent: 0, mount_point: null, raid_member_of: null, last_self_test: null, attributes: [] };
}
function smart(...statuses: string[]): SmartStatusResponse { return { checked_at: 'x', devices: statuses.map(dev) }; }

const noOther = { raidData: null, allSchedulers: [], services: [], isAdmin: false };

describe('useDashboardAlerts', () => {
  it('emits a critical alert for FAILED SMART devices', () => {
    const { result } = renderHook(() => useDashboardAlerts({ smartData: smart('FAILED', 'PASSED'), ...noOther }));
    const a = result.current.find(x => x.id === 'smart-failure');
    expect(a?.type).toBe('critical');
  });

  it('emits a warning alert for UNKNOWN SMART devices', () => {
    const { result } = renderHook(() => useDashboardAlerts({ smartData: smart('UNKNOWN'), ...noOther }));
    expect(result.current.find(x => x.id === 'smart-unknown')?.type).toBe('warning');
  });

  it('suppresses scheduler/service alerts for non-admins', () => {
    const schedulers = [{ last_status: 'failed' }] as never;
    const services = [{ state: 'error' }] as never;
    const { result } = renderHook(() => useDashboardAlerts({ smartData: null, raidData: null, allSchedulers: schedulers, services, isAdmin: false }));
    expect(result.current.some(x => x.id === 'scheduler-failed' || x.id === 'service-error')).toBe(false);
  });

  it('emits scheduler + service alerts for admins', () => {
    const schedulers = [{ last_status: 'failed' }] as never;
    const services = [{ state: 'error' }] as never;
    const { result } = renderHook(() => useDashboardAlerts({ smartData: null, raidData: null, allSchedulers: schedulers, services, isAdmin: true }));
    expect(result.current.some(x => x.id === 'scheduler-failed')).toBe(true);
    expect(result.current.some(x => x.id === 'service-error')).toBe(true);
  });
});
```

*(The `as never` casts here are for the two fields the alert logic reads — acceptable in a hook test that exercises only those branches; the page integration test in Task 9 uses complete objects.)*

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/hooks/useDashboardAlerts.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

Create `client/src/hooks/useDashboardAlerts.ts`; port the memo body verbatim from Dashboard.tsx 180–254, dependency array `[smartData, raidData, allSchedulers, services, isAdmin, t]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/hooks/useDashboardAlerts.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useDashboardAlerts.ts client/src/__tests__/hooks/useDashboardAlerts.test.tsx
git commit -m "feat(dashboard): extract useDashboardAlerts derivation hook (#301)"
```

---

### Task 4: `statIcons` + `QuickStatCard`

**Files:**
- Create: `client/src/components/dashboard/statIcons.tsx`
- Create: `client/src/components/dashboard/QuickStatCard.tsx`
- Test: `client/src/__tests__/components/dashboard/QuickStatCard.test.tsx`

**Interfaces:**
- `statIcons.tsx` exports `cpuIcon`, `memoryIcon`, `storageIcon`, `uptimeIcon` (`React.ReactNode`) — the four `<svg>` blocks from Dashboard.tsx `quickStats` (cpu 285–287, memory 300–302, storage 314–316, uptime 328–330), each wrapped exactly as in the source (`className="h-6 w-6" ...`).
- `QuickStatCard.tsx`:
  ```ts
  import type { Delta } from '../../hooks/useDashboardStats';
  export interface QuickStat { id: string; title: string; value: string; meta: string; submeta?: string; delta: Delta; accent: string; progress: number; icon: React.ReactNode; }
  interface QuickStatCardProps { stat: QuickStat; onClick?: () => void; }
  export function QuickStatCard({ stat, onClick }: QuickStatCardProps): JSX.Element;
  ```

**Note:** `QuickStatCard` owns the `deltaToneClass` switch (verbatim 371–377) and the card markup (389–420). `isClickable = !!onClick`; the outer `div` gets `onClick={onClick}` and appends `cursor-pointer` when clickable (verbatim class logic 392).

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuickStatCard, type QuickStat } from '../../../components/dashboard/QuickStatCard';

function stat(overrides: Partial<QuickStat> = {}): QuickStat {
  return { id: 'memory', title: 'Memory', value: '8 GB', meta: 'of 16 GB', delta: { label: '+2%', tone: 'increase' }, accent: 'from-sky-500 to-indigo-500', progress: 50, icon: <svg data-testid="icon" />, ...overrides };
}

describe('QuickStatCard', () => {
  it('renders title, value, meta and delta label', () => {
    render(<QuickStatCard stat={stat({ submeta: 'DDR4' })} />);
    expect(screen.getByText('Memory')).toBeInTheDocument();
    expect(screen.getByText('8 GB')).toBeInTheDocument();
    expect(screen.getByText('of 16 GB')).toBeInTheDocument();
    expect(screen.getByText('+2%')).toBeInTheDocument();
    expect(screen.getByText('DDR4')).toBeInTheDocument();
  });

  it('fires onClick when provided', () => {
    const onClick = vi.fn();
    const { container } = render(<QuickStatCard stat={stat()} onClick={onClick} />);
    fireEvent.click(container.firstChild as Element);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render submeta line when absent', () => {
    render(<QuickStatCard stat={stat()} />);
    expect(screen.queryByText('DDR4')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** — `cd client ; npx vitest run src/__tests__/components/dashboard/QuickStatCard.test.tsx` → FAIL.
- [ ] **Step 3: Implement** `statIcons.tsx` (4 icon constants) and `QuickStatCard.tsx` (delta-tone switch + card markup verbatim, driven by `stat` props + `onClick`).
- [ ] **Step 4: Run to verify pass** → PASS (3/3).
- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/statIcons.tsx client/src/components/dashboard/QuickStatCard.tsx client/src/__tests__/components/dashboard/QuickStatCard.test.tsx
git commit -m "feat(dashboard): extract QuickStatCard + statIcons (#301)"
```

---

### Task 5: `SmartDeviceCard`

**Files:**
- Create: `client/src/components/dashboard/SmartDeviceCard.tsx`
- Test: `client/src/__tests__/components/dashboard/SmartDeviceCard.test.tsx`

**Interfaces:**
- Consumes: `SmartDevice` from `../../api/smart`; `formatBytes` from `../../lib/formatters`.
- Produces:
  ```ts
  interface SmartDeviceCardProps { device: SmartDevice; usedBytes: number; usagePercent: number; }
  export function SmartDeviceCard({ device, usedBytes, usagePercent }: SmartDeviceCardProps): JSX.Element;
  ```

**Note:** presentational only. Markup verbatim from Dashboard.tsx 515–575 (the mapped `<div key={device.serial}>…`), but `usedBytes`/`usagePercent` come from props (the panel computes them). Keep the internal `criticalAttributes` filter (479–481), `tempAttr` find (482), `circleStyle` conic-gradient (511–513), and the `t('smart.device.*')` keys verbatim. Uses `useTranslation('dashboard')`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SmartDeviceCard } from '../../../components/dashboard/SmartDeviceCard';
import type { SmartDevice } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const device: SmartDevice = { name: '/dev/sda', model: 'Samsung SSD', serial: 'SN-9', temperature: 41, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] };

describe('SmartDeviceCard', () => {
  it('renders model, serial, status and usage percent', () => {
    render(<SmartDeviceCard device={device} usedBytes={400} usagePercent={40} />);
    expect(screen.getByText('Samsung SSD')).toBeInTheDocument();
    expect(screen.getByText(/SN-9/)).toBeInTheDocument();
    expect(screen.getByText('PASSED')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** `SmartDeviceCard.tsx` (markup verbatim, `usedBytes`/`usagePercent` from props).
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/SmartDeviceCard.tsx client/src/__tests__/components/dashboard/SmartDeviceCard.test.tsx
git commit -m "feat(dashboard): extract SmartDeviceCard (#301)"
```

---

### Task 6: `SmartHealthPanel`

**Files:**
- Create: `client/src/components/dashboard/SmartHealthPanel.tsx`
- Test: `client/src/__tests__/components/dashboard/SmartHealthPanel.test.tsx`

**Interfaces:**
- Consumes: `SmartStatusResponse` (`../../api/smart`), `computeSmartDeviceUsage` (`./computeSmartDeviceUsage`), `SmartDeviceCard` (`./SmartDeviceCard`). Uses `useTranslation('dashboard')`.
- Produces:
  ```ts
  interface SmartHealthPanelProps {
    smartData: SmartStatusResponse | null;
    smartLoading: boolean;
    smartError: string | null;
    smartMode: string | null;
    smartModeLoading: boolean;
    onToggleSmartMode: () => void;
    storageUsed: number;
  }
  export function SmartHealthPanel(props: SmartHealthPanelProps): JSX.Element;
  ```

**Note:** the full SMART card verbatim from Dashboard.tsx 440–585. Header (441–466): title, dev-only mode toggle button (`smartMode &&` → button with `onClick={onToggleSmartMode}`, `disabled={smartModeLoading}`, verbatim `title`/label logic), status badge (loading/error/healthy). Body (467–584): loading/error/empty states, and `smartData.devices.map(device => { const { usedBytes, usagePercent } = computeSmartDeviceUsage(device, smartData.devices, storageUsed); return <SmartDeviceCard device={device} usedBytes={usedBytes} usagePercent={usagePercent} />; })`. Preserve all i18n keys.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SmartHealthPanel } from '../../../components/dashboard/SmartHealthPanel';
import type { SmartStatusResponse } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = { smartLoading: false, smartError: null, smartMode: null, smartModeLoading: false, onToggleSmartMode: () => {}, storageUsed: 0 };
const oneDevice: SmartStatusResponse = { checked_at: 'x', devices: [
  { name: '/dev/sda', model: 'Disk A', serial: 'A', temperature: 40, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] },
] };

describe('SmartHealthPanel', () => {
  it('shows loading state', () => {
    render(<SmartHealthPanel {...base} smartData={null} smartLoading />);
    expect(screen.getByText('smart.loading')).toBeInTheDocument();
  });
  it('shows empty state', () => {
    render(<SmartHealthPanel {...base} smartData={{ checked_at: 'x', devices: [] }} />);
    expect(screen.getByText('smart.noDevices')).toBeInTheDocument();
  });
  it('renders devices', () => {
    render(<SmartHealthPanel {...base} smartData={oneDevice} />);
    expect(screen.getByText('Disk A')).toBeInTheDocument();
  });
  it('renders and fires the dev mode toggle', () => {
    const onToggleSmartMode = vi.fn();
    render(<SmartHealthPanel {...base} smartData={oneDevice} smartMode="mock" onToggleSmartMode={onToggleSmartMode} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onToggleSmartMode).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** `SmartHealthPanel.tsx` (verbatim, wired to props + helper + `SmartDeviceCard`).
- [ ] **Step 4: Run to verify pass** → PASS (4/4).
- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/SmartHealthPanel.tsx client/src/__tests__/components/dashboard/SmartHealthPanel.test.tsx
git commit -m "feat(dashboard): extract SmartHealthPanel (#301)"
```

---

### Task 7: `RaidSummaryCard`

**Files:**
- Create: `client/src/components/dashboard/RaidSummaryCard.tsx`
- Test: `client/src/__tests__/components/dashboard/RaidSummaryCard.test.tsx`

**Interfaces:**
- Consumes: `RaidStatusResponse` (`../../api/raid`); `formatBytes`, `formatNumber` (`../../lib/formatters`). Uses `useTranslation('dashboard')`.
- Produces:
  ```ts
  interface RaidSummaryCardProps { raidData: RaidStatusResponse | null; raidLoading: boolean; }
  export function RaidSummaryCard({ raidData, raidLoading }: RaidSummaryCardProps): JSX.Element;
  ```

**Note:** verbatim from Dashboard.tsx 593–644 — the outer `card` wrapper, `t('raid.configTitle')`/`t('raid.title')` header, loading/empty states, per-array status pill (full status→class chain 607–617), device counts (`t('raid.devices'/'raid.active')`), resync progress bar.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RaidSummaryCard } from '../../../components/dashboard/RaidSummaryCard';
import type { RaidStatusResponse } from '../../../api/raid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const withArray: RaidStatusResponse = { arrays: [
  { name: 'md0', level: '1', size_bytes: 1000, status: 'clean', devices: [{ name: 'sda', state: 'active' }, { name: 'sdb', state: 'active' }], resync_progress: null },
] };

describe('RaidSummaryCard', () => {
  it('shows loading', () => {
    render(<RaidSummaryCard raidData={null} raidLoading />);
    expect(screen.getByText('raid.loading')).toBeInTheDocument();
  });
  it('shows no-arrays state', () => {
    render(<RaidSummaryCard raidData={{ arrays: [] }} raidLoading={false} />);
    expect(screen.getByText('raid.noArrays')).toBeInTheDocument();
  });
  it('renders an array with its status', () => {
    render(<RaidSummaryCard raidData={withArray} raidLoading={false} />);
    expect(screen.getByText('md0')).toBeInTheDocument();
    expect(screen.getByText('clean')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** `RaidSummaryCard.tsx` (verbatim).
- [ ] **Step 4: Run to verify pass** → PASS (3/3).
- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/RaidSummaryCard.tsx client/src/__tests__/components/dashboard/RaidSummaryCard.test.tsx
git commit -m "feat(dashboard): extract RaidSummaryCard (#301)"
```

---

### Task 8: `SystemHealthCard`

**Files:**
- Create: `client/src/components/dashboard/SystemHealthCard.tsx`
- Test: `client/src/__tests__/components/dashboard/SystemHealthCard.test.tsx`

**Interfaces:**
- Consumes: `SmartStatusResponse` (`../../api/smart`), `RaidStatusResponse` (`../../api/raid`); `formatBytes`, `formatNumber` (`../../lib/formatters`). Uses `useTranslation('dashboard')`.
- Produces:
  ```ts
  interface SystemHealthCardProps {
    smartData: SmartStatusResponse | null;
    smartLoading: boolean;
    smartError: string | null;
    raidData: RaidStatusResponse | null;
    raidLoading: boolean;
    storagePercent: number;
  }
  export function SystemHealthCard(props: SystemHealthCardProps): JSX.Element;
  ```

**Note:** verbatim from Dashboard.tsx 646–703 — the `card` wrapper, `t('health.title')`/`t('health.checksTitle')`, and the six `<li>` rows (SMART status, RAID status, physical drives count, total capacity, avg temp, storage used % = `formatNumber(storagePercent, 1)`). All conditionals and i18n keys verbatim.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SystemHealthCard } from '../../../components/dashboard/SystemHealthCard';
import type { SmartStatusResponse } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const smart: SmartStatusResponse = { checked_at: 'x', devices: [
  { name: 'a', model: 'm', serial: 's1', temperature: 40, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] },
] };

describe('SystemHealthCard', () => {
  it('renders health rows with all-drives-ok when SMART passed', () => {
    render(<SystemHealthCard smartData={smart} smartLoading={false} smartError={null} raidData={{ arrays: [] }} raidLoading={false} storagePercent={40} />);
    expect(screen.getByText('health.checksTitle')).toBeInTheDocument();
    expect(screen.getByText('health.allDrivesOk')).toBeInTheDocument();
    expect(screen.getByText('40.0%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** `SystemHealthCard.tsx` (verbatim).
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit**

```bash
git add client/src/components/dashboard/SystemHealthCard.tsx client/src/__tests__/components/dashboard/SystemHealthCard.test.tsx
git commit -m "feat(dashboard): extract SystemHealthCard (#301)"
```

---

### Task 9: Barrel + Dashboard.tsx orchestrator rewrite + page integration test

**Files:**
- Modify: `client/src/components/dashboard/index.ts`
- Modify: `client/src/pages/Dashboard.tsx`
- Test: `client/src/__tests__/pages/Dashboard.test.tsx`

**Interfaces:**
- Consumes everything from Tasks 1–8. Page keeps its data hooks (`useSystemTelemetry`, `useSmartData`, `useRaidStatus`, `useSmartMode`, `useGpuPresence`, `useGpuCurrent`, `useNextMaintenance`, `useServicesSummary`, `useLiveActivities`) and navigation.
- Barrel adds: `QuickStatCard` (+ `QuickStat`), `SmartHealthPanel`, `SmartDeviceCard`, `RaidSummaryCard`, `SystemHealthCard`.

**Page composition (after):**
- `const stats = useDashboardStats({ systemInfo, storageInfo, smartData, history });`
- `const alerts = useDashboardAlerts({ smartData, raidData, allSchedulers, services, isAdmin });`
- Build `quickStats: QuickStat[]` from `stats` + icons from `statIcons` (cpu card gated on `!hasGpu`, using `stats.cpuStatBase`; memory/storage/uptime as in 290–332, deltas from `stats.memoryDelta`/`stats.storageDelta`/`{label:'Live',tone:'live'}`).
- Render `quickStats.map(stat => <QuickStatCard key={stat.id} stat={stat} onClick={handlerFor(stat.id)} />)` where `handlerFor` reproduces the id→navigate mapping (380–384).
- Replace inline SMART block with `<SmartHealthPanel smartData={smartData} smartLoading={smartLoading} smartError={smartError} smartMode={smartMode} smartModeLoading={smartModeLoading} onToggleSmartMode={handleToggleSmartMode} storageUsed={stats.storageStats.used} />`.
- Replace RAID card with `<RaidSummaryCard raidData={raidData} raidLoading={raidLoading} />`.
- Replace health card with `<SystemHealthCard smartData={smartData} smartLoading={smartLoading} smartError={smartError} raidData={raidData} raidLoading={raidLoading} storagePercent={stats.storageStats.percent} />`.
- Keep `CpuGpuPanel` (gated on `hasGpu && gpuInfo`, `cpu={stats.cpuStatBase}`), `AlertBanner`, `LiveActivities`, `ActivityFeed`, the four panels, `ConnectedDevicesWidget`, `NextMaintenanceWidget`, the header, `error`, and `loading` gate — all verbatim in placement.

- [ ] **Step 1: Write the failing page integration test**

Model the test on `client/src/__tests__/pages/SharesPage.test.tsx` (same repo conventions — mock the data hooks + `react-i18next`, wrap in the router/query provider as that file does). Assert:
```tsx
// mock ../../hooks/useSystemTelemetry, useSmartData, useRaidStatus, useSmartMode,
// useGpuPresence, useGpuCurrent, useNextMaintenance, useServicesSummary,
// useLiveActivities, and ../../contexts/AuthContext (isAdmin) with complete fixtures.
it('renders the dashboard with a quick-stat value and the SMART panel', () => {
  // smartData has one PASSED device; systemInfo present; hasGpu false
  render(<Dashboard />, { wrapper });
  expect(screen.getByText('title')).toBeInTheDocument();      // header i18n key
  expect(screen.getByText('Disk A')).toBeInTheDocument();     // SMART panel device
});
it('surfaces a critical alert when a SMART device has FAILED', () => {
  // smartData with a FAILED device
  render(<Dashboard />, { wrapper });
  expect(screen.getByText('alerts.smartFailure.title')).toBeInTheDocument();
});
```
Use complete fixture objects for every mocked hook return (no partial casts). If a router/QueryClient wrapper is needed, reuse `__tests__/helpers/queryClient.tsx` + `MemoryRouter` exactly as `SharesPage.test.tsx` does.

- [ ] **Step 2: Run to verify fail**

Run: `cd client ; npx vitest run src/__tests__/pages/Dashboard.test.tsx`
Expected: FAIL (page still inline / imports not wired).

- [ ] **Step 3: Update barrel and rewrite the page**

Add the five new exports to `components/dashboard/index.ts`. Rewrite `pages/Dashboard.tsx` per the composition above. Delete the now-unused inline interfaces (`SystemStats`, `StorageStats`), memos, `formatDelta`, and the moved JSX. Keep imports minimal (remove `useMemo`/`formatUptime` etc. only if genuinely unused — verify against the final page).

- [ ] **Step 4: Run to verify pass**

Run: `cd client ; npx vitest run src/__tests__/pages/Dashboard.test.tsx`
Expected: PASS.

- [ ] **Step 5: Verify page size + full gates**

Run:
```bash
cd client
node -e "console.log(require('fs').readFileSync('src/pages/Dashboard.tsx','utf8').split(/\r?\n/).length)"   # expect < 500
npx eslint .
npm run build
npx vitest run
```
Expected: line count < 500; eslint 0 errors; build green; full suite green.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/dashboard/index.ts client/src/pages/Dashboard.tsx client/src/__tests__/pages/Dashboard.test.tsx
git commit -m "refactor(dashboard): compose Dashboard from extracted hooks + cards (#301)"
```

---

### Task 10: Docs + final line-count confirmation

**Files:**
- Modify: `client/src/components/CLAUDE.md`
- Modify: `client/src/hooks/CLAUDE.md`

**Note:** add the new dashboard components (QuickStatCard, statIcons, SmartHealthPanel, SmartDeviceCard, RaidSummaryCard, SystemHealthCard, computeSmartDeviceUsage) to the dashboard line in `components/CLAUDE.md`, and the two new hooks (`useDashboardStats`, `useDashboardAlerts`) to `hooks/CLAUDE.md`, matching the existing one-line style.

- [ ] **Step 1: Update both CLAUDE.md files** (match surrounding format; no behavior claims beyond what exists).
- [ ] **Step 2: Confirm the final page size**

Run: `cd client ; node -e "console.log(require('fs').readFileSync('src/pages/Dashboard.tsx','utf8').split(/\r?\n/).length)"`
Expected: < 500 (target ~150–180).

- [ ] **Step 3: Commit**

```bash
git add client/src/components/CLAUDE.md client/src/hooks/CLAUDE.md
git commit -m "docs(dashboard): document extracted hooks + components (#301)"
```

---

## Self-Review

**Spec coverage:** every spec unit maps to a task — computeSmartDeviceUsage (T1), useDashboardStats (T2), useDashboardAlerts (T3), statIcons+QuickStatCard (T4), SmartDeviceCard (T5), SmartHealthPanel (T6), RaidSummaryCard (T7), SystemHealthCard (T8), barrel+page+integration test (T9), docs (T10). Testing matrix from the spec is covered across T1–T9.

**Placeholder scan:** the `/* verbatim NN–NN */` markers in Task 2 are explicit pointers to exact source lines the implementer copies (not vague TODOs); all other steps carry complete code or exact copy-from-source ranges.

**Type consistency:** `Delta`/`DeltaTone` defined in T2, consumed by `QuickStat` in T4; `CpuStatBase` (T2) is structurally assignable to `CpuGpuPanel`'s `CpuPart` prop (verified: same fields, `Vendor` exported, identical `DeltaTone` union). `SmartDevice`/`SmartStatusResponse`, `RaidStatusResponse`, `ServiceStatus`, `SchedulerStatus`, `SystemInfoResponse`, `TelemetryHistory` are the real API types used consistently. `computeSmartDeviceUsage` signature identical in T1 (definition) and T6 (consumer).
