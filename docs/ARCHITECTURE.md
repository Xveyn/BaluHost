# BaluHost - Architecture Documentation

**Version:** 1.16.0
**Last Updated:** 15. März 2026
**Status:** ✅ DEPLOYED IN PRODUCTION (seit 25. Januar 2026)

## 📐 System Overview

BaluHost is a modern, full-stack NAS management application designed for self-hosted file storage and system monitoring. The architecture follows a clear separation of concerns with a React frontend, FastAPI backend, and simulated/real hardware integration.

```
┌─────────────────────────────────────────────────────────────┐
│                         Client Layer                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  React 18 + TypeScript + Vite + Tailwind CSS       │   │
│  │  - Dashboard                                        │   │
│  │  - File Manager (with Drag & Drop, Preview)       │   │
│  │  - User Management                                  │   │
│  │  - RAID Management                                  │   │
│  │  - System Monitor                                   │   │
│  │  - Audit Logging                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↕ HTTP/REST API                   │
└─────────────────────────────────────────────────────────────┘
                               ↕
┌─────────────────────────────────────────────────────────────┐
│                      Backend Layer (FastAPI)                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  API Routes (JWT Auth, CORS, Error Handling)       │   │
│  │  ├─ /auth      - Authentication                     │   │
│  │  ├─ /files     - File Operations                    │   │
│  │  ├─ /users     - User Management                    │   │
│  │  ├─ /system    - System Info & Monitoring           │   │
│  │  └─ /logging   - Audit Logs                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↕                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Service Layer (Business Logic)                     │   │
│  │  ├─ Auth Service        (JWT, Roles)               │   │
│  │  ├─ File Service        (CRUD, Quota, Ownership)   │   │
│  │  ├─ User Service        (User Management)          │   │
│  │  ├─ RAID Service        (Status, Management)       │   │
│  │  ├─ SMART Service       (Disk Health)              │   │
│  │  ├─ Telemetry Service   (System Metrics)           │   │
│  │  ├─ Audit Logger        (Activity Tracking)        │   │
│  │  ├─ Permissions Service (Access Control)           │   │
│  │  ├─ Power Manager       (CPU Frequency Scaling)    │   │
│  │  ├─ Fan Control         (PWM, Temperature Curves)  │   │
│  │  ├─ Monitoring Orch.    (Unified Collectors)       │   │
│  │  ├─ Service Status      (Health Monitoring)        │   │
│  │  ├─ Admin DB            (Database Inspection)      │   │
│  │  ├─ Energy Stats        (Tapo Integration)         │   │
│  │  └─ Network Discovery   (mDNS/Bonjour)             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                               ↕
┌─────────────────────────────────────────────────────────────┐
│                    Storage & System Layer                    │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  File System     │  │  RAID Arrays │  │  System APIs │ │
│  │  (dev-storage/)  │  │  (mdadm)     │  │  (psutil)    │ │
│  └──────────────────┘  └──────────────┘  └──────────────┘ │
│           Dev Mode: Simulated    │    Prod Mode: Real       │
└─────────────────────────────────────────────────────────────┘
```

## 🏗️ Technology Stack

### Frontend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | React 18 | UI library with hooks and concurrent features |
| Language | TypeScript | Type-safe development |
| Build Tool | Vite | Fast dev server and optimized builds |
| Styling | Tailwind CSS | Utility-first CSS framework |
| Routing | React Router | Client-side navigation |
| Charts | Recharts | Data visualization |
| HTTP Client | Axios | API communication |

### Backend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI | Modern, async Python web framework |
| Language | Python 3.11+ | Backend language with type hints |
| Validation | Pydantic | Data validation and serialization |
| Server | Uvicorn | ASGI server for FastAPI |
| Auth | JWT | Token-based authentication |
| System Monitoring | psutil | Cross-platform system utilities |
| Testing | pytest | Unit and integration testing |

### Development
| Tool | Purpose |
|------|---------|
| `start_dev.py` | Orchestrates backend and frontend in dev mode |
| Dev Mode | Sandbox with 2x5GB RAID1 simulation |
| Hot Reload | Vite HMR + Uvicorn --reload |
| Mock Data | Deterministic seed data for testing |

## 📦 Project Structure

