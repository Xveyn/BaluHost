# Hooks

Custom React hooks encapsulating data fetching, polling, and UI logic. Each hook typically wraps one or more API modules.

## Data Fetching Hooks

| Hook | API module | Purpose |
|---|---|---|
| `useMonitoring.ts` | `api/monitoring` | Unified CPU/memory/network/disk/process data via **TanStack Query** (`useQuery`), configurable `pollInterval` (mapped to `refetchInterval`) + history; public return shape unchanged |
| `useSystemTelemetry.ts` | `api/system` | System telemetry (CPU, RAM, network) for dashboard widgets |
| `useFanControl.ts` | `api/fan-control` | Fan config, curves, schedules — full fan management state |
| `useSchedulers.ts` | `api/schedulers` | Scheduler list, status, history, run-now |
| `useBenchmark.ts` | `api/benchmark` | Disk benchmark state, progress, results |
| `useSmartData.ts` | `api/smart` | SMART disk health data |
| `useAdminDb.ts` | `api/admin-db` | Admin database inspection |
| `useUserManagement.ts` | `api/users` | User CRUD operations |
| `useDeviceManagement.ts` | `api/devices` | Device list, pairing, removal |
| `useMobile.ts` | `api/mobile` | Mobile device management |
| `useRemoteServers.ts` | `api/remote-servers` | Remote server profiles |
| `useActivityFeed.ts` | `api/activity` | Dashboard activity feed (own / admin all-users) |
| `useLiveActivities.ts` | — | Real-time activity via polling |
| `useDocsIndex.ts` | `api/docs` | Documentation article index |
| `useDocsArticle.ts` | `api/docs` | Single documentation article content |
| `usePluginsSummary.ts` | `api/plugins` | Plugin list summary for dashboard |
| `useServicesSummary.ts` | `api/service-status` | Service health summary for dashboard |
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
- Accept `enabled?: boolean` option to conditionally disable fetching
- Accept `pollInterval?: number` for configurable refresh rates
- API calls go through typed functions in `api/` — hooks don't use `apiClient` directly
