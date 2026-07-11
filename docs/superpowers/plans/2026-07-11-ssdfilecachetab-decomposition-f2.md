# SsdFileCacheTab.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behavior-preserving decomposition of `client/src/components/ssd-cache/SsdFileCacheTab.tsx` (657 lines) into one data/state hook, one pure helper, and a `components/ssd-cache/file-cache/` directory of presentational components, leaving the tab a thin ~130-line orchestrator.

**Architecture:** All fetching/state moves into `hooks/useSsdFileCache.ts`. Presentational components take props + callbacks only. Moved markup is byte-identical (same JSX, same Tailwind, same hard-coded English copy, same toast strings). The component keeps its default export + path + `initialArray` prop so consumers and the `ssd-cache` barrel are untouched. `MigrationPanel` is reused unmodified.

**Tech Stack:** React 18 + TypeScript (strict, `verbatimModuleSyntax`) + Vite + Tailwind + react-i18next (only 2 existing `t()` calls) + react-hot-toast + lucide-react + Vitest + @testing-library/react.

## Global Constraints

- **`verbatimModuleSyntax`:** every type-only import MUST use `import type { ... }`. `tsc -b` (CI `npm run build`) enforces this; vitest/esbuild does NOT. Run `npx tsc -b` before each commit.
- **Behavior byte-identical:** same API calls (`getRaidStatus`, `getCacheStats`, `getCacheConfig`, `getCacheHealth`, `getCacheEntries`, `updateCacheConfig`, `evictEntry`, `triggerEviction`, `clearCache`), same `Promise.all` in `loadData`, same array auto-select logic, same 3 effects, same toast strings, same `confirm(...)` clear-cache wording, same `getApiErrorMessage`/`handleApiError` targets, same `loadEntries` empty-catch, same `pageSize = 20`.
- **DO NOT introduce i18n / change copy.** This file renders mostly hard-coded English strings ON PURPOSE for this refactor — preserve them verbatim. The i18n gap is tracked separately in issue #406. Only the two existing `t('ssdCache.migration.cacheTab', 'File Cache')` / `t('ssdCache.migration.title', 'Data Migration')` calls stay as `t()`.
- **Test hygiene (T7):** assert on role/text/title, never Tailwind class names. Fixtures are complete objects of the real API types (`SSDCacheStats`, `SSDCacheConfigResponse`, `CacheHealthResponse`, `SSDCacheEntryResponse`, `SSDCacheConfigUpdate`) from `../api/ssd-file-cache`. Each test asserts the SPECIFIC targeted behavior of its unit.
- Source of truth for every moved block: the current `client/src/components/ssd-cache/SsdFileCacheTab.tsx` at branch base. Line numbers below refer to that file.
- New component dir: `client/src/components/ssd-cache/file-cache/`. New tests: `client/src/__tests__/components/ssd-cache/file-cache/` and `client/src/__tests__/hooks/`.

---

### Task 1: `cacheUsageBarColor` pure helper

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/cacheUsageBarColor.ts`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/cacheUsageBarColor.test.ts`

**Interfaces:**
- Produces: `export function cacheUsageBarColor(usagePercent: number): string`

- [ ] **Step 1: Write the failing test**

```ts
// cacheUsageBarColor.test.ts
import { describe, it, expect } from 'vitest';
import { cacheUsageBarColor } from '../../../../components/ssd-cache/file-cache/cacheUsageBarColor';

describe('cacheUsageBarColor', () => {
  it('returns red at/above 90%', () => {
    expect(cacheUsageBarColor(95)).toBe('bg-red-500');
    expect(cacheUsageBarColor(90)).toBe('bg-red-500');
  });
  it('returns amber at/above 70% and below 90%', () => {
    expect(cacheUsageBarColor(75)).toBe('bg-amber-500');
    expect(cacheUsageBarColor(70)).toBe('bg-amber-500');
  });
  it('returns cyan below 70%', () => {
    expect(cacheUsageBarColor(50)).toBe('bg-cyan-500');
    expect(cacheUsageBarColor(0)).toBe('bg-cyan-500');
  });
});
```

- [ ] **Step 2: Run to verify fail.** `cd client ; npx vitest run src/__tests__/components/ssd-cache/file-cache/cacheUsageBarColor.test.ts` → FAIL (module not found).
- [ ] **Step 3: Write the implementation** (thresholds verbatim from `SsdFileCacheTab.tsx:363-365`):

