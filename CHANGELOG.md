# Changelog

All notable changes to BaluHost will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.8.2] - 2026-02-20

### Desktop Pairing (Device Code Flow)

Adds 6-digit code-based pairing for BaluDesk desktop clients.

### Added

- **Desktop Pairing Backend** — DB model, service, API routes (`/api/desktop-pairing/*`), rate limits, and Alembic migration for code-based desktop client authentication
- **Desktop Pairing Dialog** — Frontend component with 6-digit code input, device confirmation/deny flow, and auto-open via `?pair=1` URL parameter
- **i18n** — Pairing translations for EN and DE

### Fixed

- **Pairing Dialog integration** — Moved button and dialog from unused `SyncPrototype.tsx` to `DeviceManagement.tsx` where `/devices` route actually renders

### Changed

- **Root directory cleanup** — Deleted obsolete scripts, moved utilities to `tools/`

---

## [1.8.1] - 2026-02-20

### Test & CI Fixes

Patch release with test infrastructure fixes and CI pipeline simplification.

### Fixed

- **Raid API tests** — Mock `apiClient` (axios) instead of `globalThis.fetch`, fixing `AxiosError: Network Error`
- **ErrorBoundary test** — Correct `ThrowingComponent` return type to `never`
- **Test setup** — Use `globalThis.ResizeObserver` instead of deprecated `global`
- **Test TypeScript config** — Add dedicated `tsconfig.test.json` for test files

### Changed

- **Playwright CI** — Mocked E2E tests no longer require backend; Playwright `webServer` config handles dev server automatically
- **Playwright CI** — Bump Node.js from 18 to 20 to fix Vite `crypto.hash` error
- **Live E2E CI** — Moved secret check earlier, removed redundant frontend server, simplified service wait logic

---

## [1.8.0] - 2026-02-20

### API Keys, Mobile UX & CI Improvements

Feature release adding API key management for programmatic access and comprehensive mobile responsiveness fixes.

### Added

- **API Key Management** — Generate and manage API keys for programmatic access
  - Create, revoke, and list API keys from Settings page
  - Scoped permissions and expiration support
  - Admin-only feature in Settings tab

### Fixed

- **Mobile sidebar scrolling** — Admin users can now scroll all 14 nav items on small screens
- **Mobile responsiveness** — Improved layouts across multiple pages:
  - AdminDataTable: CSS breakpoints replace JS-based mobile detection
  - AdminDatabase: Stacked toolbar layout with proper touch targets
  - AdminHealth: Disk info grid adapts to screen size
  - ApiCenterPage: Endpoint headers stack on mobile
  - FileManager: Path breadcrumb always visible with tooltip
  - MobileDevicesPage: Notification status wraps properly
  - PowerManagement: Grid breakpoints adjusted for small screens
  - SettingsPage: Tab bar with scroll fade indicator

### Changed

- **CI**: Automatic GitHub Release creation on tag push

---

## [1.7.0] - 2026-02-19

### Sleep Mode, Ownership Transfer & 2FA for All Users

Major feature release adding intelligent sleep management, file ownership transfer, and universal two-factor authentication.

### Added

- **Sleep Mode** — Full soft-sleep and true-suspend (S3) support
  - Auto-idle detection with configurable CPU, disk I/O, and HTTP thresholds
  - Scheduled sleep/wake windows with rtcwake integration
  - Wake-on-LAN configuration per interface
  - Disk spindown via hdparm for data disks during sleep
  - Auto-escalation from soft sleep to true suspend
  - Auto-wake middleware: incoming HTTP requests wake the system from soft sleep
  - Service registration for admin dashboard monitoring
  - Collapsible setup help for missing capabilities (hdparm, rtcwake, WoL, suspend)
  - Sleep history table with state transitions
- **File Ownership Transfer** — Transfer file/folder ownership between users
  - Backend service with residency enforcement migration
  - API endpoints with admin and owner authorization
  - Frontend modal with user selector and residency panel
- **2FA for all users** — Two-factor authentication no longer limited to admins
- **E2E test suite** — Comprehensive Playwright end-to-end tests
- **Performance**: `calculate_used_bytes()` cached with 30s TTL

### Fixed

- Frontend `goBack` navigation simplified to avoid edge cases

### Changed

- Repaired and expanded existing backend test suite

### Status

- **Production Readiness**: Stable
- **Version**: 1.7.0

---

## [1.6.1] - 2026-02-18

### 📚 Documentation Restructure & Code Quality Release

