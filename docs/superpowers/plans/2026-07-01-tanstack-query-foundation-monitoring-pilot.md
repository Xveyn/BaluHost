# TanStack Query Foundation + Monitoring Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce TanStack Query v5 as the frontend data-fetching standard and migrate the 5 copy-paste monitoring hooks to it internally, without changing any consumer or user-visible behavior.

**Architecture:** A single shared `QueryClient` (mounted via `QueryClientProvider` in `main.tsx`) with defaults that mirror today's behavior. A central query-key factory (`lib/queryKeys.ts`). The 5 hooks in `useMonitoring.ts` are rewritten to use `useQuery` internally but keep their exact public return shape (Approach A), so `SystemMonitor` and its children are untouched.

**Tech Stack:** React 18.2, TypeScript (strict, `verbatimModuleSyntax`), Vite 7, Vitest 4, `@testing-library/react`, `@tanstack/react-query` v5, axios via `apiClient`.

**Spec:** `docs/superpowers/specs/2026-07-01-frontend-data-fetching-tanstack-query-design.md`
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299)

## Global Constraints

- **Public hook signatures unchanged.** Every migrated hook keeps its exact return shape (`{ current, history, loading, error, refetch, lastUpdated }` and the disk-io/process variants). Consumers must not be edited.
- **TanStack Query v5** (`@tanstack/react-query@^5`). React 18.2 — do not bump React.
- **`verbatimModuleSyntax: true`** — all type-only imports MUST use `import type`.
- **Tests live under `client/src/__tests__/`** and match `**/*.test.{ts,tsx}` (vite.config `test.include`). Non-test helper modules under `__tests__/` must NOT end in `.test.` (they'd be collected as suites).
- **Query defaults (verbatim):** `staleTime: 0`, `retry: 1`, `refetchOnWindowFocus: false`.
- **CI gate:** `npm run build` (= `tsc -b && vite build`, over app/node/test projects) AND `eslint .` must be green; existing Vitest suite must stay green. Unused imports fail eslint.
- **Repo is CRLF** (`core.autocrlf=true` on Windows) — editing tools normalize; not a concern for content.
- **Commit trailer:** every commit ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **All work on branch `feat/tanstack-query-foundation-299`** (already created off `main`).

---

## File Structure

- `client/package.json` / `client/package-lock.json` — add `@tanstack/react-query` (Task 1).
- `client/src/lib/queryClient.ts` *(new)* — shared `QueryClient` + defaults (Task 1).
- `client/src/lib/queryKeys.ts` *(new)* — query-key factory, monitoring keys (Task 1).
- `client/src/main.tsx` — mount `QueryClientProvider` (Task 1).
- `client/src/__tests__/lib/query-foundation.test.ts` *(new)* — asserts defaults + key shapes (Task 1).
- `client/src/__tests__/helpers/queryClient.tsx` *(new)* — `createTestQueryClient`, `createQueryWrapper`, `renderWithQueryClient` (Task 2).
- `client/src/hooks/useMonitoring.ts` — internal migration to `useQuery` (Tasks 2–4).
- `client/src/__tests__/hooks/useMonitoring.cpu.test.tsx` *(new)* — CPU hook tests (Task 2).
- `client/src/__tests__/hooks/useMonitoring.simple.test.tsx` *(new)* — memory + network hook tests (Task 3).
- `client/src/__tests__/hooks/useMonitoring.record.test.tsx` *(new)* — disk-io + processes hook tests (Task 4).
- `client/src/hooks/CLAUDE.md`, `client/src/lib/CLAUDE.md` — document the convention (Task 5).

---

### Task 1: Foundation — dependency, QueryClient, provider, query keys

**Files:**
- Modify: `client/package.json`, `client/package-lock.json`
- Create: `client/src/lib/queryClient.ts`
- Create: `client/src/lib/queryKeys.ts`
- Modify: `client/src/main.tsx`
- Test: `client/src/__tests__/lib/query-foundation.test.ts`

**Interfaces:**
- Produces: `queryClient: QueryClient` (default export-free named export from `lib/queryClient.ts`).
- Produces: `queryKeys` object from `lib/queryKeys.ts` with `queryKeys.monitoring.{cpuCurrent, cpuHistory, memoryCurrent, memoryHistory, networkCurrent, networkHistory, diskIoCurrent, diskIoHistory, processesCurrent, processesHistory}` — factory functions returning `readonly` key arrays. Signatures:
  - `cpuCurrent(): readonly ['monitoring','cpu','current']`
  - `cpuHistory(duration: TimeRange, source: DataSource): readonly ['monitoring','cpu','history', TimeRange, DataSource]`
  - `diskIoHistory(duration: TimeRange, source: DataSource, diskName?: string): readonly [...]`
  - `processesHistory(duration: TimeRange, source: DataSource, processName?: string): readonly [...]`
  - memory/network mirror cpu; `*Current()` take no args.

- [ ] **Step 1: Install the dependency**

Run (from `client/`):
```bash
npm install @tanstack/react-query@^5
```
Expected: `package.json` gains `"@tanstack/react-query": "^5.x"` under `dependencies`; `package-lock.json` updated.

- [ ] **Step 2: Create the query key factory**

Create `client/src/lib/queryKeys.ts`:
```ts
import type { TimeRange, DataSource } from '../api/monitoring';

/**
 * Central query-key factory for TanStack Query.
 *
 * Convention: keys are namespaced arrays `[domain, entity, kind, ...params]`.
 * Follow-up migrations add their domain here (e.g. `queryKeys.raid`, `queryKeys.shares`).
 */
export const queryKeys = {
  monitoring: {
    cpuCurrent: () => ['monitoring', 'cpu', 'current'] as const,
    cpuHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'cpu', 'history', duration, source] as const,
    memoryCurrent: () => ['monitoring', 'memory', 'current'] as const,
    memoryHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'memory', 'history', duration, source] as const,
    networkCurrent: () => ['monitoring', 'network', 'current'] as const,
    networkHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'network', 'history', duration, source] as const,
    diskIoCurrent: () => ['monitoring', 'diskIo', 'current'] as const,
    diskIoHistory: (duration: TimeRange, source: DataSource, diskName?: string) =>
      ['monitoring', 'diskIo', 'history', duration, source, diskName ?? null] as const,
    processesCurrent: () => ['monitoring', 'processes', 'current'] as const,
    processesHistory: (duration: TimeRange, source: DataSource, processName?: string) =>
      ['monitoring', 'processes', 'history', duration, source, processName ?? null] as const,
  },
} as const;
```

- [ ] **Step 3: Create the shared QueryClient**

Create `client/src/lib/queryClient.ts`:
```ts
import { QueryClient } from '@tanstack/react-query';

/**
 * App-wide TanStack Query client.
 *
 * Defaults mirror the previous hand-rolled behavior:
 * - staleTime 0: freshness is driven by per-query refetchInterval, not staleTime.
 * - retry 1: the old code did not retry; keep a dead endpoint from hammering.
 * - refetchOnWindowFocus false: a polling LAN dashboard needs no focus refetch.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

- [ ] **Step 4: Write the failing foundation test**

Create `client/src/__tests__/lib/query-foundation.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { queryClient } from '../../lib/queryClient';
import { queryKeys } from '../../lib/queryKeys';

describe('queryClient defaults', () => {
  it('mirrors the previous behavior', () => {
    const q = queryClient.getDefaultOptions().queries;
    expect(q?.staleTime).toBe(0);
    expect(q?.retry).toBe(1);
    expect(q?.refetchOnWindowFocus).toBe(false);
  });
});

describe('queryKeys.monitoring', () => {
  it('builds namespaced current keys', () => {
    expect(queryKeys.monitoring.cpuCurrent()).toEqual(['monitoring', 'cpu', 'current']);
  });

  it('builds history keys with params', () => {
    expect(queryKeys.monitoring.cpuHistory('1h', 'auto')).toEqual([
      'monitoring', 'cpu', 'history', '1h', 'auto',
    ]);
  });

  it('normalizes optional diskName to null', () => {
    expect(queryKeys.monitoring.diskIoHistory('1h', 'auto')).toEqual([
      'monitoring', 'diskIo', 'history', '1h', 'auto', null,
    ]);
    expect(queryKeys.monitoring.diskIoHistory('1h', 'auto', 'sda')).toEqual([
      'monitoring', 'diskIo', 'history', '1h', 'auto', 'sda',
    ]);
  });
});
```

- [ ] **Step 5: Run the test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/lib/query-foundation.test.ts
```
Expected: PASS (3–4 tests). (This test needs only the two new lib files, both created above.)

- [ ] **Step 6: Mount the provider in main.tsx**

Edit `client/src/main.tsx`. Add the imports and wrap the tree with `QueryClientProvider`:
```tsx
import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { ThemeProvider } from './contexts/ThemeContext'
import { queryClient } from './lib/queryClient'
import './i18n' // Initialize i18n before app renders
import './index.css'
import App from './App.tsx'

// Loading fallback for i18n
const I18nLoadingFallback = () => (
  <div className="flex items-center justify-center h-screen bg-slate-950">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
  </div>
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={<I18nLoadingFallback />}>
        <ThemeProvider>
          <App />
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: '#1f2937',
                color: '#f9fafb',
                border: '1px solid #374151'
              }
            }}
          />
        </ThemeProvider>
      </Suspense>
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 7: Verify build + lint are green**

Run (from `client/`):
```bash
npm run build
npm run lint
```
Expected: both succeed (tsc -b type-checks the new lib + test files; vite build produces the bundle; `lint` = `eslint .`, 0-error gate).

- [ ] **Step 8: Commit**

Run (from repo root):
```bash
git add client/package.json client/package-lock.json client/src/lib/queryClient.ts client/src/lib/queryKeys.ts client/src/main.tsx client/src/__tests__/lib/query-foundation.test.ts
git commit -m "feat(client): add TanStack Query foundation (client, provider, query keys) (#299)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Test helper + CPU hook migration (the reference pattern)

**Files:**
- Create: `client/src/__tests__/helpers/queryClient.tsx`
- Modify: `client/src/hooks/useMonitoring.ts` (imports + `useCpuMonitoring` only)
- Test: `client/src/__tests__/hooks/useMonitoring.cpu.test.tsx`

**Interfaces:**
- Produces (test helper): `createTestQueryClient(): QueryClient`, `createQueryWrapper(client?: QueryClient): ({ children }) => JSX.Element`, `renderWithQueryClient(ui, client?)`.
- Consumes: `queryKeys` (Task 1), `getApiErrorMessage` from `lib/errorHandling`, monitoring API fns.
- Produces (hook): `useCpuMonitoring` keeps its existing signature and return shape `UseMonitoringResult<CurrentCpuResponse, CpuSample>`.

- [ ] **Step 1: Create the test helper**

Create `client/src/__tests__/helpers/queryClient.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

/** Fresh client per test: no retries, no GC eviction mid-test. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
    },
  });
}

export function createQueryWrapper(client: QueryClient = createTestQueryClient()) {
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export function renderWithQueryClient(ui: ReactElement, client: QueryClient = createTestQueryClient()) {
  return render(ui, { wrapper: createQueryWrapper(client) });
}
```

- [ ] **Step 2: Write the failing CPU hook test**

Create `client/src/__tests__/hooks/useMonitoring.cpu.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useCpuMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useCpuMonitoring', () => {
  it('maps current + history into the legacy return shape', async () => {
    api.getCpuCurrent.mockResolvedValue({ timestamp: 't0', usage_percent: 42 });
    api.getCpuHistory.mockResolvedValue({
      samples: [{ timestamp: 't0', usage_percent: 42 }],
      sample_count: 1,
      source: 'memory',
    });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.current).toEqual({ timestamp: 't0', usage_percent: 42 });
    expect(result.current.history).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('is loading on first render and clears after data arrives', async () => {
    api.getCpuCurrent.mockResolvedValue({ timestamp: 't0', usage_percent: 1 });
    api.getCpuHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('surfaces an error string when a fetch rejects', async () => {
    api.getCpuCurrent.mockRejectedValue(new Error('boom'));
    api.getCpuHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('boom'));
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.cpu.test.tsx
```
Expected: FAIL — the current `useCpuMonitoring` still uses `setInterval` (999999ms) so on first tick `loading` starts `true`; the mapping assertions may pass by luck, but the "loading true on first render" expectation and the error-string timing are what pin the new behavior. Confirm at least one assertion fails (if all pass, the mock wiring is wrong — fix before implementing).

> Note: the pre-migration hook may partially pass. The point of this step is to confirm the test *runs* and mocks are wired. Proceed to implement regardless; Step 5 is the real gate.

- [ ] **Step 4: Migrate `useCpuMonitoring` to `useQuery`**

In `client/src/hooks/useMonitoring.ts`:

(a) Add these imports at the top (keep the existing `useState/useEffect/useCallback` import for the not-yet-migrated hooks):
```ts
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
```

(b) Add this module-private helper near the top of the file (after imports, before the first hook):
```ts
/** First non-null error from a set of query errors, as a user-facing string. */
function firstError(label: string, ...errors: unknown[]): string | null {
  const err = errors.find((e) => e != null);
  return err ? getApiErrorMessage(err, `Failed to fetch ${label} data`) : null;
}
```

(c) Replace the entire body of `useCpuMonitoring` with:
```ts
export function useCpuMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentCpuResponse, CpuSample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.cpuCurrent(),
    queryFn: getCpuCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.cpuHistory(historyDuration, source),
    queryFn: () => getCpuHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('CPU', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.cpu.test.tsx
```
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

Run (from repo root):
```bash
git add client/src/__tests__/helpers/queryClient.tsx client/src/hooks/useMonitoring.ts client/src/__tests__/hooks/useMonitoring.cpu.test.tsx
git commit -m "feat(client): migrate useCpuMonitoring to useQuery + query test helper (#299)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Migrate memory + network hooks

**Files:**
- Modify: `client/src/hooks/useMonitoring.ts` (`useMemoryMonitoring`, `useNetworkMonitoring`)
- Test: `client/src/__tests__/hooks/useMonitoring.simple.test.tsx`

**Interfaces:**
- Consumes: `useQuery`, `queryKeys`, `firstError` (all from Task 2), monitoring API fns.
- Produces: `useMemoryMonitoring`, `useNetworkMonitoring` with unchanged signatures/return shapes.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useMonitoring.simple.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useMemoryMonitoring, useNetworkMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMemoryMonitoring', () => {
  it('maps current + history into the legacy shape', async () => {
    api.getMemoryCurrent.mockResolvedValue({
      timestamp: 't0', used_bytes: 10, total_bytes: 100, percent: 10,
    });
    api.getMemoryHistory.mockResolvedValue({
      samples: [{ timestamp: 't0', used_bytes: 10, total_bytes: 100, percent: 10 }],
      sample_count: 1, source: 'memory',
    });

    const { result } = renderHook(() => useMemoryMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.current?.percent).toBe(10);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });
});

describe('useNetworkMonitoring', () => {
  it('surfaces an error string when a fetch rejects', async () => {
    api.getNetworkCurrent.mockRejectedValue(new Error('net-down'));
    api.getNetworkHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useNetworkMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('net-down'));
  });
});
```

- [ ] **Step 2: Run the test to verify it runs**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.simple.test.tsx
```
Expected: runs; assertions pinning new behavior may fail against the old `setInterval` hooks. Proceed to implement.

- [ ] **Step 3: Migrate `useMemoryMonitoring`**

In `client/src/hooks/useMonitoring.ts`, replace the entire body of `useMemoryMonitoring` with:
```ts
export function useMemoryMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentMemoryResponse, MemorySample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.memoryCurrent(),
    queryFn: getMemoryCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.memoryHistory(historyDuration, source),
    queryFn: () => getMemoryHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('memory', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

- [ ] **Step 4: Migrate `useNetworkMonitoring`**

In `client/src/hooks/useMonitoring.ts`, replace the entire body of `useNetworkMonitoring` with:
```ts
export function useNetworkMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentNetworkResponse, NetworkSample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.networkCurrent(),
    queryFn: getNetworkCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.networkHistory(historyDuration, source),
    queryFn: () => getNetworkHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('network', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.simple.test.tsx
```
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

Run (from repo root):
```bash
git add client/src/hooks/useMonitoring.ts client/src/__tests__/hooks/useMonitoring.simple.test.tsx
git commit -m "feat(client): migrate memory + network monitoring hooks to useQuery (#299)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Migrate disk-io + processes hooks (record shapes + special cases)

**Files:**
- Modify: `client/src/hooks/useMonitoring.ts` (`useDiskIoMonitoring`, `useProcessMonitoring`, import cleanup)
- Test: `client/src/__tests__/hooks/useMonitoring.record.test.tsx`

**Interfaces:**
- Consumes: `useQuery`, `queryKeys`, `firstError`, monitoring API fns.
- Produces: `useDiskIoMonitoring` returns `UseDiskIoResult` (`{ disks, history, availableDisks, loading, error, refetch, lastUpdated }`); `useProcessMonitoring` returns `UseProcessResult` (`{ processes, history, crashesDetected, loading, error, refetch, lastUpdated }`). Signatures unchanged (both accept the extra `diskName?` / `processName?` option).

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useMonitoring.record.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useDiskIoMonitoring, useProcessMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDiskIoMonitoring', () => {
  it('maps record-shaped disks/history and availableDisks', async () => {
    api.getDiskIoCurrent.mockResolvedValue({
      disks: { sda: { timestamp: 't0', disk_name: 'sda', read_mbps: 1, write_mbps: 2, read_iops: 3, write_iops: 4 } },
    });
    api.getDiskIoHistory.mockResolvedValue({
      disks: { sda: [] },
      available_disks: ['sda'],
      sample_count: 0,
      source: 'memory',
    });

    const { result } = renderHook(() => useDiskIoMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.availableDisks).toEqual(['sda']);
    expect(result.current.disks.sda?.read_mbps).toBe(1);
    expect(result.current.history.sda).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('fast-polls (~1s) while no disks are available, then backs off', async () => {
    vi.useFakeTimers();
    // Always report no disks so the fast-poll gate stays active.
    api.getDiskIoCurrent.mockResolvedValue({ disks: {} });
    api.getDiskIoHistory.mockResolvedValue({
      disks: {}, available_disks: [], sample_count: 0, source: 'memory',
    });

    renderHook(() => useDiskIoMonitoring({ pollInterval: 5000 }), {
      wrapper: createQueryWrapper(),
    });

    // Flush the initial mount fetch.
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(api.getDiskIoHistory).toHaveBeenCalledTimes(1);

    // After 1s the empty-disks fast-poll fires again (not the 5s pollInterval).
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(api.getDiskIoHistory).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});

describe('useProcessMonitoring', () => {
  it('maps processes/history and crashesDetected', async () => {
    api.getProcessesCurrent.mockResolvedValue({
      processes: { web: { timestamp: 't0', process_name: 'web', pid: 1, cpu_percent: 5, memory_mb: 50, status: 'running', is_alive: true } },
    });
    api.getProcessesHistory.mockResolvedValue({
      processes: { web: [] },
      sample_count: 0,
      source: 'memory',
      crashes_detected: 2,
    });

    const { result } = renderHook(() => useProcessMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.processes.web?.pid).toBe(1);
    expect(result.current.crashesDetected).toBe(2);
  });
});

afterEach(() => {
  vi.useRealTimers();
});
```

- [ ] **Step 2: Run the test to verify it runs**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.record.test.tsx
```
Expected: runs; fails against the old hooks. Proceed to implement.

- [ ] **Step 3: Migrate `useDiskIoMonitoring`**

In `client/src/hooks/useMonitoring.ts`, replace the entire body of `useDiskIoMonitoring` with:
```ts
export function useDiskIoMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> & { diskName?: string } = {}
): UseDiskIoResult {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    diskName,
    enabled = true,
  } = options;

  const history = useQuery({
    queryKey: queryKeys.monitoring.diskIoHistory(historyDuration, source, diskName),
    queryFn: () => getDiskIoHistory(historyDuration, source, diskName),
    // Poll every 1s until disks are discovered, then back off to pollInterval.
    refetchInterval: (query) =>
      query.state.data?.available_disks?.length ? pollInterval : 1000,
    enabled,
  });

  const fastPoll = !history.data?.available_disks?.length && !history.error;
  const current = useQuery({
    queryKey: queryKeys.monitoring.diskIoCurrent(),
    queryFn: getDiskIoCurrent,
    refetchInterval: fastPoll ? 1000 : pollInterval,
    enabled,
  });

  return {
    disks: current.data?.disks ?? {},
    history: history.data?.disks ?? {},
    availableDisks: history.data?.available_disks ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('disk I/O', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

- [ ] **Step 4: Migrate `useProcessMonitoring`**

In `client/src/hooks/useMonitoring.ts`, replace the entire body of `useProcessMonitoring` with:
```ts
export function useProcessMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> & { processName?: string } = {}
): UseProcessResult {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    processName,
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.processesCurrent(),
    queryFn: getProcessesCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.processesHistory(historyDuration, source, processName),
    queryFn: () => getProcessesHistory(historyDuration, source, processName),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    processes: current.data?.processes ?? {},
    history: history.data?.processes ?? {},
    crashesDetected: history.data?.crashes_detected ?? 0,
    loading: current.isLoading || history.isLoading,
    error: firstError('process', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

- [ ] **Step 5: Remove now-unused imports**

All 5 hooks are migrated; `useState`, `useEffect`, `useCallback` are no longer used in `useMonitoring.ts`. Edit the top-of-file React import: delete the line
```ts
import { useState, useEffect, useCallback } from 'react';
```
(Leave every other import — the type imports and API fn imports are all still used. `useAllMonitoring` at the bottom stays unchanged.)

- [ ] **Step 6: Run the file's tests + typecheck**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useMonitoring.record.test.tsx
npx tsc -b
npx eslint src/hooks/useMonitoring.ts
```
Expected: tests PASS (3 tests), tsc clean, eslint clean (no unused-import errors).

- [ ] **Step 7: Commit**

Run (from repo root):
```bash
git add client/src/hooks/useMonitoring.ts client/src/__tests__/hooks/useMonitoring.record.test.tsx
git commit -m "feat(client): migrate disk-io + processes monitoring hooks to useQuery (#299)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Documentation + full verification gate

**Files:**
- Modify: `client/src/hooks/CLAUDE.md`
- Modify: `client/src/lib/CLAUDE.md`

- [ ] **Step 1: Document the convention in `lib/CLAUDE.md`**

In `client/src/lib/CLAUDE.md`, add two rows to the Files table (alphabetically near `api.ts`), and a short note under "Key Patterns":

Table rows:
```markdown
| `queryClient.ts` | Shared TanStack Query `QueryClient` + app-wide query defaults (`staleTime 0`, `retry 1`, `refetchOnWindowFocus false`). Mounted via `QueryClientProvider` in `main.tsx` |
| `queryKeys.ts` | Central query-key factory (`queryKeys.<domain>.<entity>()`) — the canonical key namespace for all `useQuery` calls |
```

Key Patterns bullet:
```markdown
- **Data fetching uses TanStack Query** (`@tanstack/react-query` v5). Hooks call typed `api/*` functions inside `useQuery`; keys come from `lib/queryKeys.ts`. Migration is incremental per domain (see #299) — new/edited data hooks should use `useQuery`, not hand-rolled `useState`+`setInterval`.
```

- [ ] **Step 2: Document the pattern in `hooks/CLAUDE.md`**

In `client/src/hooks/CLAUDE.md`, update the `useMonitoring.ts` row and add a Conventions note.

Change the `useMonitoring.ts` table row's Purpose to:
```markdown
| `useMonitoring.ts` | `api/monitoring` | Unified CPU/memory/network/disk/process data via **TanStack Query** (`useQuery`), configurable `pollInterval` (mapped to `refetchInterval`) + history; public return shape unchanged |
```

Replace the first Conventions bullet (`Use useState + useEffect for polling...`) with:
```markdown
- **Data hooks use TanStack Query** (`useQuery`) with keys from `lib/queryKeys.ts` and `refetchInterval` for polling — not hand-rolled `useState`+`setInterval`. `useMonitoring.ts` is the reference; remaining hooks migrate incrementally (#299). Keep the `{ data|current|..., loading, error, refetch }` public shape so consumers are unaffected.
```

- [ ] **Step 3: Full verification**

Run (from `client/`):
```bash
npm run build
npm run lint
npx vitest run
```
Expected: build succeeds; eslint clean (0-error gate); **entire** Vitest suite green (foundation + cpu + simple + record + all pre-existing tests).

- [ ] **Step 4: Commit**

Run (from repo root):
```bash
git add client/src/hooks/CLAUDE.md client/src/lib/CLAUDE.md
git commit -m "docs(client): document TanStack Query convention in hooks/lib CLAUDE.md (#299)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-Plan: open the PR

After Task 5, push the branch and open a PR against `main` referencing #299 (checks the "PR 1" box in the #299 checklist). Do not merge — Xveyn merges after CI.

```bash
git push -u origin feat/tanstack-query-foundation-299
```