```ts
// cacheUsageBarColor.ts
export function cacheUsageBarColor(usagePercent: number): string {
  return usagePercent >= 90 ? 'bg-red-500' : usagePercent >= 70 ? 'bg-amber-500' : 'bg-cyan-500';
}
```

- [ ] **Step 4: Run to verify pass** → PASS (3 tests).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract cacheUsageBarColor helper (F2, #301)`.

---

### Task 2: `useSsdFileCache` hook

**Files:**
- Create: `client/src/hooks/useSsdFileCache.ts`
- Test: `client/src/__tests__/hooks/useSsdFileCache.test.ts`

**Interfaces:**
- Consumes: `getRaidStatus` from `../api/raid`; the eight cache functions + types from `../api/ssd-file-cache`; `useConfirmDialog` from `./useConfirmDialog`; `toast` from `react-hot-toast`; `getApiErrorMessage`/`handleApiError` from `../lib/errorHandling`; `formatBytes` from `../lib/formatters`.
- Produces: `useSsdFileCache(initialArray?: string): UseSsdFileCacheResult` (full shape below). Consumed by Task 9.

```ts
import type {
  SSDCacheStats, SSDCacheConfigResponse, SSDCacheConfigUpdate,
  SSDCacheEntryResponse, CacheHealthResponse,
} from '../api/ssd-file-cache';
import type { Dispatch, SetStateAction, ReactNode } from 'react';

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
  setPage: Dispatch<SetStateAction<number>>;
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

**Porting notes (byte-identical):** move lines 56–240 verbatim — the 13 `useState`, the `pageSize = 20` const, `useConfirmDialog()`, the three effects (deps unchanged: `[]`, `[selectedArray]`, `[page, selectedArray]`), and every handler (`loadArrays`, `loadData`, `loadEntries`, `resetConfigForm`, `handleConfigChange`, `handleSaveConfig`, `handleEvictEntry`, `handleTriggerEviction`, `handleClearCache`). Keep `loadArrays` internal (not exported). Preserve the `cfg.eviction_policy as 'lfru' | 'lru' | 'lfu'` cast, the `Promise.all`, all toast strings, the clear-cache `confirm(...)` wording, and the `loadEntries` empty catch. Return the full object above.

> ESLint note: the original disables no rules for the effect deps; keep the same `// eslint-disable-next-line` comments IF the original had them — it does NOT (the effects intentionally omit function deps). If eslint flags `react-hooks/exhaustive-deps` on the moved effects, add `// eslint-disable-next-line react-hooks/exhaustive-deps` to match the original's behavior WITHOUT changing deps. Verify against `npx eslint` in Step 4.

- [ ] **Step 1: Write the failing test**

```ts
// useSsdFileCache.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { SSDCacheStats, SSDCacheConfigResponse, CacheHealthResponse } from '../../api/ssd-file-cache';

vi.mock('../../api/raid', () => ({
  getRaidStatus: vi.fn().mockResolvedValue({ arrays: [{ name: 'md0' }] }),
}));
const mockConfirm = vi.fn();
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm, dialog: null }),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../lib/errorHandling', () => ({
  getApiErrorMessage: (_e: unknown, fb: string) => fb,
  handleApiError: vi.fn(),
}));

const stats: SSDCacheStats = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1000,
  current_size_bytes: 500, usage_percent: 50, total_entries: 3, valid_entries: 3,
  total_hits: 10, total_misses: 2, hit_rate_percent: 83.3, total_bytes_served: 999,
  ssd_available_bytes: 800, ssd_total_bytes: 1000,
};
const config: SSDCacheConfigResponse = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1000,
  current_size_bytes: 500, eviction_policy: 'lfru', min_file_size_bytes: 1,
  max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 10,
  total_misses: 2, total_bytes_served_from_cache: 999, updated_at: null,
};
const health: CacheHealthResponse = {
  array_name: 'md0', is_mounted: true, ssd_total_bytes: 1000,
  ssd_available_bytes: 800, ssd_used_percent: 20, cache_dir_exists: true,
};

vi.mock('../../api/ssd-file-cache', () => ({
  getCacheStats: vi.fn().mockResolvedValue(stats),
  getCacheConfig: vi.fn().mockResolvedValue(config),
  getCacheHealth: vi.fn().mockResolvedValue(health),
  getCacheEntries: vi.fn().mockResolvedValue({ entries: [], total: 0 }),
  updateCacheConfig: vi.fn().mockResolvedValue(config),
  evictEntry: vi.fn().mockResolvedValue({ freed_bytes: 10, source_path: '/x' }),
  triggerEviction: vi.fn().mockResolvedValue({ freed_bytes: 10, deleted_count: 1 }),
  clearCache: vi.fn().mockResolvedValue({ freed_bytes: 10, deleted_count: 1 }),
}));

import { useSsdFileCache } from '../../hooks/useSsdFileCache';
import * as api from '../../api/ssd-file-cache';

describe('useSsdFileCache', () => {
  beforeEach(() => vi.clearAllMocks());

  it('auto-selects the sole array on mount and loads its data', async () => {
    const { result } = renderHook(() => useSsdFileCache());
    await waitFor(() => expect(result.current.selectedArray).toBe('md0'));
    await waitFor(() => expect(result.current.stats).not.toBeNull());
    expect(result.current.config).not.toBeNull();
  });

  it('does not call clearCache when the confirm dialog is declined', async () => {
    mockConfirm.mockResolvedValueOnce(false);
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.selectedArray).toBe('md0'));
    await act(async () => { await result.current.handleClearCache(); });
    expect(api.clearCache).not.toHaveBeenCalled();
  });

  it('handleConfigChange marks the form dirty and updates the field', async () => {
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => result.current.handleConfigChange('is_enabled', false));
    expect(result.current.configDirty).toBe(true);
    expect(result.current.configForm.is_enabled).toBe(false);
  });

  it('handleSaveConfig sends the current form to updateCacheConfig', async () => {
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => result.current.handleConfigChange('max_size_bytes', 2048));
    await act(async () => { await result.current.handleSaveConfig(); });
    expect(api.updateCacheConfig).toHaveBeenCalledWith(
      'md0', expect.objectContaining({ max_size_bytes: 2048 }),
    );
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL (module not found).
- [ ] **Step 3: Write the hook** per the porting notes (move 56–240 verbatim; return the full object).
- [ ] **Step 4: Run test + gates**

Run: `cd client ; npx vitest run src/__tests__/hooks/useSsdFileCache.test.ts` → PASS (4 tests).
Run: `cd client ; npx tsc -b` → no errors.
Run: `cd client ; npx eslint src/hooks/useSsdFileCache.ts` → 0 errors.

- [ ] **Step 5: Commit** `feat(ssd-cache): add useSsdFileCache hook (state + actions) (F2, #301)`.

---

### Task 3: `CacheViewTabs` + `CacheArraySelector`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheViewTabs.tsx`
- Create: `client/src/components/ssd-cache/file-cache/CacheArraySelector.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheViewTabs.test.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheArraySelector.test.tsx`

**Interfaces:**
- Produces:
```ts
import type { TabView } from '../../../hooks/useSsdFileCache';
export function CacheViewTabs(props: { tabView: TabView; onSelect: (v: TabView) => void }): JSX.Element;
export function CacheArraySelector(props: { arrays: string[]; selectedArray: string; onSelect: (name: string) => void }): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** `CacheViewTabs` = the two view-tab buttons verbatim from `SsdFileCacheTab.tsx:274-298` (keep the two `t('ssdCache.migration.*', 'fallback')` calls; `useTranslation()` internally; `Zap`/`ArrowRightLeft` icons). `CacheArraySelector` = the selector row verbatim from `304-324` (the `arrays.length > 1` guard stays in the orchestrator — this component just renders the row).

- [ ] **Step 1: Write the failing tests**

```tsx
// CacheViewTabs.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb: string) => fb }) }));
import { CacheViewTabs } from '../../../../components/ssd-cache/file-cache/CacheViewTabs';

describe('CacheViewTabs', () => {
  it('renders both view tabs', () => {
    render(<CacheViewTabs tabView="cache" onSelect={() => {}} />);
    expect(screen.getByText('File Cache')).toBeInTheDocument();
    expect(screen.getByText('Data Migration')).toBeInTheDocument();
  });
  it('fires onSelect with the clicked view', () => {
    const onSelect = vi.fn();
    render(<CacheViewTabs tabView="cache" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Data Migration'));
    expect(onSelect).toHaveBeenCalledWith('migration');
  });
});
```

```tsx
// CacheArraySelector.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CacheArraySelector } from '../../../../components/ssd-cache/file-cache/CacheArraySelector';

describe('CacheArraySelector', () => {
  it('renders one button per array', () => {
    render(<CacheArraySelector arrays={['md0', 'md1']} selectedArray="md0" onSelect={() => {}} />);
    expect(screen.getByText('md0')).toBeInTheDocument();
    expect(screen.getByText('md1')).toBeInTheDocument();
  });
  it('fires onSelect with the clicked array name', () => {
    const onSelect = vi.fn();
    render(<CacheArraySelector arrays={['md0', 'md1']} selectedArray="md0" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('md1'));
    expect(onSelect).toHaveBeenCalledWith('md1');
  });
});
```

- [ ] **Step 2: Run both → FAIL.**
- [ ] **Step 3: Write both components** per porting notes.
- [ ] **Step 4: Run both tests + `npx tsc -b`** → PASS (4 tests total).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheViewTabs + CacheArraySelector (F2, #301)`.

---

### Task 4: `CacheStatsGrid`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheStatsGrid.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheStatsGrid.test.tsx`

**Interfaces:**
- Consumes: `cacheUsageBarColor` (Task 1), `formatBytes` from `../../../lib/formatters`, `SSDCacheStats`.
- Produces: `export function CacheStatsGrid(props: { stats: SSDCacheStats }): JSX.Element;`
- Consumed by Task 9.

**Porting notes:** Move the 4 stat cards verbatim from `SsdFileCacheTab.tsx:332-399` (Status / Cache Usage / Hit Rate / Bytes Served). The usage-bar inline color ternary at 363-365 becomes `cacheUsageBarColor(stats.usage_percent)`. Keep `formatBytes`, all icons, the `Math.min(stats.usage_percent, 100)` width.

- [ ] **Step 1: Write the failing test**

```tsx
// CacheStatsGrid.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SSDCacheStats } from '../../../../api/ssd-file-cache';
import { CacheStatsGrid } from '../../../../components/ssd-cache/file-cache/CacheStatsGrid';

const stats = (over: Partial<SSDCacheStats> = {}): SSDCacheStats => ({
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, usage_percent: 50, total_entries: 3, valid_entries: 2,
  total_hits: 10, total_misses: 5, hit_rate_percent: 66.7, total_bytes_served: 2048,
  ssd_available_bytes: 900, ssd_total_bytes: 1024, ...over,
});

describe('CacheStatsGrid', () => {
  it('shows Enabled status when enabled', () => {
    render(<CacheStatsGrid stats={stats({ is_enabled: true })} />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });
  it('shows Disabled status when disabled', () => {
    render(<CacheStatsGrid stats={stats({ is_enabled: false })} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });
  it('renders the hit-rate percentage', () => {
    render(<CacheStatsGrid stats={stats({ hit_rate_percent: 66.7 })} />);
    expect(screen.getByText('66.7%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (3 tests).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheStatsGrid (F2, #301)`.

---

### Task 5: `CacheHealthCard`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheHealthCard.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheHealthCard.test.tsx`

**Interfaces:**
- Consumes: `formatBytes`, `CacheHealthResponse`.
- Produces: `export function CacheHealthCard(props: { health: CacheHealthResponse }): JSX.Element;`
- Consumed by Task 9.

**Porting notes:** Move the health card verbatim from `SsdFileCacheTab.tsx:401-433` (the outer `{health && ...}` guard stays in the orchestrator — this component always renders given a `health` prop). Keep `Check`/`X`/`Heart` icons, `formatBytes`, the `ssd_used_percent.toFixed(1)`.

- [ ] **Step 1: Write the failing test**

```tsx
// CacheHealthCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CacheHealthResponse } from '../../../../api/ssd-file-cache';
import { CacheHealthCard } from '../../../../components/ssd-cache/file-cache/CacheHealthCard';

const health = (over: Partial<CacheHealthResponse> = {}): CacheHealthResponse => ({
  array_name: 'md0', is_mounted: true, ssd_total_bytes: 1024, ssd_available_bytes: 900,
  ssd_used_percent: 12.5, cache_dir_exists: true, ...over,
});

describe('CacheHealthCard', () => {
  it('shows Mounted when the ssd is mounted', () => {
    render(<CacheHealthCard health={health({ is_mounted: true })} />);
    expect(screen.getByText('Mounted')).toBeInTheDocument();
  });
  it('shows Not Mounted and Missing when unmounted with no cache dir', () => {
    render(<CacheHealthCard health={health({ is_mounted: false, cache_dir_exists: false })} />);
    expect(screen.getByText('Not Mounted')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheHealthCard (F2, #301)`.

---

### Task 6: `CacheConfigCard`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheConfigCard.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheConfigCard.test.tsx`

**Interfaces:**
- Consumes: `ByteSizeInput` from `../ui/ByteSizeInput`, `SSDCacheConfigUpdate`, `SSDCacheConfigResponse`.
- Produces:
```ts
import type { SSDCacheConfigUpdate, SSDCacheConfigResponse } from '../../../api/ssd-file-cache';
export function CacheConfigCard(props: {
  configForm: SSDCacheConfigUpdate;
  config: SSDCacheConfigResponse;
  configDirty: boolean;
  actionLoading: boolean;
  onConfigChange: (key: keyof SSDCacheConfigUpdate, value: unknown) => void;
  onSave: () => void;
  onReset: (cfg: SSDCacheConfigResponse) => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the config card verbatim from `SsdFileCacheTab.tsx:435-525`: enable checkbox (`onChange` → `onConfigChange('is_enabled', e.target.checked)`), the four `ByteSizeInput`s (`onChange` → `onConfigChange('<field>', bytes)`), the eviction-policy `<select>` (`onChange` → `onConfigChange('eviction_policy', e.target.value)`), the save button (`disabled={actionLoading || !configDirty}`, `onClick={onSave}`), and the conditional reset button (`{configDirty && config && (...)}`, `onClick={() => onReset(config)}`). Copy verbatim, incl. the three `<option>` texts.

- [ ] **Step 1: Write the failing test**

```tsx
// CacheConfigCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { SSDCacheConfigUpdate, SSDCacheConfigResponse } from '../../../../api/ssd-file-cache';
import { CacheConfigCard } from '../../../../components/ssd-cache/file-cache/CacheConfigCard';

const config: SSDCacheConfigResponse = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, eviction_policy: 'lfru', min_file_size_bytes: 1,
  max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 0,
  total_misses: 0, total_bytes_served_from_cache: 0, updated_at: null,
};
const form: SSDCacheConfigUpdate = {
  is_enabled: true, max_size_bytes: 1024, eviction_policy: 'lfru',
  min_file_size_bytes: 1, max_file_size_bytes: 100, sequential_cutoff_bytes: 50,
};
const base = {
  configForm: form, config, actionLoading: false,
  onConfigChange: () => {}, onSave: () => {}, onReset: () => {},
};

describe('CacheConfigCard', () => {
  it('disables Save when not dirty and enables it when dirty', () => {
    const { rerender } = render(<CacheConfigCard {...base} configDirty={false} />);
    expect(screen.getByText('Save Configuration').closest('button')).toBeDisabled();
    rerender(<CacheConfigCard {...base} configDirty={true} />);
    expect(screen.getByText('Save Configuration').closest('button')).not.toBeDisabled();
  });
  it('shows the Reset button only when dirty', () => {
    const { rerender } = render(<CacheConfigCard {...base} configDirty={false} />);
    expect(screen.queryByText('Reset')).not.toBeInTheDocument();
    rerender(<CacheConfigCard {...base} configDirty={true} />);
    expect(screen.getByText('Reset')).toBeInTheDocument();
  });
  it('fires onConfigChange when the enabled checkbox toggles', () => {
    const onConfigChange = vi.fn();
    render(<CacheConfigCard {...base} configDirty={false} onConfigChange={onConfigChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onConfigChange).toHaveBeenCalledWith('is_enabled', false);
  });
  it('fires onSave when Save is clicked (dirty)', () => {
    const onSave = vi.fn();
    render(<CacheConfigCard {...base} configDirty={true} onSave={onSave} />);
    fireEvent.click(screen.getByText('Save Configuration'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (4 tests).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheConfigCard (F2, #301)`.

---

### Task 7: `CacheActionsCard`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheActionsCard.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheActionsCard.test.tsx`

**Interfaces:**
- Produces:
```ts
export function CacheActionsCard(props: {
  actionLoading: boolean;
  onTriggerEviction: () => void;
  onClearCache: () => void;
  onRefresh: () => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the actions card verbatim from `SsdFileCacheTab.tsx:527-559`: Trigger Eviction (`onClick={onTriggerEviction}`), Clear Cache (`onClick={onClearCache}`), Refresh (`onClick={onRefresh}`), each `disabled={actionLoading}`, keep the `RefreshCw` spin class `${actionLoading ? 'animate-spin' : ''}` and `Trash2` icon.

- [ ] **Step 1: Write the failing test**

```tsx
// CacheActionsCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CacheActionsCard } from '../../../../components/ssd-cache/file-cache/CacheActionsCard';

describe('CacheActionsCard', () => {
  it('fires each action callback on its button', () => {
    const onTriggerEviction = vi.fn(), onClearCache = vi.fn(), onRefresh = vi.fn();
    render(<CacheActionsCard actionLoading={false}
      onTriggerEviction={onTriggerEviction} onClearCache={onClearCache} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByText('Trigger Eviction'));
    fireEvent.click(screen.getByText('Clear Cache'));
    fireEvent.click(screen.getByText('Refresh'));
    expect(onTriggerEviction).toHaveBeenCalledTimes(1);
    expect(onClearCache).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
  it('disables all buttons while an action is loading', () => {
    render(<CacheActionsCard actionLoading={true}
      onTriggerEviction={() => {}} onClearCache={() => {}} onRefresh={() => {}} />);
    for (const label of ['Trigger Eviction', 'Clear Cache', 'Refresh']) {
      expect(screen.getByText(label).closest('button')).toBeDisabled();
    }
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheActionsCard (F2, #301)`.

---

### Task 8: `CacheEntriesTable`

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/CacheEntriesTable.tsx`
- Test: `client/src/__tests__/components/ssd-cache/file-cache/CacheEntriesTable.test.tsx`

**Interfaces:**
- Consumes: `formatBytes`, `SSDCacheEntryResponse`.
- Produces:
```ts
import type { SSDCacheEntryResponse } from '../../../api/ssd-file-cache';
export function CacheEntriesTable(props: {
  entries: SSDCacheEntryResponse[];
  entriesTotal: number;
  page: number;
  totalPages: number;
  actionLoading: boolean;
  onEvict: (entryId: number) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the entries table + pagination verbatim from `SsdFileCacheTab.tsx:561-647`: the header (`Cached Entries` + `({entriesTotal})`), the table with the 6 columns, the row map (evict button `onClick={() => onEvict(entry.id)}`, `disabled={actionLoading}`), the empty-row (`colSpan={6}` "No cached entries"), and the pagination block guarded `{totalPages > 1 && (...)}` (prev `onClick={onPrevPage}` `disabled={page === 0}`, next `onClick={onNextPage}` `disabled={page >= totalPages - 1}`, "Page {page + 1} of {totalPages}"). Keep `formatBytes`, `new Date(entry.last_accessed).toLocaleString()`, all icons.

- [ ] **Step 1: Write the failing test**

```tsx
// CacheEntriesTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { SSDCacheEntryResponse } from '../../../../api/ssd-file-cache';
import { CacheEntriesTable } from '../../../../components/ssd-cache/file-cache/CacheEntriesTable';

const entry = (over: Partial<SSDCacheEntryResponse> = {}): SSDCacheEntryResponse => ({
  id: 1, array_name: 'md0', source_path: '/data/file.bin', file_size_bytes: 2048,
  access_count: 7, last_accessed: '2026-07-01T10:00:00Z', first_cached: '2026-06-01T10:00:00Z',
  is_valid: true, ...over,
});
const base = { entriesTotal: 1, page: 0, totalPages: 1, actionLoading: false,
  onEvict: () => {}, onPrevPage: () => {}, onNextPage: () => {} };

describe('CacheEntriesTable', () => {
  it('renders the empty-state row when there are no entries', () => {
    render(<CacheEntriesTable {...base} entries={[]} entriesTotal={0} />);
    expect(screen.getByText('No cached entries')).toBeInTheDocument();
  });
  it('renders a row per entry and fires onEvict with the entry id', () => {
    const onEvict = vi.fn();
    render(<CacheEntriesTable {...base} entries={[entry({ id: 42 })]} onEvict={onEvict} />);
    expect(screen.getByText('/data/file.bin')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Evict'));
    expect(onEvict).toHaveBeenCalledWith(42);
  });
  it('hides pagination when there is only one page', () => {
    render(<CacheEntriesTable {...base} entries={[entry()]} totalPages={1} />);
    expect(screen.queryByText(/Page 1 of/)).not.toBeInTheDocument();
  });
  it('disables prev on the first page and next on the last page, firing callbacks otherwise', () => {
    const onPrevPage = vi.fn(), onNextPage = vi.fn();
    // the Evict button has text; the two pagination controls are icon-only (empty textContent)
    const iconButtons = () => screen.getAllByRole('button').filter((b) => !b.textContent?.trim());
    const { rerender } = render(
      <CacheEntriesTable {...base} entries={[entry()]} page={0} totalPages={3}
        onPrevPage={onPrevPage} onNextPage={onNextPage} />,
    );
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    const [prev0, next0] = iconButtons(); // DOM order: ChevronLeft (prev), ChevronRight (next)
    expect(prev0).toBeDisabled();          // first page → prev disabled
    expect(next0).not.toBeDisabled();
    fireEvent.click(next0);
    expect(onNextPage).toHaveBeenCalledTimes(1);
    rerender(
      <CacheEntriesTable {...base} entries={[entry()]} page={2} totalPages={3}
        onPrevPage={onPrevPage} onNextPage={onNextPage} />,
    );
    expect(screen.getByText(/Page 3 of 3/)).toBeInTheDocument();
    const [prev2, next2] = iconButtons();
    expect(next2).toBeDisabled();           // last page → next disabled
    expect(prev2).not.toBeDisabled();
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS.
- [ ] **Step 5: Commit** `feat(ssd-cache): extract CacheEntriesTable (F2, #301)`.

---

### Task 9: Barrel + `SsdFileCacheTab.tsx` orchestrator + integration test

**Files:**
- Create: `client/src/components/ssd-cache/file-cache/index.ts`
- Modify: `client/src/components/ssd-cache/SsdFileCacheTab.tsx` (full rewrite to orchestrator)
- Test: `client/src/__tests__/components/ssd-cache/SsdFileCacheTab.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1–8 via the barrel, `useSsdFileCache` (Task 2), `MigrationPanel` (unchanged).

**Barrel** `index.ts` re-exports: `cacheUsageBarColor`, `type TabView` (re-export from the hook OR define canonical here — keep the hook as the canonical source and `export type { TabView } from '../../../hooks/useSsdFileCache'`), `CacheViewTabs`, `CacheArraySelector`, `CacheStatsGrid`, `CacheHealthCard`, `CacheConfigCard`, `CacheActionsCard`, `CacheEntriesTable`.

**Orchestrator rewrite:** keep the file header comment + default export `SsdFileCacheTab({ initialArray })`. Call `useSsdFileCache(initialArray)`. Compute `const totalPages = Math.ceil(entriesTotal / pageSize)`. Structure:
1. Early returns verbatim: initial spinner (`loading && !selectedArray`, 242–248), no-arrays (`arrays.length === 0 && !loading`, 250–256), error (`error && !stats`, 258–268 — the `Retry` button keeps `onClick={loadData}`).
2. `<div className="space-y-6">` → `<CacheViewTabs tabView={tabView} onSelect={setTabView} />`.
3. `{tabView === 'migration' ? <MigrationPanel /> : (<> ... </>)}`.
4. Inside the cache fragment: `{arrays.length > 1 && <CacheArraySelector arrays={arrays} selectedArray={selectedArray} onSelect={setSelectedArray} />}`, then `{loading ? <spinner/> : stats && config ? (<> <CacheStatsGrid stats={stats}/> {health && <CacheHealthCard health={health}/>} <CacheConfigCard .../> <CacheActionsCard .../> <CacheEntriesTable .../> </>) : null}`.
5. `{dialog}`: preserve the EXACT original nesting (lines 651-653) — `{dialog}` lives INSIDE the migration-ternary's else-branch fragment (`tabView === 'migration' ? <MigrationPanel/> : (<> ...cache view... {dialog} </>)`), i.e. it renders only in the cache view, after the loading/stats block, NOT at the top `space-y-6` level. Do not move it outside the ternary.

Wire the callbacks:
- `CacheConfigCard`: `configForm`, `config={config}`, `configDirty`, `actionLoading`, `onConfigChange={handleConfigChange}`, `onSave={handleSaveConfig}`, `onReset={resetConfigForm}`.
- `CacheActionsCard`: `actionLoading`, `onTriggerEviction={handleTriggerEviction}`, `onClearCache={handleClearCache}`, `onRefresh={() => { loadData(); loadEntries(); }}`.
- `CacheEntriesTable`: `entries`, `entriesTotal`, `page`, `totalPages`, `actionLoading`, `onEvict={handleEvictEntry}`, `onPrevPage={() => setPage((p) => Math.max(0, p - 1))}`, `onNextPage={() => setPage((p) => Math.min(totalPages - 1, p + 1))}`.

Delete all now-unused imports (the API functions, `getRaidStatus`, `useState`/`useEffect`, `useConfirmDialog`, `toast`, `getApiErrorMessage`/`handleApiError`, `ByteSizeInput`, `formatBytes`, and the lucide icons only used by moved markup — keep only icons still used by the early-returns, e.g. `AlertCircle`). Keep `useTranslation`? The orchestrator no longer calls `t()` directly (tabs moved out) — remove it if unused. Keep `MigrationPanel`, `useSsdFileCache`, the barrel imports. Run eslint to catch leftovers.

- [ ] **Step 1: Write the failing integration test**

```tsx
// client/src/__tests__/components/ssd-cache/SsdFileCacheTab.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SSDCacheStats, SSDCacheConfigResponse } from '../../../api/ssd-file-cache';
import type { UseSsdFileCacheResult } from '../../../hooks/useSsdFileCache';

const stats: SSDCacheStats = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, usage_percent: 50, total_entries: 1, valid_entries: 1,
  total_hits: 5, total_misses: 1, hit_rate_percent: 83.3, total_bytes_served: 100,
  ssd_available_bytes: 900, ssd_total_bytes: 1024,
};
const config: SSDCacheConfigResponse = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, eviction_policy: 'lfru', min_file_size_bytes: 1,
  max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 5,
  total_misses: 1, total_bytes_served_from_cache: 100, updated_at: null,
};

const hookValue: UseSsdFileCacheResult = {
  tabView: 'cache', setTabView: vi.fn(), arrays: ['md0'], selectedArray: 'md0',
  setSelectedArray: vi.fn(), stats, config, health: null, entries: [], entriesTotal: 0,
  loading: false, error: null, actionLoading: false, configForm: {}, configDirty: false,
  page: 0, setPage: vi.fn(), pageSize: 20, handleConfigChange: vi.fn(),
  handleSaveConfig: vi.fn(), resetConfigForm: vi.fn(), handleEvictEntry: vi.fn(),
  handleTriggerEviction: vi.fn(), handleClearCache: vi.fn(), loadData: vi.fn(),
  loadEntries: vi.fn(), dialog: null,
};
vi.mock('../../../hooks/useSsdFileCache', () => ({ useSsdFileCache: () => hookValue }));
vi.mock('../../../components/ssd-cache/MigrationPanel', () => ({ default: () => <div data-testid="migration" /> }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb: string) => fb }) }));

import SsdFileCacheTab from '../../../components/ssd-cache/SsdFileCacheTab';

describe('SsdFileCacheTab', () => {
  beforeEach(() => {
    Object.assign(hookValue, { tabView: 'cache', arrays: ['md0'], stats, config, loading: false });
  });

  it('renders the cache view (stats + config + actions) for a populated fixture', () => {
    render(<SsdFileCacheTab />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();      // stats grid
    expect(screen.getByText('Configuration')).toBeInTheDocument(); // config card
    expect(screen.getByText('Actions')).toBeInTheDocument();       // actions card
    expect(screen.queryByTestId('migration')).not.toBeInTheDocument();
  });

  it('renders MigrationPanel when tabView is migration', () => {
    hookValue.tabView = 'migration';
    render(<SsdFileCacheTab />);
    expect(screen.getByTestId('migration')).toBeInTheDocument();
    expect(screen.queryByText('Configuration')).not.toBeInTheDocument();
  });

  it('shows the no-arrays message when there are no arrays', () => {
    Object.assign(hookValue, { arrays: [], loading: false, stats: null });
    render(<SsdFileCacheTab />);
    expect(screen.getByText(/No RAID arrays found/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL (old shape / barrel not built).
- [ ] **Step 3: Write the barrel, then rewrite `SsdFileCacheTab.tsx`** per the structure above.
- [ ] **Step 4: Full verification**

Run: `cd client ; npx vitest run src/__tests__/components/ssd-cache/SsdFileCacheTab.test.tsx` → PASS (3 tests).
Run: `cd client ; node -e "console.log(require('fs').readFileSync('src/components/ssd-cache/SsdFileCacheTab.tsx','utf8').split(/\r?\n/).length)"` → under 500 (target ~130).
Run: `cd client ; npx tsc -b` → no errors.
Run: `cd client ; npx eslint src/components/ssd-cache/SsdFileCacheTab.tsx src/components/ssd-cache/file-cache src/hooks/useSsdFileCache.ts` → 0 errors (no unused imports).

- [ ] **Step 5: Commit** `refactor(ssd-cache): compose SsdFileCacheTab from useSsdFileCache + file-cache/* (F2, #301)`.

---

## Final Verification (after all tasks)

- [ ] `cd client ; npx eslint .` → 0 errors.
- [ ] `cd client ; npm run build` → green (tsc -b + vite).
- [ ] `cd client ; npx vitest run` → full suite green.
- [ ] `SsdFileCacheTab.tsx` < 500 lines.
- [ ] Update `client/src/components/CLAUDE.md` `ssd-cache/` row to note the `file-cache/` decomposition + `useSsdFileCache` hook (docs-only; fold into the Task 9 commit or a trailing `docs(ssd-cache): ...` commit).
- [ ] Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of every moved block, especially the three effects, the array auto-select in `loadArrays`, and the config save→refresh-stats sequence).