This release focuses on improved documentation organization and significant client-side refactoring.

### ✨ Added

#### Documentation
- **Structured documentation directory** with logical subdirectories:
  - `docs/api/` - API documentation
  - `docs/deployment/` - Deployment, SSL, reverse proxy, production guides
  - `docs/features/` - Feature documentation
  - `docs/getting-started/` - User guide and dev checklist
  - `docs/monitoring/` - Monitoring and telemetry
  - `docs/network/` - VPN, WebDAV, mDNS setup
  - `docs/security/` - Security, audit logging, rate limiting
  - `docs/storage/` - RAID and backup documentation
- **Updated navigation** in docs/README.md with table-based quick links

#### Features
- **Time-based fan schedules** (scheduled mode) for fan control
- **Collapsible LiveActivities section** on dashboard below panels

### 🔧 Changed

#### Client Refactoring
- **Decomposed FileManager and RaidManagement** into smaller, focused components
- **Consolidated API layer** from raw fetch calls to unified `apiClient`
- **Added barrel exports** for all component directories
- **Activated AuthContext** with proper error handling
- **Stabilized idle-timeout hook** to prevent unnecessary re-renders

#### UI Improvements
- **SharesPage and modals** aligned with SystemMonitor design language
- **PluginsPage** aligned with SystemMonitor design language
- **UpdatePage** aligned with SystemMonitor design language
- **Admin Database page** redesigned with sidebar and browse/analytics split
- **Improved analytics tabs** with skeletons and shared UI components
- **Simplified 2FA step** in login page

### 🐛 Fixed

- **RAID 1 disk capacity display** corrected on dashboard
- **Auth idle-timeout** re-render issues resolved

### 📊 Status

- **Production Readiness**: ✅ Stable
- **Version**: 1.6.1

---

## [1.4.2] - 2026-01-29

### 🗓️ Unified Scheduler Dashboard

This release introduces a comprehensive scheduler management system for all background jobs.

### ✨ Added

#### Scheduler Dashboard
- **Unified Scheduler Dashboard** with 5 tabs for complete scheduler management
- **Timeline view** for visual execution history across all schedulers
- **Retry mechanism** for failed executions with one-click re-run
- **Execution history tracking** with status, duration, and error details
- **Real-time status monitoring** for all 6 system schedulers

#### Managed Schedulers
- **RAID Scrub** - Data integrity checks (configurable interval, default: weekly)
- **SMART Scan** - Disk health monitoring (default: hourly)
- **Auto Backup** - Automated system backups (default: daily)
- **Sync Check** - Sync schedule trigger checks (every 5 minutes)
- **Notification Check** - Device expiration warnings (hourly)
- **Upload Cleanup** - Chunked upload cleanup (daily at 3 AM)

#### New API Endpoints (`/api/schedulers/*`)
- `GET /api/schedulers` - List all schedulers with status
- `GET /api/schedulers/{name}` - Get specific scheduler details
- `POST /api/schedulers/{name}/run-now` - Trigger immediate execution
- `GET /api/schedulers/{name}/history` - Get execution history
- `GET /api/schedulers/history/all` - Get combined execution timeline
- `POST /api/schedulers/{name}/toggle` - Enable/disable scheduler

#### Database Models
- `SchedulerExecution` - Tracks individual execution runs with timing, status, and error info
- `SchedulerConfig` - Stores per-scheduler configuration and enabled state

### 🔧 Changed

- Integrated RAID scrub and SMART scan schedulers with service status monitoring
- Enhanced SyncSettings UI with device dropdown and day pickers
- Added execution logging to all scheduler services

### 📊 Status

- **Production Readiness**: 100% (DEPLOYED)
- **Version**: 1.4.2

---

## [1.4.1] - 2026-01-28

### 🚀 Production Deployment Release

This release marks the production deployment of BaluHost on January 25, 2026.

### ✨ Added

#### Production Deployment
- **Live production deployment** on Debian 13 server (Ryzen 5 5600GT, 16GB RAM)
- **PostgreSQL 17.7 migration** complete and verified
- **Nginx reverse proxy** with rate limiting (100 req/s API, 10 req/s auth)
- **Systemd services** for backend (4 Uvicorn workers)
- **Auto-start on reboot** configured

#### Per-Thread CPU Monitoring
- **Task Manager-style display** showing individual thread usage
- **CPU thread breakdown** in monitoring dashboard
- **Historical per-thread data** with retention policies

