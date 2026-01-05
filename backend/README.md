# Baluhost Python Backend

FastAPI-basierter Backend für NAS-Management mit vollständiger Database-Integration.

## Features
- **JWT Authentication** - Sichere Token-basierte Auth
- **SQLite/PostgreSQL Database** - Persistente Datenspeicherung mit Alembic Migrations
- **User Management** - CRUD Operations mit Rollen (Admin/User)
- **File Metadata** - Database-backed Ownership & Permissions
- **File Sharing** - Public Links mit Passwortschutz und Ablaufdatum
- **Backup & Restore** - Vollständige und inkrementelle Backups mit Verschlüsselung
- **Sync System** - Desktop Sync Client mit Konfliktauflösung
- **Mobile Support** - Geräteregistrierung und Kamera-Backup
- **System Monitoring** - CPU, RAM, Disk, Network via psutil
- **RAID Management** - Simulation im Dev-Mode, Production-Ready
- **Audit Logging** - Comprehensive Security & File Operation Logs
- **Quota System** - Storage Limits & Monitoring
- **Custom API Docs** - Styled Swagger UI matching frontend design
- **Network Discovery** - mDNS/Bonjour for automatic server discovery
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
      shares.py          # File Sharing
      backup.py          # Backup & Restore
      sync.py            # Sync System
      sync_advanced.py   # Advanced Sync Features
      mobile.py          # Mobile Device Management
      system.py          # System Metrics, RAID, SMART
      logging.py         # Audit Logs API
    docs.py              # Custom Swagger UI Styling
    deps.py              # Dependencies (Auth, DB Session)
  core/
    config.py            # Settings & Logging Setup
    database.py          # SQLAlchemy Engine & Session
  models/                # SQLAlchemy ORM Models
    base.py              # Base Model
    user.py              # User Model
    file_metadata.py     # FileMetadata Model
    share.py             # Share Model
    backup.py            # Backup Model
    sync_folder.py       # SyncFolder Model
    mobile_device.py     # MobileDevice Model
  services/              # Business Logic Layer
    auth.py              # JWT Token & Authentication
    users.py             # User CRUD Operations
    files.py             # File Operations (Upload, Delete, etc.)
    shares.py            # File Sharing Logic
    backup.py            # Backup/Restore Operations
    sync.py              # Sync Logic
    sync_background.py   # Background Sync Scheduler
    mobile.py            # Mobile Device Management
    network_discovery.py # mDNS/Bonjour Service
    file_metadata_db.py  # File Metadata DB Operations
    permissions.py       # Permission Checks
    audit_logger.py      # Security & File Audit Logging
    system.py            # System Metrics (CPU, RAM, Disk)
    disk_monitor.py      # Disk I/O Monitoring
    raid.py              # RAID Management
    smart.py             # SMART Disk Health
    network_discovery.py # mDNS/Bonjour Service

## API Endpoints

### Core Endpoints
- **Auth**: `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- **Files**: `/api/files/list`, `/api/files/upload`, `/api/files/download`, `/api/files/permissions`
- **Shares**: `/api/shares` - File sharing with public links
- **Backups**: `/api/backups` - Backup creation and restoration
- **Sync**: `/api/sync/folders`, `/api/sync/conflicts` - Desktop sync
- **Mobile**: `/api/mobile/devices`, `/api/mobile/camera/settings` - Mobile device management
- **Users**: `/api/users` - User management (Admin only)
- **System**: `/api/system/info`, `/api/system/raid/status`, `/api/system/smart/status`
- **Logging**: `/api/logging/audit`, `/api/logging/disk-io`

**Vollständige API-Referenz**: `http://localhost:3001/docs`
  schemas/               # Pydantic Models (Request/Response)
    auth.py              # Login, Register, Token
    user.py              # UserPublic, UserCreate, UserUpdate
    files.py             # FileItem, FileListResponse
    system.py            # SystemInfo, StorageInfo, RAIDStatus
  main.py                # FastAPI Application

alembic/                 # Database Migrations
  versions/              # Migration Scripts
  env.py                 # Alembic Configuration

scripts/                 # Utility Scripts
  seed.py                # Database Seeding
  reset_dev_storage.py   # Dev Storage Reset
  dev_check.py           # Development Health Check

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
- `GET /api/auth/me` - Get Current User

### Users (Admin Only)
- `GET /api/users/` - List all users
- `POST /api/users/` - Create user
- `PUT /api/users/{id}` - Update user
- `DELETE /api/users/{id}` - Delete user

### Files
- `GET /api/files/list?path=` - List files/folders
- `GET /api/files/download/{path}` - Download file
- `POST /api/files/upload` - Upload file(s)
- `POST /api/files/folder` - Create folder
- `DELETE /api/files/{path}` - Delete file/folder
- `PUT /api/files/rename` - Rename file/folder
- `PUT /api/files/move` - Move file/folder
- `GET /api/files/storage/available` - Get storage quota

### System
- `GET /api/system/info` - System information
- `GET /api/system/storage` - Storage statistics
- `GET /api/system/raid` - RAID status
- `GET /api/system/smart` - SMART disk health
- `GET /api/system/telemetry` - Historical metrics

### Logging
- `GET /api/logging/audit` - Audit logs
- `GET /api/logging/disk-io` - Disk I/O history

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
- **Database Migration**: `docs/DATABASE_MIGRATION.md`
- **Integration Complete**: `docs/DATABASE_INTEGRATION_COMPLETE.md`
- **Migration Summary**: `MIGRATION_SUMMARY.md`

## Nächste Schritte
- SQLite/PostgreSQL anbinden und Mock-Daten ablösen
- Persistente File-Metadaten und Quotas modellieren
- Upload-Progress, Sharing und Websocket-Events ergänzen
- Express-Backend mittelfristig ablösen und FastAPI auch produktiv einsetzen
