# Lib (Utilities)

Shared utility functions and core infrastructure. No React components — pure TypeScript.

## Files

| File | Purpose |
|---|---|
| `api.ts` | **Core API client**: axios instance (`apiClient`), auth interceptor, 401 handling, `memoizedApiRequest()` with TTL cache, `buildApiUrl()` for dev/prod path resolution, API version check via `X-API-Min-Version` header |
| `errorHandling.ts` | `getApiErrorMessage(err, fallback)` — extracts message from axios/FastAPI errors. `handleApiError(err, fallback)` — shows toast.error |
| `features.ts` | Build-time feature flags via `__DEVICE_MODE__` (Vite define). `FEATURES.*` object, `isDesktop`/`isPi` booleans. Dead code elimination in minifier |
| `chunkedUpload.ts` | Resumable chunked file upload client |
| `byteUnits.ts` | Binary (GiB) vs decimal (GB) formatting |
| `csv.ts` | CSV export utility |
| `dateUtils.ts` | Date/time formatting helpers |
| `fileTypes.ts` | File type detection and icon mapping |
| `formatters.ts` | Number/percentage/duration formatters |
| `statusColors.ts` | Status-to-color mapping for UI indicators |
| `localApi.ts` | Local-only API helpers (system shutdown, etc.) |
| `secureStore.ts` | Secure storage abstraction |
| `notificationGrouping.ts` | Notification grouping logic |
| `adminDbFormatters.ts` | Admin database value formatters |
| `openapi-transform.ts` | OpenAPI schema transformation for API docs page |
| `pluginLoader.ts` | Dynamic plugin JS bundle loader |
| `pluginSDK.ts` | Plugin SDK exposed to plugin bundles |
| `pluginI18n.ts` | Plugin translation resolution helper |
| `mockSyncApi.ts` | Mock sync API for development |

## Key Patterns

- `apiClient` is the single axios instance — all API calls go through it
- Auth token auto-attached via request interceptor from `localStorage.getItem('token')`
- 401 responses fire `auth:expired` CustomEvent — `AuthContext` listens and logs out
- `memoizedApiRequest()` uses an in-memory `Map` cache with configurable TTL (default 60s)
- `FEATURES` object enables tree-shaking: `isDesktop ? import('./HeavyPage') : null` ensures Pi builds exclude desktop-only code
