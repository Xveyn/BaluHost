# Frontend Data-Fetching Framework — TanStack Query Foundation + Monitoring Pilot

**Date:** 2026-07-01
**Issue:** [#299](https://github.com/Xveyn/BaluHost/issues/299) (F1, part of [#298](https://github.com/Xveyn/BaluHost/issues/298) Code-Assessment)
**Scope of this spec:** PR 1 of the incremental track — foundation + one pilot area. Follow-up areas are tracked as a checklist in #299.

---

## Problem

The frontend has **no data-fetching framework**. The current state (verified against `package.json` and the source):

- ~18 data hooks all follow the same hand-rolled `useState×5 + useEffect + setInterval` pattern.
- `client/src/hooks/useMonitoring.ts` contains **5 near-identical copy-paste hooks** (CPU / memory / network / disk-io / processes).
- **Three competing cache approaches** coexist:
  1. `memoizedApiRequest` — in-memory `Map` with TTL, **no invalidation** (`lib/api.ts:83-97`; also filed as #309/F6).
  2. `sessionStorage` caches — hand-rolled stale-while-revalidate in `Dashboard.tsx` (RAID) and `useSystemTelemetry.ts` (2-min TTL).
  3. Ad-hoc effect state — everywhere else.
- `useSystemTelemetry.ts` uses raw `fetch()` bypassing `apiClient` (overlaps #307/F5).
- `useAsyncData.ts` exists but is used in only one place, and calls `setLoading(true)` on every poll (loading flicker), with no caching/dedup.
- 55 manual `setInterval` pollers total — many for the same endpoints, so identical data is fetched by multiple independent timers.

TanStack Query is the single largest lever: request deduplication, stale-while-revalidate without flicker, a unified cache, and standard polling via `refetchInterval`.

## Goal (this PR)

Introduce TanStack Query as the standard, establish the reusable pattern (provider + query-key convention + test helper), and migrate the worst copy-paste area (the 5 monitoring hooks) as the reference implementation — **without changing any consumer** and **without changing user-visible behavior** beyond the deliberate defaults below.

## Non-Goals (deferred to follow-up PRs, tracked in #299)

- Migrating `useSystemTelemetry`, Dashboard/`sessionStorage` caches, or the remaining ~16 data hooks.
- Removing `memoizedApiRequest` (#309/F6) or reworking `useAsyncData`.
- React Query Devtools in the production bundle.
- Persistent cache, global error toasts, global `onError` handling.

---

## Approach

**Approach A — internal migration, identical public API** (chosen over: B = house `useApiQuery` wrapper first; C = expose native `useQuery` shape and update consumers).

Rewrite `useMonitoring.ts` hooks to use `useQuery` internally while returning the **exact same** `{ current, history, loading, error, refetch, lastUpdated }` shape. Consumers (`SystemMonitor` and children) are untouched. This gives the smallest blast radius, a trivial review, and a trivial revert. The one piece of B we keep is a lightweight **query-key convention** (no heavy wrapper) so follow-up PRs have a pattern to copy.

---

## Architecture & Foundation

**New dependency:** `@tanstack/react-query` v5 (compatible with React 18.2). No `@tanstack/react-query-devtools` in the production bundle (optional dev-only lazy import may be added later; out of scope here).

**Provider:** a single `QueryClient` mounted in `client/src/main.tsx` around `<App/>`. Defaults are chosen to **mirror current behavior** — no surprises:

| Option | Value | Rationale |
|---|---|---|
| `staleTime` | `0` global | Monitoring freshness is driven by `refetchInterval`, not `staleTime`; leaving it at `0` needs no per-query override. |
| `retry` | `1` | Current code does not retry; TanStack default is `3`. Keep a dead endpoint from hammering 4× per poll cycle. |
| `refetchOnWindowFocus` | `false` | **Deliberate.** TanStack default `true` would add refetches on tab focus (a behavior change). A LAN NAS dashboard already polls; unnecessary. |
| `gcTime` | default (5 min) | Fine. |

**Auth is unchanged:** queries call the typed `api/monitoring` functions, which use `apiClient`. The axios response interceptor still fires `fireAuthExpired()` on 401; `AuthContext` logs out as today. No auth-flow changes.

**Query-key convention:** a central `client/src/lib/queryKeys.ts` using the factory pattern, e.g.:

```ts
export const queryKeys = {
  monitoring: {
    cpuCurrent: () => ['monitoring', 'cpu', 'current'] as const,
    cpuHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'cpu', 'history', duration, source] as const,
    // memory / network / diskIo / processes analogous
  },
} as const;
```

Documented briefly in `hooks/CLAUDE.md` and `lib/CLAUDE.md` as the standard follow-up PRs must follow.

---

## The Monitoring Pilot

Each of the 5 hooks currently does: fetch current + history in parallel, 5× `useState`, a `useEffect` with `setInterval`. After migration the core of each hook is two `useQuery` calls plus an adapter that reproduces the current return shape:

```ts
export function useCpuMonitoring(options = {}) {
  const { pollInterval = 5000, historyDuration = '1h', source = 'auto', enabled = true } = options;

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
    error: current.error ? extractError(current.error)
         : history.error ? extractError(history.error)
         : null,
    refetch: async () => { await Promise.all([current.refetch(), history.refetch()]); },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}
```

**Deliberate details:**

- **Consumers unchanged** — identical public return shape.
- **No flicker** — TanStack keeps prior data during refetch; `isLoading` is true only on the first load (`isFetching` on subsequent polls). This directly fixes the `useAsyncData` flicker problem.
- **Request dedup** — two components mounting the same hook share one fetch instead of running two timers. This is the real lever against "55 pollers".
- **Disk-I/O special case** — the current "poll every 1s until `availableDisks` is non-empty, then `pollInterval`" logic maps to a `refetchInterval` function. Note `available_disks` comes from the **history** response (not `current`), so the fast-poll gate reads the history query's cached data; both the current and history queries use that same gate until disks appear:
  `refetchInterval: () => (diskIoHistoryHasDisks() ? pollInterval : 1000)`, where the gate reads the history query's cached `available_disks` (e.g. via `queryClient.getQueryData(historyKey)` or a shared derived value). The implementation plan pins the exact wiring.
- **`useAllMonitoring`** remains a thin composition wrapper over the five hooks.
- **`extractError`** — a small helper wrapping the existing `getApiErrorMessage`/`extractErrorMessage`, so the `error: string | null` shape is preserved exactly.

---

## Error Handling

No outward behavior change:

- Queries go through `apiClient`; the axios interceptor fires `fireAuthExpired()` on 401 as today.
- `retry: 1` global (see defaults table) so a dead backend endpoint does not hammer 4× per poll cycle.
- Per-hook `error` string comes from `extractError` (thin wrapper around the existing `getApiErrorMessage`), preserving the public `error: string | null` shape.
- No global `onError` toast in the foundation — pages already surface errors via the hook return. Global error handling would be a separate, deliberate step, not a side effect of this PR.

---

## Testing

- **Foundation test helper:** `renderWithQueryClient` (fresh `QueryClient` per test, `retry: false`, `gcTime: Infinity`) in `client/src/__tests__/`. This is the infrastructure #316/T2 calls for, established here in the small.
- **Pilot hook tests:** Vitest + `@testing-library/react` `renderHook` for the 5 monitoring hooks:
  1. maps `current`/`history` correctly into the legacy shape;
  2. `loading` is true only on first load, false during background refetch;
  3. error path yields a string;
  4. disk-I/O special case (1s vs. `pollInterval`).
  API functions (`getCpuCurrent`, etc.) mocked via `vi.mock('../api/monitoring')`.
- **Regression gate:** `npm run build` (tsc -b over app/node/test projects) and `eslint .` must be green — this is the CI `frontend-build` gate. The existing Vitest suite must stay green.

---

## Files Touched (this PR)

- `client/package.json` — add `@tanstack/react-query`.
- `client/src/main.tsx` — mount `QueryClientProvider` with the configured client.
- `client/src/lib/queryClient.ts` *(new)* — the shared `QueryClient` + defaults.
- `client/src/lib/queryKeys.ts` *(new)* — query-key factory (monitoring keys for this PR).
- `client/src/hooks/useMonitoring.ts` — internal migration to `useQuery` (public API unchanged).
- `client/src/__tests__/` — `renderWithQueryClient` helper + monitoring hook tests.
- `client/src/hooks/CLAUDE.md`, `client/src/lib/CLAUDE.md` — document the convention.

## Rollback

Single dependency + one provider + one hook file. Reverting the PR restores the prior behavior with no data migration to undo (cache is in-memory only).
