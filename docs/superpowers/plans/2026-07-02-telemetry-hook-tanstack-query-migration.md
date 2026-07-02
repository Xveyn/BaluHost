# Telemetry Hook TanStack Query Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `useSystemTelemetry` internals to a single TanStack Query `useQuery` over the typed `apiClient`, keeping the public return shape bit-for-bit identical (Approach A) so `Dashboard.tsx` is untouched.

**Architecture:** Move the three raw `fetch()` calls into typed `api/system.ts` functions that go through `apiClient` (central auth + 401 interceptor). The hook combines them in one `queryFn` (`Promise.all`) under a single `queryKey`, maps loading/refreshing/error/lastUpdated from the query, and keeps the existing sessionStorage cache wired as `initialData` (removal deferred to the later #299 persister PR).

**Tech Stack:** React 18.2, TypeScript (strict, `verbatimModuleSyntax`), Vite 7, Vitest 4, `@testing-library/react`, `@tanstack/react-query` v5, axios via `apiClient`.

**Spec:** `docs/superpowers/specs/2026-07-02-telemetry-hook-tanstack-query-migration-design.md`
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299) — Track "PR — Telemetry"
**Precedent:** #364 (monitoring pilot — the reference pattern)

## Global Constraints

- **Public hook signature unchanged.** `useSystemTelemetry(pollInterval = 15000)` keeps its exact return shape `{ system, storage, loading, refreshing, error, lastUpdated, history }`. Consumers (`pages/Dashboard.tsx:80`) must not be edited.
- **TanStack Query v5** (already a dependency after #364). React 18.2 — do not bump.
- **`verbatimModuleSyntax: true`** — all type-only imports MUST use the `type` modifier (`import { fn, type Foo }` or `import type`).
- **Tests live under `client/src/__tests__/`** and match `**/*.test.{ts,tsx}`. Non-test helpers under `__tests__/` must NOT end in `.test.`.
- **Query defaults (verbatim, from `lib/queryClient.ts`):** `staleTime: 0`, `retry: 1`, `refetchOnWindowFocus: false`. Test client (`__tests__/helpers/queryClient.tsx`) uses `retry: false`, `gcTime: Infinity`.
- **CI gate:** `npm run build` (= `tsc -b && vite build`) AND `npm run lint` (= `eslint .`, 0-error) must be green; full Vitest suite stays green. Unused imports fail eslint.
- **Repo is CRLF** (`core.autocrlf=true`) — editing tools normalize; not a content concern.
- **Commit trailer:** every commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **All work on branch `feat/tanstack-telemetry-hook-299`** (already created off `main`; the design spec is already committed there).

---

## File Structure

- `client/src/lib/queryKeys.ts` — add a `system` domain (Task 1).
- `client/src/api/system.ts` — add `system_uptime?` to `SystemInfoResponse`; add `getAggregatedStorage()` (returns the existing `StorageInfoResponse`, snake_case, matching the backend `StorageInfo` model); add `TelemetryHistory` (+ point types) + `getTelemetryHistory()` (Task 1).
- `client/src/__tests__/lib/query-foundation.test.ts` — extend with the `system.telemetry()` key assertion (Task 1).
- `client/src/__tests__/api/system.telemetry.test.ts` *(new)* — the two new API fns hit the right endpoints (Task 1).
- `client/src/hooks/useSystemTelemetry.ts` — internal migration to `useQuery` (Task 2).
- `client/src/__tests__/hooks/useSystemTelemetry.test.tsx` *(new)* — hook mapping + sessionStorage seed + error (Task 2).
- `client/src/hooks/CLAUDE.md` — document the migration (Task 3).

---

### Task 1: API layer + query key

**Files:**
- Modify: `client/src/lib/queryKeys.ts`
- Modify: `client/src/api/system.ts`
- Test: `client/src/__tests__/lib/query-foundation.test.ts` (extend)
- Test: `client/src/__tests__/api/system.telemetry.test.ts` (new)

**Interfaces:**
- Produces: `queryKeys.system.telemetry(): readonly ['system','telemetry']`.
- Produces: `getAggregatedStorage(): Promise<StorageInfoResponse>` (reuses the existing `StorageInfoResponse` in `api/system.ts` — the aggregated endpoint returns the same backend `StorageInfo` model, snake_case `use_percent`/`mount_point`), `getTelemetryHistory(): Promise<TelemetryHistory>`, and the exported types `TelemetryHistory`, `CpuHistoryPoint`, `MemoryHistoryPoint`, `NetworkHistoryPoint`. `SystemInfoResponse` gains optional `system_uptime?: number`. No new `StorageInfoResponse` type is introduced (avoids duplicating `StorageInfoResponse`).
- Consumes (test): `apiClient` from `lib/api` (mocked).

- [ ] **Step 1: Add the `system` domain to the query-key factory**

In `client/src/lib/queryKeys.ts`, add a `system` block after the closing `},` of the `monitoring` block (still inside the top-level `queryKeys` object):
```ts
  system: {
    telemetry: () => ['system', 'telemetry'] as const,
  },
```

- [ ] **Step 2: Extend the foundation test with the new key**

In `client/src/__tests__/lib/query-foundation.test.ts`, add this `describe` block at the end of the file (after the existing `queryKeys.monitoring` block):
```ts
describe('queryKeys.system', () => {
  it('builds the telemetry key', () => {
    expect(queryKeys.system.telemetry()).toEqual(['system', 'telemetry']);
  });
});
```

- [ ] **Step 3: Run the key test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/lib/query-foundation.test.ts
```
Expected: PASS (existing tests + the new `queryKeys.system` test).

- [ ] **Step 4: Add telemetry types + fetch functions to `api/system.ts`**

In `client/src/api/system.ts`:

(a) Add `system_uptime?: number;` to the existing `SystemInfoResponse` interface (after `uptime: number;`). This is additive — existing `getSystemInfo` consumers are unaffected.

(b) Append these exports at the end of the file (after `getStorageBreakdown`). Note: `getAggregatedStorage` **reuses the existing `StorageInfoResponse`** already declared in this file (the aggregated endpoint returns the same backend `StorageInfo` model — snake_case `use_percent`/`mount_point`, all required). Do NOT introduce a new `StorageInfoResponse` type.
```ts
export interface CpuHistoryPoint {
  timestamp: number;
  usage: number;
}

export interface MemoryHistoryPoint {
  timestamp: number;
  used: number;
  total: number;
  percent: number;
}

export interface NetworkHistoryPoint {
  timestamp: number;
  downloadMbps: number;
  uploadMbps: number;
}

export interface TelemetryHistory {
  cpu: CpuHistoryPoint[];
  memory: MemoryHistoryPoint[];
  network: NetworkHistoryPoint[];
}

/** Get aggregated storage totals across all mountpoints (dashboard telemetry). */
export async function getAggregatedStorage(): Promise<StorageInfoResponse> {
  const { data } = await apiClient.get<StorageInfoResponse>(
    '/api/system/storage/aggregated'
  );
  return data;
}

/** Get rolling CPU/memory/network telemetry history (dashboard charts). */
export async function getTelemetryHistory(): Promise<TelemetryHistory> {
  const { data } = await apiClient.get<TelemetryHistory>(
    '/api/system/telemetry/history'
  );
  return data;
}
```

- [ ] **Step 5: Write the failing API test**

Create `client/src/__tests__/api/system.telemetry.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getAggregatedStorage, getTelemetryHistory } from '../../api/system';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn() },
}));
const mockedGet = vi.mocked(apiClient.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('telemetry api', () => {
  it('getAggregatedStorage calls the aggregated endpoint and unwraps data', async () => {
    mockedGet.mockResolvedValue({ data: { total: 100, used: 10, available: 90 } });
    const res = await getAggregatedStorage();
    expect(mockedGet).toHaveBeenCalledWith('/api/system/storage/aggregated');
    expect(res.total).toBe(100);
  });

  it('getTelemetryHistory calls the history endpoint and unwraps data', async () => {
    mockedGet.mockResolvedValue({ data: { cpu: [], memory: [], network: [] } });
    const res = await getTelemetryHistory();
    expect(mockedGet).toHaveBeenCalledWith('/api/system/telemetry/history');
    expect(res.cpu).toEqual([]);
  });
});
```

- [ ] **Step 6: Run the API test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/api/system.telemetry.test.ts
```
Expected: PASS (2 tests). (If a resolution error appears, confirm the mock path `../../lib/api` matches how `api/system.ts` imports it as `../lib/api` — both resolve to the same module.)

- [ ] **Step 7: Typecheck + lint the touched files**

Run (from `client/`):
```bash
npx tsc -b
npx eslint src/api/system.ts src/lib/queryKeys.ts
```
Expected: tsc clean, eslint clean.

- [ ] **Step 8: Commit**

Run (from repo root):
```bash
git add client/src/lib/queryKeys.ts client/src/api/system.ts client/src/__tests__/lib/query-foundation.test.ts client/src/__tests__/api/system.telemetry.test.ts
git commit -m "feat(client): add system telemetry api fns + query key (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Migrate `useSystemTelemetry` to `useQuery`

**Files:**
- Modify: `client/src/hooks/useSystemTelemetry.ts` (full internal rewrite; public shape + module-level helpers preserved)
- Test: `client/src/__tests__/hooks/useSystemTelemetry.test.tsx` (new)

**Interfaces:**
- Consumes: `queryKeys.system.telemetry` (Task 1), `getSystemInfo`/`getAggregatedStorage`/`getTelemetryHistory` + their types (Task 1), `useAuth` from `contexts/AuthContext`, `getApiErrorMessage` from `lib/errorHandling`, `useQuery`.
- Produces: `useSystemTelemetry(pollInterval?: number): TelemetryState` — unchanged shape. Re-exports the telemetry types.

- [ ] **Step 1: Write the failing hook test**

Create `client/src/__tests__/hooks/useSystemTelemetry.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useSystemTelemetry } from '../../hooks/useSystemTelemetry';
import * as systemApi from '../../api/system';

