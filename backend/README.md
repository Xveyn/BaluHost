# Baluhost Python Backend

FastAPI-basierter Backend für NAS-Management mit vollständiger Database-Integration.

## Features

### Core Features
- **JWT Authentication** - Sichere Token-basierte Auth mit Refresh Tokens
- **Two-Factor Authentication (TOTP)** - Optionale 2FA mit Authenticator Apps
- **SQLite/PostgreSQL Database** - Persistente Datenspeicherung mit Alembic Migrations
- **User Management** - CRUD Operations mit Rollen (Admin/User)
- **File Metadata** - Database-backed Ownership & Permissions
- **File Sharing** - Public Links mit Passwortschutz und Ablaufdatum
- **Chunked Upload** - Große Dateien in Chunks hochladen mit Fortschrittsanzeige

### Storage & Backup
- **Backup & Restore** - Vollständige und inkrementelle Backups mit Verschlüsselung
- **SSD Cache** - SSD-Cache-Layer für HDD-Arrays
- **RAID Management** - Simulation im Dev-Mode, mdadm Production-Ready
- **S.M.A.R.T. Monitoring** - Festplatten-Gesundheitsüberwachung
- **Quota System** - Storage Limits & Monitoring pro Benutzer

### Sync & Mobile
- **Sync System** - Desktop Sync Client mit Konfliktauflösung
- **Mobile Support** - Geräteregistrierung und Kamera-Backup
- **WebDAV Server** - WebDAV-Zugriff für externe Clients
- **Samba Integration** - Windows-Netzwerkfreigaben

### Network & Access
- **VPN Management** - WireGuard VPN-Konfiguration und Profile
- **Network Discovery** - mDNS/Bonjour for automatic server discovery
- **Remote Server Profiles** - Verwaltung mehrerer BaluHost-Server

### Power & Hardware
- **Power Management** - CPU-Governor-Steuerung und Energieprofile
- **Fan Control** - Temperaturbasierte Lüftersteuerung
- **Tapo Smart Plug Integration** - TP-Link Tapo Steckdosen für Power-Monitoring
- **Energy Monitoring** - Stromverbrauchsüberwachung und Preiskonfiguration

### System & Monitoring
- **System Monitoring** - CPU, RAM, Disk, Network via psutil
- **Telemetry Service** - Historische Metriken mit konfigurierbarem Intervall
- **Audit Logging** - Comprehensive Security & File Operation Logs
- **Disk I/O Monitor** - Festplatten-I/O-Überwachung

### Automation & Plugins
- **Scheduler System** - Geplante Tasks (Backups, Cleanup, etc.)
- **Plugin System** - Erweiterbare Plugin-Architektur
- **Update Service** - System-Update-Verwaltung

### Cloud & Integration
- **Cloud Import** - Import von Dropbox, Google Drive, OneDrive
- **Email Notifications** - SMTP-basierte Benachrichtigungen
- **Firebase Push** - Mobile Push-Benachrichtigungen
- **WebSocket Events** - Echtzeit-Benachrichtigungen

### Admin & DevOps
- **Admin Database Tools** - Datenbank-Verwaltung und Health-Checks
- **Rate Limiting** - Konfigurierbare API-Rate-Limits
- **Service Status Management** - Überwachung aller Hintergrunddienste
- **Custom API Docs** - Styled Swagger UI matching frontend design
- **VCL (Virtual Command Line)** - Web-basierte Terminal-Emulation
- **Benchmark Tools** - Storage-Performance-Tests
- **Dev Mode** - Windows-kompatible Sandbox (2x5GB RAID1 = 5 GB effective)

## Quickstart

### Installation
```bash
# Virtual Environment erstellen (empfohlen)
py -3.11 -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Dependencies installieren
pip install -e ".\[dev]"  # PowerShell
# oder
pip install -e .[dev]  # CMD/Git Bash
```

### Configuration
```bash
# Dev mode defaults (Windows sandbox, 2x5GB RAID1 = 5 GB effective)
echo "NAS_MODE=dev" >> .env
echo "NAS_QUOTA_BYTES=10737418240" >> .env
```

### Database Setup

#### Development (SQLite)
```bash
# Database seeden (Admin User + Demo Data)
python scripts/seed.py

# Alembic Migrations (bei Schema-Änderungen)
alembic upgrade head
```

