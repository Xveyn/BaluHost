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
| `useFanControl.ts` | `api/fan-control` | Fan config, curves, schedules — full fan management state |
| `useSchedulers.ts` | `api/schedulers` | Scheduler list + history via **TanStack Query**; the three actions (runNow/toggle/updateConfig) via **`useMutation`** with `onSettled: invalidateQueries(schedulers.all())` — the reference for the mutation pattern. runNow keeps the 3s/30s fast-poll (via a function `refetchInterval`). `useSchedulerHistory` is fully options-driven (page/filter in the key → changing them refetches; fixed a latent no-refetch bug) |
| `useBenchmark.ts` | `api/benchmark` | Disk benchmark state, progress, results |
| `useSmartData.ts` | `api/smart` | SMART disk health data |
| `useAdminDb.ts` | `api/admin-db` | Admin database inspection |
| `useUserManagement.ts` | `api/users` | User list via **TanStack Query** (key includes the active search/role/status/sort → changing filters refetches; search debounced); CRUD (create/update/delete/bulkDelete/toggleActive) via **`useMutation`** with `onSettled: invalidateQueries(users.all())`. Filter/selection/sort/CSV/confirm state stays local. Public shape unchanged |
| `useDeviceManagement.ts` | `api/devices` | Device list, pairing, removal |
| `useMobile.ts` | `api/mobile` | Mobile device management |
| `useRemoteServers.ts` | `api/remote-servers` | `useServerProfiles` + `useVPNProfiles` — lists via **TanStack Query**, CRUD (+ startServer) via **`useMutation`** with `onSettled: invalidateQueries(<domain>)`. testConnection is a passthrough (no cache effect). User-scoped — cache cleared on identity change |
| `useActivityFeed.ts` | `api/activity` | Dashboard activity feed (own / admin all-users) via **TanStack Query** (`useQuery`, default 30s poll). Query holds raw API items (persister-safe); view mapping (i18n titles, relative "ago") is derived per render. User-scoped — cache cleared on identity change (AuthContext); `scope`+`limit` are part of the key |
| `useLiveActivities.ts` | — | Real-time activity via polling. **Not yet on TanStack Query** — still polls fan/power status via `useAsyncData`; migrate together with the fans/power domains + the `useAsyncData` cleanup (#299) |
| `useDocsIndex.ts` | `api/docs` | Documentation article index via **TanStack Query** (`useQuery`; `lang` in the key → language switch refetches). Re-exports the `DocsGroupInfo`/`DocsArticleInfo` types |
| `useDocsArticle.ts` | `api/docs` | Single documentation article content via **TanStack Query** (`useQuery`; `slug`+`lang` in the key, `enabled: !!slug`). Re-exports the `DocsArticle` type |
| `usePluginsSummary.ts` | `api/plugins` | Plugin list summary for dashboard via **TanStack Query** (`useQuery`, default 60s poll). A 403 (non-admin) is treated as an empty list, silently — no error surfaced |
| `useServicesSummary.ts` | `api/service-status` | Service health summary for dashboard via **TanStack Query** (`useQuery`, default 30s poll). Mounted at 3 sites (ServicesPanel, Dashboard, ServiceSummaryWidget) — the shared query key collapses them into one cache entry + one poll |
| `useOpenApiSchema.ts` | — | OpenAPI schema for API docs page |

## Utility Hooks

| Hook | Purpose |
|---|---|
| `useAsyncData.ts` | Generic async data fetcher with loading/error state |
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
| `useStatusBarState.ts` | Aggregated status-bar strip state (catalog-driven multi-indicator) |
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
