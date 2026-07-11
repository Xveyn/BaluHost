# PowerTab.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `client/src/components/system-monitor/PowerTab.tsx` (690 lines) into two data/state hooks, one pure helper, and a `power-tab/` directory of presentational components, behavior-preserving, dropping the tab to ~150 lines.

**Architecture:** `usePowerTabData` owns both queries + derived read-values; `useEnergyPrice` owns the price editor state + save; `parseDevicePower` is a pure helper; presentational components under `components/system-monitor/power-tab/` receive props + callbacks. PowerTab keeps the selection state and composes everything.

**Tech Stack:** React 18 + TypeScript (strict), Vite, Tailwind, react-i18next, @tanstack/react-query, recharts, react-hot-toast, Vitest + @testing-library/react.

## Global Constraints

- **Behavior-preserving:** every moved value is byte-identical — same query keys (`queryKeys.powerTab.summary()` / `.cumulative(...)`), `refetchInterval` (5000 / 60000), 404-swallow, `resolveCumulativeArgs`, validation bounds (0.01–10.0), i18n keys, recharts props, Tailwind classes.
- **Tab stays at path:** `components/system-monitor/PowerTab.tsx`, named `export function PowerTab()`. The `system-monitor/index.ts` barrel line is unchanged.
- **Presentational components** are props-in/callbacks-in, no fetch. **Hooks** own fetch/state and call `useTranslation`/`usePlugins`/`useQueryClient` internally as needed.
- **i18n test mock (verbatim):**
  ```ts
  vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (k: string, d?: string) => (typeof d === 'string' ? d : k), i18n: { language: 'en' } }),
  }));
  ```
  (PowerTab uses `t(key, defaultString)` in several places — returning the default when present keeps those assertions meaningful; assert on the returned string.)
- **recharts mock** for chart tests (no real chart dims in jsdom):
  ```ts
  vi.mock('recharts', () => new Proxy({}, { get: () => (props: { children?: unknown }) => props?.children ?? null }));
  ```
- **T7:** assert on role/text/title, never Tailwind classes. Fixtures are complete objects of the real API types (`SmartDevice`, `CumulativeEnergyResponse`, `EnergyPriceConfig`, `PowerSummary`).
- **QueryClient tests:** use `__tests__/helpers/queryClient.tsx` (`createQueryWrapper`, `renderWithQueryClient`).
- **Windows/CRLF:** LF→CRLF warning on commit is expected.
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017SpZfCSw8idoeYBoci5rZD
  ```

## Reference types (already in the codebase)

```ts
// api/smart-devices.ts
interface SmartDevice { id: number; name: string; plugin_name: string; capabilities: string[]; is_active: boolean; is_online: boolean; state: Record<string, unknown> | null; /* …others… */ }
interface PowerSummary { total_watts: number; }
smartDevicesApi.list() // -> { data: { devices: SmartDevice[] } }
smartDevicesApi.getPowerSummary() // -> { data: PowerSummary }
// api/energy.ts
interface CumulativeEnergyResponse { device_id: number; device_name: string; period: string; cost_per_kwh: number; currency: string; total_kwh: number; total_cost: number; data_points: CumulativeDataPoint[]; }
interface CumulativeDataPoint { timestamp: string; cumulative_kwh: number; cumulative_cost: number; instant_watts: number; }
interface EnergyPriceConfig { id: number; cost_per_kwh: number; currency: string; updated_at: string; updated_by_user_id: number | null; }
// queryKeys.powerTab.summary() / .cumulative(deviceId, period, start, end)
// lib/energyPolling.ts: resolveCumulativeArgs(period, customStart, customEnd) -> { period, start?, end? }
```

## File Structure

- Create `client/src/components/system-monitor/power-tab/parseDevicePower.ts`
- Create `client/src/hooks/usePowerTabData.ts`
- Create `client/src/hooks/useEnergyPrice.ts`
- Create `client/src/components/system-monitor/power-tab/PowerStates.tsx`
- Create `client/src/components/system-monitor/power-tab/PowerSummaryCards.tsx`
- Create `client/src/components/system-monitor/power-tab/PowerDeviceCard.tsx`
- Create `client/src/components/system-monitor/power-tab/EnergyPriceEditor.tsx`
- Create `client/src/components/system-monitor/power-tab/ChartDeviceTabs.tsx`
- Create `client/src/components/system-monitor/power-tab/CustomRangePicker.tsx`
- Create `client/src/components/system-monitor/power-tab/ChartModePeriodControls.tsx`
- Create `client/src/components/system-monitor/power-tab/EnergyChartSummary.tsx`
- Create `client/src/components/system-monitor/power-tab/CumulativeEnergyChart.tsx`
- Create `client/src/components/system-monitor/power-tab/InstantPowerChart.tsx`
- Create `client/src/components/system-monitor/power-tab/EnergyChart.tsx`
- Create `client/src/components/system-monitor/power-tab/index.ts`
- Modify `client/src/components/system-monitor/PowerTab.tsx`
- Tests mirror source under `client/src/__tests__/...`
- Docs: `client/src/components/CLAUDE.md`, `client/src/hooks/CLAUDE.md`

All extractions copy from the current `client/src/components/system-monitor/PowerTab.tsx` (HEAD of this branch); line ranges are given per task.

---

### Task 1: `parseDevicePower` pure helper

**Files:**
- Create: `client/src/components/system-monitor/power-tab/parseDevicePower.ts`
- Test: `client/src/__tests__/components/system-monitor/power-tab/parseDevicePower.test.ts`

**Interfaces:**
- Consumes: `SmartDevice` from `../../../api/smart-devices`.
- Produces:
  ```ts
  export interface DevicePower { watts?: number; voltage?: number; currentA?: number; energyToday?: number; }
  export function parseDevicePower(device: SmartDevice): DevicePower;
  ```

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { parseDevicePower } from '../../../../components/system-monitor/power-tab/parseDevicePower';
import type { SmartDevice } from '../../../../api/smart-devices';

function dev(power_monitor: Record<string, unknown> | undefined): SmartDevice {
  return {
    id: 1, name: 'Plug', plugin_name: 'p', device_type_id: 't', address: 'a', mac_address: null,
    capabilities: ['power_monitor'], is_active: true, is_online: true, last_seen: null, last_error: null,
    state: power_monitor ? { power_monitor } : null, created_at: '', updated_at: '',
  };
}

describe('parseDevicePower', () => {
  it('prefers watts and current/energy in base units', () => {
    expect(parseDevicePower(dev({ watts: 12.5, voltage: 230, current: 0.05, energy_today_kwh: 1.2 })))
      .toEqual({ watts: 12.5, voltage: 230, currentA: 0.05, energyToday: 1.2 });
  });
  it('falls back to current_power, current_ma/1000, energy_today_wh/1000', () => {
    expect(parseDevicePower(dev({ current_power: 9, current_ma: 250, energy_today_wh: 800 })))
      .toEqual({ watts: 9, voltage: undefined, currentA: 0.25, energyToday: 0.8 });
  });
  it('returns all-undefined when power_monitor missing', () => {
    expect(parseDevicePower(dev(undefined))).toEqual({ watts: undefined, voltage: undefined, currentA: undefined, energyToday: undefined });
  });
});
```