#### Production (PostgreSQL Migration)
Phase 1 PostgreSQL Migration ist implementiert. Schritte zur Migration:

**1. PostgreSQL Setup**
```bash
# Option A: Docker Compose (empfohlen)
python scripts/setup_postgresql.py --docker

# Option B: Native PostgreSQL Installation
python scripts/setup_postgresql.py --native

# Verify PostgreSQL connection
python scripts/setup_postgresql.py --verify
```

**2. Environment konfigurieren**
```bash
# .env file aktualisieren mit PostgreSQL URL:
DATABASE_URL=postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost

# Async variant (für Produktionsumgebungen):
DATABASE_URL=postgresql+asyncpg://baluhost_user:baluhost_password@localhost:5432/baluhost
```

**3. SQLite → PostgreSQL Migration**
```bash
# Dry-run (preview ohne Änderungen)
python scripts/migrate_sqlite_to_postgresql.py --dry-run

# Tatsächliche Migration (erstellt automatisch Backup)
python scripts/migrate_sqlite_to_postgresql.py

# Mit Custom-Backup-Verzeichnis
python scripts/migrate_sqlite_to_postgresql.py --backup --source baluhost.db

# Verbose Logging
python scripts/migrate_sqlite_to_postgresql.py --verbose
```

**Migration Features:**
- ✅ Automatische SQLite Backup vor Migration
- ✅ Datenbankverifikation (SQLite Format Validierung)
- ✅ Dry-Run Mode (Vorschau ohne Schreiben)
- ✅ JSON Audit Log (`dev-backups/migration_*.json`)
- ✅ Fehlerbehandlung & Logging
- ✅ Tabellen-für-Tabellen Migration mit Zähler

**4. Alembic Migrations ausführen**
```bash
alembic upgrade head
```

**Nach erfolgreichem Migration:**
```bash
# Verify PostgreSQL connection
python -c "from app.core.database import engine; print(engine)"

# Backup vor Migrationen
python scripts/migrate_sqlite_to_postgresql.py --backup --no-migrate
```

### Start Application
```bash
# Backend alleine starten
python -m uvicorn app.main:app --reload --port 3001

# Kombinierter Start (Frontend + Backend): im Projektstamm
python start_dev.py

# API Dokumentation öffnen (Custom Styled)
# http://localhost:3001/docs (Swagger UI - BaluHost Design)
# http://localhost:3001/redoc (ReDoc)
```

### Custom API Documentation
Das Backend verwendet ein angepasstes Swagger UI Design:
- **Dark Theme** - Passend zum Frontend Design
- **Glassmorphism Effects** - Moderne UI-Effekte
- **Color-coded Methods** - Farbcodierte HTTP-Methoden (GET, POST, PUT, DELETE)
- **Enhanced Readability** - Verbesserte Lesbarkeit durch Custom Styling

### Development Tools
```bash
# Tests ausführen
pytest tests/ -v

# Spezifische Tests
pytest tests/test_file_metadata_db.py -v
pytest tests/test_files_api_integration.py -v

# Coverage Report
pytest tests/ --cov=app --cov-report=html

# Dev-Test-Script (System-/Quota-/SMART-/RAID-Checks)
python scripts/dev_check.py --raid-cycle

# Database Reset (Dev Mode)
python scripts/reset_dev_storage.py
```