```
baluhost/
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── api/               # API Layer
│   │   │   ├── deps.py        # Dependencies (auth, DB session)
│   │   │   └── routes/        # 51 API route modules
│   │   ├── services/          # 143 service modules (business logic)
│   │   │   ├── files/         # File operations, quota, multi-mountpoint
│   │   │   ├── hardware/      # RAID (mdadm), SMART monitoring
│   │   │   ├── power/         # CPU frequency, fan control, energy
│   │   │   ├── vpn/           # WireGuard VPN, encryption
│   │   │   ├── monitoring/    # Unified monitoring with collectors
│   │   │   ├── scheduler/     # Scheduler management
│   │   │   ├── notifications/ # Firebase push notifications
│   │   │   ├── backup/        # Backup/restore
│   │   │   ├── sync/          # Desktop sync coordination
│   │   │   ├── audit/         # Audit logging, admin DB
│   │   │   └── ...            # Cloud, versioning, pihole, cache, etc.
│   │   ├── models/            # 42 SQLAlchemy ORM models
│   │   ├── schemas/           # 41 Pydantic schemas
│   │   ├── core/              # Config, security, database, rate limiter
│   │   └── middleware/        # Security headers, rate limiting, device tracking
│   ├── baluhost_tui/          # Terminal UI (Textual)
│   ├── tests/                 # 82 test files, 1465 test functions
│   ├── alembic/               # 74 database migrations
│   └── pyproject.toml         # Python dependencies
│
├── client/                    # React + TypeScript + Vite
│   └── src/
│       ├── pages/             # 31 page components
│       ├── components/        # 29 component directories
│       ├── api/               # 38 typed API client modules
│       ├── hooks/             # 25 custom React hooks
│       ├── contexts/          # Auth & theme contexts
│       └── lib/api.ts         # Base API client (Axios)
│
├── deploy/                    # Deployment configs
│   ├── nginx/                 # Reverse proxy configs
│   ├── systemd/               # Service files
│   └── ...                    # Samba, Prometheus, Grafana
│
├── docs/                      # Documentation
├── .github/workflows/         # 7 CI/CD pipelines
└── start_dev.py               # Dev environment orchestrator
```

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
   │                  Generate JWT token │
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
   │                      Extract user   │
   │                      Check permissions
   │                                     │
   │        200 OK                       │
   │ { files: [...] }                    │
   │<────────────────────────────────────│
```

### Authorization Model

**Roles:**
- `admin` - Full system access
- `user` - Limited to own files

**Permission Checks:**
```python
def can_access_file(user: User, file: FileItem) -> bool:
    """Check if user can access a file."""
    return user.role == "admin" or file.owner_id == user.id
```

**Protected Routes:**
- JWT token required in `Authorization: Bearer <token>` header
- User context populated via `get_current_user` dependency
- Role checks in route handlers or service layer

## 💾 Data Models

### User Model
```python
class User:
    id: int
    username: str
    email: str
    role: Literal["admin", "user"]
    created_at: datetime
```

### File Item Model
```python
class FileItem:
    name: str           # File/folder name
    path: str           # Relative path
    is_directory: bool  # True if folder
    size: int           # Size in bytes (0 for folders)
    modified: str       # ISO timestamp
    owner_id: int       # User ID of owner
```

### RAID Array Model
```python
class RaidArray:
    name: str           # e.g., "md0"
    level: str          # e.g., "raid1"
    state: str          # healthy, degraded, rebuilding
    size_gb: int        # Total capacity
    devices: List[RaidDevice]
    
class RaidDevice:
    name: str           # e.g., "sda1"
    state: str          # active, spare, failed
```

### Telemetry Snapshot
```python
class TelemetrySnapshot:
    timestamp: str
    cpu_percent: float
    memory_percent: float
    disk_read_mbps: float
    disk_write_mbps: float
    network_down_mbps: float
    network_up_mbps: float
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
       
3. Backend (FastAPI)
   ├─> CORS middleware
   ├─> Authentication (get_current_user)
   └─> files.upload_file() route handler
   
4. Service Layer (files.py)
   ├─> Validate path (sandbox check)
   ├─> Check quota (get_storage_info)
   ├─> Check permissions (owner or admin)
   ├─> Save file to disk
   ├─> Update file metadata (owner_id)
   └─> Log audit event
   
5. Response to Frontend
   └─> 200 OK { message, file: FileItem }
   
6. Frontend updates UI
   ├─> Reload file list
   ├─> Show success toast
   └─> Update storage info