vi.mock('../../api/system');
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));
const api = vi.mocked(systemApi);

const sampleSystem = {
  cpu: { usage: 5, cores: 4 },
  memory: { total: 100, used: 40, free: 60 },
  disk: { total: 200, used: 50, free: 150 },
  uptime: 10,
  dev_mode: true,
};
const sampleStorage = {
  filesystem: '/dev/md0',
  total: 200,
  used: 50,
  available: 150,
  use_percent: '25%',
  mount_point: '/',
};
const sampleHistory = { cpu: [{ timestamp: 1, usage: 5 }], memory: [], network: [] };

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe('useSystemTelemetry', () => {
  it('maps system/storage/history into the legacy shape', async () => {
    api.getSystemInfo.mockResolvedValue(sampleSystem);
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.system?.cpu.usage).toBe(5);
    expect(result.current.storage?.percent).toBe(25); // 50 / 200
    expect(result.current.history.cpu).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('is loading on first render with an empty cache', async () => {
    api.getSystemInfo.mockResolvedValue(sampleSystem);
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('paints instantly (loading false) when a fresh sessionStorage cache exists', async () => {
    sessionStorage.setItem(
      'system_telemetry_cache',
      JSON.stringify({
        system: sampleSystem,
        storage: sampleStorage,
        history: sampleHistory,
        timestamp: Date.now(),
      })
    );
    api.getSystemInfo.mockResolvedValue(sampleSystem);
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.system?.cpu.usage).toBe(5);
  });

  it('surfaces an error string when a fetch rejects', async () => {
    api.getSystemInfo.mockRejectedValue(new Error('telemetry boom'));
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('telemetry boom'));
  });
});
```

- [ ] **Step 2: Run the test to verify it runs (fails against the old hook)**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useSystemTelemetry.test.tsx
```
Expected: the suite runs; assertions fail against the old `fetch`+`setInterval` hook (it uses raw `fetch`, not the mocked `api/system` fns, so the mocked resolves never arrive). Confirm it runs, then implement.

- [ ] **Step 3: Rewrite the hook**

Replace the **entire** contents of `client/src/hooks/useSystemTelemetry.ts` with:
```ts
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getSystemInfo,
  getAggregatedStorage,
  getTelemetryHistory,
  type SystemInfoResponse,
  type StorageInfoResponse,
  type TelemetryHistory,
  type CpuHistoryPoint,
  type MemoryHistoryPoint,
  type NetworkHistoryPoint,
} from '../api/system';

interface NormalisedStorageInfo extends StorageInfoResponse {
  percent: number;
}

interface TelemetryState {
  system: SystemInfoResponse | null;
  storage: NormalisedStorageInfo | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastUpdated: Date | null;
  history: TelemetryHistory;
}

interface TelemetrySnapshot {
  system: SystemInfoResponse;
  storage: StorageInfoResponse;
  history: TelemetryHistory;
}

const parsePercent = (value: string | number | undefined): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^0-9.]/g, '');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const TELEMETRY_CACHE_KEY = 'system_telemetry_cache';
const TELEMETRY_CACHE_DURATION = 120000; // 2 minutes

function getCachedTelemetry(): TelemetrySnapshot | null {
  try {
    const cached = sessionStorage.getItem(TELEMETRY_CACHE_KEY);
    if (cached) {
      const data = JSON.parse(cached);
      const age = Date.now() - (data.timestamp || 0);
      if (age < TELEMETRY_CACHE_DURATION && data.system && data.storage && data.history) {
        return { system: data.system, storage: data.storage, history: data.history };
      }
    }
  } catch {
    // Ignore cache read failures
  }
  return null;
}

function setCachedTelemetry(
  system: SystemInfoResponse,
  storage: StorageInfoResponse,
  history: TelemetryHistory
): void {
  try {
    sessionStorage.setItem(
      TELEMETRY_CACHE_KEY,
      JSON.stringify({ system, storage, history, timestamp: Date.now() })
    );
  } catch {
    // Ignore cache write failures
  }
}

export const useSystemTelemetry = (pollInterval = 15000): TelemetryState => {
  const { token } = useAuth();

  const query = useQuery({
    queryKey: queryKeys.system.telemetry(),
    queryFn: async (): Promise<TelemetrySnapshot> => {
      const [system, storage, history] = await Promise.all([
        getSystemInfo(),
        getAggregatedStorage(),
        getTelemetryHistory(),
      ]);
      setCachedTelemetry(system, storage, history); // keep the F5 instant-paint cache warm
      return { system, storage, history };
    },
    refetchInterval: pollInterval,
    enabled: !!token,
    // Lazy: only read/parse sessionStorage when the cache actually seeds initial data.
    initialData: () => getCachedTelemetry() ?? undefined,
  });

  const normalisedStorage = useMemo<NormalisedStorageInfo | null>(() => {
    const storage = query.data?.storage;
    if (!storage) {
      return null;
    }

    const total = Number(storage.total) || 0;
    const used = Number(storage.used) || 0;
    const available = Number(storage.available) || Math.max(total - used, 0);
    const percent = total ? (used / total) * 100 : parsePercent(storage.use_percent);

    return {
      ...storage,
      total,
      used,
      available,
      percent: Math.min(Math.max(percent, 0), 100),
    };
  }, [query.data?.storage]);

  return {
    system: query.data?.system ?? null,
    storage: normalisedStorage,
    loading: query.isLoading,
    refreshing: query.isFetching && !query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Unexpected telemetry error')
      : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    history: query.data?.history ?? { cpu: [], memory: [], network: [] },
  };
};

export type {
  SystemInfoResponse,
  StorageInfoResponse,
  NormalisedStorageInfo,
  TelemetryHistory,
  CpuHistoryPoint,
  MemoryHistoryPoint,
  NetworkHistoryPoint,
};
```

- [ ] **Step 4: Run the hook test to verify it passes**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useSystemTelemetry.test.tsx
```
Expected: PASS (4 tests).

- [ ] **Step 5: Typecheck + lint the hook**

Run (from `client/`):
```bash
npx tsc -b
npx eslint src/hooks/useSystemTelemetry.ts
```
Expected: tsc clean; eslint clean (no unused-import errors — `buildApiUrl`/`fireAuthExpired`/`useState`/`useEffect`/`useRef` are gone).

- [ ] **Step 6: Commit**

Run (from repo root):
```bash
git add client/src/hooks/useSystemTelemetry.ts client/src/__tests__/hooks/useSystemTelemetry.test.tsx
git commit -m "feat(client): migrate useSystemTelemetry to useQuery (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Documentation + full verification gate

**Files:**
- Modify: `client/src/hooks/CLAUDE.md`

- [ ] **Step 1: Update the hooks doc**

In `client/src/hooks/CLAUDE.md`, replace the `useSystemTelemetry.ts` table row with:
```markdown
| `useSystemTelemetry.ts` | `api/system` | System info + aggregated storage + telemetry history for the dashboard via **TanStack Query** (`useQuery`, one combined snapshot, `pollInterval`→`refetchInterval`); sessionStorage seeds `initialData` (removal deferred to #299 persister PR); public shape unchanged |
```

- [ ] **Step 2: Full verification**

Run (from `client/`):
```bash
npm run build
npm run lint
npx vitest run
```
Expected: build succeeds (`tsc -b` + `vite build`); eslint clean (0-error gate); **entire** Vitest suite green (foundation + api + hook + all pre-existing).

- [ ] **Step 3: Commit**

Run (from repo root):
```bash
git add client/src/hooks/CLAUDE.md
git commit -m "docs(client): document useSystemTelemetry TanStack Query migration (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Post-Plan

1. **Manual smoke (dev):** `python start_dev.py`; open the dashboard; confirm telemetry widgets populate, poll ~15 s, repaint instantly after F5 (sessionStorage seed), and that an expired/removed token triggers the central `auth:expired` logout (no manual 401 handler left in the hook).

2. **Side finding — drifted duplicate `SystemInfoResponse`.** The `/api/system/info` shape is declared twice with different fields (hook history vs `api/system.ts`); this PR only reconciles additively. Per project CLAUDE.md, **ask the maintainer** whether to open a GitHub issue for the full unification before creating one.

3. **Push + PR** (do not merge — Xveyn merges after CI):
```bash
git push -u origin feat/tanstack-telemetry-hook-299
```
Open a PR against `main` referencing #299 (checks the "PR — Telemetry" box in the #299 track).
