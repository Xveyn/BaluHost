# PowerTab.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-11
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/components/system-monitor/PowerTab.tsx` — currently **690 lines**.

## Goal

Behavior-preserving decomposition of `PowerTab.tsx` (the smart-device energy
monitoring tab) into two data/state hooks, one pure helper, and a directory of
presentational components under a new `components/system-monitor/power-tab/`.

**Non-goals:** no change to queries, endpoints, polling intervals (5s power /
60s cumulative), i18n keys, copy, Tailwind styling, recharts configuration, or
any computed value. The tab stays at its path
(`components/system-monitor/PowerTab.tsx`, named export `PowerTab`) so the
`system-monitor/index.ts` barrel and `SystemMonitor` consumer are untouched.
This is distinct from `components/power/` (CPU power **profiles**) — do not
merge the two.

## Constraints

- Every extracted value is **byte-identical** in behavior: same query keys,
  same `refetchInterval`, same 404-swallow, same `resolveCumulativeArgs` usage,
  same validation bounds, same i18n keys, same recharts props.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching. Extracted hooks own the fetching/state.
- Tests are T7-conform: assert on role/text/title, never Tailwind classes;
  recharts is mocked; fixtures are complete objects of the real API types
  (`SmartDevice`, `CumulativeEnergyResponse`, `EnergyPriceConfig`).

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| `powerQuery` + `cumulativeQuery` + derived (`devices`, `powerSummary`, `loading`, `error`, `cumulativeData`, `cumulativeLoading`, `cumulativeReady`, `totalCurrentPower`, `powerPluginName`, `rangeArgs`) | 68–163 | `hooks/usePowerTabData.ts` |
| Energy-price state (4 `useState`) + mount fetch + `handleSavePrice` | 48–51, 114–158 | `hooks/useEnergyPrice.ts` |
| `pm` parsing (`watts`/`voltage`/`currentA`/`energyToday` with `current_ma`/`energy_today_wh` fallbacks) | 232–236 | `power-tab/parseDevicePower.ts` (pure) |
| Loading / error / empty-state (icon + `/smart-devices` link) | 165–202 | `power-tab/PowerStates.tsx` |
| Top StatCards (3×) | 207–228 | `power-tab/PowerSummaryCards.tsx` |
| Per-device card | 231–274 | `power-tab/PowerDeviceCard.tsx` |
| Inline price editor | 307–361 | `power-tab/EnergyPriceEditor.tsx` |
| Chart device tabs | 279–305 | `power-tab/ChartDeviceTabs.tsx` |
| Mode toggle + period selector + custom picker | 364–448 | `power-tab/ChartModePeriodControls.tsx` + `CustomRangePicker.tsx` |
| Summary stats (instant vs cumulative) | 451–515 | `power-tab/EnergyChartSummary.tsx` |
| Chart block (2 ComposedCharts) | 517–686 | `power-tab/EnergyChart.tsx` → `CumulativeEnergyChart.tsx` + `InstantPowerChart.tsx` |

## New units & interfaces

### `hooks/usePowerTabData.ts`

```ts
import type { SmartDevice } from '../api/smart-devices';
import type { CumulativeEnergyResponse } from '../api/energy';