#### AdminDatabase Page Enhancements
- **Stats tab** with database statistics and table counts
- **Storage tab** with storage breakdown visualization
- **History tab** for query history tracking
- **Maintenance tab** for database maintenance tools

#### Fan Control UI
- **Fan curve chart editor** with drag-to-edit functionality
- **Visual temperature-to-PWM mapping**
- **Real-time RPM and PWM display**
- **Mode switching** (auto/manual/emergency)

#### Network Discovery
- **mDNS/Bonjour integration** for local network discovery
- **Zero-configuration networking** support
- **Service announcement** for web interface and API
- **Device discovery** for other BaluHost instances

#### Service Status Monitoring
- **Health check dashboard** for all services
- **Service registry** with real-time status
- **Admin controls** for service restart/stop/start

### 🔧 Changed

- Updated documentation to reflect production deployment status
- Unified version numbers across all components to 1.4.0
- Enhanced monitoring orchestrator with per-thread CPU support
- Improved fan control service with better curve interpolation

### 🐛 Fixed

- Email validation regex pattern in user registration
- Frontend routing issues with nested routes
- Memory leak in disk I/O monitoring long-running sessions

### 📝 Documentation

- Updated `TODO.md` with completed features and production status
- Updated `README.md` with production deployment information
- Updated `PRODUCTION_READINESS.md` with deployment confirmation
- Updated `TECHNICAL_DOCUMENTATION.md` with new features (Power Management, Fan Control, etc.)
- Updated `ARCHITECTURE.md` with production deployment architecture
- Documented known issues (integer overflow in monitoring tables)

### 📊 Status

- **Production Readiness**: 100% (DEPLOYED)
- **Server**: Debian 13, Ryzen 5 5600GT, 16GB RAM
- **Database**: PostgreSQL 17.7
- **Version**: 1.4.1

---

## [1.4.0] - 2026-01-14

### 🎯 Production Readiness Release

This release makes BaluHost fully production-ready with automated backup system, structured logging, and comprehensive deployment documentation.

### ✨ Added

#### Backup Automation
- **Automated backup scheduler** using APScheduler for periodic backups
- **PostgreSQL pg_dump support** for production database backups
- **Configurable backup intervals** (hourly, daily, weekly, custom)
- **Multiple backup types**: full, incremental, database_only, files_only
- **Retention policies**: max count and age-based cleanup
- **Manual backup script** (`deploy/scripts/backup.sh`) for on-demand backups
- **Backup configuration** via environment variables (`BACKUP_AUTO_ENABLED`, `BACKUP_AUTO_INTERVAL_HOURS`, `BACKUP_AUTO_TYPE`)

#### Production Logging
- **Structured JSON logging** using python-json-logger for log aggregation
- **Environment-based log format**: JSON for production, human-readable for development
- **Configurable log levels** via `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Log format configuration** via `LOG_FORMAT` environment variable (json, text)
- **Logging initialization** in application startup for consistent configuration

#### Documentation
- **Comprehensive deployment guide** (`docs/DEPLOYMENT.md`) with:
  - 5-minute quick start guide
  - Detailed Docker Compose deployment steps
  - SSL/TLS configuration with Let's Encrypt
  - Monitoring setup instructions
  - Backup configuration guide
  - Troubleshooting section
  - Maintenance procedures
- **Updated `.env.production.example`** with backup and logging configuration
- **Production readiness status** updated to ~98% complete

### 🔧 Changed

#### Backend
- `backend/app/core/config.py`:
  - Added backup automation settings (`backup_auto_enabled`, `backup_auto_interval_hours`, `backup_auto_type`)
  - Added logging configuration settings (`log_level`, `log_format`)
- `backend/app/services/backup.py`:
  - Enhanced with PostgreSQL pg_dump/psql support
  - Added `_backup_postgres_database()` method for PostgreSQL backups
  - Added `_restore_postgres_database()` method for PostgreSQL restores
  - Modified `_get_database_info()` to detect database type (SQLite/PostgreSQL)
- `backend/app/main.py`:
  - Integrated backup scheduler startup/shutdown
  - Added structured logging initialization on app startup
- `backend/pyproject.toml`:
  - Added `python-json-logger>=2.0.0,<3.0.0` dependency

#### Documentation
- `PRODUCTION_READINESS.md`:
  - Updated executive summary to ~98% production-ready
  - Marked backup automation as ✅ COMPLETED
  - Marked error handling & logging as ✅ COMPLETED
  - Marked deployment documentation as ✅ COMPLETED
  - Updated production checklist
  - Changed status to "READY FOR PRODUCTION DEPLOYMENT"

### 📦 Dependencies

- Added: `python-json-logger` (^2.0.0) for structured JSON logging

### 🚀 Deployment

#### New Environment Variables
```bash
# Logging
LOG_LEVEL=INFO              # DEBUG|INFO|WARNING|ERROR|CRITICAL
LOG_FORMAT=json             # json|text

