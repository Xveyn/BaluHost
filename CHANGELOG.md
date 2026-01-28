# Changelog

All notable changes to BaluHost will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
