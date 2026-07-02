# Dashboard Caches → TanStack Query Persister Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two hand-rolled dashboard `sessionStorage` data-caches (telemetry + RAID) with the TanStack Query cache made durable across reloads by the official Query persister, migrating the RAID fetch to a `useQuery` hook — preserving instant-paint-after-F5 without any hand-rolled cache.

**Architecture:** A global `PersistQueryClientProvider` mirrors the whole query cache to `sessionStorage` and rehydrates on boot. The RAID fetch becomes `useRaidStatus` (a `useQuery` hook). The telemetry hook and Dashboard drop their `sessionStorage` machinery, which the persister now supersedes.

**Tech Stack:** React 18.2, TypeScript (strict, `verbatimModuleSyntax`), Vite 7, Vitest 4, `@testing-library/react`, `@tanstack/react-query` v5 + `@tanstack/query-sync-storage-persister` + `@tanstack/react-query-persist-client`.

**Spec:** `docs/superpowers/specs/2026-07-02-dashboard-caches-query-persister-design.md`
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299) — Track "PR — Dashboard-Caches"
**Precedents:** #364 (pilot), #365 (telemetry — deferred sessionStorage removal to this PR)

## Global Constraints

- **Public shapes unchanged.** `useSystemTelemetry` keeps its exact return shape; `Dashboard.tsx` behavior is unchanged for the user. `useRaidStatus` is new.
- **New dependencies:** `@tanstack/query-sync-storage-persister`, `@tanstack/react-query-persist-client` (both official TanStack, versioned with react-query v5).
- **Persister storage = `sessionStorage`**, key `baluhost-query-cache`, `maxAge` 24h, `buster` = `API_VERSION` (from `lib/api`). QueryClient `gcTime` must be `>= maxAge` (set to 24h).
- **`verbatimModuleSyntax: true`** — type-only imports use the `type` modifier.
- **Tests** live under `client/src/__tests__/`, match `**/*.test.{ts,tsx}`. Reuse the existing `__tests__/helpers/queryClient.tsx` `createQueryWrapper`.
- **CI gate:** `npm run build` (= `tsc -b && vite build`) AND `npm run lint` (= `eslint .`, 0-error) green; full Vitest suite green. Unused imports fail eslint.
- **Do NOT touch** non-cache `sessionStorage` use (`secureStore.ts`, `AuthContext` impersonation, `usePresenceHeartbeat`, `chunk-reload` guard) or the `useOpenApiSchema`/`FileManager` caches (other pages). Do NOT migrate GPU polling / `getSystemMode` (ad-hoc effects, out of scope).
- **Repo is CRLF** (`core.autocrlf=true`) — not a content concern.
- **Commit trailer:** every commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Branch `feat/tanstack-dashboard-caches-persister-299`** (already created off `main`; spec already committed there).

---

## File Structure

- `client/package.json` / `package-lock.json` — 2 new deps (Task 1).
- `client/src/lib/queryPersister.ts` *(new)* — persister + `persistOptions` (Task 1).
- `client/src/lib/queryClient.ts` — add `gcTime` (Task 1).
- `client/src/main.tsx` — `PersistQueryClientProvider` (Task 1).
- `client/src/__tests__/lib/queryPersister.test.ts` *(new)* — persister round-trip/config (Task 1).
- `client/src/lib/queryKeys.ts` — add `raid` domain (Task 2).
- `client/src/hooks/useRaidStatus.ts` *(new)* — RAID `useQuery` hook (Task 2).
- `client/src/__tests__/lib/query-foundation.test.ts` — extend with `raid` key (Task 2).
- `client/src/__tests__/hooks/useRaidStatus.test.tsx` *(new)* (Task 2).
- `client/src/pages/Dashboard.tsx` — drop RAID cache/effect, use `useRaidStatus` (Task 3).
- `client/src/hooks/useSystemTelemetry.ts` — drop sessionStorage machinery (Task 3).
- `client/src/__tests__/hooks/useSystemTelemetry.test.tsx` — drop the sessionStorage-seed case (Task 3).
- `client/src/lib/CLAUDE.md`, `client/src/hooks/CLAUDE.md` — docs (Task 4).

---

### Task 1: Persister foundation (deps, persister, provider, gcTime)