# Backup Automation
BACKUP_AUTO_ENABLED=true    # Enable automated backups
BACKUP_AUTO_INTERVAL_HOURS=24  # Backup interval (hours)
BACKUP_AUTO_TYPE=full       # full|incremental|database_only|files_only
```

#### Backup Script Usage
```bash
# Full backup (default)
./deploy/scripts/backup.sh

# Database-only backup
./deploy/scripts/backup.sh --type database_only

# Files-only backup
./deploy/scripts/backup.sh --type files_only

# Without Docker
./deploy/scripts/backup.sh --no-docker
```

### 🔒 Security

- No security changes in this release
- Existing security hardening from v1.3.0 remains active (8/8 critical vulnerabilities fixed)

### 📊 Status

- **Production Readiness**: ~98% (up from ~95%)
- **Critical Blockers**: None
- **Optional Enhancements**: Print statement cleanup, load testing, PWA

### 📝 Notes

This release focuses on operational excellence and production deployment readiness. BaluHost is now suitable for production deployment with:
- Automated backup system
- Production-grade logging
- Comprehensive deployment documentation
- Full PostgreSQL support

---

## [1.3.0] - 2025-12-20

### 🎯 Feature Complete Release

Major features implemented: Monitoring, Security Hardening, Testing Infrastructure.

### ✨ Added

#### Monitoring & Alerting
- **Prometheus metrics endpoint** (`/api/metrics`) with 40+ custom metrics
- **Grafana dashboards**: System Overview, RAID Health
- **20+ alert rules** across 6 groups (Critical, Warning, Info severity)
- **Docker Compose monitoring profile** for easy deployment
- System metrics: CPU, memory, disk, network monitoring
- RAID metrics: array status, disk count, sync progress
- SMART metrics: disk health, temperature, power-on hours
- Application metrics: HTTP requests, file operations, database connections

#### Security Hardening
- Refresh token revocation with JTI tracking
- Password policy enforcement (8+ chars, uppercase, lowercase, number)
- Consolidated auth system (single secret key)
- Security headers middleware activated
- Rate limiting on all critical endpoints (login, register, password change)
- Secret key validation in production mode
- Deprecated code removal (datetime.utcnow)

#### Testing Infrastructure
- 40 test files with 364 test functions
- Security tests (critical vulnerabilities, headers, JWT, input validation)
- Integration tests (files API, sync, mobile, remote server)
- RAID tests (9 files: parsing, dry-run, scrubbing, scheduling)
- Feature tests (audit logging, database, upload progress)
- 3 GitHub Actions workflows (RAID tests, Playwright E2E, mdadm tests)

#### Deployment Infrastructure
- Docker Compose with multi-stage Dockerfiles (backend + frontend + PostgreSQL)
- Nginx reverse proxy with SSL/TLS (Let's Encrypt automation)
- Security headers configuration (OWASP best practices)
- Rate limiting zones (API, auth, file uploads)
- `.env.production.example` template

### 🔧 Changed

- PostgreSQL fully supported with docker-compose.postgres.yml
- Database session management improved
- File metadata service migrated to database
- Alembic migrations configured
- Audit logs moved from JSON files to database

### 📦 Dependencies

- Added: `prometheus-client` for metrics collection
- Added: `slowapi` for rate limiting

### 🚀 Deployment

- Docker: `docker-compose up -d`
- Monitoring: `docker-compose --profile monitoring up -d`
- SSL: `./deploy/ssl/setup-letsencrypt.sh domain.com email@example.com`

---

## [1.2.0] - 2025-11-XX

### Previous Release

_(Add details from previous releases as they become available)_

---

## Legend

- ✨ Added: New features
- 🔧 Changed: Changes to existing functionality
- 🗑️ Deprecated: Soon-to-be removed features
- 🔒 Security: Security improvements
- 🐛 Fixed: Bug fixes
- 📦 Dependencies: Dependency updates
- 🚀 Deployment: Deployment-related changes
- 📝 Notes: Additional information

---

**Maintained by**: Xveyn
**License**: MIT
**Repository**: https://github.com/your-org/baluhost
