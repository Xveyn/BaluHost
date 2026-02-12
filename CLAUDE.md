# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BaluHost is a full-stack NAS management platform with multiple components:
- **Backend**: Python FastAPI (primary), located in `backend/`
- **Frontend**: React + TypeScript + Vite (Web UI), located in `client/`
- **TUI**: Terminal UI (Textual), located in `backend/baluhost_tui/`
- **BaluDesk**: Desktop sync client (C++ backend + Electron frontend), located in `baludesk/`
- **Mobile Apps**: Native Android (Kotlin), iOS implementation guide available
- **Legacy**: Express/TypeScript backend in `server/` (deprecated, do not modify)

**Current Production Status**: ~99% production-ready, deployed in production (Jan 2026). PostgreSQL, security hardening, and deployment complete.

## Architecture

### Backend (FastAPI)
```
backend/
├── app/
│   ├── api/routes/        # API endpoints
│   ├── services/          # Business logic
│   ├── schemas/           # Pydantic models
│   ├── models/            # SQLAlchemy ORM models
│   └── core/config.py     # Configuration
├── baluhost_tui/          # Terminal UI application
├── tests/                 # Pytest tests (40+ files, 364 test functions)
└── pyproject.toml         # Dependencies
```

**Key Services**:
- `auth.py` - JWT authentication, role-based access control (admin/user)
- `files.py` - File operations, multi-mountpoint support, quota management
- `raid.py` - RAID management (mdadm integration + dev-mode simulation)
- `smart.py` - Disk health monitoring via smartctl
- `telemetry.py` - System metrics collection (CPU, RAM, Network)
- `disk_monitor.py` - Real-time disk I/O monitoring
- `audit_logger.py` - JSON-based activity logging
- `vpn.py` - WireGuard VPN configuration & client management
- `shares.py` - File sharing (public links + user permissions)
- `backup.py` - Backup/restore functionality
- `sync.py` - Desktop sync client coordination
- `mobile.py` - Mobile device registration with QR code pairing
- `power_manager.py` - CPU frequency scaling (AMD Ryzen & Intel support)
- `power_monitor.py` - CPU power-state monitoring
- `fan_control.py` - PWM fan control with temperature curves
- `service_status.py` - Service health monitoring for admin dashboard
- `network_discovery.py` - mDNS/Bonjour for local network discovery
- `scheduler_service.py` - Unified scheduler management with execution history
- `admin_db.py` - Secure read-only database inspection
- `monitoring/orchestrator.py` - Unified monitoring system with collectors

### Frontend (React + TypeScript)
```
client/
├── src/
│   ├── pages/             # Page components
│   │   ├── Dashboard.tsx
│   │   ├── FileManager.tsx
│   │   ├── RaidManagement.tsx
│   │   ├── SystemMonitor.tsx
│   │   ├── SettingsPage.tsx
│   │   ├── PowerManagement.tsx
│   │   ├── FanControl.tsx
│   │   ├── AdminDatabase.tsx
│   │   ├── AdminHealth.tsx
│   │   ├── ApiCenterPage.tsx
│   │   ├── Logging.tsx
│   │   ├── MobileDevicesPage.tsx
│   │   ├── RemoteServersPage.tsx
│   │   └── SchedulerDashboard.tsx
│   ├── components/        # Reusable components
│   ├── api/               # API client modules
│   ├── lib/api.ts         # Base API client (axios)
│   └── hooks/             # Custom React hooks
└── vite.config.ts
```

**UI Stack**: React 18, Tailwind CSS, Recharts for charts, lucide-react for icons

### Database
- **Dev**: SQLite (`backend/baluhost.db`)
- **Production**: PostgreSQL 17.7 (deployed, migration complete)
- **ORM**: SQLAlchemy 2.0+ with Alembic migrations

## Common Development Commands

### Combined Development Start
```bash
# Starts both backend (port 3001) and frontend (port 5173)
python start_dev.py
```

### Backend
```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Run server (dev mode with auto-reload)
uvicorn app.main:app --reload --port 3001

# Run tests
python -m pytest
python -m pytest tests/test_permissions.py -v  # Specific test

# Run TUI
python -m baluhost_tui
# or
baluhost-tui  # if installed
```