**Files:**
- Modify: `client/package.json`, `client/package-lock.json`
- Create: `client/src/lib/queryPersister.ts`
- Modify: `client/src/lib/queryClient.ts`
- Modify: `client/src/main.tsx`
- Test: `client/src/__tests__/lib/queryPersister.test.ts`

**Interfaces:**
- Produces: `queryPersister` (a sync-storage persister) and `persistOptions` (`{ persister, maxAge, buster }`) from `lib/queryPersister.ts`.

- [ ] **Step 1: Install the two persister packages**

Run (from `client/`):
```bash
npm install @tanstack/query-sync-storage-persister @tanstack/react-query-persist-client
```
Expected: both added under `dependencies` at a `^5.x` matching react-query; `package-lock.json` updated.

- [ ] **Step 2: Create the persister module**

Create `client/src/lib/queryPersister.ts`:
```ts
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { API_VERSION } from './api';

/**
 * Mirrors the whole TanStack Query cache to sessionStorage so it survives a full
 * page reload (F5). This is the app-wide replacement for hand-rolled sessionStorage
 * caches — tab-scoped, survives F5, cleared on tab close (sessionStorage semantics).
 */
export const queryPersister = createSyncStoragePersister({
  storage: typeof window !== 'undefined' ? window.sessionStorage : undefined,
  key: 'baluhost-query-cache',
});

/**
 * Passed to PersistQueryClientProvider. maxAge drops entries older than 24h on
 * hydration (per-query freshness is still driven by staleTime/refetchInterval);
 * buster invalidates every persisted cache when the API contract version changes.
 */
export const persistOptions = {
  persister: queryPersister,
  maxAge: 1000 * 60 * 60 * 24,
  buster: API_VERSION,
};
```

- [ ] **Step 3: Raise the QueryClient gcTime to match maxAge**

Edit `client/src/lib/queryClient.ts`. In the `queries` defaults, add the `gcTime` line (keep the others exactly):
```ts
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      retry: 1,
      refetchOnWindowFocus: false,
      gcTime: 1000 * 60 * 60 * 24, // >= persister maxAge (24h) for reliable persistence
    },
  },
});
```

- [ ] **Step 4: Swap the provider in main.tsx**

Edit `client/src/main.tsx` — replace the `QueryClientProvider` import + usage with `PersistQueryClientProvider`, and import `persistOptions`. The full file:
```tsx
import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { Toaster } from 'react-hot-toast'
import { ThemeProvider } from './contexts/ThemeContext'
import { queryClient } from './lib/queryClient'
import { persistOptions } from './lib/queryPersister'
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
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
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
    </PersistQueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 5: Write the failing persister test**

Create `client/src/__tests__/lib/queryPersister.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { queryPersister, persistOptions } from '../../lib/queryPersister';
import { API_VERSION } from '../../lib/api';

const emptyClient = () => ({
  timestamp: 1,
  buster: '',
  clientState: { queries: [], mutations: [] },
});

beforeEach(() => {
  sessionStorage.clear();
});

describe('queryPersister', () => {
  it('persists under the baluhost-query-cache sessionStorage key', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    expect(sessionStorage.getItem('baluhost-query-cache')).not.toBeNull();
  });

  it('round-trips a persisted client', async () => {
    const client = emptyClient();
    client.clientState.queries = [{ queryKey: ['x'], state: { data: 42 } }] as never;
    await queryPersister.persistClient(client as never);
    const restored = await queryPersister.restoreClient();
    expect(restored?.clientState.queries).toHaveLength(1);
  });

  it('removeClient clears the entry', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    await queryPersister.removeClient();
    const restored = await queryPersister.restoreClient();
    expect(restored).toBeUndefined();
  });
});