## Struktur
```
app/
  api/
    routes/              # FastAPI Router
      auth.py            # Login, Register, Token Management
      users.py           # User CRUD (Admin)
      files.py           # File Operations & Upload
      upload_progress.py # Upload Progress Tracking
      chunked_upload.py  # Chunked Upload für große Dateien
      shares.py          # File Sharing
      backup.py          # Backup & Restore
      sync.py            # Sync System
      sync_advanced.py   # Advanced Sync Features
      sync_compat.py     # Sync Compatibility Layer
      mobile.py          # Mobile Device Management
      system.py          # System Metrics, RAID, SMART
      logging.py         # Audit Logs API
      vpn.py             # VPN Management
      vpn_profiles.py    # VPN Profile Management
      health.py          # Health Check Endpoints
      admin_db.py        # Admin Database Tools
      rate_limit_config.py # Rate Limiting Config
      vcl.py             # Virtual Command Line
      server_profiles.py # Remote Server Profiles
      metrics.py         # Prometheus Metrics
      tapo.py            # Tapo Smart Plug Control
      energy.py          # Energy Monitoring
      monitoring.py      # System Monitoring
      power.py           # Power Management
      power_presets.py   # Power Preset Profiles
      fans.py            # Fan Control
      service_status.py  # Service Status Management
      schedulers.py      # Scheduled Tasks
      plugins.py         # Plugin Management
      benchmark.py       # Storage Benchmarks
      notifications.py   # Notification System
      updates.py         # System Updates
      webdav.py          # WebDAV Server
      samba.py           # Samba Integration
      cloud.py           # Cloud Import
      devices.py         # Device Management
    docs.py              # Custom Swagger UI Styling
    deps.py              # Dependencies (Auth, DB Session)
  core/
    config.py            # Settings & Logging Setup
    database.py          # SQLAlchemy Engine & Session
    rate_limiter.py      # Rate Limiting Setup
  models/                # SQLAlchemy ORM Models
    base.py              # Base Model
    user.py              # User Model
    file_metadata.py     # FileMetadata Model
    file_share.py        # FileShare Model
    share_link.py        # ShareLink Model
    backup.py            # Backup Model
    sync_state.py        # Sync State Model
    sync_progress.py     # Sync Progress Model
    device.py            # Device Model
    mobile.py            # Mobile Device Model
    audit_log.py         # Audit Log Model
    vpn.py               # VPN Configuration Model
    vpn_profile.py       # VPN Profile Model
    power.py             # Power Settings Model
    power_preset.py      # Power Preset Model
    power_sample.py      # Power Sample Model
    energy_price_config.py # Energy Price Config
    fans.py              # Fan Configuration Model
    ssd_cache.py         # SSD Cache Model
    plugin.py            # Plugin Model
    scheduler_state.py   # Scheduler State Model
    scheduler_history.py # Scheduler History Model
    notification.py      # Notification Model
    update_history.py    # Update History Model
    benchmark.py         # Benchmark Results Model
    cloud.py             # Cloud Import Model
    server_profile.py    # Server Profile Model
    tapo_device.py       # Tapo Device Model
    refresh_token.py     # Refresh Token Model
    rate_limit_config.py # Rate Limit Config Model
    vcl.py               # VCL Session Model
    webdav_state.py      # WebDAV State Model
    monitoring.py        # Monitoring Data Model
  services/              # Business Logic Layer
    auth.py              # JWT Token & Authentication
    users.py             # User CRUD Operations
    files/               # File Operations
    audit/               # Audit Logging
    backup/              # Backup/Restore Operations
    sync/                # Sync Logic & Background Jobs
    mobile.py            # Mobile Device Management
    network_discovery.py # mDNS/Bonjour Service
    permissions.py       # Permission Checks
    system.py            # System Metrics (CPU, RAM, Disk)
    disk_monitor.py      # Disk I/O Monitoring
    telemetry.py         # Telemetry Service
    hardware/            # Hardware Services (RAID, SMART)
    cloud/               # Cloud Import Services
    vpn/                 # VPN Services
    power/               # Power Management (wenn vorhanden)
    notifications/       # Notification Services
    versioning/          # File Versioning
    email_service.py     # Email Notifications
    totp_service.py      # 2FA/TOTP Service
    token_service.py     # Token Management
    websocket_manager.py # WebSocket Management
    upload_progress.py   # Upload Progress Tracking
    user_metadata_cache.py # User Metadata Cache
    jobs.py              # Background Jobs
    scheduler_service.py # Scheduler Service
    scheduler_worker_service.py # Scheduler Worker
    benchmark_service.py # Benchmark Service
    samba_service.py     # Samba Integration
    webdav_service.py    # WebDAV Service
    update_service.py    # Update Service
    service_status.py    # Service Status Management
    rate_limit_config.py # Rate Limit Config Service
    ssh_service.py       # SSH Service
    monitoring/          # Monitoring Orchestrator
  middleware/            # Custom Middleware
    device_tracking.py   # Device Tracking
    local_only.py        # Local Network Only
    security_headers.py  # Security Headers
    error_counter.py     # Error Counting
  plugins/               # Plugin System
    manager.py           # Plugin Manager
  schemas/               # Pydantic Models (Request/Response)
    auth.py              # Login, Register, Token
    user.py              # UserPublic, UserCreate, UserUpdate
    files.py             # FileItem, FileListResponse
    system.py            # SystemInfo, StorageInfo, RAIDStatus
    ...                  # (weitere Schemas für alle Endpoints)
  main.py                # FastAPI Application

alembic/                 # Database Migrations
  versions/              # Migration Scripts
  env.py                 # Alembic Configuration

scripts/                 # Utility Scripts
  seed.py                # Database Seeding
  setup/                 # Setup Scripts
  migration/             # Migration Scripts
  benchmark/             # Benchmark Scripts
  debug/                 # Debug Tools
  fixes/                 # Fix Scripts
  test/                  # Test Scripts
  scheduler_worker.py    # Scheduler Worker Process
  webdav_worker.py       # WebDAV Worker Process

tests/                   # Test Suite
  conftest.py            # Test Fixtures & Configuration
  test_*.py              # Unit & Integration Tests
```

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
```

### FileMetadata Table
```sql
CREATE TABLE file_metadata (
    id INTEGER PRIMARY KEY,
    path VARCHAR(1000) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    is_directory BOOLEAN NOT NULL,
    mime_type VARCHAR(100),
    parent_path VARCHAR(1000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - User Login
- `POST /api/auth/register` - User Registration
- `POST /api/auth/logout` - User Logout
- `POST /api/auth/refresh` - Refresh Access Token
- `GET /api/auth/me` - Get Current User
- `POST /api/auth/2fa/setup` - Setup 2FA/TOTP
- `POST /api/auth/2fa/verify` - Verify 2FA Code

### Users (Admin Only)
- `GET /api/users/` - List all users
- `POST /api/users/` - Create user
- `PUT /api/users/{id}` - Update user
- `DELETE /api/users/{id}` - Delete user

### Files
- `GET /api/files/list?path=` - List files/folders
- `GET /api/files/download/{path}` - Download file
- `POST /api/files/upload` - Upload file(s)
- `POST /api/files/upload/chunk` - Chunked upload
- `POST /api/files/folder` - Create folder
- `DELETE /api/files/{path}` - Delete file/folder
- `PUT /api/files/rename` - Rename file/folder
- `PUT /api/files/move` - Move file/folder
- `GET /api/files/storage/available` - Get storage quota
- `GET /api/files/upload-progress/{id}` - Upload progress

### Shares
- `GET /api/shares/` - List shares
- `POST /api/shares/` - Create share
- `DELETE /api/shares/{id}` - Delete share
- `GET /api/shares/public/{token}` - Access public share

### Backups
- `GET /api/backups/` - List backups
- `POST /api/backups/` - Create backup
- `POST /api/backups/{id}/restore` - Restore backup
- `DELETE /api/backups/{id}` - Delete backup

### Sync
- `GET /api/sync/folders` - List sync folders
- `POST /api/sync/folders` - Create sync folder
- `GET /api/sync/conflicts` - List conflicts
- `POST /api/sync/conflicts/{id}/resolve` - Resolve conflict
- `POST /api/sync/delta` - Get delta changes

### Mobile
- `GET /api/mobile/devices` - List mobile devices
- `POST /api/mobile/register` - Register device
- `GET /api/mobile/camera/settings` - Camera backup settings
- `POST /api/mobile/camera/upload` - Camera upload

### System
- `GET /api/system/info` - System information
- `GET /api/system/storage` - Storage statistics
- `GET /api/system/raid` - RAID status
- `GET /api/system/smart` - SMART disk health
- `GET /api/system/telemetry` - Historical metrics

### Power Management
- `GET /api/power/status` - Power status
- `GET /api/power/presets` - Power presets
- `POST /api/power/presets` - Create preset
- `PUT /api/power/presets/{id}/apply` - Apply preset

### Fan Control
- `GET /api/fans/` - Fan status
- `POST /api/fans/mode` - Set fan mode
- `POST /api/fans/speed` - Set fan speed

### Energy Monitoring
- `GET /api/energy/` - Energy consumption data
- `GET /api/energy/prices` - Energy price config

### Tapo Smart Plugs
- `GET /api/tapo/devices` - List Tapo devices
- `POST /api/tapo/devices` - Add device
- `GET /api/tapo/devices/{id}/status` - Device status

### VPN
- `GET /api/vpn/status` - VPN status
- `GET /api/vpn/profiles` - VPN profiles
- `POST /api/vpn/profiles` - Create profile
- `DELETE /api/vpn/profiles/{id}` - Delete profile

### Schedulers
- `GET /api/schedulers/` - List scheduled tasks
- `POST /api/schedulers/` - Create scheduled task
- `PUT /api/schedulers/{id}` - Update task
- `DELETE /api/schedulers/{id}` - Delete task

### Plugins
- `GET /api/plugins/` - List plugins
- `POST /api/plugins/{name}/enable` - Enable plugin
- `POST /api/plugins/{name}/disable` - Disable plugin

### Cloud Import
- `GET /api/cloud/providers` - Available providers
- `POST /api/cloud/import` - Start import
- `GET /api/cloud/import/{id}/status` - Import status

### WebDAV
- `GET /api/webdav/status` - WebDAV status
- `POST /api/webdav/start` - Start WebDAV
- `POST /api/webdav/stop` - Stop WebDAV

### Samba
- `GET /api/samba/shares` - Samba shares
- `POST /api/samba/shares` - Create share
- `DELETE /api/samba/shares/{name}` - Delete share

### Monitoring
- `GET /api/monitoring/status` - Monitoring status
- `GET /api/metrics` - Prometheus metrics

### Admin
- `GET /api/admin/db/health` - Database health
- `GET /api/admin/rate-limits` - Rate limit config
- `POST /api/admin/rate-limits` - Update rate limits
- `GET /api/admin/services` - Service status

### Notifications
- `GET /api/notifications/` - List notifications
- `POST /api/notifications/settings` - Update settings

### Updates
- `GET /api/updates/check` - Check for updates
- `POST /api/updates/install` - Install update

### VCL (Version Control Light)
- `POST /api/vcl/execute` - Execute command
- `GET /api/vcl/history` - Command history

### Logging
- `GET /api/logging/audit` - Audit logs
- `GET /api/logging/disk-io` - Disk I/O history

### Health
- `GET /api/health` - Health check

**Vollständige API-Referenz**: `http://localhost:3001/docs`

## RAID Settings (CI and Production Safety)

Two environment settings control RAID backend selection and safety:

- `RAID_FORCE_DEV_BACKEND`: when set to `1` forces the use of the development (simulated) RAID backend even on Linux. Useful for CI runners without `mdadm` or for safe unit tests.
- `RAID_ASSUME_CLEAN_BY_DEFAULT`: when set to `1`, `mdadm --create` will include `--assume-clean`. WARNING: this is dangerous in production and should remain `0` except in isolated test VMs.

For full details and self-hosted runner instructions, see: `docs/RAID_CI_AND_SETTINGS.md`.

## Authentication

### JWT Token
```python
# Login Request
POST /api/auth/login
{
  "username": "admin",
  "password": "changeme"
}

# Response
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "1",
    "username": "admin",
    "email": "admin@baluhost.local",
    "role": "admin"
  }
}

# Verwendung in Requests
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

## Testing

### Unit Tests
```bash
# Alle Tests
pytest tests/ -v

# Nur Metadata Tests
pytest tests/test_file_metadata_db.py -v

# Mit Coverage
pytest tests/ --cov=app --cov-report=term-missing
```

### Integration Tests
```bash
# API Integration Tests
pytest tests/test_files_api_integration.py -v

# Spezifischer Test
pytest tests/test_files_api_integration.py::test_create_folder_creates_metadata -v
```

### Test Coverage
- 25+ Unit Tests
- 8 Integration Tests
- Database-backed Fixtures
- Automatic Rollback für Test Isolation

## Deployment

### Production Setup
```bash
# Environment Variables
export DATABASE_URL="postgresql://user:pass@localhost/baluhost"
export NAS_MODE="production"
export TOKEN_SECRET="your-secret-key-here"

# Run Migrations
alembic upgrade head

# Create Admin User
python scripts/seed.py

# Start with Gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker (Optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Documentation

- **API Docs**: http://localhost:3001/docs (Swagger UI)
- **ReDoc**: http://localhost:3001/redoc
- **Deployment**: `docs/DEPLOYMENT.md`

## Nächste Schritte
- Weitere Plugin-Integrationen entwickeln
- Cluster-Support für Multi-Node-Setups
- LDAP/Active Directory Integration
- S3-kompatible API für externe Tools