### Frontend
```bash
cd client

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Run tests
npm run test        # Unit tests (placeholder)
npm run test:e2e    # E2E tests (placeholder)
```

### Database Migrations
```bash
cd backend

# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Development Modes

### Dev Mode (`NAS_MODE=dev`)
- Enabled by default in `start_dev.py`
- Creates sandbox storage in `backend/dev-storage/` (2x5GB RAID1 simulated)
- Mock SMART data, RAID arrays, and system metrics
- Automatic seed data (admin/DevMode2024, user/User123)
- Windows-compatible (no Linux dependencies required)
- Mock VPN key generation (no `wg` command needed)

### Production Mode (`NAS_MODE=prod`)
- Real mdadm RAID commands
- Actual smartctl disk health data
- System-wide file access
- PostgreSQL database (recommended)

## Code Standards

### Python (Backend)
- **Async/await** for all I/O operations
- **Type hints** required on all functions
- **Pydantic models** for request/response validation
- **Docstrings** for all services
- **Services pattern**: Business logic in `services/`, not in routes
- **Testing**: Pytest with async support, 80%+ coverage target
- **Formatting**: Follow existing patterns (4 spaces, snake_case)

**Example service function**:
```python
async def get_file_list(
    path: str,
    current_user: User,
    db: Session
) -> List[FileItem]:
    """
    Retrieve file list for a given path.

    Args:
        path: Relative path to list
        current_user: Authenticated user context
        db: Database session

    Returns:
        List of FileItem objects

    Raises:
        PermissionError: If user lacks access
    """
    # Implementation
```

### TypeScript (Frontend)
- **Functional components** with hooks (no class components)
- **TypeScript strict mode** enabled
- **Tailwind CSS** for all styling (no inline styles)
- **API calls** through typed client in `src/lib/api.ts`
- **Error handling**: Use toast notifications (react-hot-toast)
- **Loading states**: Show loading indicators for async operations

**Example component**:
```typescript
interface FileItemProps {
  file: FileItem;
  onDelete: (path: string) => Promise<void>;
}

