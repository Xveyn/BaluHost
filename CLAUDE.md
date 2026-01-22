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

**Current Production Status**: ~75% production-ready. Core features implemented, but needs PostgreSQL migration, security hardening, and deployment setup.

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
├── tests/                 # Pytest tests (20+ files)
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

### Frontend (React + TypeScript)
```
client/
├── src/
│   ├── pages/             # Page components
│   │   ├── Dashboard.tsx
│   │   ├── FileManager.tsx
│   │   ├── RaidManagement.tsx
│   │   ├── SystemMonitor.tsx
│   │   └── SettingsPage.tsx
│   ├── components/        # Reusable components
│   ├── api/               # API client modules
│   ├── lib/api.ts         # Base API client (axios)
│   └── hooks/             # Custom React hooks
└── vite.config.ts
```

**UI Stack**: React 18, Tailwind CSS, Recharts for charts, lucide-react for icons

### Database
- **Dev**: SQLite (`backend/baluhost.db`)
- **Production**: PostgreSQL (recommended, migration pending)
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
- Run with: `python -m pytest -v`

### Frontend Tests (Planned)
- Unit tests with Vitest
- E2E tests with Playwright
- Visual regression tests

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
- **iOS**: Implementation guide in `docs/IOS_APP_GUIDE.md`
- Both use QR code pairing with VPN config embedded
- 30-day refresh tokens for mobile sessions

## Production Readiness Gaps

**Critical (must fix before production)**:
1. Migrate to PostgreSQL (currently using SQLite)
2. Security audit (OWASP top 10, penetration testing)
3. Structured logging (JSON format for log aggregation)
4. Deployment documentation (Docker, systemd, reverse proxy)

**Important (should fix)**:
1. Frontend E2E tests (Playwright)
2. Load testing (locust, k6)
3. CI/CD pipeline (GitHub Actions)
4. Backup & disaster recovery strategy

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

- **Main branch**: `tui` (current working branch)
- **No main branch configured**: Set up main/master for PR targets
- Recent commits focus on TUI implementation and RAID safety features

## Contact & Support

- **Issues**: GitHub Issues (repository URL needed)
- **Documentation**: See `docs/` directory
- **Maintainer**: Xveyn
- **Version**: 1.3.0 (as of Dec 2025)