- [ ] **Step 2: Run to verify fail** — `cd client ; npx vitest run src/__tests__/components/system-monitor/power-tab/parseDevicePower.test.ts` → FAIL (module not found).
- [ ] **Step 3: Implement** (verbatim logic from PowerTab.tsx 232–236):

```ts
import type { SmartDevice } from '../../../api/smart-devices';

export interface DevicePower {
  watts?: number;
  voltage?: number;
  currentA?: number;
  energyToday?: number;
}

export function parseDevicePower(device: SmartDevice): DevicePower {
  const pm = device.state?.power_monitor as
    | { watts?: number; current_power?: number; voltage?: number; current?: number; current_ma?: number; energy_today_kwh?: number; energy_today_wh?: number }
    | undefined;
  const watts = pm?.watts ?? pm?.current_power;
  const voltage = pm?.voltage;
  const currentA = pm?.current ?? (pm?.current_ma != null ? pm.current_ma / 1000 : undefined);
  const energyToday = pm?.energy_today_kwh ?? (pm?.energy_today_wh != null ? pm.energy_today_wh / 1000 : undefined);
  return { watts, voltage, currentA, energyToday };
}
```

- [ ] **Step 4: Run to verify pass** → PASS (3/3).
- [ ] **Step 5: Commit** — `feat(powertab): extract parseDevicePower pure helper (#301)`

---

### Task 2: `usePowerTabData` hook

**Files:**
- Create: `client/src/hooks/usePowerTabData.ts`
- Test: `client/src/__tests__/hooks/usePowerTabData.test.tsx`

**Interfaces:**
- Consumes: `smartDevicesApi` (`../api/smart-devices`), `getCumulativeEnergy`/`getCumulativeEnergyTotal` + `CumulativeEnergyResponse` (`../api/energy`), `queryKeys` (`../lib/queryKeys`), `resolveCumulativeArgs` (`../lib/energyPolling`), `getApiErrorMessage` (`../lib/errorHandling`), `usePlugins` (`../contexts/PluginContext`), `SmartDevice`/`PowerSummary` (`../api/smart-devices`).
- Produces:
  ```ts
  export interface UsePowerTabDataInput { selectedDeviceId: number | null; cumulativePeriod: 'today'|'week'|'month'|'custom'; customStart: string | null; customEnd: string | null; }
  export interface CumulativeKeyArgs { period: string; start: string | null; end: string | null; }
  export interface UsePowerTabDataResult {
    devices: SmartDevice[]; powerSummary: PowerSummary | null; loading: boolean; error: string | null;
    cumulativeData: CumulativeEnergyResponse | null; cumulativeLoading: boolean; cumulativeReady: boolean;
    totalCurrentPower: number; powerPluginName: string | undefined; cumulativeKeyArgs: CumulativeKeyArgs;
  }
  export function usePowerTabData(input: UsePowerTabDataInput): UsePowerTabDataResult;
  ```