describe('persistOptions', () => {
  it('uses a 24h maxAge and the API_VERSION buster', () => {
    expect(persistOptions.maxAge).toBe(1000 * 60 * 60 * 24);
    expect(persistOptions.buster).toBe(API_VERSION);
  });
});
```

- [ ] **Step 6: Run the persister test**

Run (from `client/`):
```bash
npx vitest run src/__tests__/lib/queryPersister.test.ts
```
Expected: PASS (4 tests). (jsdom provides `sessionStorage`.)

- [ ] **Step 7: Typecheck + lint + build**

Run (from `client/`):
```bash
npx tsc -b
npx eslint src/lib/queryPersister.ts src/lib/queryClient.ts src/main.tsx
npm run build
```
Expected: tsc clean; eslint clean; `vite build` succeeds (proves `PersistQueryClientProvider` + the new deps resolve and bundle). If `npm run build` fails on a missing type for `persistOptions`, confirm the two packages installed at a `^5` version matching react-query.

- [ ] **Step 8: Commit**

```bash
git add client/package.json client/package-lock.json client/src/lib/queryPersister.ts client/src/lib/queryClient.ts client/src/main.tsx client/src/__tests__/lib/queryPersister.test.ts
git commit -m "feat(client): add TanStack Query sessionStorage persister (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: RAID query key + `useRaidStatus` hook

**Files:**
- Modify: `client/src/lib/queryKeys.ts`
- Create: `client/src/hooks/useRaidStatus.ts`
- Test: `client/src/__tests__/lib/query-foundation.test.ts` (extend)
- Test: `client/src/__tests__/hooks/useRaidStatus.test.tsx` (new)

**Interfaces:**
- Produces: `queryKeys.raid.status(): readonly ['raid','status']`.
- Produces: `useRaidStatus(options?: { pollInterval?: number; enabled?: boolean }): UseRaidStatusResult` where `UseRaidStatusResult = { raidData: RaidStatusResponse | null; raidLoading: boolean; error: string | null; refetch: () => Promise<void> }`.
- Consumes: `getRaidStatus` + `RaidStatusResponse` from `api/raid`, `getApiErrorMessage` from `lib/errorHandling`, `useQuery`.

- [ ] **Step 1: Add the `raid` domain to the query-key factory**

In `client/src/lib/queryKeys.ts`, add a `raid` block after the `system` block (still inside the top-level object):
```ts
  raid: {
    status: () => ['raid', 'status'] as const,
  },
```

- [ ] **Step 2: Extend the foundation test**

In `client/src/__tests__/lib/query-foundation.test.ts`, append:
```ts
describe('queryKeys.raid', () => {
  it('builds the status key', () => {
    expect(queryKeys.raid.status()).toEqual(['raid', 'status']);
  });
});
```

- [ ] **Step 3: Run the key test**

Run (from `client/`):
```bash
npx vitest run src/__tests__/lib/query-foundation.test.ts
```
Expected: PASS (existing + new `queryKeys.raid`).

- [ ] **Step 4: Write the failing hook test**

Create `client/src/__tests__/hooks/useRaidStatus.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useRaidStatus } from '../../hooks/useRaidStatus';
import * as raidApi from '../../api/raid';

vi.mock('../../api/raid');
const api = vi.mocked(raidApi);

const sample = {
  arrays: [{ name: 'md0', level: 'raid1', size_bytes: 100, status: 'active', devices: [] }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useRaidStatus', () => {
  it('maps raid status into the result shape', async () => {
    api.getRaidStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useRaidStatus({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.raidLoading).toBe(false));
    expect(result.current.raidData?.arrays).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error string when the fetch rejects', async () => {
    api.getRaidStatus.mockRejectedValue(new Error('raid boom'));
    const { result } = renderHook(() => useRaidStatus({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.error).toBe('raid boom'));
  });

  it('does not fetch when disabled', () => {
    api.getRaidStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useRaidStatus({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });
    expect(result.current.raidLoading).toBe(false);
    expect(api.getRaidStatus).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 5: Run the test to verify it fails**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useRaidStatus.test.tsx
```
Expected: FAIL — `useRaidStatus` does not exist yet.

- [ ] **Step 6: Implement the hook**

Create `client/src/hooks/useRaidStatus.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { getRaidStatus, type RaidStatusResponse } from '../api/raid';

export interface UseRaidStatusResult {
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * RAID array status for the dashboard. Query-backed (persisted across F5 via the
 * app-wide persister); polls every `pollInterval` ms (default 60s).
 */
export function useRaidStatus(
  options: { pollInterval?: number; enabled?: boolean } = {}
): UseRaidStatusResult {
  const { pollInterval = 60000, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.raid.status(),
    queryFn: getRaidStatus,
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    raidData: query.data ?? null,
    raidLoading: query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Failed to fetch RAID status')
      : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}
```

