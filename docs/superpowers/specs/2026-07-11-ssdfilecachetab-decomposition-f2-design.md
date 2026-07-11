# SsdFileCacheTab.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-11
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/components/ssd-cache/SsdFileCacheTab.tsx` — currently **657 lines**.

## Goal

Behavior-preserving decomposition of `SsdFileCacheTab.tsx` (the admin per-array
SSD file-cache tab) into one data/state hook, one pure helper, and a directory
of presentational components under a new
`components/ssd-cache/file-cache/`.

**Non-goals:** no change to API calls, endpoints, the copy (this file uses
mostly hard-coded English strings — they stay verbatim; do NOT introduce i18n,
that is scope creep — the i18n gap is tracked separately in the collective
issue #406), Tailwind styling, toast messages, `useConfirmDialog`
wording, pagination size (20), or any computed value. The component keeps its
path (`components/ssd-cache/SsdFileCacheTab.tsx`, **default export**
`SsdFileCacheTab`, prop `initialArray?: string`) so consumers and the
`ssd-cache` barrel are untouched. The already-extracted `MigrationPanel` is
reused as-is.

## Constraints

- Every extracted value is **byte-identical** in behavior: same six cache API
  calls + `getRaidStatus`, same `Promise.all` in `loadData`, same array
  auto-select logic, same three effects (mount → `loadArrays`; `[selectedArray]`
  → `loadData` + `setPage(0)`; `[page, selectedArray]` → `loadEntries`), same
  toast strings, same `confirm(...)` clear-cache wording, same
  `getApiErrorMessage`/`handleApiError` usage, same error-swallow on
  `loadEntries`.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching. The extracted hook owns all fetching/state.
- Tests are T7-conform: assert on role/text/title, never Tailwind classes;
  fixtures are complete objects of the real API types (`SSDCacheStats`,
  `SSDCacheConfigResponse`, `CacheHealthResponse`, `SSDCacheEntryResponse`).
- Hard-coded English strings are preserved verbatim; the two `t(...)` calls
  (`ssdCache.migration.cacheTab`, `ssdCache.migration.title`) stay as `t()`.

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| 13 `useState` + `pageSize` const + `useConfirmDialog` + 3 effects + all handlers (`loadArrays`, `loadData`, `loadEntries`, `resetConfigForm`, `handleConfigChange`, `handleSaveConfig`, `handleEvictEntry`, `handleTriggerEviction`, `handleClearCache`) | 56–240 | `hooks/useSsdFileCache.ts` |
| Usage-bar color (`usage_percent >= 90 ? red : >= 70 ? amber : cyan`) | 363–365 | `file-cache/cacheUsageBarColor.ts` (pure) |
| View tabs (cache / migration) | 274–298 | `file-cache/CacheViewTabs.tsx` |
| Array selector | 304–324 | `file-cache/CacheArraySelector.tsx` |
| Stats grid (4 cards) | 332–399 | `file-cache/CacheStatsGrid.tsx` |
| Health card | 401–433 | `file-cache/CacheHealthCard.tsx` |
| Config card (form + save/reset) | 435–525 | `file-cache/CacheConfigCard.tsx` |
| Actions card | 527–559 | `file-cache/CacheActionsCard.tsx` |
| Entries table + pagination | 561–647 | `file-cache/CacheEntriesTable.tsx` |

## New units & interfaces

### `hooks/useSsdFileCache.ts`

```ts
import type {
  SSDCacheStats, SSDCacheConfigResponse, SSDCacheConfigUpdate,
  SSDCacheEntryResponse, CacheHealthResponse,
} from '../api/ssd-file-cache';
import type { ReactNode } from 'react';

export type TabView = 'cache' | 'migration';

export interface UseSsdFileCacheResult {
  tabView: TabView;
  setTabView: (v: TabView) => void;
  arrays: string[];
  selectedArray: string;
  setSelectedArray: (name: string) => void;
  stats: SSDCacheStats | null;
  config: SSDCacheConfigResponse | null;
  health: CacheHealthResponse | null;
  entries: SSDCacheEntryResponse[];
  entriesTotal: number;
  loading: boolean;
  error: string | null;
  actionLoading: boolean;
  configForm: SSDCacheConfigUpdate;
  configDirty: boolean;
  page: number;
  setPage: (updater: number | ((p: number) => number)) => void;
  pageSize: number;
  handleConfigChange: (key: keyof SSDCacheConfigUpdate, value: unknown) => void;
  handleSaveConfig: () => Promise<void>;
  resetConfigForm: (cfg: SSDCacheConfigResponse) => void;
  handleEvictEntry: (entryId: number) => Promise<void>;
  handleTriggerEviction: () => Promise<void>;
  handleClearCache: () => Promise<void>;
  loadData: () => Promise<void>;
  loadEntries: () => Promise<void>;
  dialog: ReactNode;
}

