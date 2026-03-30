# API Client Modules

Typed axios wrappers for backend API communication. One file per feature domain, mirroring the backend `api/routes/` structure.

## Base Client

All modules import from `lib/api.ts`:
- `apiClient` — axios instance with auth interceptor (auto-attaches `Bearer` token from localStorage)
- `memoizedApiRequest<T>(url, params?, ttl?)` — GET with in-memory cache (60s default TTL)
- `buildApiUrl(path)` — resolves path for dev (Vite proxy) vs production
- `extractErrorMessage(detail, fallback)` — extracts user-facing message from FastAPI error responses

## Conventions

- Export typed interfaces for request/response shapes (mirrors backend Pydantic schemas)
- Export async functions, not classes — each function maps to one API endpoint
- Use `apiClient.get/post/put/delete()` for standard calls
- Use `memoizedApiRequest()` for frequently polled read-only data (e.g., permissions, system info)
- Return `res.data` directly (unwrap axios response)
- No error handling here — callers handle errors via `handleApiError()` from `lib/errorHandling.ts`

## Files (~45 modules)

| File | Backend prefix | Key operations |
|---|---|---|
| `files.ts` | `/api/files` | Permissions, duplicates, ownership transfer |
| `monitoring.ts` | `/api/monitoring` | CPU/memory/network/disk history + current, types for samples |
| `raid.ts` | `/api/system` | RAID status, create/delete arrays, disk management |
| `backup.ts` | `/api/backups` | Create/restore/delete backups |
| `shares.ts` | `/api/shares` | Public/user file sharing |
| `sync.ts` | `/api/sync` | Desktop sync folder management |
| `vcl.ts` | `/api/vcl` | File versioning (version list, restore, settings) |
| `plugins.ts` | `/api/plugins` | Plugin CRUD, toggle, config, UI manifest |
| `power-management.ts` | `/api/power` | CPU profiles, demands, auto-scaling |
| `fan-control.ts` | `/api/fans` | Fan config, curves, schedules |
| `smart-devices.ts` | `/api/smart-devices` | Smart device status, control |
| `notifications.ts` | `/api/notifications` | Push notifications, WebSocket token |
| `schedulers.ts` | `/api/schedulers` | Scheduler status, history, run-now |
| `pihole.ts` | `/api/pihole` | Pi-hole status, DNS queries, blocklists |
| `cloud-import.ts` | `/api/cloud` | Cloud import (rclone) operations |

## Adding a New API Module

1. Create `src/api/my-feature.ts`
2. Import `apiClient` from `../lib/api`
3. Define TypeScript interfaces for request/response types
4. Export async functions wrapping `apiClient` calls
5. Import in the component/hook that needs it
