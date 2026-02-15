# Architecture & Patterns

## Backend Key Services (`backend/app/services/`)

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

## Frontend UI Stack

- React 18, Tailwind CSS, Recharts for charts, lucide-react for icons
- Pages: Dashboard, FileManager, RaidManagement, SystemMonitor, SettingsPage, PowerManagement, FanControl, AdminDatabase, AdminHealth, ApiCenterPage, Logging, MobileDevicesPage, RemoteServersPage, SchedulerDashboard

## Database

- **Dev**: SQLite (`backend/baluhost.db`)
- **Production**: PostgreSQL 17.7 (deployed, migration complete)
- **ORM**: SQLAlchemy 2.0+ with Alembic migrations

### Schema

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

## Multi-Component Architecture

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