export function useSsdFileCache(initialArray?: string): UseSsdFileCacheResult;
```

Body ports lines 56–240 verbatim: the state, the `pageSize = 20` const, the
three effects (unchanged deps), and every handler (same `Promise.all`, same
toast strings, same `confirm` wording, same `getApiErrorMessage`/`handleApiError`
targets, same `loadEntries` empty-catch, same `resetConfigForm` cast
`cfg.eviction_policy as 'lfru' | 'lru' | 'lfu'`). `useConfirmDialog()` lives
inside; `dialog` is returned. `loadArrays` stays internal (only the mount effect
calls it). `page`'s setter must accept the functional-updater form used by the
pagination buttons (`setPage((p) => ...)`).

### `file-cache/cacheUsageBarColor.ts` (pure)

```ts
export function cacheUsageBarColor(usagePercent: number): string;
```

Verbatim thresholds from 363–365: `>= 90` → `'bg-red-500'`, `>= 70` →
`'bg-amber-500'`, else `'bg-cyan-500'`.

### Presentational components (`components/ssd-cache/file-cache/`)

- **`CacheViewTabs.tsx`** — `{ tabView: TabView; onSelect: (v: TabView) => void }`.
  The two view-tab buttons (274–298). `useTranslation()` internally (keeps the
  two `t('ssdCache.migration.*', 'fallback')` calls verbatim).
- **`CacheArraySelector.tsx`** — `{ arrays: string[]; selectedArray: string;
  onSelect: (name: string) => void }`. The selector row (304–324). The
  `arrays.length > 1` guard stays in the orchestrator.
- **`CacheStatsGrid.tsx`** — `{ stats: SSDCacheStats }`. The 4 cards verbatim
  (332–399), using `formatBytes` + `cacheUsageBarColor` for the usage bar.
- **`CacheHealthCard.tsx`** — `{ health: CacheHealthResponse }`. Health card
  (401–433). The `{health && ...}` guard stays in the orchestrator (render only
  when health present).
- **`CacheConfigCard.tsx`** — `{ configForm: SSDCacheConfigUpdate; config:
  SSDCacheConfigResponse; configDirty: boolean; actionLoading: boolean;
  onConfigChange: (key: keyof SSDCacheConfigUpdate, value: unknown) => void;
  onSave: () => void; onReset: (cfg: SSDCacheConfigResponse) => void }`. The
  form (435–525): enable checkbox, `ByteSizeInput`s, eviction-policy select,
  save button (`disabled={actionLoading || !configDirty}`), conditional reset
  button (`configDirty && config`).
- **`CacheActionsCard.tsx`** — `{ actionLoading: boolean; onTriggerEviction:
  () => void; onClearCache: () => void; onRefresh: () => void }`. The three
  action buttons (527–559).
- **`CacheEntriesTable.tsx`** — `{ entries: SSDCacheEntryResponse[];
  entriesTotal: number; page: number; totalPages: number; actionLoading:
  boolean; onEvict: (entryId: number) => void; onPrevPage: () => void;
  onNextPage: () => void }`. The table + pagination (561–647), including the
  empty-row (`colSpan={6}`) and the `totalPages > 1` pagination guard.

### `file-cache/index.ts`

Barrel exporting all components + `cacheUsageBarColor` + `TabView`.

### `SsdFileCacheTab.tsx` (after)

Calls `useSsdFileCache(initialArray)`. Computes `totalPages = Math.ceil(
entriesTotal / pageSize)`. Keeps the three early-returns verbatim (initial
spinner 242–248, no-arrays 250–256, error 258–268 with its `Retry` → `loadData`).
Renders `CacheViewTabs`, then the migration branch (`MigrationPanel`) vs the
cache view: `CacheArraySelector` (guarded `arrays.length > 1`), the inner
loading spinner, then `stats && config` → `CacheStatsGrid`, `{health && }`
`CacheHealthCard`, `CacheConfigCard`, `CacheActionsCard`, `CacheEntriesTable`
(passing `onRefresh={() => { loadData(); loadEntries(); }}`, `onPrevPage={() =>
setPage((p) => Math.max(0, p - 1))}`, `onNextPage={() => setPage((p) =>
Math.min(totalPages - 1, p + 1))}`), and `{dialog}`. Target: **~130 lines**
(from 657).

## Testing

Broad + integration (Vitest, T7-conform):

- **`cacheUsageBarColor`** — `95 → bg-red-500`, `75 → bg-amber-500`,
  `50 → bg-cyan-500`; boundaries `90 → red`, `70 → amber`.
- **`useSsdFileCache`** — `renderHook`: mount loads arrays and auto-selects the
  sole array; `handleClearCache` with `confirm` resolving `false` makes no
  `clearCache` call; `handleSaveConfig` calls `updateCacheConfig` with the
  current `configForm` then refreshes stats; `handleConfigChange` sets
  `configDirty`. Mock `../api/ssd-file-cache`, `../api/raid`,
  `../hooks/useConfirmDialog`, `react-hot-toast`.
- **Component renders** — `CacheViewTabs` (select fires), `CacheArraySelector`
  (one button per array, select fires), `CacheStatsGrid` (enabled/disabled
  status label, hit-rate value), `CacheHealthCard` (mounted vs not),
  `CacheConfigCard` (save disabled until dirty, reset shown only when dirty,
  onConfigChange fires on checkbox/select), `CacheActionsCard` (each callback
  fires), `CacheEntriesTable` (empty-state row when no entries; evict fires with
  id; prev disabled on page 0, next disabled on last page).
- **Integration** (`__tests__/components/ssd-cache/SsdFileCacheTab.test.tsx`) —
  mock the hook; assert the migration branch renders `MigrationPanel` when
  `tabView === 'migration'`; the cache view renders stats grid + config + table
  for a populated fixture; the no-arrays early-return.

## Verification gates

- `SsdFileCacheTab.tsx` < 500 lines (target ~130).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green (`import type` for type-only imports —
  `verbatimModuleSyntax` enforced by `tsc -b`, not vitest).
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved block, especially the three effects, the array auto-select, and
  the config save/refresh sequence).
