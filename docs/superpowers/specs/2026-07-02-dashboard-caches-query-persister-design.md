# Dashboard Caches → TanStack Query Persister Design

**Date:** 2026-07-02
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299) — Track "PR — Dashboard-Caches"
**Overarching spec:** `docs/superpowers/specs/2026-07-01-frontend-data-fetching-tanstack-query-design.md`
**Precedents:** #364 (monitoring pilot), #365 (telemetry hook — deferred sessionStorage removal to this PR)

## Context

Issue #299 migrates the frontend to TanStack Query one domain per PR. Two hand-rolled
`sessionStorage` data-caches remain on the dashboard path, each giving "instant paint after a
full page reload (F5)" that TanStack's in-memory cache does not provide on its own:

- **`hooks/useSystemTelemetry.ts`** — `system_telemetry_cache` (kept as `initialData` in #365,
  explicitly deferring removal to this PR).
- **`pages/Dashboard.tsx`** — `raid_status_cache` (`Dashboard.tsx:46-74`), fed by a hand-rolled
  `getRaidStatus` `useEffect` + `setInterval(60s)` (`Dashboard.tsx:117-134`).

These are two of the "3 competing cache approaches" from #299 F1. The reason they were not
simply dropped when their hooks migrated: a plain `useQuery` cache is in-memory only and is
lost on F5, regressing the instant-paint.

**Storage landscape (verified):** the only other `sessionStorage` *data* caches are
`useOpenApiSchema.ts` and `FileManager.tsx` (different pages — out of scope here). All other
`sessionStorage` use is auth/state, not data caching (`secureStore.ts`, `AuthContext`
impersonation, `usePresenceHeartbeat` client-id, the `chunk-reload` reload-loop guard) and
MUST NOT be touched.

## Goal

Replace the two dashboard `sessionStorage` data-caches with the TanStack Query cache made
durable across reloads by the official **Query persister**, and migrate the Dashboard RAID
fetch to a `useQuery` hook — preserving the instant-paint-after-F5 behavior without any
hand-rolled cache.

## Decision (assumed pending review): global persister

Approach chosen: a **global** persister (mirrors the whole query cache to `sessionStorage`,
rehydrates on boot), not a per-query one. Rationale: it is the #299 end-state ("3 cache
approaches → 1 mechanism"), every migrated/future hook gets F5 persistence for free, and it is
strictly simpler than maintaining per-key persistence. Alternatives considered:

- **Scoped persister** (`shouldDehydrateQuery` allowlist of dashboard keys): more control, less
  `sessionStorage` volume, but reintroduces per-key management. Kept as a documented fallback if
  cache volume becomes a problem.