export const FileItem: React.FC<FileItemProps> = ({ file, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(file.path);
      toast.success('File deleted');
    } catch (error) {
      toast.error('Failed to delete file');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    // JSX with Tailwind classes
  );
};
```

## Important Patterns & Conventions

### Authentication Flow
1. User logs in via `POST /api/auth/login`
2. Backend returns JWT token + user info
3. Frontend stores token in localStorage
4. All API requests include `Authorization: Bearer <token>` header
5. Backend validates token via `get_current_user` dependency

### File Operations
- All file paths are **relative** to storage root
- Sandbox checks prevent path traversal
- Ownership tracked via `.metadata.json` + database
- Quota checked before uploads
- Multi-mountpoint support (RAID arrays as separate drives)

### RAID Management
- **Dev Mode**: `DevRaidBackend` simulates mdadm with 7 mock disks
- **Prod Mode**: `MdadmRaidBackend` executes real mdadm commands
- RAID status parsed from `/proc/mdstat` (Linux) or mocked
- Frontend shows real-time resync progress

### Background Jobs
- Telemetry collection runs every 3 seconds (configurable)
- Disk I/O monitor samples every 1 second
- Jobs managed via FastAPI lifespan events
- Graceful shutdown on app termination

## Testing Strategy

### Backend Tests (`backend/tests/`)
- **Unit tests**: Test services in isolation with mocks
- **Integration tests**: Test API endpoints with test database
- **Fixtures**: Use pytest fixtures for database, auth tokens
- **Test database**: Separate SQLite database for tests
- **Coverage**: 40+ test files, 364 test functions
- Run with: `python -m pytest -v`

### Frontend Tests
- Unit tests with Vitest (configured)
- E2E tests with Playwright (configured)
- Visual regression tests (planned)

## Database Schema

Key tables:
- `users` - User accounts with roles
- `file_metadata` - File ownership and metadata
- `shares` - Public share links and user shares
- `mobile_devices` - Registered mobile devices
- `vpn_clients` - WireGuard VPN configurations
- `audit_logs` - Security audit trail
- `backups` - Backup metadata
- `sync_folders` - Sync configuration

**Monitoring tables:**
- `cpu_samples` - CPU usage, frequency, temperature, per-thread usage
- `memory_samples` - RAM usage
- `network_samples` - Network throughput
- `disk_io_samples` - Disk I/O IOPS
- `process_samples` - BaluHost process tracking
- `monitoring_config` - Retention policies

**Power management tables:**
- `power_profile_config` - CPU frequency profiles
- `power_sample` - Power consumption
- `power_profile_log` - Profile change history

**Fan control tables:**
- `fan_config` - Fan configuration (mode, curves, limits)
- `fan_sample` - Historical RPM/PWM values

**Scheduler tables:**
- `scheduler_executions` - Execution history with timing and status
- `scheduler_configs` - Per-scheduler configuration and enabled state

## API Structure

All API routes are prefixed with `/api`:
- `/api/auth/*` - Authentication
- `/api/files/*` - File operations
- `/api/users/*` - User management (admin only)
- `/api/system/*` - System info, RAID, SMART, telemetry
- `/api/logging/*` - Audit logs
- `/api/shares/*` - File sharing
- `/api/backup/*` - Backup/restore
- `/api/sync/*` - Desktop sync
- `/api/mobile/*` - Mobile device management
- `/api/vpn/*` - VPN configuration
- `/api/monitoring/*` - Real-time metrics (CPU, Memory, Network, Disk I/O)
- `/api/power/*` - Power profiles & CPU frequency
- `/api/fans/*` - Fan control & temperature curves
- `/api/admin/*` - Admin dashboard services
- `/api/admin-db/*` - Database inspection
- `/api/energy/*` - Energy consumption statistics
- `/api/tapo/*` - TP-Link Tapo smart plug integration
- `/api/schedulers/*` - Scheduler management (status, history, run-now)

API documentation available at: `http://localhost:3001/docs` (Swagger UI with custom BaluHost styling)

## Project-Specific Considerations

### DO NOT Modify
- `server/` directory (legacy Express backend)
- `.metadata.json` files (managed by file service)
- `dev-storage/` contents (recreated on startup in dev mode)

### Security
- All file operations check ownership or admin role
- Path traversal prevention via `is_within_sandbox()`
- JWT tokens expire after 12 hours (configurable)
- Audit logging for sensitive operations
- Rate limiting implemented via slowapi

### Middleware
- `error_counter.py` - Tracks 4xx/5xx errors for admin metrics
- `security_headers.py` - CSP, X-Frame-Options, HSTS
- `device_tracking.py` - Mobile device last_seen tracking
- `local_only.py` - Enforces local-network-only access for sensitive endpoints

### Performance
- Telemetry: 3s interval (prod), 2s (dev)
- Telemetry history: 60 samples (3 minutes at 3s interval)
- Disk I/O: 1s sampling, 120 samples history
- API response caching: Storage info cached 30s

### Windows Compatibility
- All features work on Windows via dev-mode simulation
- Disk I/O monitor detects Windows drives (`PhysicalDrive0`, `PhysicalDrive1`)
- No Linux-specific commands required in dev mode

## Multi-Component Architecture Notes

### BaluDesk (Desktop Sync Client)
- C++ backend with Electron frontend
- Located in `baludesk/`
- Uses vcpkg for C++ dependencies
- Communicates with backend API for sync operations

### TUI (Terminal UI)
- Built with Python Textual framework
- Located in `backend/baluhost_tui/`
- Provides CLI access to backend features
- Run with `baluhost-tui` command

### Mobile Apps
- **Android**: Full native app in `android-app/` (175+ Kotlin files)
- Both use QR code pairing with VPN config embedded
- 30-day refresh tokens for mobile sessions

## Production Status

**Deployed**: January 25, 2026 on Debian 13 (Ryzen 5 5600GT, 16GB RAM)

**Completed:**
- PostgreSQL 17.7 migration
- Security hardening (OWASP, rate limiting, security headers)
- Structured JSON logging
- Systemd deployment with 4 Uvicorn workers
- Nginx reverse proxy with rate limiting
- 40+ test files, 364 test functions
- CI/CD pipeline (GitHub Actions)
- Comprehensive monitoring (Prometheus/Grafana ready)

**Optional/Future:**
- SSL/HTTPS (currently HTTP on port 80)
- Email notifications
- PWA support
- Localization (i18n)

See `PRODUCTION_READINESS.md` for complete checklist.

## Documentation Structure

- `README.md` - Project overview, quick start
- `TECHNICAL_DOCUMENTATION.md` - Complete feature documentation (1600+ lines)
- `ARCHITECTURE.md` - System architecture and design decisions
- `TODO.md` - Roadmap and planned features
- `PRODUCTION_READINESS.md` - Production deployment checklist
- `docs/` - Feature-specific documentation (RAID, VPN, Mobile, etc.)
- `CONTRIBUTING.md` - Contribution guidelines
- `SECURITY.md` - Security policy

## Quick Reference: Finding Things

**Authentication logic**: `backend/app/services/auth.py` + `backend/app/api/deps.py`
**File upload handling**: `backend/app/services/files.py:upload_file()`
**RAID status**: `backend/app/services/raid.py`
**Frontend API client**: `client/src/lib/api.ts`
**Dashboard page**: `client/src/pages/Dashboard.tsx`
**Database models**: `backend/app/models/`
**API schemas**: `backend/app/schemas/`
**Tests**: `backend/tests/`
**Fan control**: `backend/app/services/fan_control.py`
**Power management**: `backend/app/services/power_manager.py`
**Monitoring orchestrator**: `backend/app/services/monitoring/orchestrator.py`
**Service status**: `backend/app/services/service_status.py`
**Network discovery**: `backend/app/services/network_discovery.py`
**Scheduler service**: `backend/app/services/scheduler_service.py`
**Scheduler Dashboard**: `client/src/pages/SchedulerDashboard.tsx`

## Development Tips

1. **Always use dev mode** for local development (`python start_dev.py`)
2. **Check logs** in terminal where `start_dev.py` is running
3. **API testing**: Use Swagger UI at `http://localhost:3001/docs`
4. **Database inspection**: Use SQLite browser on `backend/baluhost.db`
5. **Reset dev environment**: `python backend/scripts/reset_dev_storage.py`
6. **Test a specific feature**: Write pytest test, then implement feature (TDD)

## Common Issues & Solutions

**Backend won't start**: Check if port 3001 is already in use
**Frontend can't reach API**: Verify proxy config in `client/vite.config.ts`
**Permission denied on file operation**: Check file ownership in `.metadata.json`
**RAID commands fail**: Ensure dev mode is active or run on Linux with mdadm
**Tests fail**: Run `python -m pytest -v` to see detailed error messages
**Import errors**: Ensure virtual environment is activated and dependencies installed

## Git Workflow

- **Main branch**: `main` (production deployments)
- **Development branch**: `development` (active development)
- Features branch off from `development`, PRs merge to `main`

## Production Deployment

### Systemd Services
- `baluhost-backend.service` - FastAPI/Uvicorn (4 workers, port 8000)
- `baluhost-frontend.service` - Optional (Nginx serves static files)

### Production Commands
```bash
# Start/Stop Services
sudo systemctl start baluhost-backend
sudo systemctl stop baluhost-backend
sudo systemctl status baluhost-backend

# View Logs
sudo journalctl -u baluhost-backend -f

# Production Launcher (Alternative)
python start_prod.py    # Start backend + optional frontend
python kill_prod.py     # Stop all BaluHost processes
```

### Configuration
- **Environment**: `.env.production` (auto-generated secrets)
- **Nginx**: `/etc/nginx/sites-available/baluhost`
- **Database**: PostgreSQL on localhost:5432

## Contact & Support

- **Issues**: GitHub Issues (repository URL needed)
- **Documentation**: See `docs/` directory
- **Maintainer**: Xveyn
- **Version**: 1.4.2 (as of Jan 2026)
