# BaluHost - Architecture Documentation

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
│  │  └─ Permissions Service (Access Control)           │   │
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
| HTTP Client | fetch API | API communication |

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
│   │   ├── __init__.py        # Version info
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── api/               # API Layer
│   │   │   ├── deps.py        # Dependencies (auth, user context)
│   │   │   └── routes/        # API endpoints
│   │   │       ├── auth.py    # Authentication endpoints
│   │   │       ├── files.py   # File operations
│   │   │       ├── users.py   # User management
│   │   │       ├── system.py  # System info & monitoring
│   │   │       └── logging.py # Audit logs
│   │   ├── services/          # Business Logic Layer
│   │   │   ├── auth.py        # JWT authentication
│   │   │   ├── files.py       # File management
│   │   │   ├── users.py       # User management
│   │   │   ├── permissions.py # Access control
│   │   │   ├── file_metadata.py # File ownership
│   │   │   ├── raid.py        # RAID management
│   │   │   ├── smart.py       # Disk health monitoring
│   │   │   ├── telemetry.py   # System metrics collection
│   │   │   ├── disk_monitor.py # Disk I/O monitoring
│   │   │   ├── audit_logger.py # Activity logging
│   │   │   ├── system.py      # System info
│   │   │   ├── jobs.py        # Background jobs
│   │   │   └── seed.py        # Dev mode seed data
│   │   ├── schemas/           # Pydantic Models (API contracts)
│   │   │   ├── auth.py        # Auth models
│   │   │   ├── files.py       # File models
│   │   │   ├── user.py        # User models
│   │   │   └── system.py      # System models
│   │   ├── core/              # Core utilities
│   │   │   └── config.py      # Configuration management
│   │   └── compat/            # Python version compatibility
│   ├── tests/                 # Test suite
│   │   ├── test_permissions.py
│   │   ├── test_audit_logging.py
│   │   ├── test_dev_mode.py
│   │   └── ...
│   ├── scripts/               # Utility scripts
│   │   ├── dev_check.py
│   │   ├── reset_dev_storage.py
│   │   └── ...
│   ├── dev-storage/           # Dev mode sandbox (2x5GB RAID1)
│   ├── dev-tmp/               # Temporary files (dev mode)
│   ├── pyproject.toml         # Python dependencies
│   └── README.md
│
├── client/                    # React Frontend
│   ├── src/
│   │   ├── main.tsx           # App entry point
│   │   ├── App.tsx            # Root component
│   │   ├── pages/             # Page components
│   │   │   ├── Dashboard.tsx  # System overview
│   │   │   ├── FileManager.tsx # File browser with preview
│   │   │   ├── UserManagement.tsx
│   │   │   ├── RaidManagement.tsx
│   │   │   ├── SystemMonitor.tsx
│   │   │   ├── Logging.tsx    # Audit logs
│   │   │   └── Login.tsx
│   │   ├── components/        # Reusable components
│   │   │   ├── Layout.tsx
│   │   │   └── ...
│   │   ├── api/               # API client functions
│   │   │   ├── logging.ts
│   │   │   ├── raid.ts
│   │   │   └── smart.ts
│   │   ├── lib/               # Utilities
│   │   │   └── api.ts         # Base API client
│   │   └── hooks/             # Custom React hooks
│   ├── public/                # Static assets
│   ├── index.html
│   ├── vite.config.ts         # Vite configuration
│   ├── tailwind.config.js     # Tailwind configuration
│   ├── package.json
│   └── README.md
│
├── server/                    # Legacy Express Backend (deprecated)
│   └── ... (not actively developed)
│
├── docs/                      # Documentation
│   ├── AUDIT_LOGGING.md
│   ├── DISK_IO_MONITOR.md
│   ├── NETWORK_DRIVE_SETUP.md
│   ├── PERFORMANCE_ANALYSIS.md
│   ├── RAID_SETUP_WIZARD.md
│   └── ...
│
├── scripts/                   # Project scripts
│   ├── mount-dev-storage.ps1  # Mount dev storage as network drive
│   └── unmount-dev-storage.ps1
│
├── start_dev.py               # Dev environment orchestrator
├── README.md                  # Main documentation
├── TECHNICAL_DOCUMENTATION.md # Complete feature docs
├── TODO.md                    # Roadmap
├── CONTRIBUTING.md            # Contribution guidelines
└── ARCHITECTURE.md            # This file
```

## 🔐 Authentication & Authorization

### Authentication Flow

```
┌──────┐                           ┌──────────┐
│Client│                           │ Backend  │
└──┬───┘                           └────┬─────┘
   │                                     │
   │ POST /api/auth/login                │
   │ { username, password }              │
   │────────────────────────────────────>│
   │                                     │
   │                  Validate credentials
   │                  Generate JWT token │
   │                                     │
   │        200 OK                       │
   │ { token, user: { id, role, ... } } │
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