```

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

### Database

**Current State:** SQLAlchemy 2.0 ORM with Alembic migrations

- **Dev:** SQLite (`backend/baluhost.db`)
- **Production:** PostgreSQL 17.7 (deployed since January 2026)
- 42 ORM models, 74 migrations
- Full persistence for users, file metadata, audit logs, monitoring, VPN, power, fans, scheduler, and more

### Dev Mode Architecture

**Problem:** Developing NAS features on Windows without real RAID/hardware

**Solution:** Comprehensive simulation layer
- `DevRaidBackend` simulates mdadm operations
- Mock SMART data for virtual disks
- Sandbox storage (2x5GB) with quota enforcement
- Deterministic seed data for reproducibility

**Benefits:**
- Cross-platform development (Windows, Linux, Mac)
- No root/admin privileges required
- Fast iteration without hardware
- Easy onboarding for contributors

**Production Fallback:**
- `MdadmRaidBackend` for real Linux RAID arrays
- Real SMART data via `smartctl`
- System-wide file access

## 🚀 Performance Considerations

### Backend Optimization
- **Async I/O:** All file operations use async
- **Background Jobs:** Telemetry collection runs independently
- **Caching:** Storage info cached for 30 seconds
- **Lazy Loading:** Files loaded on-demand

### Frontend Optimization
- **Code Splitting:** Vite automatically splits chunks
- **Lazy Imports:** Routes loaded dynamically
- **Memoization:** React hooks optimize re-renders
- **Debouncing:** Search/filter inputs debounced

### Scalability Limits
**Current Design:**
- ✅ 1-10 users (typical home NAS)
- ✅ 10,000-100,000 files
- ✅ PostgreSQL database for all metadata
- ✅ WebSocket for real-time notifications
- ✅ Chunked upload with progress tracking (32MB chunks)

**Future Improvements:**
- Redis for caching
- Upload queue for concurrent uploads
- Cluster support for multi-node setups

## 🔒 Security Architecture

### Authentication
- JWT tokens with HS256 signing (access: 15min, refresh: 7 days)
- Two-Factor Authentication (TOTP) support
- Token stored in localStorage (client-side, mitigated by CSP)

### Authorization
- Role-based access control (admin/user)
- File ownership tracking with `_jail_path()` sandbox
- Permission checks via `ensure_owner_or_privileged()`

### Input Validation
- Pydantic schemas validate all request bodies
- Path traversal prevention (`..` rejection, PurePosixPath normalization)
- subprocess with list arguments only (no `shell=True`)
- SQLAlchemy ORM-only queries (no raw SQL with user input)

### Network Security
- Security headers middleware (CSP, HSTS, X-Frame-Options)
- CORS scoped to configured origins
- Rate limiting via slowapi (per-endpoint limits)
- WireGuard VPN for encrypted remote access

### Implemented Security Features
- [x] Token refresh mechanism (7-day refresh tokens with JTI)
- [x] Rate limiting (slowapi with per-endpoint limits)
- [x] Security headers middleware (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [x] Password hashing with bcrypt (passlib)
- [x] Two-Factor Authentication (TOTP)
- [x] Audit logging for all security-relevant actions
- [x] Encrypted VPN/SSH keys (Fernet AES)
- [ ] HTTPS (external access via WireGuard VPN, HTTP on trusted LAN)

## 🧪 Testing Strategy

### Test Pyramid

```
          ┌────────────┐
          │   E2E      │  Manual testing (TODO: Playwright)
          │   Tests    │
          └────────────┘
        ┌──────────────┐
        │ Integration  │  API endpoint tests (pytest)
        │   Tests      │
        └──────────────┘
    ┌──────────────────┐
    │   Unit Tests     │  Service layer tests (pytest)
    │                  │
    └──────────────────┘
```

### Test Coverage
- 82 test files, 1465 test functions
- Services: Comprehensive coverage
- API routes: Integration tests
- Frontend: Vitest unit tests configured

### Test Fixtures
- Dev mode provides reproducible state
- Seed data creates consistent test data
- Mock services for external dependencies

## 🔮 Future Architecture

### Potential Improvements
- **Redis caching** — Session storage, API response cache, job queues
- **Cluster support** — Multi-node setups for high availability
- **LDAP/AD integration** — Enterprise user management
- **S3-compatible API** — External tool compatibility
- **Media service** — Transcoding, thumbnails, DLNA

## 📊 Monitoring & Observability

### Production Monitoring Stack (ACTIVE)
- **Prometheus metrics endpoint** (`/api/metrics`) with 40+ custom metrics
- **Grafana dashboards** for system visualization
- **20+ alert rules** across 6 severity groups
- **Structured JSON logging** for log aggregation
- **Per-thread CPU monitoring** (Task Manager-style)

### Monitoring Orchestrator
The unified monitoring system uses a collector pattern:
```
┌─────────────────────────────────────────────────────────────┐
│                  Monitoring Orchestrator                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Collectors                                           │  │
│  │  ├─ CPUCollector      (usage, freq, temp, threads)   │  │
│  │  ├─ MemoryCollector   (RAM, swap, available)         │  │
│  │  ├─ NetworkCollector  (throughput, packets)          │  │
│  │  ├─ DiskIOCollector   (IOPS, throughput)             │  │
│  │  └─ ProcessCollector  (BaluHost process tracking)    │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Database Persistence (with retention policies)       │  │
│  │  - cpu_samples, memory_samples, network_samples       │  │
│  │  - disk_io_samples, process_samples                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Power & Hardware Monitoring
- **Power Management**: CPU frequency scaling (AMD Ryzen & Intel)
- **Fan Control**: PWM control with temperature curves
- **Energy Monitoring**: Tapo smart plug integration (P115/P110)
- **Service Status**: Health dashboard for all services