**Note:** port `powerQuery` (68–90), `rangeArgs`/`cumulativeReady`/`cumulativeQuery` (92–112), `totalCurrentPower`/`powerPluginName` (160–163) verbatim. `cumulativeKeyArgs = { period: rangeArgs.period, start: rangeArgs.start ?? null, end: rangeArgs.end ?? null }`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('../../api/smart-devices', () => ({ smartDevicesApi: { list: vi.fn(), getPowerSummary: vi.fn() } }));
vi.mock('../../api/energy', () => ({ getCumulativeEnergy: vi.fn(), getCumulativeEnergyTotal: vi.fn() }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => ({ plugins: [] }) }));

import { smartDevicesApi } from '../../api/smart-devices';
import { getCumulativeEnergyTotal } from '../../api/energy';
import { usePowerTabData } from '../../hooks/usePowerTabData';

const device = { id: 1, name: 'Plug', plugin_name: 'p', device_type_id: 't', address: 'a', mac_address: null, capabilities: ['power_monitor'], is_active: true, is_online: true, last_seen: null, last_error: null, state: null, created_at: '', updated_at: '' };

beforeEach(() => {
  vi.clearAllMocks();
  (smartDevicesApi.list as any).mockResolvedValue({ data: { devices: [device] } });
  (smartDevicesApi.getPowerSummary as any).mockResolvedValue({ data: { total_watts: 42 } });
  (getCumulativeEnergyTotal as any).mockResolvedValue({ device_id: 0, device_name: '', period: 'today', cost_per_kwh: 0.3, currency: 'EUR', total_kwh: 1, total_cost: 0.3, data_points: [] });
});

const base = { selectedDeviceId: null, cumulativePeriod: 'today' as const, customStart: null, customEnd: null };