export interface UsePowerTabDataInput {
  selectedDeviceId: number | null;
  cumulativePeriod: 'today' | 'week' | 'month' | 'custom';
  customStart: string | null;
  customEnd: string | null;
}
export interface UsePowerTabDataResult {
  devices: SmartDevice[];
  powerSummary: { total_watts?: number } | null;
  loading: boolean;
  error: string | null;
  cumulativeData: CumulativeEnergyResponse | null;
  cumulativeLoading: boolean;
  cumulativeReady: boolean;
  totalCurrentPower: number;
  powerPluginName: string | undefined;
}
export function usePowerTabData(input: UsePowerTabDataInput): UsePowerTabDataResult;
```

Body ports `powerQuery` (key `queryKeys.powerTab.summary()`, 5s poll, filters
`capabilities?.includes('power_monitor')`), the 404-swallow error logic, the
`resolveCumulativeArgs` + `cumulativeReady` gate, `cumulativeQuery` (key
`queryKeys.powerTab.cumulative(...)`, 60s poll, total-vs-device branch), and the
derived `totalCurrentPower` / `powerPluginName` (via `usePlugins()` internally).
The `rangeArgs` object is internal but its `period/start/end` must be
reachable by the orchestrator for the price-save invalidation — expose a
`cumulativeKeyArgs: { period, start: string | null, end: string | null }` field
too (used only to rebuild the invalidation key).

### `hooks/useEnergyPrice.ts`

```ts
import type { EnergyPriceConfig } from '../api/energy';

export interface UseEnergyPriceResult {
  priceConfig: EnergyPriceConfig | null;
  editingPrice: boolean;
  setEditingPrice: (v: boolean) => void;
  priceInput: string;
  setPriceInput: (v: string) => void;
  savingPrice: boolean;
  savePrice: () => Promise<void>;
}
export function useEnergyPrice(onSaved?: () => void | Promise<void>): UseEnergyPriceResult;
```

Ports the mount `useEffect` fetch (best-effort, sets `priceConfig` +
`priceInput`), and `handleSavePrice`: `parseFloat`, bounds `0.01–10.0`
(`toast.error(t('monitor.power.priceMustBeBetween'))` on invalid),
`updateEnergyPriceConfig({ cost_per_kwh, currency: priceConfig?.currency || 'EUR' })`,
success toast, then `await onSaved?.()`. `useTranslation(['system','common'])`
internally. The queryClient invalidation lives in the orchestrator's `onSaved`
callback (hook stays queryKey-decoupled).

### `power-tab/parseDevicePower.ts` (pure)

```ts
import type { SmartDevice } from '../../api/smart-devices';