- [ ] **Step 7: Run the hook test + typecheck**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useRaidStatus.test.tsx
npx tsc -b
npx eslint src/hooks/useRaidStatus.ts src/lib/queryKeys.ts
```
Expected: tests PASS (3), tsc clean, eslint clean.

- [ ] **Step 8: Commit**

```bash
git add client/src/lib/queryKeys.ts client/src/hooks/useRaidStatus.ts client/src/__tests__/lib/query-foundation.test.ts client/src/__tests__/hooks/useRaidStatus.test.tsx
git commit -m "feat(client): add useRaidStatus query hook + raid query key (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Remove hand-rolled dashboard caches (RAID + telemetry)

**Files:**
- Modify: `client/src/pages/Dashboard.tsx`
- Modify: `client/src/hooks/useSystemTelemetry.ts`
- Test: `client/src/__tests__/hooks/useSystemTelemetry.test.tsx`

**Interfaces:**
- Consumes: `useRaidStatus` (Task 2). The persister (Task 1) now provides F5 persistence, so both hand-rolled `sessionStorage` caches are redundant.

- [ ] **Step 1: Migrate the Dashboard RAID fetch to `useRaidStatus`**

In `client/src/pages/Dashboard.tsx`:

(a) Replace the raid API import (line 8):
```ts
import { getRaidStatus, type RaidStatusResponse } from '../api/raid';
```
with the hook import:
```ts
import { useRaidStatus } from '../hooks/useRaidStatus';
```

(b) Delete the RAID sessionStorage cache block (the `RAID_CACHE_KEY`/`RAID_CACHE_DURATION` consts and the `getCachedRaid`/`setCachedRaid` functions) — everything from `const RAID_CACHE_KEY = 'raid_status_cache';` through the end of `setCachedRaid`.

(c) Replace the cached-raid state setup:
```ts
  const cachedRaid = getCachedRaid();
  const [raidData, setRaidData] = useState<RaidStatusResponse | null>(cachedRaid);
  const [raidLoading, setRaidLoading] = useState(!cachedRaid);
```
with:
```ts
  const { raidData, raidLoading } = useRaidStatus();
```

(d) Delete the RAID polling `useEffect` entirely:
```ts
  useEffect(() => {
    const loadRaidData = async () => {
      try {
        const data = await getRaidStatus();
        setRaidData(data);
        setCachedRaid(data);
      } catch {
        // RAID data load failed
      } finally {
        setRaidLoading(false);
      }
    };

    loadRaidData();
    const interval = setInterval(loadRaidData, 60000); // Poll every 60 seconds

    return () => clearInterval(interval);
  }, []);
```

Leave the GPU polling effect, the `getSystemMode`/SMART-mode effect, `useLiveActivities({ raidData, ... })`, and all rendering untouched.

- [ ] **Step 2: Verify Dashboard typechecks/lints (no stray refs)**

Run (from `client/`):
```bash
npx tsc -b
npx eslint src/pages/Dashboard.tsx
```
Expected: clean. If eslint flags `useState` as unused, it is still used by `gpuSample`/`smartMode`/`smartModeLoading` — do not remove it. If it flags `RaidStatusResponse` unused, remove it from imports (only referenced by the deleted `useState`); if tsc reports it still used elsewhere, keep it.

- [ ] **Step 3: Drop the sessionStorage machinery from the telemetry hook**

In `client/src/hooks/useSystemTelemetry.ts`:

(a) Delete the entire sessionStorage block — the `TELEMETRY_CACHE_KEY`/`TELEMETRY_CACHE_DURATION` consts and the `getCachedTelemetry`/`setCachedTelemetry` functions (from `const TELEMETRY_CACHE_KEY` through the end of `setCachedTelemetry`). Keep `parsePercent` and `TelemetrySnapshot`.

(b) Replace the `useQuery` call so the `queryFn` no longer writes the cache and there is no `initialData`:
```ts
  const query = useQuery({
    queryKey: queryKeys.system.telemetry(),
    queryFn: async (): Promise<TelemetrySnapshot> => {
      const [system, storage, history] = await Promise.all([
        getSystemInfo(),
        getAggregatedStorage(),
        getTelemetryHistory(),
      ]);
      return { system, storage, history };
    },
    refetchInterval: pollInterval,
    enabled: !!token,
  });
```
Everything else in the hook (the `normalisedStorage` memo, the return mapping, the type re-exports) stays exactly as-is.

