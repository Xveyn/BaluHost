# BaluHost - Architecture Documentation

**Status:** ✅ DEPLOYED IN PRODUCTION (seit 25. Januar 2026)
**Version:** see `backend/pyproject.toml` (single source of truth) or the top of `CHANGELOG.md` — deliberately not repeated here, because the hand-maintained copy sat at 1.16.4 until July 2026 while the project was at 1.38.0 (#349)
**Last content change:** `git log -1 --format=%ad -- docs/ARCHITECTURE.md`
**Illustrated version:** [`architecture-overview.html`](architecture-overview.html) — the same structure as an interactive diagram (German). Open it in a browser.

## 📐 System Overview

BaluHost is a full-stack self-hosted home server platform, built around a NAS core (file storage, RAID) and extended with system monitoring, power & hardware control, networking, and a plugin marketplace. A React frontend talks to a FastAPI backend; hardware access is real in production and simulated in dev mode.

In production BaluHost is not one process. It is five systemd units that share no memory: everything more than one process needs to know lives in PostgreSQL or as a JSON file under `/dev/shm`.

### Runtime Topology

| Client | Entry point | Process (systemd unit) |
|---|---|---|
| Web UI (browser), BaluApp (Android), BaluDesk (desktop sync) | nginx `:443` — TLS, static SPA, rate limits, proxies `/api` to `127.0.0.1:8000` | `baluhost-backend` — FastAPI on Uvicorn, 4 workers, port 8000 |
| Desktop tray (KDE), TUI — both on the box itself | direct to port 8000, no nginx (the TUI's default server is `http://127.0.0.1:8000`) | `baluhost-backend` |
| Companion app (Tauri) — on the box itself | Unix socket `/run/baluhost/local.sock` (systemd socket unit) | `baluhost-backend-local` — the same FastAPI app, 2 workers, channel `local` |
| WebDAV clients (Explorer, Finder, …) | port `8080`, TLS, HTTP Basic | `baluhost-webdav` — WsgiDAV on cheroot |
| — (no network ingress) | — | `baluhost-monitoring` — telemetry, disk I/O, metric collectors, smart-device poller |
| — (no network ingress) | — | `baluhost-scheduler` — APScheduler jobs (backup, RAID scrub, SMART scan, …) |

Unit templates: `deploy/install/templates/`. Worker entry points: `backend/scripts/{monitoring,scheduler,webdav}_worker.py`.

**The primary worker.** Exactly one of the four `baluhost-backend` workers wins a file lock (`/tmp/baluhost-primary.lock`) at startup and becomes the *primary* (`core/lifespan.py`). Only the primary runs hardware loops — fan control, CPU power management, the sleep state machine, mDNS announcement — and plugin background tasks. The local channel never volunteers. Every other worker is a follower: it serves requests and WebSockets and hands hardware commands to the primary through a database queue.

**The local channel.** `baluhost-backend-local` exists so that an endpoint can require physical presence. `ChannelMarkerMiddleware` tags every request arriving over the Unix socket with `request.state.channel = "local"`; destructive admin endpoints check that tag (`require_local_admin`).

### How the Processes Talk

| Channel | Writer | Reader | Purpose |
|---|---|---|---|
| Postgres `LISTEN`/`NOTIFY` (`services/ws_bus.py`) | any process, including scheduler and monitoring | one listener connection per API process | WebSocket broadcasts. Only the process holding a socket can deliver to it, so every message goes over the bus to all of them. Not durable by design |
| JSON files in `/dev/shm/baluhost/` (`services/monitoring/shm.py`) | monitoring worker | API workers | Live metrics without a database round trip per request. Dev mode uses `/dev/shm/baluhost-dev/` |
| DB command queue `power_commands` / `gpu_power_commands` (`services/power/db_command_queue.py`) | follower workers | primary | Hardware commands. A row moves `pending → running → applied \| failed`, carries a deadline, and is claimed at most once |
| `scheduler_executions` rows | API (status `requested`) | scheduler worker (polls) | "Run now" from the UI, plus the execution history |
| Singleton state rows (`sleep_runtime_state`, `webdav_state`, `scheduler_state`) | the process that owns the state | everyone else | Heartbeats and state every worker must be able to answer, e.g. "is the system asleep" |
| Plugin enablement (`services/plugin_enablement.py`) | the worker that handled the toggle | all workers, 5 s TTL cache | A plugin toggle takes effect in every worker within seconds, no restart |

### Layers Inside the API Process

```
                 HTTPS · /api/... · Authorization: Bearer <JWT>
                                      │
┌─────────────────────────────────────▼──────────────────────────────────────┐
│  middleware/      security headers, channel marker, plugin gate,           │
│                   sleep auto-wake, device tracking, error counter, ...     │
├────────────────────────────────────────────────────────────────────────────┤
│  api/routes/      HTTP concerns only: auth dependency (api/deps.py),       │
│  api/deps.py      rate-limit decorator, request validation                 │
├────────────────────────────────────────────────────────────────────────────┤
│  schemas/         Pydantic request/response models                         │
├────────────────────────────────────────────────────────────────────────────┤
│  services/        business logic; hardware services pick a dev or a        │
│                   Linux backend at start                                   │
├────────────────────────────────────────────────────────────────────────────┤
│  models/          SQLAlchemy 2.0 ORM, migrated with Alembic                │
├────────────────────────────────────────────────────────────────────────────┤
│  plugins/         bundled plugins in-process, external plugins in a        │
│                   sandboxed subprocess                                     │
└───────────────┬───────────────────────┬───────────────────────┬────────────┘
                │                       │                       │
        PostgreSQL / SQLite      /dev/shm (JSON)      Linux: mdadm, smartctl,
                                                      hwmon/sysfs, systemd,
                                                      WireGuard, rclone
```

`core/` cuts across all layers: configuration from environment variables, the database engine, JWT handling, the rate limiter, exception classes with client-safe messages, and the lifespan that starts and stops background services.

The frontend mirrors this cut — one file per feature domain per layer:

```
pages/  →  hooks/ (TanStack Query)  →  api/ (one typed function per endpoint)  →  lib/api.ts (the one axios instance)
```

## 🏗️ Technology Stack

### Frontend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | React 18 | UI library |
| Language | TypeScript | Type-safe development |
| Build Tool | Vite | Dev server and production builds |
| Styling | Tailwind CSS | Utility-first CSS |
| Routing | React Router | Client-side navigation, lazy-loaded pages |
| Data fetching | TanStack Query v5 | Caching, polling, mutation invalidation; cache persisted to `sessionStorage` |
| HTTP Client | Axios | API communication (`lib/api.ts`) |
| Charts | Recharts | Data visualization |
| i18n | i18next / react-i18next | German and English |
| Icons | lucide-react | Icon set |
| Testing | Vitest, Playwright | Unit tests, E2E tests |
| Companion shell | Tauri 2 | Local desktop app over the Unix socket (`client/src-tauri/`) |

### Backend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI | Async Python web framework |
| Language | Python 3.11+ | Backend language with type hints |
| Validation | Pydantic v2, pydantic-settings | Request/response models, configuration |
| Server | Uvicorn | ASGI server |
| ORM / Migrations | SQLAlchemy 2.0, Alembic | Persistence |
| Database | PostgreSQL (prod), SQLite (dev) | Data, plus `LISTEN`/`NOTIFY` as broadcast bus |
| Auth | PyJWT, passlib/bcrypt, pyotp | JWT, password hashing, TOTP |
| Rate limiting | slowapi | Per-endpoint limits |
| Scheduling | APScheduler | Periodic jobs in the scheduler worker |
| Plugins | pluggy | Hook specifications |
| WebDAV | WsgiDAV, cheroot | Standalone WebDAV server |
| System | psutil, pySMART | Metrics, disk health |
| Push | firebase-admin | Mobile push notifications |
| TUI | Textual | Terminal UI |
| Testing | pytest | Unit and integration testing |

### Development
| Tool | Purpose |
|------|---------|
| `start_dev.py` | Starts backend (port 8000) and Vite (port 5173) in dev mode |
| Dev Mode | Sandbox with simulated RAID, SMART, fans, CPU power and sleep |
| Hot Reload | Vite HMR + Uvicorn `--reload` |
| Mock Data | Deterministic seed data for testing |

## 📦 Project Structure

File counts are deliberately not listed here: every hand-maintained count in this document had drifted (see #349). Use `ls` or the per-directory `CLAUDE.md` files.

```
baluhost/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point, middleware registration
│   │   ├── api/
│   │   │   ├── deps.py        # Auth dependencies, DB session
│   │   │   └── routes/        # One route module per feature domain
│   │   ├── services/          # Business logic (see "Service Domains")
│   │   │   ├── files/         # File operations, quota, shares, chunked upload
│   │   │   ├── hardware/      # RAID (mdadm), SMART
│   │   │   ├── power/         # CPU profiles, fan control, sleep, energy
│   │   │   ├── monitoring/    # Collectors, SHM, monitoring worker
│   │   │   ├── scheduler/     # Scheduler service and worker
│   │   │   ├── vpn/           # WireGuard, key encryption
│   │   │   ├── notifications/ # Firebase push, in-app events
│   │   │   ├── audit/         # Audit log, admin DB inspection
│   │   │   └── ...            # backup, sync, cloud, versioning, pihole, cache, update, setup
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── middleware/        # Security headers, channel marker, plugin gate, ...
│   │   ├── core/              # Config, database, security, lifespan, rate limiter
│   │   ├── compat/            # WSGI bridge for WebDAV
│   │   └── plugins/           # Plugin system (see plugins/README.md)
│   │       ├── manager.py     # Discovery, lifecycle, route mounting
│   │       ├── hooks.py       # Pluggy hook specs
│   │       ├── events.py      # Async event manager
│   │       ├── sandbox/       # Subprocess isolation for external plugins
│   │       ├── signing.py     # Marketplace index signature verification
│   │       ├── smart_device/  # Smart device framework
│   │       └── installed/     # Bundled plugins
│   ├── scripts/               # Worker entry points (monitoring, scheduler, webdav)
│   ├── baluhost_tui/          # Terminal UI (Textual)
│   ├── baluhost_tray/         # Desktop tray for KDE Plasma
│   ├── tests/                 # Pytest suite (size: Testing row in README.md)
│   ├── alembic/               # Database migrations
│   └── pyproject.toml         # Python dependencies, version
│
├── client/
│   ├── src/
│   │   ├── pages/             # Route-level pages
│   │   ├── components/        # Feature components, ui/ primitives
│   │   ├── hooks/             # Data hooks (TanStack Query) and UI hooks
│   │   ├── api/               # Typed API client modules
│   │   ├── contexts/          # Auth, version, plugin, notification, upload, theme
│   │   ├── i18n/              # Locale files (de, en)
│   │   ├── lib/               # api.ts, query client, feature flags, utilities
│   │   └── plugin-runtime/    # Bundle that boots inside a plugin's iframe
│   ├── src-tauri/             # Companion app (Rust shell + Unix-socket proxy)
│   └── tests/e2e/             # Playwright specs
│
├── deploy/
│   ├── install/templates/     # systemd units, sudoers templates
│   ├── nginx/                 # Reverse proxy configs
│   ├── scripts/               # ci-deploy.sh, installers
│   └── ...                    # samba, nfs, wsdd, avahi, ssl, update
│
├── docs/                      # Documentation
├── .github/workflows/         # CI/CD pipelines (see docs/CI.md)
└── start_dev.py               # Dev environment launcher
```

### Service Domains

| Domain | Modules under `services/` |
|---|---|
| Files & storage | `files/`, `versioning/`, `cache/`, `storage_breakdown`, `game_libraries/` |
| Drives | `hardware/raid/`, `hardware/smart/`, `benchmark/`, `disk_monitor` |
| Power & cooling | `power/` (manager, fan control, sleep, energy, scheduled reboot) |
| Network & shares | `vpn/`, `samba_service`, `nfs_service`, `webdav_service`, `network_discovery`, `pihole/` |
| Identity & security | `auth`, `token_service`, `totp_service`, `api_key_service`, `permissions`, `step_up`, `audit/` |
| Devices, sync & backup | `mobile`, `desktop_pairing`, `sync/`, `backup/`, `cloud/`, `balupi_handshake` |
| Observability & operations | `monitoring/`, `scheduler/`, `service_status`, `notifications/`, `status_bar/`, `update/`, `setup/` |
| Extension | `plugin_service`, `plugin_marketplace`, `plugin_enablement`, `plugin_storage_service`, `dashboard_panel_bridge` |

## 🔐 Authentication & Authorization

### Authentication Flow

```
┌──────┐                            ┌──────────┐
│Client│                            │ Backend  │
└──┬───┘                            └────┬─────┘
   │                                     │
   │ POST /api/auth/login                │
   │ { username, password }              │
   │────────────────────────────────────>│
   │                                     │
   │                  Validate credentials
   │                  (2FA step if enabled)
   │                  Issue access + refresh token
   │                                     │
   │        200 OK                       │
   │ { token, user: { id, role, ... } }  │
   │<────────────────────────────────────│
   │                                     │
   │ Store token in localStorage         │
   │                                     │
   │ GET /api/files/list                 │
   │ Authorization: Bearer <token>       │
   │────────────────────────────────────>│
   │                                     │
   │                      Validate token │
   │                      (type claim!)  │
   │                      Extract user   │
   │                      Check permissions
   │                                     │
   │        200 OK                       │
   │ { files: [...] }                    │
   │<────────────────────────────────────│
```

Every token carries a `type` claim and is only accepted where that type is expected (`core/security.py`), so a refresh token cannot be used as an access token. Besides `access` and `refresh` there are short-lived special-purpose types (`sse`, `ws`, `2fa_pending`, `setup`); TTLs are listed in `backend/app/core/CLAUDE.md`. The access-token lifetime is admin-configurable (default 15 minutes).

Two further credentials exist next to JWT: API keys (`balu_…` prefix, `services/api_key_service.py`) and, for WebDAV only, username and password over HTTP Basic.

### Authorization Model

**Roles:**
- `admin` - Full system access
- `user` - Limited to own files and shares

**Checks:**
- `Depends(deps.get_current_user)` / `Depends(deps.get_current_admin)` on every protected route
- `services/permissions.py`: `is_privileged(user)` and `ensure_owner_or_privileged()` for ownership
- `_jail_path()` (`api/routes/files.py`) confines a non-admin to their home directory, `Shared/` and paths shared with them
- Delegated power permissions (`can_launch_games`, `can_manage_bluetooth`, …) via `require_power_<action>`
- Some actions are additionally gated on the request coming from a private network, on the local channel, or on a fresh second factor (step-up). `.claude/rules/security-agent.md` lists them

## 💾 Data Models

ORM models live in `backend/app/models/`, grouped as: auth & users, files & storage, monitoring & metrics, power & hardware, networking, system services, versioning, plugins & integrations, desktop sync. `backend/app/models/CLAUDE.md` has the file-by-file list.

API shapes are Pydantic schemas in `backend/app/schemas/`. Two examples, as they are today:

```python
class FileItem(BaseModel):                  # schemas/files.py
    name: str
    path: str
    size: int
    type: Literal["file", "directory"]
    modified_at: datetime
    owner_id: str | None = None
    owner_name: str | None = None
    mime_type: str | None = None
    file_id: int | None = None
    checksum: str | None = None
    sync_info: list[SyncDeviceInfo] | None = None
    can_read: bool | None = None
    can_write: bool | None = None
    can_delete: bool | None = None

class RaidDevice(BaseModel):                # schemas/system.py
    name: str
    state: str
    disk_type: str = "hdd"                  # "hdd", "ssd", "nvme"

class RaidArray(BaseModel):
    name: str
    level: str
    size_bytes: int
    status: str
    devices: list[RaidDevice]
    resync_progress: float | None = None
    bitmap: str | None = None
    sync_action: str | None = None
```

## 🔄 Request Flow

### Example: File Upload

```
1. User drops file in FileManager
   └─> handleDrop() triggered

2. Frontend prepares FormData
   └─> POST /api/files/upload
       └─> Authorization: Bearer <token>
       └─> Content-Type: multipart/form-data

3. nginx
   ├─> TLS termination, rate limit
   └─> proxy to one of the four Uvicorn workers

4. Backend (FastAPI)
   ├─> Middleware chain
   ├─> Authentication (get_current_user)
   └─> files.upload_file() route handler

5. Service Layer (services/files/)
   ├─> Validate path (_jail_path)
   ├─> Check quota
   ├─> Check permissions (owner or admin)
   ├─> Save file to disk
   ├─> Update file metadata (owner)
   └─> Log audit event

6. Response to Frontend
   └─> 200 OK (FileUploadResponse)

7. Frontend updates UI
   ├─> Reload file list
   ├─> Show success toast
   └─> Update storage info
```

Large files use the resumable chunked upload instead (`api/routes/chunked_upload.py`, also under `/api/files`), with progress reported over Server-Sent Events.

## 🎯 Design Decisions

### Why FastAPI over Express?

| Aspect | FastAPI | Express |
|--------|---------|---------|
| Type Safety | Native with Pydantic | Requires TypeScript setup |
| Async Support | Built-in async/await | Requires middleware |
| Documentation | Auto-generated (Swagger/ReDoc) | Manual |
| Validation | Pydantic models | Manual or libraries |
| Performance | High (ASGI) | Good (but sync by default) |
| Python Integration | Native (psutil, system libs) | Requires child processes |

**Verdict:** FastAPI is better suited for system-level operations and provides better developer experience for a NAS backend.

### Why Separate Worker Processes?

Scheduled jobs (backup, RAID scrub) do heavy I/O, and metric collection runs every few seconds. Inside a web worker both would compete with request handling; with four web workers they would also run four times. So each concern that must run exactly once lives in its own unit (`baluhost-scheduler`, `baluhost-monitoring`) or in the elected primary worker (hardware control loops, which need services the worker processes do not have).

The cost is that state has to be shared explicitly — see "How the Processes Talk" above. A rule that follows from it: nothing a request depends on may live only in process memory, because the next request may land on a different worker.

### Database

**Current State:** SQLAlchemy 2.0 ORM with Alembic migrations

- **Dev:** SQLite (`backend/baluhost.db`), tables created at startup
- **Production:** PostgreSQL 17 (deployed since January 2026), schema changes through Alembic only
- Full persistence for users, file metadata, audit logs, monitoring, VPN, power, fans, scheduler, and more
- PostgreSQL also carries the WebSocket broadcast bus (`LISTEN`/`NOTIFY`) and the command queues

### Dev Mode Architecture

**Problem:** Developing NAS features on Windows without real RAID/hardware

**Solution:** Hardware services are written against a protocol and ship two implementations. `settings.is_dev_mode` (`NAS_MODE=dev`) selects one at start:

| Service | Dev mode | Production |
|---|---|---|
| RAID | `DevRaidBackend` (7 virtual disks) | `MdadmRaidBackend` (real mdadm) |
| SMART | mock data | `smartctl` |
| CPU power | `DevCpuPowerBackend` | cpufreq via sysfs |
| Fan control | `DevFanControlBackend` (3 virtual fans) | hwmon PWM |
| Sleep | `DevSleepBackend` (no-op suspend), no logind locks | `systemctl suspend`, logind sleep locks |
| Storage | `backend/dev-storage/`, recreated at start | RAID mount |
| SHM directory | `/dev/shm/baluhost-dev/` | `/dev/shm/baluhost/` |
| Database | SQLite | PostgreSQL |

**Benefits:**
- Cross-platform development (Windows, Linux, Mac)
- No root/admin privileges required
- Fast iteration without hardware
- A dev instance on the production box cannot touch production's RAID, sleep locks or SHM files

`start_dev.py` is the authoritative reference for what dev mode switches.

## 🚀 Performance Considerations

### Backend
- **Work off the request path:** scheduled jobs and metric collection run in their own processes
- **Live metrics from memory:** API workers read JSON files from `/dev/shm` instead of querying the database
- **Caching:** storage info cached for 30 seconds; plugin enablement cached 5 seconds per worker
- **Blocking calls in threads:** blocking work (subprocess, zeroconf, DB writes from middleware) is moved off the event loop
- **Telemetry:** 3 s interval in production, 2 s in dev; disk I/O sampled every second

### Frontend
- **Code splitting:** every page is lazy-loaded; the Pi build tree-shakes desktop-only pages via `__DEVICE_MODE__`
- **Query cache:** TanStack Query deduplicates requests across components and persists the cache to `sessionStorage`, so a reload paints immediately
- **Polling per query:** each data hook sets its own interval; mutations invalidate their domain

### Scalability Limits
**Current Design:**
- ✅ 1-10 users (typical home NAS)
- ✅ 10,000-100,000 files
- ✅ PostgreSQL database for all metadata
- ✅ WebSocket for real-time notifications, across all workers via the broadcast bus
- ✅ Chunked upload with progress tracking
- ⚠️ Rate limiter state is in process memory: per worker, reset on restart. Acceptable for a single box

**Future Improvements:**
- Redis for caching and shared rate-limit state
- Cluster support for multi-node setups

## 🔒 Security Architecture

The binding rules and the list of accepted risks are in `.claude/rules/security-agent.md`. Summary:

### Authentication
- JWT with HS256 signing and a mandatory `type` claim (access: admin-configurable, default 15 min; refresh: 7 days with JTI)
- Two-Factor Authentication (TOTP), recovery codes
- API keys for automation
- Token stored in localStorage (client-side, mitigated by CSP)

### Authorization
- Role-based access control (admin/user), delegated power permissions
- File ownership tracking with `_jail_path()` sandbox
- Permission checks via `ensure_owner_or_privileged()`
- Presence gates: local channel, private-network check, step-up for service-interrupting actions

### Input Validation
- Pydantic schemas validate all request bodies
- Path traversal prevention (`..` rejection, PurePosixPath normalization)
- subprocess with list arguments only (no `shell=True`)
- SQLAlchemy ORM-only queries (no raw SQL with user input)

### Network Security
- nginx terminates TLS on 443 and redirects port 80 (`deploy/nginx/baluhost-https.conf`)
- Security headers middleware (CSP, HSTS, X-Frame-Options)
- CORS scoped to configured origins
- Rate limiting in two places: nginx zones (`api_limit` 100 r/s, `auth_limit` 5 r/min) and slowapi per endpoint. There is no app-level default limit — an undecorated route is limited by nginx only
- WireGuard VPN for remote access

### Untrusted Code
- External plugins run in a sandboxed subprocess with default-deny capability scopes
- The marketplace index is verified against a detached ed25519 signature before it is parsed; fail-closed, no unsigned fallback
- Plugin frontends run in a sandboxed iframe and reach the host only via `postMessage`

### Implemented Security Features
- [x] Token refresh mechanism (7-day refresh tokens with JTI)
- [x] Rate limiting (nginx + slowapi per endpoint)
- [x] Security headers middleware (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [x] Password hashing with bcrypt (passlib)
- [x] Two-Factor Authentication (TOTP)
- [x] Audit logging for security-relevant actions
- [x] Encrypted VPN/SSH keys (Fernet)
- [x] HTTPS via nginx (TLS on 443, port 80 redirects)
- [x] Plugin sandbox and signed marketplace index

## 🧪 Testing Strategy

### Test Pyramid

```
          ┌────────────┐
          │   E2E      │  Playwright (client/tests/e2e)
          │   Tests    │
          └────────────┘
        ┌──────────────┐
        │ Integration  │  API endpoint tests (pytest)
        │   Tests      │
        └──────────────┘
    ┌──────────────────┐
    │   Unit Tests     │  Service tests (pytest), component tests (Vitest)
    │                  │
    └──────────────────┘
```

### Test Coverage
- Suite size: see the Testing row in `README.md`, kept current by `scripts/generate_readme_stats.py`. Not restated here — this line claimed "82 test files, 1465 test functions" long after the suite had grown past four times that (#349)
- Backend: CI enforces a coverage floor of 65% on `app/` (`--cov-fail-under` in `ci-check.yml`)
- Frontend: Vitest unit tests; Playwright E2E against a mocked backend (`playwright-e2e.yml`)
- RAID: real mdadm against loop devices on a GitHub-hosted runner (`raid-mdadm-loopback.yml`), never on self-hosted hardware

### Test Fixtures
- Dev mode provides reproducible state
- Seed data creates consistent test data
- Mock services for external dependencies
- The suite refuses to take real logind sleep locks and uses its own SHM directory

## 🔮 Future Architecture

### Potential Improvements
- **Redis caching** — Session storage, API response cache, job queues
- **Cluster support** — Multi-node setups for high availability
- **LDAP/AD integration** — Enterprise user management
- **S3-compatible API** — External tool compatibility
- **Media service** — Transcoding, thumbnails, DLNA

## 📊 Monitoring & Observability

### Production Monitoring
Built in, no external stack: the monitoring worker below writes the time series,
the web UI shows them, and alerts go out as push/in-app notifications. The
Prometheus endpoint (`/api/metrics`) and the Compose/Grafana/alert-rule stack
that once came with it were removed as unused (stack 2026-03, endpoint #494).
- **Structured JSON logging** for log aggregation
- **Per-thread CPU monitoring** (Task Manager-style)

### Monitoring Orchestrator
The orchestrator runs in the `baluhost-monitoring` process, not in the web workers. It uses a collector pattern and has two outputs: SHM for live values, the database for history.
```
┌────────────────────────────────────────────────────────────┐
│        Monitoring Orchestrator (baluhost-monitoring)       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Collectors                                          │  │
│  │  ├─ CpuMetricCollector     (usage, freq, temp)       │  │
│  │  ├─ MemoryMetricCollector  (RAM, swap, available)    │  │
│  │  ├─ NetworkMetricCollector (throughput)              │  │
│  │  ├─ DiskIoMetricCollector  (IOPS, throughput)        │  │
│  │  ├─ GpuMetricCollector     (GPU metrics)             │  │
│  │  ├─ UptimeCollector        (uptime tracking)         │  │
│  │  └─ process tracker        (BaluHost processes)      │  │
│  └──────────────────────────────────────────────────────┘  │
│              ↓                              ↓              │
│  ┌──────────────────────────┐  ┌────────────────────────┐  │
│  │  /dev/shm/baluhost/      │  │  Database              │  │
│  │  JSON per metric, read   │  │  *_samples tables with │  │
│  │  by the API workers      │  │  retention policies    │  │
│  └──────────────────────────┘  └────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Power & Hardware Monitoring
- **Power Management**: CPU frequency scaling (AMD Ryzen & Intel)
- **Fan Control**: PWM control with temperature curves
- **Smart Device Monitoring**: Plugin-based IoT integration (e.g., Tapo P110/P115 via plugin)
- **Service Status**: Health dashboard for all services

### Scheduler Architecture

All periodic jobs are owned by the `baluhost-scheduler` process. The web API never runs a job itself.

```
┌────────────────────────────────────────────────────────────┐
│            Scheduler Worker (baluhost-scheduler)           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Registry (schemas/scheduler.py: SCHEDULER_REGISTRY) │  │
│  │  ├─ raid_scrub            (RAID integrity, weekly)   │  │
│  │  ├─ smart_scan            (disk health, hourly)      │  │
│  │  ├─ backup                (auto backup, daily)       │  │
│  │  ├─ sync_check            (sync triggers, 5 min)     │  │
│  │  ├─ notification_check    (device warnings, hourly)  │  │
│  │  ├─ upload_cleanup        (chunked uploads, daily)   │  │
│  │  ├─ auto_update           (update check, daily)      │  │
│  │  ├─ cloud_sync            (cloud providers, hourly)  │  │
│  │  ├─ file_activity_cleanup (old activity, daily)      │  │
│  │  ├─ plugin_update_check   (marketplace, 6 h)         │  │
│  │  └─ system_reboot         (weekly, see note)         │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Execution Flow                                      │  │
│  │  1. APScheduler triggers a job at its interval, or   │  │
│  │     the API inserts a row with status "requested"    │  │
│  │     and the worker picks it up                       │  │
│  │  2. A SchedulerExecution row tracks the run          │  │
│  │  3. Result or error is written to the database       │  │
│  │  4. Failures raise a notification                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Database Tables                                     │  │
│  │  - scheduler_executions (history, timing, errors)    │  │
│  │  - scheduler_configs (intervals, enabled state)      │  │
│  │  - scheduler_state (worker heartbeat)                │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

**Note on `system_reboot`:** it appears in the registry so that its schedule and history show up in the scheduler UI, but it is not an APScheduler job. The reboot is executed by the primary worker in the power layer (`services/power/scheduled_reboot.py`), because its gates need the sleep manager, which the scheduler process does not have. It is off by default.

**Key Features:**
- **Run-Now**: Trigger a scheduler immediately via API/UI
- **Per-scheduler config**: interval and enabled state in `scheduler_configs`
- **History**: execution log per scheduler (`SchedulerDashboard.tsx`)
- **Service Integration**: RAID scrub and SMART scan update service status

### Metrics Categories
| Category | Metrics | Endpoint |
|----------|---------|----------|
| System | CPU, memory, disk, network | `/api/monitoring/*` |
| RAID | Array status, sync progress | `/api/system/raid/status` |
| SMART | Disk health, temperature | `/api/system/smart/status` |
| Power | CPU frequency, consumption | `/api/power/status` |
| Fans | RPM, PWM, temperature | `/api/fans/status` |
| Energy | Watts, kWh, cost | `/api/energy/status` |

## 🎓 Learning Path for Contributors

### Prerequisites
1. Python basics (functions, classes, async/await)
2. TypeScript/JavaScript (ES6+, promises, async/await)
3. React fundamentals (components, hooks, state)
4. REST API concepts

### Understanding BaluHost
1. Read `README.md` - Project overview
2. Run `python start_dev.py` - See it in action
3. Open `docs/architecture-overview.html` - The runtime picture
4. Read this file - Architecture overview
5. Read `TECHNICAL_DOCUMENTATION.md` - Feature details
6. Read `CONTRIBUTING.md` - Development guidelines

### Code Exploration Path
1. Start with `backend/app/main.py` - App entry point
2. Follow a route: `api/routes/files.py` → `services/files/operations.py`
3. Understand data flow: Request → Middleware → Route → Service → Model → Response
4. Check schemas: `schemas/files.py` - API shapes
5. Read tests: `backend/tests/files/` - How features work
6. Read the `CLAUDE.md` in the directory you are about to change - conventions and pitfalls

### First Contribution Ideas
- Fix a typo in documentation
- Add a test for existing functionality
- Implement a small feature from the [issue tracker](https://github.com/Xveyn/BaluHost/issues)
- Improve error messages
- Add code comments

## 📞 Questions?

If you have questions about the architecture:
1. Check existing documentation
2. Open a GitHub Discussion
3. Join our community (TODO: Discord/Matrix)

---

## 🔌 Plugin System Architecture

### Overview

BaluHost uses a modular plugin architecture for extensibility. Plugins can provide API routes, background tasks, event handlers, dashboard panels, status pills, menu actions, and frontend UI — all managed through a central `PluginManager`.

```
┌────────────────────────────────────────────────────────────┐
│                      Plugin Manager                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Discovery → Loading → Permission Check → Activation │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐    │
│  │ Pluggy Hooks │ │ Async Events │ │ Background Tasks │    │
│  │ (hooks.py)   │ │ (Queue-based)│ │ (primary only)   │    │
│  └──────────────┘ └──────────────┘ └──────────────────┘    │
│                            ↓                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Route Mounting: /api/plugins/{name}/...             │  │
│  │  Dashboard Panels, Status Pills, Menu Actions        │  │
│  │  Frontend UI: nav items, sandboxed iframe            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Two Trust Tiers

| | Bundled | External |
|---|---|---|
| Origin | `plugins/installed/`, maintained in this repo | Marketplace, installed under `/var/lib/baluhost/plugins` |
| Runs | as Python inside the host process | as a subprocess under the unprivileged `baluhost-plugin` user, in its own network namespace (loopback only) |
| Rights | `required_permissions`, granted by the admin when enabling | capability scopes, default-deny; the admin grants a subset when enabling |
| Host access | full host API | UDS-RPC only — no host import, no database, no filesystem, no shell |

The same split exists in the browser: the host app (`lib/plugin-sandbox/`) renders an external plugin's UI in a sandboxed iframe, where `client/src/plugin-runtime/` boots it. The iframe reaches API, toasts, storage and navigation only through `postMessage` RPC.

**Marketplace trust.** The marketplace `index.json` is where foreign code enters the system. `MarketplaceService.get_index()` verifies a detached ed25519 signature over the exact bytes it then parses. A missing key, a missing signature or a bad signature rejects the index; there is no unsigned fallback. Details: `docs/superpowers/specs/2026-06-28-plugin-marketplace-index-signing-design.md`.

**Enablement across workers.** Which plugins are enabled is stored in the database. Each worker reconciles itself against it (`services/plugin_enablement.py`), so a toggle reaches all workers within seconds. One exception: a bundled plugin that ships its own router is mounted at startup and needs a backend restart before its endpoints exist.

### Two Event Systems

| | Pluggy Hooks | Async Events |
|---|---|---|
| Execution | Synchronous | Async, queue-based |
| Subscriber | `@hookimpl` method | Any async function |
| Use case | System events with fixed contract | Loose coupling, plugin-to-plugin |

### Smart Device Framework

For IoT devices, a specialized `SmartDevicePlugin` base class extends `PluginBase` with:
- **Capability protocols**: Switch, PowerMonitor, Sensor, Dimmer, ColorControl
- **Unified API**: All devices share `/api/smart-devices/` endpoints
- **SHM-based polling**: `SmartDevicePoller` runs in the monitoring worker process, writes state to shared memory files consumed by the web workers
- **Encrypted config**: Device credentials stored with Fernet encryption

### Permission System

Bundled plugins declare required permissions (15 available, 5 marked as dangerous). Dangerous permissions (`file:write`, `file:delete`, `system:execute`, `db:write`, `user:write`) require explicit admin approval when enabling a plugin. External plugins use capability scopes instead (`plugins/scope_catalog.py`).

### Bundled Plugins

| Plugin | What it does |
|--------|-------------|
| `audio_control` | Volume, output device and per-app mixer of the desktop session (pactl) |
| `bluetooth` | BlueZ over D-Bus: devices, scan, pairing with its own agent |
| `display_output` | Output selection and video mode (kscreen-doctor), brightness (powerdevil) |
| `optical_drive` | CD/DVD burning, reading, ISO browsing |
| `steam_gaming` | Status pill, session ledger, Gaming-Mode menu action, game launch |
| `tapo_smart_plug` | TP-Link Tapo smart plugs via the SmartDevice framework |
| `storage_analytics` | Demo only — every number is hard-coded |

Each bundled plugin has its own `CLAUDE.md`. For the framework see [`backend/app/plugins/README.md`](../backend/app/plugins/README.md).

---

## 🏭 Production Deployment Architecture

### Current Production Setup (ACTIVE)
```
┌─────────────────────────────────────────────────────────────┐
│                    nginx Reverse Proxy                      │
│              (443 TLS/HTTP2, 80 redirects to 443)           │
│  - Rate limiting (api_limit 100 r/s, auth_limit 5 r/min)    │
│  - Static file serving (/opt/baluhost/client/dist)          │
│  - Proxies /api, /docs and the WebSocket to 127.0.0.1:8000  │
└───────────────────────┬─────────────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
┌─────────▼─────────┐   ┌─────────────▼─────────────┐
│  Static Files     │   │  baluhost-backend         │
│  (Vite build)     │   │  4 Uvicorn workers, :8000 │
└───────────────────┘   └─────────────┬─────────────┘
                                      │
  baluhost-backend-local ─────────────┤
  baluhost-monitoring ────────────────┤
  baluhost-scheduler ─────────────────┤
  baluhost-webdav (:8080) ────────────┤
                        ┌─────────────▼─────────────┐
                        │   PostgreSQL 17           │
                        │   localhost:5432          │
                        └───────────────────────────┘
```

### Systemd Units
| Unit | Role |
|---|---|
| `baluhost-backend.service` | FastAPI, 4 Uvicorn workers, port 8000, `--proxy-headers` |
| `baluhost-backend-local.service` + `.socket` | Same app on `/run/baluhost/local.sock`, 2 workers, channel `local` |
| `baluhost-monitoring.service` | Monitoring worker |
| `baluhost-scheduler.service` | Scheduler worker |
| `baluhost-webdav.service` | WebDAV server, port 8080 |
| `baluhost-tray.service` | Desktop tray — a systemd *user* unit, set up separately |

All five system units restart on failure. `POST /api/system/restart-all` restarts them together (admin, local network, step-up).

### Delivery
A merge to `main` triggers `deploy-production.yml` on the self-hosted `prod` runner, behind the `production` environment approval. `deploy/scripts/ci-deploy.sh` updates `/opt/baluhost`, renders the unit files, restarts the services, runs a health check and rolls back on failure; a pre-release tag is created only after a successful deploy. Pull-request code never runs on the prod runner. Trust model: `.claude/rules/ci-cd-security.md`; overview: `docs/CI.md`.

### Environment
- **Server**: Debian 13, Ryzen 5 5600GT, 16GB RAM, 250GB NVMe
- **Database**: PostgreSQL 17 with connection pooling
- **Configuration**: `.env.production`
- **Logging**: Structured JSON (python-json-logger) to the journal

---

**Maintainer:** Xveyn
**Version & last change:** see the header of this document
**Status:** ✅ DEPLOYED IN PRODUCTION
