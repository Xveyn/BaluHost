# API Client Modules

Typed axios wrappers for backend API communication. One file per feature domain, mirroring the backend `api/routes/` structure.

## Base Client

All modules import from `lib/api.ts`:
- `apiClient` — axios instance with auth interceptor (auto-attaches `Bearer` token from localStorage)
- `buildApiUrl(path)` — resolves path for dev (Vite proxy) vs production
- `extractErrorMessage(detail, fallback)` — extracts user-facing message from FastAPI error responses

## Conventions

- Export typed interfaces for request/response shapes (mirrors backend Pydantic schemas)
- Export async functions, not classes — each function maps to one API endpoint
- Use `apiClient.get/post/put/delete()` for standard calls
- No client-side memo caching in api/* — read-caching/dedup lives in TanStack Query hooks (`useQuery` + `lib/queryKeys.ts`); mutations invalidate their domain (`invalidateQueries`)
- Return `res.data` directly (unwrap axios response)
- No error handling here — callers handle errors via `handleApiError()` from `lib/errorHandling.ts`

## Files (~57 modules)

| File | Backend prefix | Key operations |
|---|---|---|
| `files.ts` | `/api/files` | Permissions, duplicates, ownership transfer |
| `monitoring.ts` | `/api/monitoring` | CPU/memory/network/disk history + current, types for samples |
| `raid.ts` | `/api/system` | RAID status, create/delete arrays, disk management |
| `backup.ts` | `/api/backups` | Create/restore/delete backups |
| `shares.ts` | `/api/shares` | Public/user file sharing |
| `sync.ts` | `/api/sync` | Sync schedules, bandwidth limits, preflight |
| `vcl.ts` | `/api/vcl` | File versioning (version list, restore, settings) |
| `plugins.ts` | `/api/plugins` | Plugin CRUD, toggle, config, UI manifest |
| `power-management.ts` | `/api/power` | CPU profiles, demands, auto-scaling |
| `fan-control.ts` | `/api/fans` | Fan config, curves, schedules |
| `smart-devices.ts` | `/api/smart-devices` | Smart device status, control |
| `notifications.ts` | `/api/notifications` | Push notifications, WebSocket token |
| `schedulers.ts` | `/api/schedulers` | Scheduler status, history, run-now |
| `pihole.ts` | `/api/pihole` | Pi-hole status, DNS queries, blocklists |
| `cloud-import.ts` | `/api/cloud` | Cloud import (rclone) operations |
| `cloud-export.ts` | `/api/cloud` | Cloud export operations |
| `users.ts` | `/api/users` | User CRUD, role management |
| `mobile.ts` | `/api/mobile` | Mobile device registration and management |
| `samba.ts` | `/api/samba` | Samba/SMB share configuration |
| `webdav.ts` | `/api/webdav` | WebDAV server management |
| `updates.ts` | `/api/updates` | Self-hosted update mechanism |
| `energy.ts` | `/api/energy` | Energy consumption statistics |
| `benchmark.ts` | `/api/benchmark` | Disk benchmark initiation and results |
| `setup.ts` | `/api/setup` | Setup wizard steps and state |
| `two-factor.ts` | `/api/totp` | TOTP two-factor authentication |
| `remote-servers.ts` | `/api/remote-servers` | Remote server profile management |
| `statusBar.ts` | `/api/system` | Status bar indicator data (catalog-driven) |
| `gpuPower.ts` | `/api/power` | GPU power monitoring and presence detection |
| `nfs.ts` | `/api/nfs` | NFS share management |
| `plugins-marketplace.ts` | `/api/plugins` | Plugin marketplace listing and install (external market) |
| `docs.ts` | `/api/docs` | User-manual index + article content (language-scoped); consumed by useDocsIndex/useDocsArticle |

## Adding a New API Module

1. Create `src/api/my-feature.ts`
2. Import `apiClient` from `../lib/api`
3. Define TypeScript interfaces for request/response types
4. Export async functions wrapping `apiClient` calls
5. Import in the component/hook that needs it