- **Plain `useQuery`, no persister:** simplest, no new dependency, but regresses F5 instant-paint
  — rejected (it is exactly what #365 deferred to avoid).

**New dependencies** (both official TanStack, versioned with `@tanstack/react-query` v5):
`@tanstack/query-sync-storage-persister`, `@tanstack/react-query-persist-client`.

## Architecture

### 1. Persister — `client/src/lib/queryPersister.ts` *(new)*

```ts
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { API_VERSION } from './api';

export const queryPersister = createSyncStoragePersister({
  storage: typeof window !== 'undefined' ? window.sessionStorage : undefined,
  key: 'baluhost-query-cache',
});

export const persistOptions = {
  persister: queryPersister,
  maxAge: 1000 * 60 * 60 * 24, // 24h — stale entries dropped on hydration; per-query freshness still driven by staleTime/refetchInterval
  buster: API_VERSION,          // bump invalidates all persisted caches on an API-shape change
} as const;
```

`sessionStorage` (not `localStorage`) matches the current caches' semantics: tab-scoped,
survives F5, cleared on tab close.

### 2. Provider — `client/src/main.tsx`

Swap `QueryClientProvider` for `PersistQueryClientProvider`:

```tsx
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { queryClient } from './lib/queryClient';
import { persistOptions } from './lib/queryPersister';
// ...
<PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
  <Suspense fallback={<I18nLoadingFallback />}>
    {/* ...unchanged tree... */}
  </Suspense>
</PersistQueryClientProvider>
```

The provider gates children on cache restoration (a synchronous `sessionStorage` read → no
perceptible delay). On restore failure it renders anyway. Placement stays outermost, exactly
where `QueryClientProvider` was — auth/theme nesting unchanged.

### 3. QueryClient default — `client/src/lib/queryClient.ts`

Add `gcTime: 1000 * 60 * 60 * 24` to the `queries` defaults. TanStack requires
`gcTime >= maxAge` for reliable persistence (an inactive query GC'd before dehydration would
not be persisted). `staleTime: 0` / `retry: 1` / `refetchOnWindowFocus: false` stay.

### 4. Query key — `client/src/lib/queryKeys.ts`

Add a `raid` domain:
```ts
raid: {
  status: () => ['raid', 'status'] as const,
},
```

### 5. RAID hook — `client/src/hooks/useRaidStatus.ts` *(new)*

```ts
export interface UseRaidStatusResult {
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useRaidStatus(options: { pollInterval?: number; enabled?: boolean } = {}): UseRaidStatusResult {
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
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to fetch RAID status') : null,
    refetch: async () => { await query.refetch(); },
  };
}
```
Mirrors the monitoring-hook pattern (#364). 60s poll matches the old interval. Data comes from
the persistent cache on F5.

### 6. Dashboard — `client/src/pages/Dashboard.tsx`

- Delete `RAID_CACHE_KEY`, `RAID_CACHE_DURATION`, `getCachedRaid`, `setCachedRaid`, the
  `raidData`/`raidLoading` `useState`, and the RAID `useEffect` + `setInterval` (`:46-74`,
  `:87-89`, `:117-134`).
- Replace with `const { raidData, raidLoading } = useRaidStatus();`.
- `raidData` still flows into `useLiveActivities({ raidData, ... })` unchanged.
- GPU polling, `getSystemMode`/SMART-mode effects are **untouched** (not caches; separate #299
  scope).

### 7. Telemetry hook — `client/src/hooks/useSystemTelemetry.ts`

Remove `TELEMETRY_CACHE_KEY`, `TELEMETRY_CACHE_DURATION`, `getCachedTelemetry`,
`setCachedTelemetry`, the `TelemetrySnapshot` no longer needs the cache round-trip, and the
`initialData` option. The persister now supplies F5 instant-paint. The `queryFn` drops its
`setCachedTelemetry` call. Public return shape and all mappings stay identical.

## Testing

- **`__tests__/lib/queryPersister.test.ts`** *(new)*: round-trip — build a `QueryClient`, seed a
  query, `persistOptions.persister.persistClient(dehydrate(...))`, then `restoreClient()` into a
  fresh client via a mocked `sessionStorage`; assert the data survives and that a stale-beyond-
  `maxAge` payload is discarded. Assert `buster` mismatch discards.
- **`__tests__/hooks/useRaidStatus.test.tsx`** *(new)*: mock `api/raid`; assert mapping
  (`raidData`/`raidLoading`/`error`) and `enabled:false` idles, via `createQueryWrapper`.
- **`__tests__/lib/query-foundation.test.ts`**: extend with `queryKeys.raid.status()`.
- **`__tests__/hooks/useSystemTelemetry.test.tsx`**: remove the "sessionStorage instant-paint
  seed" case (the hook no longer reads sessionStorage); the mapping/loading/error cases stay.
- Full gate: `npm run build` + `npm run lint` + `npx vitest run` green.

## Documentation

- `client/src/lib/CLAUDE.md`: add `queryPersister.ts` row; note the global persister in Key
  Patterns.
- `client/src/hooks/CLAUDE.md`: add `useRaidStatus.ts` row; update `useSystemTelemetry.ts` row
  (sessionStorage seed removed — persister-backed).

## Verification

1. `cd client && npm run build && npm run lint && npx vitest run` — all green.
2. `python start_dev.py`; dashboard populates; RAID + telemetry widgets repaint **instantly
   after F5** (now via the persister, not hand-rolled caches); confirm `sessionStorage` holds a
   single `baluhost-query-cache` blob and no `system_telemetry_cache` / `raid_status_cache`.
3. Confirm polling still runs (telemetry ~15s, RAID ~60s) and pauses on a hidden tab.

## Non-Goals

- GPU polling / `getSystemMode` migration (ad-hoc effects, not caches).
- `useOpenApiSchema` / `FileManager` sessionStorage caches (other pages — own migrations).
- A `shouldDehydrateQuery` allowlist (documented fallback only, not implemented now).
