# Hooks

Custom React hooks encapsulating data fetching, polling, and UI logic. Each hook typically wraps one or more API modules.

## Data Fetching Hooks

| Hook | API module | Purpose |
|---|---|---|
| `useMonitoring.ts` | `api/monitoring` | Unified CPU/memory/network/disk/process data via **TanStack Query** (`useQuery`), configurable `pollInterval` (mapped to `refetchInterval`) + history; public return shape unchanged |
| `useSystemTelemetry.ts` | `api/system` | System info + aggregated storage + telemetry history for the dashboard via **TanStack Query** (`useQuery`, one combined snapshot, `pollInterval`→`refetchInterval`); hand-rolled sessionStorage cache removed, F5 persistence now comes from the app-wide persister (#299); public shape unchanged |
| `useRaidStatus.ts` | `api/raid` | RAID array status via **TanStack Query** (`useQuery`; default 60s poll, 8s on the RAID page — shared cache key); F5-persisted via the app-wide persister. Exposes `lastUpdated` + a `refetch` resolving to a success boolean |
| `useAvailableDisks.ts` | `api/raid` | Unassigned disks for the RAID management page via **TanStack Query** (no polling; format/create/delete mutations invalidate `queryKeys.raid.availableDisks()`). Returns raw `error` |
| `useBackups.ts` | `api/backup` | Backup list via **TanStack Query** (no polling; create/delete mutations invalidate). Returns raw `error` for i18n formatting by the caller |
| `useFileShares.ts` | `api/shares` | The three shares-domain reads (user shares, shared-with-me, statistics) via **TanStack Query**; user-scoped — cache is cleared on every identity change (AuthContext) |
| `useFanControl.ts` | `api/fan-control` | Fan status + write-permission for the fan page via **TanStack Query** (`useQuery`, combined `fans.control()` key, default 5s poll). `refetchInterval` pauses while `pauseRefresh` is set (curve editing); keeps the old "don't flash 'no fans'" guard (masks a transient empty list with the last non-empty snapshot). Public shape unchanged (`{ status, permissionStatus, loading, error, refetch, isReadOnly }`) |
| `useSchedulers.ts` | `api/schedulers` | Scheduler list + history via **TanStack Query**; the three actions (runNow/toggle/updateConfig) via **`useMutation`** with `onSettled: invalidateQueries(schedulers.all())` — the reference for the mutation pattern. runNow keeps the 3s/30s fast-poll (via a function `refetchInterval`). `useSchedulerHistory` is fully options-driven (page/filter in the key → changing them refetches; fixed a latent no-refetch bug) |
| `useBenchmark.ts` | `api/benchmark` | Disk benchmark (8 hooks) via **TanStack Query**: disks/profiles/detail/history reads via `useQuery` (`useBenchmark` gated by `enabled: id !== null`); `useBenchmarkProgress` keeps its imperative `startPolling`/`stopPolling` surface but polls via a function `refetchInterval` that auto-stops on a terminal status (`enabled` gated by `isPolling`); the three actions (start/cancel/mark-failed) via **`useMutation`** with `onSettled: invalidateQueries(benchmark.all())`. All public shapes unchanged — `BenchmarkPanel` untouched |
| `useSmartData.ts` | `api/smart` | SMART disk health via **TanStack Query** (`useQuery`, default 60s poll); the hand-rolled localStorage cache was removed — F5 instant-paint now comes from the app-wide persister. Public shape unchanged (`{ smartData, loading, error, lastUpdated, refetch }`) |
| `useAdminDb.ts` | `api/admin-db` | Admin database inspector via **TanStack Query**: `useAdminTables` (tables + categories, once) and `useAdminTableData(table, params)` (schema + rows, `enabled: table !== null`, key carries page/pageSize/sort/filter/search → param change refetches, revisiting is cache-served). Replaced the old imperative passthrough; `AdminDatabase.tsx` now derives its data from the queries instead of two `useEffect` fetches. The one-off owner-name loader stays imperative (bespoke page-size fallback) and calls `getAdminTableRows` directly |
| `useUserManagement.ts` | `api/users` | User list via **TanStack Query** (key includes the active search/role/status/sort → changing filters refetches; search debounced); CRUD (create/update/delete/bulkDelete/toggleActive) via **`useMutation`** with `onSettled: invalidateQueries(users.all())`. Filter/selection/sort/CSV/confirm state stays local. Public shape unchanged |
| `useDeviceManagement.ts` | `api/devices` (+ `api/sync`, `api/mobile`) | Devices/schedules/bandwidth/preflight reads via **TanStack Query** (was the last `useAsyncData` list consumer); the mutation handlers stay imperative and call the `refetch*` wrappers (stable `() => void` around `query.refetch`). Public shape unchanged |
| `useMobileDevices.ts` | `api/mobile` | Registered mobile devices for MobileDevicesPage via **TanStack Query** (`useQuery`, 10s poll); exposes `isFetching` for the refresh spinner. Mutations (generate token / delete) stay imperative in the page and call `refetch` |
| `useMobile.ts` | — | **Viewport detection** (`useMobile`/`useTablet` via `matchMedia`) — NOT data fetching despite the name |
| `useRemoteServers.ts` | `api/remote-servers` | `useServerProfiles` + `useVPNProfiles` — lists via **TanStack Query**, CRUD (+ startServer) via **`useMutation`** with `onSettled: invalidateQueries(<domain>)`. testConnection is a passthrough (no cache effect). User-scoped — cache cleared on identity change |
| `useActivityFeed.ts` | `api/activity` | Dashboard activity feed (own / admin all-users) via **TanStack Query** (`useQuery`, default 30s poll). Query holds raw API items (persister-safe); view mapping (i18n titles, relative "ago") is derived per render. User-scoped — cache cleared on identity change (AuthContext); `scope`+`limit` are part of the key |
| `useLiveActivities.ts` | `api/fan-control`, `api/power-management` | Derives dashboard "live activity" items from schedulers/raid (passed in) + fan/power status via **TanStack Query** (`useQuery`, 30s/15s polls, `enabled: isAdmin`; keys `fans.status()`/`power.status()`). Was the last `useAsyncData` consumer — that generic hook is now removed (#299) |
| `useDocsIndex.ts` | `api/docs` | Documentation article index via **TanStack Query** (`useQuery`; `lang` in the key → language switch refetches). Re-exports the `DocsGroupInfo`/`DocsArticleInfo` types |
| `useDocsArticle.ts` | `api/docs` | Single documentation article content via **TanStack Query** (`useQuery`; `slug`+`lang` in the key, `enabled: !!slug`). Re-exports the `DocsArticle` type |
| `usePluginsSummary.ts` | `api/plugins` | Plugin list summary for dashboard via **TanStack Query** (`useQuery`, default 60s poll). A 403 (non-admin) is treated as an empty list, silently — no error surfaced |
| `useServicesSummary.ts` | `api/service-status` | Service health summary for dashboard via **TanStack Query** (`useQuery`, default 30s poll). Mounted at 3 sites (ServicesPanel, Dashboard, ServiceSummaryWidget) — the shared query key collapses them into one cache entry + one poll |
| `useGpuCurrent.ts` | `api/monitoring` | Current GPU sample via **TanStack Query** (`useQuery`, 3s poll, `gpu.current()` key). Mounted by `GpuTab` + `Dashboard` — the shared key collapses the two former `setInterval` pollers into one cache entry + one poll (#299). Returns `GpuSample \| null`; `enabled` arg gates polling on GPU presence. Keeps the last value on transient errors (TanStack default) |
| `useOpenApiSchema.ts` | — | OpenAPI schema for API docs page |

## Utility Hooks

| Hook | Purpose |
|---|---|
| `useConfirmDialog.ts` | Confirmation dialog state management |
| `useSortableTable.ts` | Table sorting state (column, direction) |
| `useByteUnitMode.ts` | Binary (GiB) vs decimal (GB) byte unit preference |
| `useIdleTimeout.ts` | Auto-logout after inactivity period |
| `useNetworkStatus.ts` | Online/offline detection |
| `useNotificationSocket.ts` | WebSocket connection for real-time notifications |
| `useNextMaintenance.ts` | Next scheduled maintenance window |
| `usePresenceHeartbeat.ts` | Presence heartbeat to `/api/system/sleep/presence` while tab visible (blocks auto true-suspend, #214); fire-and-forget, mounted once in `AppRoutes` (auth-gated via `enabled`); paused while the idle-logout warning is visible (#222) |
| `useChannelStatus.ts` | Channel connectivity status polling (backend channel health) |
| `useGpuPresence.ts` | Detects GPU presence via `api/gpuPower` for conditional GPU power UI |
| `useStatusBarState.ts` | Aggregated status-bar strip state via **TanStack Query** (`useQuery`, 10s `refetchInterval` — pauses when the tab is hidden via TanStack's default `refetchIntervalInBackground:false`). Returns `{ state, stale }`; keeps the last-known state and flags `stale` on poll errors (replaces the old hand-rolled "hide after 3 failures" with retain-and-flag) |
| `useSystemMode.ts` | Current system mode (e.g. desktop/pi) for conditional rendering |
| `useCountdown.ts` | Generic countdown timer utility hook |

## Conventions

- Return `{ data, loading, error, refetch }` pattern for data hooks
- **Data hooks use TanStack Query** (`useQuery`) with keys from `lib/queryKeys.ts` and `refetchInterval` for polling — not hand-rolled `useState`+`setInterval`. `useMonitoring.ts` is the reference; remaining hooks migrate incrementally (#299). Keep the `{ data|current|..., loading, error, refetch }` public shape so consumers are unaffected.
- Query-backed polling (`refetchInterval`) pauses while the browser tab is hidden and resumes on return (TanStack default; `refetchOnWindowFocus` is off) — intentional for a LAN dashboard, unlike the old always-on `setInterval`.
- **Mutations use `useMutation`** with `onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.<domain>.all() })` — reference implementations: `BackupSettings.tsx`, the share modals (`CreateFileShareModal`/`EditFileShareModal`/`ShareFileModal` invalidate themselves so every mount point is covered), `SharesPage.tsx`
- Accept `enabled?: boolean` option to conditionally disable fetching
- Accept `pollInterval?: number` for configurable refresh rates
- API calls go through typed functions in `api/` — hooks don't use `apiClient` directly