### Why No Database (Yet)?

**Current State:** File-based metadata storage (`.metadata.json`)

**Reasoning:**
- Simpler dev setup (no DB required)
- Sufficient for prototype phase
- Easy to migrate later

**Planned:** PostgreSQL/SQLite for production
- User management
- File metadata
- Audit logs
- Session management

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
- ⚠️ Concurrent uploads limited (no queue)
- ⚠️ File metadata in memory (no DB)

**Future Improvements:**
- Database for metadata
- Redis for caching
- WebSocket for real-time updates
- Upload queue with progress tracking

## 🔒 Security Architecture

### Authentication
- JWT tokens with HS256 signing
- Configurable expiry (default: 12 hours)
- Token stored in localStorage (client-side)

### Authorization
- Role-based access control (RBAC)
- File ownership tracking
- Permission checks at service layer

### Input Validation
- Pydantic schemas validate all inputs
- Path traversal prevention (sandbox checks)
- File type restrictions (optional)

### CORS Policy
- Configured for local development
- Production: Restrict to known origins

### Security TODO
- [ ] HTTPS in production
- [ ] Token refresh mechanism
- [ ] Rate limiting
- [ ] CSRF protection
- [ ] Security headers (helmet)
- [ ] Password hashing with bcrypt/argon2

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
- Services: 80%+ coverage
- API routes: Integration tests
- Frontend: TODO (Vitest)

### Test Fixtures
- Dev mode provides reproducible state
- Seed data creates consistent test data
- Mock services for external dependencies

## 🔮 Future Architecture

### Database Layer
```
┌──────────────────────────────────┐
│  PostgreSQL / MySQL              │
│  ┌────────────┐  ┌────────────┐ │
│  │   Users    │  │   Files    │ │
│  │   Roles    │  │   Metadata │ │
│  └────────────┘  └────────────┘ │
│  ┌────────────┐  ┌────────────┐ │
│  │   Shares   │  │   Audit    │ │
│  │   Links    │  │   Logs     │ │
│  └────────────┘  └────────────┘ │
└──────────────────────────────────┘
```

### Caching Layer
```
┌──────────────────────────────────┐
│  Redis                           │
│  - Session storage               │
│  - API response cache            │
│  - Real-time metrics             │
│  - Job queue (uploads)           │
└──────────────────────────────────┘
```

### Real-Time Updates
```
WebSocket Connection
  ├─> Upload progress
  ├─> System notifications
  ├─> File changes (live sync)
  └─> RAID status updates
```

### Microservices (Optional)
- File service (CRUD, storage)
- Media service (transcoding, thumbnails)
- Backup service (snapshots, restore)
- Notification service (email, webhooks)

## 📊 Monitoring & Observability

### Current Metrics
- System telemetry (CPU, RAM, Disk, Network)
- RAID status monitoring
- SMART disk health
- Audit logs (file operations)

### Future Monitoring
- Application metrics (Prometheus)
- Error tracking (Sentry)
- Performance monitoring (APM)
- Log aggregation (ELK stack)

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

**Last Updated:** November 2025  
**Version:** 0.1.0  
**Maintainer:** BaluHost Team