- [ ] **Step 4: Update the telemetry test — drop the sessionStorage-seed case**

In `client/src/__tests__/hooks/useSystemTelemetry.test.tsx`, delete the test case titled `paints instantly (loading false) when a fresh sessionStorage cache exists` (the whole `it('paints instantly ...', ...)` block). The `sessionStorage.clear()` in `beforeEach` may stay (harmless). The other three cases (mapping, loading, error) are unchanged.

- [ ] **Step 5: Run the affected tests + typecheck + lint**

Run (from `client/`):
```bash
npx vitest run src/__tests__/hooks/useSystemTelemetry.test.tsx
npx tsc -b
npx eslint src/hooks/useSystemTelemetry.ts
```
Expected: telemetry tests PASS (3 now), tsc clean, eslint clean (no unused `sessionStorage`/cache refs).

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/Dashboard.tsx client/src/hooks/useSystemTelemetry.ts client/src/__tests__/hooks/useSystemTelemetry.test.tsx
git commit -m "refactor(client): drop hand-rolled dashboard sessionStorage caches (persister supersedes) (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Documentation + full verification gate

**Files:**
- Modify: `client/src/lib/CLAUDE.md`
- Modify: `client/src/hooks/CLAUDE.md`

- [ ] **Step 1: Document the persister in `lib/CLAUDE.md`**

In `client/src/lib/CLAUDE.md`, add a Files-table row (near `queryClient.ts`):
```markdown
| `queryPersister.ts` | TanStack Query **persister** — mirrors the whole query cache to `sessionStorage` (`baluhost-query-cache`, 24h `maxAge`, `API_VERSION` buster), rehydrated on boot via `PersistQueryClientProvider` in `main.tsx`. App-wide replacement for hand-rolled sessionStorage caches (F5 instant-paint) |
```
And a Key-Patterns bullet:
```markdown
- **Query cache persists across reloads** via `queryPersister.ts` + `PersistQueryClientProvider` (sessionStorage). New data hooks get F5 instant-paint for free — do not hand-roll sessionStorage caches. `queryClient` `gcTime` is 24h to satisfy the persister's `maxAge`.
```

- [ ] **Step 2: Document `useRaidStatus` + telemetry change in `hooks/CLAUDE.md`**

In `client/src/hooks/CLAUDE.md`, add a Data-Fetching-Hooks row:
```markdown
| `useRaidStatus.ts` | `api/raid` | RAID array status via **TanStack Query** (`useQuery`, 60s poll); F5-persisted via the app-wide persister |
```
And update the `useSystemTelemetry.ts` row to drop the sessionStorage mention:
```markdown
| `useSystemTelemetry.ts` | `api/system` | System info + aggregated storage + telemetry history for the dashboard via **TanStack Query** (`useQuery`, one combined snapshot, `pollInterval`→`refetchInterval`); F5 instant-paint via the app-wide query persister; public shape unchanged |
```

- [ ] **Step 3: Full verification**

Run (from `client/`):
```bash
npm run build
npm run lint
npx vitest run
```
Expected: build succeeds; eslint 0 errors; entire Vitest suite green (persister + raid + updated telemetry + all pre-existing).

- [ ] **Step 4: Commit**

```bash
git add client/src/lib/CLAUDE.md client/src/hooks/CLAUDE.md
git commit -m "docs(client): document query persister + useRaidStatus (#299)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Post-Plan

1. **Manual smoke (dev):** `python start_dev.py`; open the dashboard; confirm RAID + telemetry widgets repaint instantly after F5; check `sessionStorage` holds a single `baluhost-query-cache` blob and **no** `system_telemetry_cache` / `raid_status_cache`; confirm polling (telemetry ~15s, RAID ~60s) and hidden-tab pause still work.
2. **Push + PR** (do not merge — Xveyn merges after CI):
```bash
git push -u origin feat/tanstack-dashboard-caches-persister-299
```
Open a PR against `main` referencing #299 (checks the "PR — Dashboard-Caches" box in the track).