export interface DevicePower {
  watts?: number; voltage?: number; currentA?: number; energyToday?: number;
}
export function parseDevicePower(device: SmartDevice): DevicePower;
```

Verbatim from 232–236: reads `device.state?.power_monitor`, `watts = pm.watts ??
pm.current_power`, `voltage = pm.voltage`, `currentA = pm.current ?? (pm.current_ma
!= null ? pm.current_ma / 1000 : undefined)`, `energyToday = pm.energy_today_kwh ??
(pm.energy_today_wh != null ? pm.energy_today_wh / 1000 : undefined)`.

### Presentational components (`power-tab/`)

- **`PowerStates.tsx`** — exposes three named renders: `PowerLoading()` (spinner),
  `PowerError({ error })` (error text), and `PowerEmptyState()` (icon +
  `t('monitor.power.noSmartDevices')` + `Link` to `/smart-devices`). The
  orchestrator early-returns each. Markup verbatim (165–202).
- **`PowerSummaryCards.tsx`** — `{ totalCurrentPower, onlineCount, deviceCount }`
  → the 3 `StatCard`s (207–228). i18n keys verbatim.
- **`PowerDeviceCard.tsx`** — `{ device }` → one card; calls `parseDevicePower`
  internally; markup verbatim (239–272). `useTranslation` internally.
- **`EnergyPriceEditor.tsx`** — `{ priceConfig, editing, priceInput, saving,
  onEdit, onInputChange, onSave, onCancel }` → the inline editor (316–361).
- **`ChartDeviceTabs.tsx`** — `{ devices, selectedDeviceId, onSelect }` → the
  Total + per-active-device tab buttons (279–305).
- **`ChartModePeriodControls.tsx`** — `{ chartMode, onModeChange, cumulativePeriod,
  onPeriodChange, customRangeSlot }` → mode toggle + period buttons (364–396),
  rendering `customRangeSlot` (the `CustomRangePicker`) in the custom slot.
- **`CustomRangePicker.tsx`** — `{ active, onApply }` where
  `onApply(startIso: string, endIso: string)` — owns `showRangePicker`,
  `draftStart`, `draftEnd` internally; the
  Apply button validates (`draftStart > draftEnd` → `toast.error`) and calls
  `localRangeToUtcIso(draftStart, draftEnd, Date.now())` then `onApply`. Markup
  verbatim (397–447). The `Date.now()` call stays here.
- **`EnergyChartSummary.tsx`** — `{ chartMode, cumulativeData }` → the instant
  (avg/max/min/dataPoints) vs cumulative (total kWh/cost/price/dataPoints)
  summary grids (451–515).
- **`EnergyChart.tsx`** — `{ chartMode, cumulativeData, cumulativeLoading,
  cumulativePeriod, language }` → loading spinner / empty (`t('monitor.noDataForPeriod')`)
  / picks `CumulativeEnergyChart` or `InstantPowerChart` (517–686).
- **`CumulativeEnergyChart.tsx`** / **`InstantPowerChart.tsx`** — `{ cumulativeData,
  cumulativePeriod, language }` → the two `ComposedChart`s verbatim (525–617 /
  619–679), including the data mapping (`formatTimeForRange`, `parseUtcTimestamp`),
  gradients, axes, tooltips, legends, all recharts props and i18n keys.

### `power-tab/index.ts`

Barrel exporting all the above components + `parseDevicePower`/`DevicePower`.

### `PowerTab.tsx` (after)

Keeps the selection state (`chartMode`, `cumulativePeriod`, `selectedDeviceId`,
`customStart`, `customEnd`). Calls `usePowerTabData({...})` and
`useEnergyPrice(onSaved)` where `onSaved` invalidates
`queryKeys.powerTab.cumulative(selectedDeviceId, keyArgs.period, keyArgs.start,
keyArgs.end)`. Early-returns via `PowerLoading`/`PowerError`/`PowerEmptyState`.
Composes `PowerSummaryCards`, `PowerDeviceCard` map, and the chart card
(`ChartDeviceTabs`, header with `EnergyPriceEditor` + `PluginBadge`,
`ChartModePeriodControls` wrapping `CustomRangePicker`, `EnergyChartSummary`,
`EnergyChart`). Target: **~150 lines** (from 690).

## Testing

Broad + integration (Vitest, T7-conform, recharts mocked):

- **`parseDevicePower`** — watts (`watts` vs `current_power`), voltage, current
  (`current` vs `current_ma/1000`), energyToday (`energy_today_kwh` vs
  `energy_today_wh/1000`), and all-undefined when `power_monitor` absent.
- **`usePowerTabData`** — `renderHook` (wrapped in QueryClient): 404 swallowed to
  `error: null`; `cumulativeReady` false for `custom` with no applied range;
  `totalCurrentPower` from `powerSummary.total_watts`. Mock `smartDevicesApi` +
  energy api + `usePlugins`.
- **`useEnergyPrice`** — mount fetch seeds config; `savePrice` rejects out-of-range
  (toast, no call), accepts in-range (calls `updateEnergyPriceConfig`, toast,
  `onSaved`). Mock energy api + `react-hot-toast`.
- **Component render tests** — `PowerSummaryCards`, `PowerDeviceCard` (values +
  `-` fallbacks), `EnergyPriceEditor` (view/edit/save/cancel), `ChartDeviceTabs`
  (select fires), `ChartModePeriodControls` (mode/period fire), `CustomRangePicker`
  (invalid range toast, apply fires with iso), `EnergyChartSummary` (both
  branches), `EnergyChart` (loading/empty/mode selection with recharts mocked),
  `PowerStates`.
- **Integration** (`__tests__/components/system-monitor/PowerTab.test.tsx`) — mock
  both hooks; assert StatCards + a device card + toolbar render for a populated
  fixture; empty `devices` → empty-state link.

## Verification gates

- `PowerTab.tsx` < 500 lines (target ~150).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green.
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved block, esp. the recharts config and the two query definitions).