describe('usePowerTabData', () => {
  it('exposes devices, totalCurrentPower and cumulative data', async () => {
    const { result } = renderHook(() => usePowerTabData(base), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.devices).toHaveLength(1);
    expect(result.current.totalCurrentPower).toBe(42);
    await waitFor(() => expect(result.current.cumulativeData?.total_kwh).toBe(1));
    expect(result.current.cumulativeReady).toBe(true);
  });

  it('cumulativeReady false for custom with no applied range', () => {
    const { result } = renderHook(() => usePowerTabData({ ...base, cumulativePeriod: 'custom' }), { wrapper: createQueryWrapper() });
    expect(result.current.cumulativeReady).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** — port the two queries + derived verbatim; `usePlugins()` internally for `powerPluginName`. `error` = 404-swallow logic (83–90).
- [ ] **Step 4: Run to verify pass** → PASS (2/2).
- [ ] **Step 5: Commit** — `feat(powertab): extract usePowerTabData hook (#301)`

---

### Task 3: `useEnergyPrice` hook

**Files:**
- Create: `client/src/hooks/useEnergyPrice.ts`
- Test: `client/src/__tests__/hooks/useEnergyPrice.test.tsx`

**Interfaces:**
- Consumes: `getEnergyPriceConfig`/`updateEnergyPriceConfig`/`EnergyPriceConfig` (`../api/energy`), `getApiErrorMessage` (`../lib/errorHandling`), `toast` (`react-hot-toast`), `useTranslation`.
- Produces:
  ```ts
  export interface UseEnergyPriceResult { priceConfig: EnergyPriceConfig | null; editingPrice: boolean; setEditingPrice: (v: boolean) => void; priceInput: string; setPriceInput: (v: string) => void; savingPrice: boolean; savePrice: () => Promise<void>; }
  export function useEnergyPrice(onSaved?: () => void | Promise<void>): UseEnergyPriceResult;
  ```

**Note:** port the mount `useEffect` fetch (114–126) and `handleSavePrice` (128–158) verbatim, replacing the inline `invalidateQueries` call with `await onSaved?.()`. `useTranslation(['system','common'])` internally.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/energy', () => ({ getEnergyPriceConfig: vi.fn(), updateEnergyPriceConfig: vi.fn() }));

import toast from 'react-hot-toast';
import { getEnergyPriceConfig, updateEnergyPriceConfig } from '../../api/energy';
import { useEnergyPrice } from '../../hooks/useEnergyPrice';

const cfg = { id: 1, cost_per_kwh: 0.3, currency: 'EUR', updated_at: '', updated_by_user_id: null };

beforeEach(() => {
  vi.clearAllMocks();
  (getEnergyPriceConfig as any).mockResolvedValue(cfg);
  (updateEnergyPriceConfig as any).mockResolvedValue({ ...cfg, cost_per_kwh: 0.4 });
});

describe('useEnergyPrice', () => {
  it('seeds config on mount', async () => {
    const { result } = renderHook(() => useEnergyPrice());
    await waitFor(() => expect(result.current.priceConfig?.cost_per_kwh).toBe(0.3));
    expect(result.current.priceInput).toBe('0.3');
  });

  it('rejects out-of-range price (no update, error toast)', async () => {
    const { result } = renderHook(() => useEnergyPrice());
    await waitFor(() => expect(result.current.priceConfig).not.toBeNull());
    act(() => result.current.setPriceInput('99'));
    await act(async () => { await result.current.savePrice(); });
    expect(updateEnergyPriceConfig).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it('saves in-range price and calls onSaved', async () => {
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEnergyPrice(onSaved));
    await waitFor(() => expect(result.current.priceConfig).not.toBeNull());
    act(() => result.current.setPriceInput('0.4'));
    await act(async () => { await result.current.savePrice(); });
    expect(updateEnergyPriceConfig).toHaveBeenCalledWith({ cost_per_kwh: 0.4, currency: 'EUR' });
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** — verbatim mount fetch + save logic; `await onSaved?.()` in place of the query invalidation; toast keys verbatim.
- [ ] **Step 4: Run to verify pass** → PASS (3/3).
- [ ] **Step 5: Commit** — `feat(powertab): extract useEnergyPrice hook (#301)`

---

### Task 4: `PowerStates` (loading / error / empty)

**Files:**
- Create: `client/src/components/system-monitor/power-tab/PowerStates.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/PowerStates.test.tsx`

**Interfaces:**
- Consumes: `Link` (`react-router-dom`), `useTranslation`.
- Produces: `export function PowerLoading(): JSX.Element;` `export function PowerError({ error }: { error: string }): JSX.Element;` `export function PowerEmptyState(): JSX.Element;`

**Note:** markup verbatim — `PowerLoading` from 166–170, `PowerError` from 174, `PowerEmptyState` from 178–201 (icon + `t('monitor.power.noSmartDevices', 'No smart devices…')` + `Link to="/smart-devices"` + `t('monitor.power.configureSmartDevices', 'Configure Smart Devices')`). `useTranslation(['system','common'])`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PowerError, PowerEmptyState } from '../../../../components/system-monitor/power-tab/PowerStates';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, d?: string) => (typeof d === 'string' ? d : k) }) }));

describe('PowerStates', () => {
  it('PowerError shows the message', () => {
    render(<PowerError error="boom" />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });
  it('PowerEmptyState links to smart devices', () => {
    render(<MemoryRouter><PowerEmptyState /></MemoryRouter>);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/smart-devices');
    expect(screen.getByText(/No smart devices/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Implement** the three renders (markup verbatim).
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit** — `feat(powertab): extract PowerStates (loading/error/empty) (#301)`

---

### Task 5: `PowerSummaryCards`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/PowerSummaryCards.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/PowerSummaryCards.test.tsx`

**Interfaces:**
- Consumes: `StatCard` (`../../ui/StatCard`), `formatNumber` (`../../../lib/formatters`), `useTranslation`.
- Produces: `interface PowerSummaryCardsProps { totalCurrentPower: number; onlineCount: number; deviceCount: number; }` `export function PowerSummaryCards(props): JSX.Element;`

**Note:** the 3 `StatCard`s (207–228). Current power = `formatNumber(totalCurrentPower, 1)` W; online = `onlineCount` unit `/ ${deviceCount}`; devices = `deviceCount`. i18n keys verbatim (`currentPower`, `onlineDevices`, `devices`).

- [ ] **Step 1: failing test** — render with `{ totalCurrentPower: 42.4, onlineCount: 2, deviceCount: 3 }`; assert `getByText('42.4')`, `getByText('2')`, `getByText('/ 3')`. Mock i18n. Mock `StatCard`? No — use the real `StatCard` (a ui primitive); assert on the rendered value/unit text.
- [ ] **Step 2: fail** → FAIL.
- [ ] **Step 3: implement** (markup verbatim; `devices.filter(d=>d.is_online).length` becomes the `onlineCount` prop, computed by the caller).
- [ ] **Step 4: pass** → PASS.
- [ ] **Step 5: commit** — `feat(powertab): extract PowerSummaryCards (#301)`

---

### Task 6: `PowerDeviceCard`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/PowerDeviceCard.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/PowerDeviceCard.test.tsx`

**Interfaces:**
- Consumes: `SmartDevice` (`../../../api/smart-devices`), `parseDevicePower` (`./parseDevicePower`), `formatNumber` (`../../../lib/formatters`), `useTranslation`.
- Produces: `interface PowerDeviceCardProps { device: SmartDevice; }` `export function PowerDeviceCard({ device }): JSX.Element;`

**Note:** markup verbatim (239–272); `const { watts, voltage, currentA, energyToday } = parseDevicePower(device);` replaces the inline `pm` block. `-` fallbacks and `formatNumber` precisions (1/1/3/2) verbatim. Online badge from `device.is_online`.

- [ ] **Step 1: failing test** — device with `state.power_monitor = { watts: 12.5, voltage: 230, current: 0.05, energy_today_kwh: 1.2 }`; assert name, online badge text, `12.5`, `230`, `0.050`, `1.20`. A second device (separate render) with `state: null` → `expect(screen.getAllByText('-')).toHaveLength(4)`. Mock i18n.
- [ ] **Step 2: fail** → FAIL.
- [ ] **Step 3: implement** (verbatim).
- [ ] **Step 4: pass** → PASS.
- [ ] **Step 5: commit** — `feat(powertab): extract PowerDeviceCard (#301)`

---

### Task 7: `EnergyPriceEditor`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/EnergyPriceEditor.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/EnergyPriceEditor.test.tsx`

**Interfaces:**
- Consumes: `EnergyPriceConfig` (`../../../api/energy`), `formatNumber` (`../../../lib/formatters`).
- Produces:
  ```ts
  interface EnergyPriceEditorProps {
    priceConfig: EnergyPriceConfig; editing: boolean; priceInput: string; saving: boolean;
    onEdit: () => void; onInputChange: (v: string) => void; onSave: () => void; onCancel: () => void;
  }
  export function EnergyPriceEditor(props): JSX.Element;
  ```

**Note:** markup verbatim (316–361). The whole block is gated by `priceConfig` in the parent, so this component assumes a non-null `priceConfig`. View mode shows `formatNumber(priceConfig.cost_per_kwh, 2) {currency}/kWh` + edit pencil (`onEdit`); edit mode shows the number input (`onInputChange`), save (`onSave`, `✓`/`...`), cancel (`onCancel`, resets input in the parent).

- [ ] **Step 1: failing test** — view mode (`editing=false`): shows price text, click pencil button → `onEdit`. Edit mode (`editing=true`): input value = `priceInput`, change fires `onInputChange`, `✓` fires `onSave`, `✕` fires `onCancel`. No i18n keys here except none — component has no `t()`; assert on values/roles.
- [ ] **Step 2: fail** → FAIL.
- [ ] **Step 3: implement** (verbatim; note the cancel button in the original also resets `priceInput` — that reset happens in the parent's `onCancel`).
- [ ] **Step 4: pass** → PASS.
- [ ] **Step 5: commit** — `feat(powertab): extract EnergyPriceEditor (#301)`

---

### Task 8: `ChartDeviceTabs`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/ChartDeviceTabs.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/ChartDeviceTabs.test.tsx`

**Interfaces:**
- Consumes: `SmartDevice` (`../../../api/smart-devices`), `useTranslation`.
- Produces: `interface ChartDeviceTabsProps { devices: SmartDevice[]; selectedDeviceId: number | null; onSelect: (id: number | null) => void; }`

**Note:** markup verbatim (279–305): Total button (`onSelect(null)`, `t('monitor.power.total')`) + one button per `devices.filter(d => d.is_active && d.capabilities?.includes('power_monitor'))` (`onSelect(device.id)`, `device.name`). Active styling by `selectedDeviceId`.

- [ ] **Step 1: failing test** — two devices (one active w/ power_monitor, one inactive); assert Total + the active device name render; click device → `onSelect(id)`; click Total → `onSelect(null)`.
- [ ] **Step 2: fail** → FAIL. **Step 3: implement** (verbatim). **Step 4: pass** → PASS. **Step 5: commit** — `feat(powertab): extract ChartDeviceTabs (#301)`

---

### Task 9: `CustomRangePicker` + `ChartModePeriodControls`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/CustomRangePicker.tsx`
- Create: `client/src/components/system-monitor/power-tab/ChartModePeriodControls.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/ChartControls.test.tsx`

**Interfaces:**
- `CustomRangePicker` consumes `localRangeToUtcIso` (`../../../lib/dateUtils`), `toast` (`react-hot-toast`), `useTranslation`. Produces:
  ```ts
  interface CustomRangePickerProps { active: boolean; onApply: (startIso: string, endIso: string) => void; }
  export function CustomRangePicker({ active, onApply }): JSX.Element;
  ```
  Owns `showRangePicker`/`draftStart`/`draftEnd` internally (from 61–63). The `Custom` toggle button (398–407) + popover (408–446) verbatim; Apply validates (`!draftStart || !draftEnd || draftStart > draftEnd` → `toast.error(t('monitor.power.customInvalidRange'))`), else `localRangeToUtcIso(draftStart, draftEnd, Date.now())` → `onApply(startIso, endIso)` + close. `active` drives the button's selected styling (was `cumulativePeriod === 'custom'`).
- `ChartModePeriodControls` consumes `useTranslation`. Produces:
  ```ts
  type ChartMode = 'cumulative' | 'instant';
  type CumulativePeriod = 'today' | 'week' | 'month' | 'custom';
  interface ChartModePeriodControlsProps {
    chartMode: ChartMode; onModeChange: (m: ChartMode) => void;
    cumulativePeriod: CumulativePeriod; onPeriodChange: (p: CumulativePeriod) => void;
    customRange: React.ReactNode;
  }
  ```
  This component **is** the whole right-hand controls cluster — the outer
  `<div className="flex gap-1 sm:gap-2 flex-wrap">` (365) containing, in order:
  the mode toggle (367–379), the vertical divider `<div className="w-px
  bg-slate-700 mx-1 self-stretch" />` (381) **verbatim — do not drop it**, the
  period buttons `today/week/month` (384–396), then `{customRange}` in the slot
  where the custom `<div className="relative">` picker sat (397). Period buttons
  call `onPeriodChange`; mode buttons call `onModeChange`.

- [ ] **Step 1: failing test** (`ChartControls.test.tsx`, mock i18n + `react-hot-toast` + `../../../lib/dateUtils`'s `localRangeToUtcIso` → returns `{ startIso: 'S', endIso: 'E' }`):
  - `ChartModePeriodControls`: renders mode + period buttons; clicking `week` fires `onPeriodChange('week')`; clicking `instant` fires `onModeChange('instant')`; `customRange` node renders.
  - `CustomRangePicker`: click Custom → popover opens; Apply with empty drafts → `toast.error`, no `onApply`; set both dates via `fireEvent.change`, Apply → `onApply('S','E')`.
- [ ] **Step 2: fail** → FAIL. **Step 3: implement** both. **Step 4: pass** → PASS. **Step 5: commit** — `feat(powertab): extract chart mode/period controls + custom range picker (#301)`

---

### Task 10: `EnergyChartSummary`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/EnergyChartSummary.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/EnergyChartSummary.test.tsx`

**Interfaces:**
- Consumes: `CumulativeEnergyResponse` (`../../../api/energy`), `formatNumber` (`../../../lib/formatters`), `useTranslation`.
- Produces: `interface EnergyChartSummaryProps { chartMode: 'cumulative' | 'instant'; cumulativeData: CumulativeEnergyResponse; }`

**Note:** the summary grids (452–515) verbatim. Instant branch computes avg/max/min from `data_points.map(dp => dp.instant_watts)` + `data_points.length`; cumulative branch shows `total_kwh` (3), `total_cost` (2) + currency, `cost_per_kwh` (2), `data_points.length`. i18n keys verbatim. (The parent only renders this when `cumulativeData` is truthy — prop is non-null.)

- [ ] **Step 1: failing test** — cumulative mode with `total_kwh: 1.234, total_cost: 0.37, currency:'EUR', cost_per_kwh:0.3, data_points:[…]` → assert `1.234`, `0.37`, `0.30`; instant mode with data_points `instant_watts:[10,20,30]` → assert avg `20.0`, max `30.0`, min `10.0`. Mock i18n.
- [ ] **Step 2: fail** → FAIL. **Step 3: implement** (verbatim). **Step 4: pass** → PASS. **Step 5: commit** — `feat(powertab): extract EnergyChartSummary (#301)`

---

### Task 11: `CumulativeEnergyChart` + `InstantPowerChart` + `EnergyChart`

**Files:**
- Create: `client/src/components/system-monitor/power-tab/CumulativeEnergyChart.tsx`
- Create: `client/src/components/system-monitor/power-tab/InstantPowerChart.tsx`
- Create: `client/src/components/system-monitor/power-tab/EnergyChart.tsx`
- Test: `client/src/__tests__/components/system-monitor/power-tab/EnergyChart.test.tsx`

**Interfaces:**
- Shared prop shape:
  ```ts
  interface ChartProps { cumulativeData: CumulativeEnergyResponse; cumulativePeriod: 'today'|'week'|'month'|'custom'; language: string; }
  ```
  `CumulativeEnergyChart(props: ChartProps)` = the cumulative `ComposedChart` (526–617) verbatim (data mapping via `formatTimeForRange(dp.timestamp, cumulativePeriod as ChartTimeRange, language)` + `parseUtcTimestamp`, gradients, axes, tooltip, legend, Area+Line). `InstantPowerChart(props: ChartProps)` = the instant `ComposedChart` (619–678) verbatim.
- `EnergyChart`:
  ```ts
  interface EnergyChartProps {
    chartMode: 'cumulative' | 'instant';
    cumulativeData: CumulativeEnergyResponse | null;
    cumulativeLoading: boolean;
    cumulativePeriod: 'today'|'week'|'month'|'custom';
    language: string;
  }
  ```
  Renders the loading spinner (518–521) / empty `t('monitor.noDataForPeriod')` (683–685) / the `ResponsiveContainer` wrapping `CumulativeEnergyChart` or `InstantPowerChart` by `chartMode` (522–681). Uses `useTranslation`, imports `formatTimeForRange`/`parseUtcTimestamp`/`ChartTimeRange` in the chart subcomponents.

**Note:** `import type { ChartTimeRange }` and `formatTimeForRange`/`parseUtcTimestamp` from `../../../lib/dateUtils`; `formatNumber` from `../../../lib/formatters`; recharts imports as in the original.

- [ ] **Step 1: failing test** (mock recharts per Global Constraints; mock i18n) — the spinner has no text/role (T7 forbids class assertions), so key the states off the empty-state text:
  - `cumulativeLoading: true` (data null) → `expect(screen.queryByText('monitor.noDataForPeriod')).toBeNull()` (loading ≠ empty), render does not throw.
  - `cumulativeData: { …, data_points: [] }`, not loading → `getByText('monitor.noDataForPeriod')`.
  - one data point + `chartMode: 'cumulative'`, not loading → `queryByText('monitor.noDataForPeriod')` is null and render does not throw (recharts stubbed — do not assert chart internals).
- [ ] **Step 2: fail** → FAIL.
- [ ] **Step 3: implement** the three files (charts verbatim, `EnergyChart` selects by mode).
- [ ] **Step 4: pass** → PASS.
- [ ] **Step 5: commit** — `feat(powertab): extract EnergyChart + cumulative/instant charts (#301)`

---

### Task 12: Barrel + PowerTab.tsx orchestrator rewrite + integration test

**Files:**
- Create: `client/src/components/system-monitor/power-tab/index.ts`
- Modify: `client/src/components/system-monitor/PowerTab.tsx`
- Test: `client/src/__tests__/components/system-monitor/PowerTab.test.tsx`

**Interfaces:**
- `index.ts` re-exports every `power-tab/*` component + `parseDevicePower`/`DevicePower`.
- `PowerTab.tsx` keeps state `chartMode`, `cumulativePeriod`, `selectedDeviceId`, `customStart`, `customEnd`. Calls:
  ```ts
  const data = usePowerTabData({ selectedDeviceId, cumulativePeriod, customStart, customEnd });
  const queryClient = useQueryClient();
  const price = useEnergyPrice(() => queryClient.invalidateQueries({
    queryKey: queryKeys.powerTab.cumulative(selectedDeviceId, data.cumulativeKeyArgs.period, data.cumulativeKeyArgs.start, data.cumulativeKeyArgs.end),
  }));
  ```
  Early returns: `if (data.loading) return <PowerLoading/>;` `if (data.error) return <PowerError error={data.error}/>;` `if (data.devices.length === 0) return <PowerEmptyState/>;`
  Then composes: `PowerSummaryCards` (`onlineCount = data.devices.filter(d=>d.is_online).length`, `deviceCount = data.devices.length`), `data.devices.map(d => <PowerDeviceCard key={d.id} device={d}/>)`, and the chart card (`<div className="card …">`): `ChartDeviceTabs`, then the header row **verbatim wrapper** `<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">` (308) containing BOTH sides — **left** `<div className="flex items-center gap-3 flex-wrap">` with the `chartMode` title (`t('monitor.power.cumulativeConsumptionCosts')` vs `instantPowerConsumption`) + `<PluginBadge pluginName={data.powerPluginName} size="sm" className="ml-2" />` + `{price.priceConfig && <EnergyPriceEditor .../>}`, and **right** `<ChartModePeriodControls … customRange={<CustomRangePicker active={cumulativePeriod==='custom'} onApply={(s,e)=>{ setCustomStart(s); setCustomEnd(e); setCumulativePeriod('custom'); }}/>} />`. Then `{data.cumulativeData && <EnergyChartSummary chartMode={chartMode} cumulativeData={data.cumulativeData}/>}` and `<EnergyChart chartMode={chartMode} cumulativeData={data.cumulativeData} cumulativeLoading={data.cumulativeLoading} cumulativePeriod={cumulativePeriod} language={i18n.language}/>`. Keep the section-order and the `space-y-4 sm:space-y-6 min-w-0` outer wrapper (205) verbatim.
  - `EnergyPriceEditor` wiring: `editing={price.editingPrice}`, `priceInput={price.priceInput}`, `saving={price.savingPrice}`, `onEdit={() => price.setEditingPrice(true)}`, `onInputChange={price.setPriceInput}`, `onSave={price.savePrice}`, `onCancel={() => { price.setEditingPrice(false); price.setPriceInput(price.priceConfig!.cost_per_kwh.toString()); }}`.
  - Keep the outer card wrappers, header title branch (`t('monitor.power.cumulativeConsumptionCosts')` vs `instantPowerConsumption`), `useTranslation(['system','common'])`, `i18n.language`.

- [ ] **Step 1: Write the failing integration test** (`PowerTab.test.tsx`) — model on the repo's page tests. Mock `../../../hooks/usePowerTabData` and `../../../hooks/useEnergyPrice`, `react-i18next`, and `../../../contexts/PluginContext` (`usePlugins`), wrap in `MemoryRouter` + a QueryClient (PowerTab uses `useQueryClient`). Complete fixtures.
  ```tsx
  // populated: usePowerTabData returns 1 device (power_monitor state), totalCurrentPower 42,
  // cumulativeData with data_points; useEnergyPrice returns priceConfig.
  it('renders stat cards, a device card and the chart toolbar', () => {
    render(<PowerTab />, { wrapper });
    expect(screen.getByText('42.0')).toBeInTheDocument();       // current power
    expect(screen.getByText('Plug')).toBeInTheDocument();       // device card + tab
  });
  it('shows the empty state when there are no devices', () => {
    // usePowerTabData returns devices: []
    render(<PowerTab />, { wrapper });
    expect(screen.getByRole('link')).toHaveAttribute('href', '/smart-devices');
  });
  ```
- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Add barrel + rewrite PowerTab.tsx** per the composition above. Remove now-unused imports (recharts, StatCard, PluginBadge stays if used in header, dateUtils, energy api, smartDevicesApi, resolveCumulativeArgs, etc. — verify against the final file). Keep `useState`, `useQueryClient`, `queryKeys`, `PluginBadge`, `useTranslation`, and the `power-tab` + hook imports.
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Verify page size + full gates**

```bash
cd client
node -e "console.log(require('fs').readFileSync('src/components/system-monitor/PowerTab.tsx','utf8').split(/\r?\n/).length)"   # expect < 500 (~150)
npx eslint .
npm run build
npx vitest run
```
Expected: < 500 lines; eslint 0 errors; build green; full suite green.

- [ ] **Step 6: Commit** — `refactor(powertab): compose PowerTab from extracted hooks + power-tab/* (#301)`

---

### Task 13: Docs + final line-count

**Files:**
- Modify: `client/src/components/CLAUDE.md` (add a `system-monitor/power-tab/*` note to the components table's system-monitor row, mentioning the extracted pieces + `parseDevicePower` and F2/#301)
- Modify: `client/src/hooks/CLAUDE.md` (add `usePowerTabData`, `useEnergyPrice`)

- [ ] **Step 1: Update both CLAUDE.md files** (match surrounding one-line style).
- [ ] **Step 2: Confirm final page size** — `cd client ; node -e "console.log(require('fs').readFileSync('src/components/system-monitor/PowerTab.tsx','utf8').split(/\r?\n/).length)"` → < 500.
- [ ] **Step 3: Commit** — `docs(powertab): document extracted hooks + power-tab components (#301)`

---

## Self-Review

**Spec coverage:** every spec unit maps to a task — parseDevicePower (T1), usePowerTabData (T2), useEnergyPrice (T3), PowerStates (T4), PowerSummaryCards (T5), PowerDeviceCard (T6), EnergyPriceEditor (T7), ChartDeviceTabs (T8), CustomRangePicker+ChartModePeriodControls (T9), EnergyChartSummary (T10), Cumulative/Instant/EnergyChart (T11), barrel+PowerTab+integration (T12), docs (T13).

**Placeholder scan:** verbatim markup is referenced by exact source line ranges (charts, toolbar, cards); complete code is given for the pure helper and the hook/test scaffolding. No vague TODOs.

**Type consistency:** `DevicePower`/`parseDevicePower` defined T1, consumed T6. `CumulativeKeyArgs`/`usePowerTabData` result (T2) consumed by the orchestrator's `onSaved` invalidation (T12). `useEnergyPrice` result (T3) wired into `EnergyPriceEditor` props (T7) by the orchestrator (T12). `ChartProps`/`EnergyChartProps` (T11) consumed by T12. `CumulativeEnergyResponse`/`SmartDevice`/`EnergyPriceConfig`/`PowerSummary` are the real API types used consistently.
