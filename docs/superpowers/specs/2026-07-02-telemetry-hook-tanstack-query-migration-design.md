# Telemetry Hook → TanStack Query Migration Design

**Date:** 2026-07-02
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299) — Track "PR — Telemetry"
**Overarching spec:** `docs/superpowers/specs/2026-07-01-frontend-data-fetching-tanstack-query-design.md`
**Precedent PR:** #364 (monitoring pilot — the reference pattern)

## Context

Issue #299 (Finding F1) tracks the incremental migration of the frontend to TanStack
Query v5, one domain per PR, keeping public hook signatures stable (Approach A). PR 1
(monitoring pilot) is merged (#364). This spec covers the next track step: migrating
`client/src/hooks/useSystemTelemetry.ts`.

The telemetry hook is the dashboard's primary data source. Today it:

- Fetches 3 endpoints with **raw `fetch()`** + manual `Authorization` header from
  `useAuth()`: `/api/system/info`, `/api/system/storage/aggregated`,
  `/api/system/telemetry/history` (`useSystemTelemetry.ts:156-166`).
- Handles 401 manually via `fireAuthExpired()` (`:169-172`) — raw `fetch()` bypasses the
  central `apiClient` interceptor. This is the #299/F5 overlap ("rohes `fetch()` →
  `apiClient`").
- Hand-rolls polling with `setInterval(pollInterval=15000)` (`:222-224`).
- Uses a **sessionStorage cache** (`system_telemetry_cache`, 2-min TTL, `:94-124`) to paint
  last values instantly after a full page reload (F5), then refreshes in the background.
- Exposes `{ system, storage, loading, refreshing, error, lastUpdated, history }`.

**Sole consumer:** `pages/Dashboard.tsx:80`, which destructures
`{ system, storage, loading, error, lastUpdated, history }` — it does **not** use
`refreshing` or `system_uptime`. Low blast radius.

## Goal

Migrate the hook's internals to a single `useQuery` over the typed `apiClient`, keeping the
public return shape bit-for-bit identical, so `Dashboard.tsx` is untouched. Route all three
requests through `apiClient` so the central auth/401 interceptor applies (closes the F5/#307
raw-`fetch()` overlap for these endpoints).

## Non-Goals (deferred by #299 sequencing)

- **Removing / replacing the sessionStorage cache.** That is the separate "Dashboard-Caches"
  PR (introduce a Query persister, delete all hand-rolled sessionStorage blobs at once).
  TanStack's in-memory cache does **not** survive a full page reload, so dropping
  sessionStorage now would regress the instant-paint-after-F5 behavior. This PR **keeps**
  sessionStorage, wired as `initialData`.
- Unifying the drifted `SystemInfoResponse` types (see Side Findings).
- Migrating `Dashboard.tsx`'s own separate sessionStorage cache.

## Architecture

### 1. API layer — `client/src/api/system.ts`

Replace the three raw `fetch()` calls with typed `apiClient` functions:

- **Reuse** existing `getSystemInfo()` for `/api/system/info`. Additively extend its
  `SystemInfoResponse` with `system_uptime?: number` (non-breaking — existing consumers of
  `getSystemInfo`/`getStorageInfo` are unaffected).
- **Add** `getAggregatedStorage(): Promise<StorageInfoResponse>` → `/api/system/storage/aggregated`,
  **reusing the existing `StorageInfoResponse`** already in `api/system.ts`. The aggregated
  endpoint is declared `response_model=StorageInfo` on the backend, i.e. the same model
  `getStorageInfo()` returns — snake_case `use_percent`/`mount_point` (all required). Reusing
  the existing type keeps the client type accurate to the wire and avoids a duplicate.
  (Correction to the initial draft, which specified a camelCase `AggregatedStorageInfo`
  mirroring the old hook's inaccurate type — the old hook read `storage.usePercent`, which was
  always `undefined` at runtime but harmless because that fallback branch only runs when
  `total === 0`. The migration fixes this to `storage.use_percent`.)
- **Add** `getTelemetryHistory(): Promise<TelemetryHistory>` → `/api/system/telemetry/history`,
  with `TelemetryHistory` + `CpuHistoryPoint` / `MemoryHistoryPoint` / `NetworkHistoryPoint`
  exported for reuse.

All go through `apiClient` → the request interceptor auto-attaches the bearer token from
`localStorage` and the response interceptor fires `fireAuthExpired()` on 401 centrally
(`lib/api.ts:48-80`).

### 2. Query key — `client/src/lib/queryKeys.ts`

Add a new `system` domain (the pilot's queryKeys already anticipates follow-up domains):

```ts
system: {
  telemetry: () => ['system', 'telemetry'] as const,
},
```

One combined key, because the hook's contract is one atomic snapshot (single `lastUpdated`,
single loading/error), not three independently-cached slices.

### 3. Hook — `client/src/hooks/useSystemTelemetry.ts`

Single `useQuery`:

```ts
const { token } = useAuth();
const query = useQuery({
  queryKey: queryKeys.system.telemetry(),
  queryFn: async () => {
    const [system, storage, history] = await Promise.all([
      getSystemInfo(),
      getAggregatedStorage(),
      getTelemetryHistory(),
    ]);
    setCachedTelemetry(system, storage, history); // keep sessionStorage warm
    return { system, storage, history };
  },
  refetchInterval: pollInterval,           // default 15000
  enabled: !!token,
  initialData: getCachedTelemetry() ?? undefined, // instant-paint seed after F5
});
```

Public mapping (shape unchanged):

| Field | Source |
|---|---|
| `system` | `query.data?.system ?? null` |
| `storage` | `normalisedStorage` (existing `useMemo` over `query.data?.storage`) |
| `loading` | `query.isLoading` |
| `refreshing` | `query.isFetching && !query.isLoading` |
| `error` | `query.isError ? getApiErrorMessage(query.error, 'Unexpected telemetry error') : null` |
| `lastUpdated` | `query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null` |
| `history` | `query.data?.history ?? { cpu: [], memory: [], network: [] }` |

The type re-exports at the bottom of the hook stay (now aliasing the `api/system.ts` types
where applicable) so any type importer keeps working. `NormalisedStorageInfo` stays
hook-owned (derived UI type). `useState`/`useEffect`/`useRef` and the manual polling/loader
are removed; `getCachedTelemetry`/`setCachedTelemetry`/`parsePercent` stay.

### Behavior parity notes

- **initialData + `staleTime: 0`** (global default) ⇒ when a fresh sessionStorage cache
  exists, `isLoading` is false immediately (instant paint) and a background refetch starts at
  once — matching today's "with cache, start background refresh" path.
- **Tab-hidden polling pause:** query-backed `refetchInterval` pauses while the tab is hidden
  (TanStack default), unlike the old always-on `setInterval`. This is the intended,
  already-documented behavior for the LAN dashboard (see `hooks/CLAUDE.md`).
- **No-token:** `enabled: !!token` idles the query (no data, no error) instead of setting the
  old `"Missing authentication token."` error. Acceptable — the dashboard is auth-gated; the
  sole consumer does not surface that specific string.

## Testing

`client/src/__tests__/hooks/useSystemTelemetry.test.tsx` (new), mocking `../../api/system`
and `sessionStorage`, using the existing `createQueryWrapper` helper:

1. Maps `system` / `storage` (normalised `percent`) / `history` into the legacy shape;
   `error` null; `lastUpdated` is a `Date`.
2. `loading` is true on first render with an empty cache, false after data arrives.
3. With a fresh sessionStorage seed, `loading` is false on first render (instant paint).
4. Surfaces an error string when a fetch rejects.

Full gate (per pilot): `npm run build` + `npm run lint` + `npx vitest run` all green.

## Documentation

Update the `useSystemTelemetry.ts` row in `client/src/hooks/CLAUDE.md` (now TanStack-backed,
`api/system`). Add the two new functions to the `api/system.ts` description if warranted.

## Side Findings (flag, do not fix here — per project CLAUDE.md "GitHub Issues für Nebenbefunde")

1. **Drifted duplicate `SystemInfoResponse`.** The `/api/system/info` shape is declared twice
   with different fields — hook (`system_uptime?`, no `dev_mode`) vs `api/system.ts`
   (`dev_mode`, no `system_uptime`). This PR only additively reconciles (`system_uptime?`);
   a full unification is a separate cleanup → propose a GitHub issue.
2. **`Dashboard.tsx` has its own sessionStorage cache** (`:46-74`) — part of the "3 competing
   cache approaches" in #299; addressed by the later Dashboard-Caches PR.

## Verification

1. `cd client && npm run build && npm run lint && npx vitest run` — all green.
2. `python start_dev.py`; open the dashboard; confirm telemetry widgets populate, poll every
   ~15 s, and repaint instantly after F5 (sessionStorage seed).
3. Simulate a 401 (expire/remove token) → confirm central `auth:expired` logout fires (no
   manual handler left in the hook).
