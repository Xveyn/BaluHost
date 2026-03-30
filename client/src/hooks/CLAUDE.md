# Hooks

Custom React hooks encapsulating data fetching, polling, and UI logic. Each hook typically wraps one or more API modules.

## Data Fetching Hooks

| Hook | API module | Purpose |
|---|---|---|
| `useMonitoring.ts` | `api/monitoring` | Unified CPU/memory/network/disk polling with configurable interval and history |
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
| `useSyncSettings.ts` | `api/sync` | Desktop sync folder config |
| `useActivityFeed.ts` | `api/files` | Recent file activity stream |
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

## Conventions

- Return `{ data, loading, error, refetch }` pattern for data hooks
- Use `useState` + `useEffect` for polling (with cleanup via `clearInterval`)
- Accept `enabled?: boolean` option to conditionally disable fetching
- Accept `pollInterval?: number` for configurable refresh rates
- API calls go through typed functions in `api/` — hooks don't use `apiClient` directly