### Scheduler Architecture

The Scheduler Service provides unified management for all background jobs with execution tracking:

```
┌─────────────────────────────────────────────────────────────┐
│                    Scheduler Service                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Managed Schedulers (6)                               │  │
│  │  ├─ raid_scrub       (RAID integrity, weekly)        │  │
│  │  ├─ smart_scan       (Disk health, hourly)           │  │
│  │  ├─ backup           (Auto backup, daily)            │  │
│  │  ├─ sync_check       (Sync triggers, 5 min)          │  │
│  │  ├─ notification_check (Device warnings, hourly)     │  │
│  │  └─ upload_cleanup   (Chunked uploads, daily)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Execution Flow                                       │  │
│  │  1. APScheduler triggers job at interval              │  │
│  │  2. SchedulerService creates SchedulerExecution       │  │
│  │  3. Job runs with status tracking (running→complete)  │  │
│  │  4. Result/error logged to database                   │  │
│  │  5. Service status integration (RAID/SMART)           │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Database Tables                                      │  │
│  │  - scheduler_executions (history, timing, errors)    │  │
│  │  - scheduler_configs (intervals, enabled state)       │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Frontend Dashboard (SchedulerDashboard.tsx)         │  │
│  │  - Overview tab: Status cards for all schedulers      │  │
│  │  - Table tab: Run-now, toggle enable/disable          │  │
│  │  - History tab: Per-scheduler execution logs          │  │
│  │  - Timeline tab: Visual execution timeline            │  │
│  │  - Settings tab: Interval configuration               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Run-Now**: Trigger any scheduler immediately via API/UI
- **Retry Mechanism**: Re-run failed executions
- **Timeline View**: Visual history across all schedulers
- **Service Integration**: RAID scrub and SMART scan update service status

### Metrics Categories
| Category | Metrics | Endpoint |
|----------|---------|----------|
| System | CPU, memory, disk, network | `/api/metrics` |
| RAID | Array status, sync progress | `/api/system/raid/status` |
| SMART | Disk health, temperature | `/api/system/smart/status` |
| Application | HTTP requests, DB connections | `/api/metrics` |
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
3. Read `TECHNICAL_DOCUMENTATION.md` - Feature details
4. Read this file - Architecture overview
5. Read `CONTRIBUTING.md` - Development guidelines

### Code Exploration Path
1. Start with `backend/app/main.py` - App entry point
2. Follow a route: `api/routes/files.py` → `services/files.py`
3. Understand data flow: Request → Route → Service → Response
4. Check schemas: `schemas/files.py` - Data models
5. Read tests: `tests/test_permissions.py` - How features work

### First Contribution Ideas
- Fix a typo in documentation
- Add a test for existing functionality
- Implement a small feature from TODO.md
- Improve error messages
- Add code comments

## 📞 Questions?

If you have questions about the architecture:
1. Check existing documentation
2. Open a GitHub Discussion
3. Join our community (TODO: Discord/Matrix)

---

## 🔌 Production Deployment Architecture

### Current Production Setup (ACTIVE)
```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx Reverse Proxy                       │
│                    (Port 80, HTTP)                           │
│  - Rate limiting (100 req/s API, 10 req/s auth)             │
│  - Security headers (CSP, X-Frame-Options, HSTS)            │
│  - Static file serving (/var/www/baluhost/)                 │
│  - WebSocket/SSE support                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
┌─────────▼─────────┐   ┌─────────────▼─────────────┐
│  Static Files     │   │    FastAPI Backend        │
│  (Vite Build)     │   │    (4 Uvicorn Workers)    │
│  /var/www/baluhost│   │    systemd managed        │
└───────────────────┘   └─────────────┬─────────────┘
                                      │
                        ┌─────────────▼─────────────┐
                        │   PostgreSQL 17.7         │
                        │   (Production Database)   │
                        └───────────────────────────┘
```

### Systemd Services
- `baluhost-backend.service` - 4 Uvicorn workers, port 8000
- Auto-restart on failure
- Graceful shutdown handling

### Environment
- **Server**: Debian 13, Ryzen 5 5600GT, 16GB RAM, 250GB NVMe
- **Database**: PostgreSQL 17.7 with connection pooling
- **Logging**: Structured JSON (python-json-logger)

---

**Last Updated:** 15. März 2026
**Version:** 1.16.0
**Maintainer:** Xveyn
**Status:** ✅ DEPLOYED IN PRODUCTION
