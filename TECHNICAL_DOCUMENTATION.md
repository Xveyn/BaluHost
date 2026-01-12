# BaluHost — Technical Documentation (Neu, 20. Dezember 2025)

Kurzfassung
-
BaluHost ist eine Full‑Stack NAS-Management-Anwendung. Das Backend ist in Python (FastAPI) implementiert, das Frontend ist ein React + TypeScript Single-Page-Application (Vite). Diese Dokumentation beschreibt Architektur, Komponenten, Deployment- und Entwicklungs-Workflows und zeigt ein ASCII-Diagramm, wie Frontend und Backend miteinander zusammenspielen.

Version & Datum
-
- **Version:** 1.3.0
- **Last Updated:** 20. Dezember 2025
- **Maintainer:** Xveyn

Technologie-Überblick
-
- Frontend: React 18, TypeScript, Vite, Tailwind CSS
- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic
- Runtime: Uvicorn (ASGI)
- System & Monitoring: psutil, smartctl (optional, Linux)
- Auth: JWT (Access + Refresh flows)
- DB (dev): SQLite; Production: PostgreSQL empfohlen

Projektstruktur (Wichtigste Ordner)
-
- `backend/` — FastAPI App (`app/`), Services, Dev‑Storage, Scripts
- `client/` — React App (Vite), `src/pages`, `src/api`, `src/lib/api.ts`
- `docs/` — technische How‑tos, RAID, Telemetrie, Mobile, etc.
- `start_dev.py` — kombiniertes Dev-Start-Skript

----------------------------------------
Architektur-Übersicht (ASCII)
-
Dieses Diagramm zeigt die wichtigsten Laufzeit-Komponenten und wie sie interagieren.
Architektur-Übersicht (ASCII)
-
Dieses Diagramm zeigt die wichtigsten Laufzeit-Komponenten und wie sie interagieren.

```text
  +----------------------+            +----------------------+            +---------------------+
  |  Developer / Browser | <---HTTP-->|  Frontend (Vite)     | <---XHR--->|  API Client (axios) |
  |  (React SPA)         |            |  client/src/...      |            |  client/src/lib/api |
  +----------------------+            +----------------------+            +----------+----------+
                                                                              |         |
                                                                              |         v
                                                                     +--------+--------------+ 
                                                                     | Backend API (FastAPI) |
                                                                     | backend/app/main.py   |
                                                                     +---+----+----+---------+
                                                                         |    |    |
                                           +-----------------------------+    |    +------------------+
                                           |                                  |                       |
                                           v                                  v                       v
                                +------------------+                  +-------------+      +--------------------+
                                | Services Layer        |             |   Background   |      | Dev / Prod Storage |
                                | backend/app/services/ |             | Jobs (jobs.py) |      | - dev-storage/     |
                                +--+--+---+---+----+--+               |  +-------+------+      +--------------------+
                                   |  |   |   |   |                             |  
                                   |  |   |   |   |                             v
                   +---------------+  |   |   |   |                 +---------------------------+
                   |                  |   |   |   |                 | Disk I/O Monitor, SMART   |
                   v                  v   v   v   v                 | (disk_monitor.py, smart.py)|
             +---------+   +---------+ +-----+ +------+              +---------------------------+
             | Auth &  |   | Files   | | RAID| | Tele- | 
             | Users   |   | (files) | | (raid)| | metry |     +----------------+
             | (auth.py|   |         | |      | | (telemetry)   | Database (SQLAlchemy) |
             +---------+   +---------+ +-----+ +------+        | backend/app/models/    |
                                                              +------------------------+
``` 

Erläuterung
-
- Browser <> Frontend: SPA served by Vite dev server während Entwicklung oder statisch aus `client/dist/` in Produktion.
- Frontend <> Backend: REST/JSON über `client/src/lib/api.ts` (axios) zu FastAPI Endpoints (`/api/*`).
- Backend Services: Logik in `backend/app/services/` (z. B. `files.py`, `raid.py`, `smart.py`, `telemetry.py`, `audit_logger.py`).
- Background Jobs: Telemetrie-Collector, Disk I/O Sampler, Job-Manager lebt in `app/services` + Lifespan events.
- Storage: Dev-Mode Sandbox unter `backend/dev-storage/` (mit Mock-RAID) oder echte Mountpoints in Production; Metadaten in `.metadata.json` plus DB‑Referenzen.

----------------------------------------
Backend — Komponenten & Pfade
-
- App-Entry: `backend/app/main.py` (FastAPI app + Lifespan)
- API-Routen: `backend/app/api/routes/` (z. B. `auth.py`, `files.py`, `system.py`, `logging.py`)
- Services (Business-Logic): `backend/app/services/` —
  - `auth.py` — JWT, Login/Refresh, Role handling
  - `files.py` — Upload/Download, Mountpoints, Quota checks
  - `raid.py` — RAID-Status, Simulation & Control (Dev-Mode)
  - `disk_monitor.py` / `smart.py` — Disk I/O & SMART
  - `telemetry.py` — Telemetry collection & history
  - `audit_logger.py` — JSON-Audit-Logs & API access
  - `vpn.py`, `mobile.py` — WireGuard config + mobile pairing
- Schemas: `backend/app/schemas/` (Pydantic Models für Requests/Responses)
- Models/ORM: `backend/app/models/` (SQLAlchemy)
- Migrations: Alembic (`alembic/`)

Wichtige Endpoints (Auszug)
-
- `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`
- `GET /api/files/mountpoints`, `POST /api/files/upload`, `GET /api/files/download`
- `GET /api/system/raid/status`, `POST /api/system/raid/rebuild`
- `GET /api/system/smart/status`, `GET /api/system/disk-io/history`
- `GET /api/logging/audit`

Security & Auth
-
- JWT Access Tokens (kurze Laufzeit) + Refresh Token Flow (mobile: 30 Tage)
- RBAC: `admin` vs `user` — Endpunkte entsprechend eingeschränkt
- Audit-Logging für sensitive Aktionen (Upload, Delete, VPN-Registration)

----------------------------------------
Frontend — Komponenten & Pfade
-
- App-Entrypoint: `client/src/main.tsx` / `client/src/App.tsx`
- Seiten: `client/src/pages/` — `Dashboard.tsx`, `FileManager.tsx`, `RaidManagement.tsx`, `SystemMonitor.tsx`, `Logging.tsx`, `UserManagement.tsx`
- API-Client: `client/src/lib/api.ts` + modulare Endpunkt-Wrapper in `client/src/api/` (e.g. `raid.ts`, `smart.ts`)
- Hooks: `client/src/hooks/` — `useSystemTelemetry.ts`, `useSmartData.ts`
- UI: Tailwind + lucide-react icons; Recharts für Graphen

Benutzerablauf (Kurz)
-
1. Nutzer öffnet Browser → React SPA lädt → `GET /api/auth/me` prüft Session
2. Dashboard ruft Telemetrie, Storage und RAID-Status per API ab
3. FileManager ruft Mountpoints, List, Upload/Download Endpoints auf; Quota wird vor Upload geprüft
4. Admins sehen zusätzliche Controls (RAID, Disk Format, Create Array)

----------------------------------------
Dev-Mode & Testing
-
- Dev-Flag: `NAS_MODE=dev` (in `backend/app/core/config.py`) aktiviert Sandbox:
  - `backend/dev-storage/` mit Mock-Disks und automatischer Seed-Daten
  - Mock SMART / RAID / Telemetry falls System-APIs fehlen
- Start-Dev (kombiniert):
  ```bash
  python start_dev.py
  ```
- Backend Tests: `cd backend && python -m pytest`

Deployment (Kurz)
-
- Production Backend: `uvicorn app.main:app --host 0.0.0.0 --port 3001`
- Frontend: `npm run build` → `client/dist/` → Serve via Nginx / static host
- DB: Verwende PostgreSQL in Produktion, setze `DATABASE_URL`

Konfigurationsempfehlungen
-
- Telemetry: `TELEMETRY_INTERVAL_SECONDS` (Prod: 3s, Dev: 2s optional)
- Telemetry History: `TELEMETRY_HISTORY_SIZE` (Prod: 60 samples)
- Quota: `NAS_QUOTA_BYTES` oder mountpoint-spezifisch

Dokumentation & Referenzen
-
- API-Referenz: `docs/API_REFERENCE.md`
- RAID-Setup: `docs/RAID_SETUP_WIZARD.md`
- Telemetrie-Empfehlungen: `docs/TELEMETRY_CONFIG_RECOMMENDATIONS.md`
- Audit Logging: `docs/AUDIT_LOGGING.md`
- Mobile/VPN: `docs/MOBILE_TOKEN_SECURITY.md`, `docs/ANDROID_APP_GUIDE.md`, `docs/IOS_APP_GUIDE.md`

Was ist neu / Highlights (Kurz)
-
- Storage Mountpoints (Multi-Drive) & Quota-Prüfung vor Upload
- Disk-Management UI (Format, Create Array, Device Actions)
- Erweiterte Disk I/O + SMART Visualisierung
- QR-basiertes VPN/Mobile Pairing + 30-Tage-Refresh-Tokens
- Audit-Logging als JSON + API-Zugriff

Änderungs- und Releasehinweis
-
- Version: 1.3.0 — Änderungen in Backend-Services (`files.py`, `raid.py`, `disk_monitor.py`, `telemetry.py`, `smart.py`, `audit_logger.py`, `vpn.py`, `mobile.py`) und Frontend-Seiten (`FileManager.tsx`, `RaidManagement.tsx`, `SystemMonitor.tsx`, `Logging.tsx`).

Kontakt & Mitwirkung
-
- Issues/PR: GitHub-Repo → Fork → Branch → PR
- Lokale Dev-Hilfe: `scripts/dev_check.py`, `scripts/reset_dev_storage.py`

Weitere Schritte (optional)
-
- Möchtest du, dass ich eine `docs/CHANGELOG.md` mit Release-Notizen anlege oder die Änderungen direkt commite? 


## ✨ Was ist neu? / What's New (20. Dezember 2025)

- Storage Mountpoints: Multi-Drive- und RAID-Darstellung in UI und Backend (siehe `app/services/files.py` und `client/pages/FileManager.tsx`).
- Quota-System: Konfigurierbare Quotas pro Mountpoint mit Echtzeitprüfung vor Uploads.
- Disk Management UI (Frontend): Verfügbarkeitsliste, Formatierung, Array-Erstellung und Device-Controls in `RaidManagement`.
- Disk I/O Monitor & SMART: Erweiterte Echtzeit-Metriken und historische Ansichten (`app/services/disk_monitor.py`, `app/services/smart.py`, `client/pages/SystemMonitor.tsx`).
- Telemetrie: Empfehlungen und konfigurierbare Intervalle; neues Dokument `docs/TELEMETRY_CONFIG_RECOMMENDATIONS.md`.
- VPN / Mobile: QR-Code-basierte VPN-Registrierung, 30-Tage-Refresh-Tokens für mobile Geräte und verbesserte Pairing-Flows.
- Audit-Logging: Verbesserte Ereignistypen und JSON-Format, API-Zugriff auf Audit-Daten.
- Dev-Mode & Windows: Verbesserter Sandbox-Modus mit Windows-Kompatibilität und Seed-Daten für Entwickler (`start_dev.py`, `backend/dev-storage/`).
- Neue/aktualisierte Dokumentation: `docs/RAID_SETUP_WIZARD.md`, `docs/UPLOAD_PROGRESS.md`, `docs/MOBILE_TOKEN_SECURITY.md`, `docs/TELEMETRY_CONFIG_RECOMMENDATIONS.md`.

## Änderungen (Kurzüberblick)

- Backend: Erweiterungen in `app/services/` — insbesondere `files.py`, `raid.py`, `disk_monitor.py`, `telemetry.py`, `smart.py`, `audit_logger.py`, `vpn.py`, `mobile.py`.
- Frontend: Neue/erweiterte Seiten in `client/src/pages/` — `FileManager.tsx`, `RaidManagement.tsx`, `SystemMonitor.tsx`, `Logging.tsx`.
- Docs: Viele technische Ergänzungen und How‑tos im `docs/`-Verzeichnis (RAID, Telemetrie, Backup/Restore, Mobile/VPN).
- Konfiguration: Neue Umgebungs-/Konfigurationsoptionen für Quotas, Telemetrie-Intervalle und Dev-Mode-Seed.


## 🔧 Backend Features

### 1. Authentication & Authorization

**Service:** `app/services/auth.py`  
**API Route:** `app/api/routes/auth.py`

#### Implemented Features:
- **JWT Token-based Authentication**
  - Access Tokens with configurable expiry
  - Secure token generation with HS256
  - Token validation in protected routes

- **Role System**
  - `admin`: Full access to all resources
  - `user`: Limited access to own files

- **User Context**
  - Authentication middleware populates `request.user`
  - User ID and roles available in every request

#### API Endpoints:
```
POST /api/auth/login       - User login
POST /api/auth/logout      - User logout
GET  /api/auth/me          - Current user
POST /api/auth/refresh     - Refresh access token (mobile)
```

#### Seed Data (Dev-Mode):
- Admin: `admin` / `admin123`
- User: `user` / `user123`

#### Token Refresh (Mobile Support):
- **Purpose:** Allow mobile clients to refresh expired access tokens without re-authentication
- **Flow:**
  1. Mobile registration returns 30-day refresh token with unique JTI
  2. App stores refresh token in secure storage (Keychain)
  3. When access token expires, call `/api/auth/refresh` with refresh token
  4. Backend checks revocation status before issuing new access token
  5. Receive new access token (if not revoked)

#### Refresh Token Revocation (Security Feature):
- **Database Model:** `RefreshToken` stores all issued refresh tokens with metadata
- **JTI (JWT ID):** Each refresh token has a unique identifier for tracking
- **Token Storage:**
  - Token stored as SHA-256 hash (not plaintext)
  - Device ID, IP address, and user agent tracked
  - Revocation status and reason logged
- **Revocation Methods:**
  - `revoke_token(jti)` - Revoke specific token
  - `revoke_all_user_tokens(user_id)` - Revoke all user tokens (e.g., password change)
  - `revoke_device_tokens(device_id)` - Revoke device-specific tokens
- **Security:** Compromised tokens can be immediately revoked, preventing unauthorized access
- **Service:** `app/services/token_service.py`

---

### 2. File Management

#### Granulare Dateiberechtigungen
- Für jede Datei können beliebig viele Berechtigungsregeln (pro Nutzer) gesetzt werden.
- Beim Speichern werden immer alle Regeln für die Datei übertragen und im Backend vollständig ersetzt (keine inkrementelle Änderung).
- Die UI lädt beim Öffnen alle existierenden Regeln aus dem Backend und zeigt sie an.
- Änderungen, Hinzufügen und Entfernen von Regeln werden direkt übernommen.

**Service:** `app/services/files.py`  
**API Route:** `app/api/routes/files.py`  
**Schemas:** `app/schemas/files.py`, `app/schemas/storage.py`

#### Implemented Features:
- **CRUD Operations**
  - Upload (Single & Multi-File)
  - Download
  - Folder creation
  - Rename
  - Move
  - Delete (Files & Folders)

- **Storage Mountpoints / Drive Selector** ⭐ NEW
  - Multi-drive support with visual selector
  - Shows RAID arrays as selectable "drives"
  - Per-mountpoint capacity and usage
  - Path structure: `root\RAID1 Setup - md0\folder\file.txt`
  - See [Storage Mountpoints Documentation](docs/STORAGE_MOUNTPOINTS.md)

- **Quota System**
  - Configurable via `NAS_QUOTA_BYTES` (Default: 5 GB per disk, 2x5GB RAID1)
  - Quota check before each upload
  - Real-time display in Storage Info
  - Per-mountpoint capacity tracking

- **File Ownership & Permissions**
  - Each file/folder has an owner (User ID)
  - Metadata stored in `.metadata.json`
  - Access control: Owner or Admin
  - Permission helpers in `app/services/permissions.py`

- **Sandbox Storage (Dev-Mode)**
  - Isolated storage under `backend/dev-storage/`
  - 2x5GB RAID1 setup (effectively 5 GB, configurable)
  - Automatic seed data on startup
  - Mock RAID arrays for testing

#### API Endpoints:
```
GET    /api/files/mountpoints       - List storage devices/arrays
GET    /api/files/list              - File list
POST   /api/files/upload            - Upload file
GET    /api/files/download          - Download file
POST   /api/files/create-folder     - Create folder
POST   /api/files/rename            - Rename
POST   /api/files/move              - Move
DELETE /api/files/delete            - Delete
```

#### Metadata Structure:
```json
{
  "version": 1,
  "items": {
    "documents/report.pdf": {
      "owner_id": 1,
      "created_at": "2025-11-23T10:00:00Z",
      "size_bytes": 2048000
    }
  }
}
```

---

### 3. File Sharing System

**Service:** `app/services/shares.py`  
**API Route:** `app/api/routes/shares.py`  
**Schemas:** `app/schemas/shares.py`

#### Implemented Features:
- **Public Share Links**
  - Generate unique shareable links for files/folders
  - Optional password protection
  - Configurable expiration dates
  - Access count tracking

- **Share Management**
  - Create, read, update, delete shares
  - List all shares for a user
  - Revoke access at any time
  - Share activity logging

- **Access Control**
  - Password validation for protected shares
  - Expiration check on every access
  - Owner-only management
  - Admin override capabilities

#### API Endpoints:
```
GET  /api/shares                  - List user's shares
POST /api/shares                  - Create new share
GET  /api/shares/{share_id}       - Get share details
DELETE /api/shares/{share_id}     - Delete share
GET  /api/shares/public/{token}   - Access shared resource
```

---

### 4. Backup & Restore System

**Service:** `app/services/backup.py`  
**API Route:** `app/api/routes/backup.py`  
**Schemas:** `app/schemas/backup.py`

#### Implemented Features:
- **Backup Creation**
  - Full and incremental backups
  - Compression support (gzip, bzip2)
  - Encryption with password protection
  - Metadata preservation

- **Backup Management**
  - List all backups with metadata
  - Size and date tracking
  - Automatic cleanup of old backups
  - Verification of backup integrity

- **Restore Operations**
  - Restore from backup with verification
  - Selective file restoration
  - Conflict resolution options
  - Progress tracking

#### API Endpoints:
```
POST /api/backups                      - Create backup
GET  /api/backups                      - List backups
GET  /api/backups/{backup_id}          - Get backup details
POST /api/backups/{backup_id}/restore  - Restore backup
DELETE /api/backups/{backup_id}        - Delete backup
```

---

### 5. Sync System

**Service:** `app/services/sync.py`, `app/services/sync_background.py`  
**API Routes:** `app/api/routes/sync.py`, `app/api/routes/sync_advanced.py`  
**Schemas:** `app/schemas/sync.py`

#### Implemented Features:
- **Desktop Sync Client**
  - Real-time folder synchronization
  - Selective folder sync
  - Conflict detection and resolution
  - Bidirectional sync support

- **Background Processing**
  - Scheduled sync jobs
  - Automatic conflict detection
  - File change monitoring
  - Bandwidth throttling

- **Conflict Resolution**
  - Manual and automatic resolution
  - Version history preservation
  - Conflict notification system
  - Merge strategies

#### API Endpoints:
```
GET  /api/sync/folders                        - List sync folders
POST /api/sync/folders                        - Create sync folder
GET  /api/sync/conflicts                      - List conflicts
POST /api/sync/conflicts/{id}/resolve         - Resolve conflict
GET  /api/sync/status                         - Sync status
POST /api/sync/force                          - Force sync
```

---

### 6. Mobile Support

**Service:** `app/services/mobile.py`  
**API Route:** `app/api/routes/mobile.py`  
**Schemas:** `app/schemas/mobile.py`

#### Mobile Applications:
- **iOS:** See `docs/IOS_APP_GUIDE.md` - Swift/SwiftUI implementation guide
- **Android:** See `docs/ANDROID_APP_GUIDE.md` - Kotlin/Jetpack Compose implementation guide

#### Implemented Features:
- **Device Registration**
  - Secure token-based registration
  - QR code pairing with desktop
  - Device management and tracking
  - Multiple device support per user
  - Device naming and identification
  - 30-day refresh tokens for long-lived sessions

- **Camera Backup**
  - Automatic photo/video backup
  - Configurable backup settings
  - WiFi-only or cellular options
  - Battery-aware scheduling

- **Sync Configuration**
  - Per-device sync folder configuration
  - Selective folder sync on mobile
  - Background sync support
  - Conflict resolution on mobile

#### API Endpoints:
```
POST /api/mobile/token/generate               - Generate registration token (with VPN config)
POST /api/mobile/register                     - Register mobile device
GET  /api/mobile/devices                      - List devices
GET  /api/mobile/devices/{device_id}          - Get device details
PATCH /api/mobile/devices/{device_id}         - Update device
DELETE /api/mobile/devices/{device_id}        - Delete device
GET  /api/mobile/camera/settings/{device_id}  - Get camera backup settings
PUT  /api/mobile/camera/settings/{device_id}  - Update camera settings
```

---

### 7. VPN Integration (WireGuard)

**Service:** `app/services/vpn.py`  
**API Route:** `app/api/routes/vpn.py`  
**Schemas:** `app/schemas/vpn.py`  
**Models:** `app/models/vpn.py`

#### Implemented Features:
- **WireGuard Configuration**
  - Automatic keypair generation (private/public keys)
  - Preshared key support for additional security
  - Client IP assignment from VPN network pool (10.8.0.0/24)
  - Server configuration management (singleton pattern)

- **VPN Client Management**
  - Multiple VPN clients per user
  - Device-specific configurations
  - Client activation/deactivation
  - Last handshake tracking
  - Public key-based authentication

- **QR Code Integration**
  - Desktop generates QR code with VPN config
  - Base64-encoded WireGuard configuration
  - One-time registration token + VPN setup
  - Seamless mobile pairing (scan & connect)

- **Security Features**
  - Immutable user IDs in JWT tokens
  - Time-limited registration tokens (5 minutes)
  - Per-device VPN credentials
  - Automatic key rotation support

#### API Endpoints:
```
POST   /api/vpn/generate-config            - Generate WireGuard config for device
GET    /api/vpn/clients                    - List user's VPN clients
GET    /api/vpn/clients/{client_id}        - Get VPN client details
PATCH  /api/vpn/clients/{client_id}        - Update VPN client (name, active status)
DELETE /api/vpn/clients/{client_id}        - Delete VPN client
POST   /api/vpn/clients/{client_id}/revoke - Revoke VPN access (deactivate)
GET    /api/vpn/server-config               - Get server config (admin only)
POST   /api/vpn/handshake/{client_id}      - Update last handshake timestamp
```

#### Configuration Example:
**Generated WireGuard Config:**
```ini
[Interface]
PrivateKey = <client_private_key>
Address = 10.8.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = <server_public_key>
PresharedKey = <preshared_key>
Endpoint = 192.168.1.100:51820
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
```

#### Database Schema:
**VPN Config Table (Singleton):**
```sql
CREATE TABLE vpn_config (
    id INTEGER PRIMARY KEY,
    server_private_key VARCHAR(64) NOT NULL,
    server_public_key VARCHAR(64) UNIQUE NOT NULL,
    server_ip VARCHAR(15) NOT NULL,
    server_port INTEGER DEFAULT 51820,
    network_cidr VARCHAR(18) NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**VPN Clients Table:**
```sql
CREATE TABLE vpn_clients (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    device_name VARCHAR(100) NOT NULL,
    public_key VARCHAR(64) UNIQUE NOT NULL,
    preshared_key VARCHAR(64) NOT NULL,
    assigned_ip VARCHAR(15) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP,
    last_handshake TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### Dev-Mode:
- **Mock Key Generation:** Uses Base64-encoded random bytes (no `wg` command required)
- **Automatic Testing:** All VPN APIs functional in dev environment
- **Windows Compatible:** No Linux-specific dependencies

---

### 8. User Management

**Service:** `app/services/users.py`  
**API Route:** `app/api/routes/users.py`  
**Schemas:** `app/schemas/user.py`

#### Implemented Features:
- **User CRUD (Admin-Only)**
  - List all users
  - Create user
  - Update user
  - Delete user

- **Role Management**
  - Assign Admin/User roles
  - Role-based access control

- **Password Hashing**
  - Secure storage (Placeholder, in production: bcrypt/argon2)

#### API Endpoints:
```
GET    /api/users           - List all users (Admin)
POST   /api/users           - Create user (Admin)
PUT    /api/users/{id}      - Update user (Admin)
DELETE /api/users/{id}      - Delete user (Admin)
```

---

### 8. System Monitoring & Telemetry

**Services:** `app/services/system.py`, `app/services/telemetry.py`, `app/services/disk_monitor.py`  
**API Route:** `app/api/routes/system.py`  
**Schemas:** `app/schemas/system.py`

#### Implemented Features:

##### 8.1 System Info
- CPU usage (psutil)
- RAM usage (Total, Used, Free)
- Network statistics (Sent/Received)
- Uptime & operating system info

##### 8.2 Telemetry History
- **Background Task** collects metrics every N seconds
- Configurable: `TELEMETRY_INTERVAL_SECONDS` (Default: 3s)
- History size: `TELEMETRY_HISTORY_SIZE` (Default: 60 Samples)
- Metrics: CPU%, RAM%, Network TX/RX

##### 8.3 Disk I/O Monitor
- **Real-time monitoring** of all physical disks
- Sampling: 1 second
- History: 120 samples (2 minutes)
- Metrics:
  - Read/Write MB/s (Throughput)
  - Read/Write IOPS (Operations per Second)
- **Platform Support:**
  - Windows: `PhysicalDrive0`, `PhysicalDrive1`, ...
  - Linux: `sda`, `sdb`, `nvme0n1`, ...
- **Audit Logging:** Automatic summary every 60 seconds

##### 8.4 Storage Info
- Total storage & usage
- Available storage
- Quota information

##### 8.5 Process List
- Top N processes by CPU/RAM
- PID, Name, CPU%, Memory%

#### API Endpoints:
```
GET /api/system/info                - System info
GET /api/system/storage             - Storage info
GET /api/system/quota               - Quota status
GET /api/system/processes           - Process list
GET /api/system/telemetry/history   - Telemetry history
GET /api/system/disk-io/history     - Disk I/O history
```

---

### 9. RAID Management

**Service:** `app/services/raid.py`  
**API Route:** `app/api/routes/system.py`

#### Implemented Features:
- **RAID Status Query**
  - Parses `/proc/mdstat` (Linux) or provides mock data (Dev-Mode)
  - Status: optimal, degraded, rebuilding, inactive

- **RAID Simulation & Control**
  - Degrade array / Start rebuild / Finalize rebuild
  - Bitmap management (internal/none)
  - Write-mostly devices
  - Add/remove spare devices
  - Start integrity check (scrub)
  - Configurable sync limits (min/max kB/s)

- **Disk Management**
  - Retrieve list of available disks
  - Format disks (ext4, ext3, xfs, btrfs)
  - Create RAID arrays (RAID 0, 1, 5, 6, 10)
  - Delete RAID arrays
  - Dev-Mode: 7 mock disks (2x5GB, 2x10GB, 3x20GB) with RAID1 setup (sda1, sdb1 in md0)

#### API Endpoints:
```
GET  /api/system/raid/status            - RAID status
POST /api/system/raid/degrade           - Degrade simulation (Admin)
POST /api/system/raid/rebuild           - Start rebuild (Admin)
POST /api/system/raid/finalize          - Finalize rebuild (Admin)
POST /api/system/raid/options           - Set RAID options (Admin)
GET  /api/system/raid/available-disks   - Available disks (Admin)
POST /api/system/raid/format-disk       - Format disk (Admin)
POST /api/system/raid/create-array      - Create array (Admin)
POST /api/system/raid/delete-array      - Delete array (Admin)
```

#### Mock Data (Dev-Mode):
```json
{
  "healthy": true,
  "arrays": [
    {
      "name": "md0",
      "level": "raid1",
      "status": "optimal",
      "size_bytes": 5368709120,
      "devices": [
        {"name": "sda1", "state": "active"},
        {"name": "sdb1", "state": "active"}
      ],
      "resync_progress": null,
      "bitmap": "internal",
      "sync_action": "idle"
    }
  ],
  "speed_limits": {
    "minimum": 5000,
    "maximum": 200000
  }
}
```

**Available Disks (Dev-Mode):**
```json
{
  "disks": [
    {
      "name": "sda",
      "size_bytes": 5368709120,
      "model": "BaluHost Dev Disk 5GB (Mirror A) (in RAID)",
      "is_partitioned": true,
      "partitions": ["sda1"],
      "in_raid": true
    },
    {
      "name": "sdb",
      "size_bytes": 5368709120,
      "model": "BaluHost Dev Disk 5GB (Mirror B) (in RAID)",
      "is_partitioned": true,
      "partitions": ["sdb1"],
      "in_raid": true
    },
    {
      "name": "sdc",
      "size_bytes": 10737418240,
      "model": "BaluHost Dev Disk 10GB (Backup A)",
      "is_partitioned": true,
      "partitions": ["sdc1"],
      "in_raid": false
    },
    {
      "name": "sdd",
      "size_bytes": 10737418240,
      "model": "BaluHost Dev Disk 10GB (Backup B)",
      "is_partitioned": true,
      "partitions": ["sdd1"],
      "in_raid": false
    },
    {
      "name": "sde",
      "size_bytes": 21474836480,
      "model": "BaluHost Dev Disk 20GB (Archive A)",
      "is_partitioned": true,
      "partitions": ["sde1"],
      "in_raid": false
    },
    {
      "name": "sdf",
      "size_bytes": 21474836480,
      "model": "BaluHost Dev Disk 20GB (Archive B)",
      "is_partitioned": true,
      "partitions": ["sdf1"],
      "in_raid": false
    },
    {
      "name": "sdg",
      "size_bytes": 21474836480,
      "model": "BaluHost Dev Disk 20GB (Archive C)",
      "is_partitioned": true,
      "partitions": ["sdg1"],
      "in_raid": false
    }
  ]
}
```

---

### 10. SMART Monitoring

**Service:** `app/services/smart.py`  
**API Route:** `app/api/routes/system.py`

#### Implemented Features:
- **SMART Status Query**
  - Reads SMART data via `smartctl` (Linux)
  - Mock data in Dev-Mode

- **Health Check**
  - Overall Health: PASSED / FAILED
  - Temperature, Power-On-Hours
  - Reallocated Sectors, Pending Sectors

#### API Endpoints:
```
GET /api/system/smart/status     - SMART status of all disks
```

#### Mock Data (Dev-Mode):
```json
{
  "devices": [
    {
      "device": "/dev/sda",
      "model": "Samsung SSD 870",
      "health": "PASSED",
      "temperature": 35,
      "power_on_hours": 1234,
      "attributes": {
        "reallocated_sectors": 0,
        "pending_sectors": 0
      }
    }
  ]
}
```

---

### 11. Audit Logging

**Service:** `app/services/audit_logger.py`  
**API Route:** `app/api/routes/logging.py`

#### Implemented Features:
- **Event Types:**
  - `FILE_ACCESS`: Upload, Download, Delete, Move, Create Folder
  - `DISK_MONITOR`: Start, Stop, Error, Summary
  - `SYSTEM_EVENT`: Startup, Shutdown, Config Changes

- **Log Format: JSON**
  ```json
  {
    "timestamp": "2025-11-23T10:30:45.123456+00:00",
    "event_type": "FILE_ACCESS",
    "user": "admin",
    "action": "upload",
    "resource": "/documents/report.pdf",
    "success": true,
    "details": {"size_bytes": 2048000}
  }
  ```

- **Configuration:**
  - Dev-Mode: Logging **disabled**
  - Production-Mode: Logging **enabled**
  - Log path: `{nas_temp_path}/audit/audit.log`

- **API Access:**
  - Read audit logs
  - Filter by event type, user, time period

#### API Endpoints:
```
GET /api/logging/audit              - Retrieve audit logs
GET /api/logging/audit/filter       - Filtered logs
```

---

### 12. Background Jobs

**Service:** `app/services/jobs.py`

#### Implemented Features:
- **Telemetry Collection**
  - Periodic background task
  - Collects CPU, RAM, Network
  - Configurable interval

- **Disk I/O Monitor**
  - Continuous sampling
  - 1 second interval
  - Automatic logging every 60s

- **Job Management:**
  - Start/stop background tasks
  - Lifecycle management via FastAPI Lifespan

---

### 13. Database Integration

**ORM:** SQLAlchemy 2.0+  
**Migration Tool:** Alembic  
**Models:** `app/models/`

#### Implemented Features:
- **Database Models**
  - User model with authentication data
  - FileMetadata model for file ownership
  - Share model for file sharing
  - Backup model for backup management
  - SyncFolder model for sync configuration
  - MobileDevice model for mobile registration
  - AuditLog model for security logging

- **Database Operations**
  - CRUD operations via SQLAlchemy
  - Relationship management (foreign keys)
  - Transaction support
  - Database session management

- **Migrations**
  - Alembic for schema versioning
  - Automatic migration generation
  - Rollback support
  - Database upgrade/downgrade

- **Database Support**
  - SQLite for development
  - PostgreSQL for production
  - Configurable via DATABASE_URL

#### Database Schema:
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE file_metadata (
    id INTEGER PRIMARY KEY,
    path VARCHAR(1000) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    is_directory BOOLEAN NOT NULL,
    mime_type VARCHAR(100),
    parent_path VARCHAR(1000),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE shares (
    id INTEGER PRIMARY KEY,
    token VARCHAR(64) UNIQUE NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    owner_id INTEGER NOT NULL,
    password_hash VARCHAR(255),
    expires_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

-- Additional tables: backups, sync_folders, mobile_devices, audit_logs
```

---

### 14. Custom API Documentation

**Module:** `app/api/docs.py`

#### Implemented Features:
- **Custom Swagger UI**
  - BaluHost branded styling
  - Matches frontend design (dark theme, glassmorphism)
  - Custom colors and fonts
  - Enhanced readability

- **Styling Features**
  - Dark background with gradient
  - Custom topbar with BaluHost branding
  - Color-coded HTTP methods (GET, POST, PUT, DELETE)
  - Glassmorphism effects on cards
  - Smooth transitions and hover effects

- **Documentation Access**
  - Swagger UI: `/docs`
  - ReDoc: `/redoc`
  - Auto-generated from FastAPI schemas

---

### 15. Dev-Mode Simulation

**Configuration:** `app/core/config.py`  
**Services:** All services with Dev-Mode support

#### Implemented Features:
- **Environment Flag:** `NAS_MODE=dev`
- **Sandbox Storage:** `backend/dev-storage/` (2x5GB RAID1 setup, effectively 5 GB)
- **Mock Data:**
  - Users (admin, user)
  - Files & folders (demo structure)
  - RAID status
  - SMART data
  - System metrics (when psutil not available)

- **Windows Compatibility:**
  - All features work on Windows
  - No Linux-specific code required
  - Disk I/O monitor detects Windows disks

- **Seed Data:**
  - Automatic initialization on startup
  - Demo folders: Documents, Media
  - Demo files with owner metadata

#### Scripts:
- `start_dev.py` - Combined frontend + backend start
- `scripts/dev_check.py` - API test script
- `scripts/reset_dev_storage.py` - Reset sandbox

---

## 🎨 Frontend Features

### 1. Authentication

**Component:** `src/pages/Login.tsx`  
**API Client:** `src/lib/api.ts`

#### Implemented Features:
- **Login Form**
  - Username & password
  - Error handling
  - Redirect after successful login

- **JWT Token Handling**
  - Token in localStorage
  - Automatic addition to API requests (Authorization Header)
  - Token refresh (Placeholder)

- **Protected Routes**
  - Redirect to login when not authenticated
  - Role-based route guards (admin pages)

---

### 2. Dashboard

**Component:** `src/pages/Dashboard.tsx`  
**Hook:** `src/hooks/useSystemTelemetry.ts`

#### Implemented Features:
- **System Overview:**
  - CPU usage (real-time)
  - RAM usage (real-time)
  - Network statistics (Sent/Received)
  - Storage overview (Used/Total)

- **Live Charts (Recharts):**
  - CPU sparkline (last 60 seconds)
  - RAM sparkline (last 60 seconds)
  - Network sparkline (TX/RX)

- **Auto-Refresh:**
  - Polling every 5 seconds
  - Custom hook: `useSystemTelemetry`

- **Stat Cards:**
  - Current values prominent
  - Color coding (Green/Yellow/Red)
  - Icons for visual orientation

---

### 3. File Manager

**Component:** `src/pages/FileManager.tsx`

#### Implemented Features:
- **File Browser:**
  - Breadcrumb navigation
  - Folder hierarchy
  - File/folder list with icons

- **Operations:**
  - Upload (Multiple Files)
  - Download
  - Create folder
  - Rename (Modal)
  - Move (Modal)
  - Delete (Confirmation)

- **Permissions:**
  - Owner display
  - Actions only visible for owner/admin
  - Error feedback for missing rights

- **UI Features:**
  - File sizes formatted (KB, MB, GB)
  - Date formatted (locale)
  - Context menu (Right-click, Placeholder)
  - Loading states

---

### 4. User Management (Admin)

**Component:** `src/pages/UserManagement.tsx`

#### Implemented Features:
- **User List:**
  - Table with ID, Username, Role
  - Sorting (Placeholder)

- **CRUD Operations:**
  - Create user (Modal)
  - Edit user (Modal)
  - Delete user (Confirmation)

- **Role Management:**
  - Admin/User dropdown
  - Role update via API

- **Validation:**
  - Client-side form validation
  - Server error handling

---

### 5. RAID Management

**Component:** `src/pages/RaidManagement.tsx`  
**API Client:** `src/api/raid.ts`

#### Implemented Features:

##### 5.1 RAID Status & Control
- **RAID Status Display:**
  - Array name, level, status, bitmap, sync action
  - Device list with states (active, failed, rebuilding, spare, write-mostly)
  - Resync progress with visual progress bar
  - Capacity & device count
  - Sync speed limits (min/max kB/s)

- **RAID Control (Admin):**
  - Enable/disable bitmap
  - Start integrity check (scrub)
  - Degrade array (Simulation/Real)
  - Start rebuild for failed devices
  - Finalize rebuild
  - Delete array (with confirmation)

- **Device Management:**
  - Degrade individual devices
  - Start rebuild for specific devices
  - Set/remove write-mostly status
  - Remove spare devices
  - Add new spare device (form)

- **Sync Limits:**
  - Configure min/max speed (kB/s)
  - Form for speed limits

##### 5.2 Disk Management (NEW)
- **Available Disks:**
  - Table with name, size, model, status
  - Status badges: "In RAID", "Partitioned"
  - Auto-refresh available disks

- **Disk Formatting:**
  - Modal dialog for formatting
  - Filesystem selection (ext4, ext3, xfs, btrfs)
  - Optional: Set label
  - Only available for disks not in RAID

- **Array Creation:**
  - Modal dialog for new arrays
  - RAID level selection (0, 1, 5, 6, 10)
  - Device input (comma-separated)
  - Optional: Spare devices
  - Array name input

- **UI Features:**
  - Loading states for all operations
  - Error/Success toasts
  - Confirmation dialogs for destructive actions
  - Buttons disabled when disk in RAID
  - Auto-refresh every 8 seconds

---

### 6. System Monitor

**Component:** `src/pages/SystemMonitor.tsx`  
**Hooks:** `src/hooks/useSystemTelemetry.ts`, `src/hooks/useSmartData.ts`

#### Implemented Features:

##### 6.1 Disk I/O Monitor
- **Disk Selection:**
  - Button group for all physical disks
  - Active disk highlighted

- **Real-Time Charts:**
  - Read/Write throughput (MB/s)
  - Read/Write IOPS
  - Toggle between views
  - 60 seconds history
  - Auto-update every 2 seconds

- **Stat Cards:**
  - Current read MB/s
  - Current write MB/s
  - Current read IOPS
  - Current write IOPS

##### 6.2 SMART Status
- **Device List:**
  - Model, device path
  - Health status (badge)
  - Temperature

- **Attributes:**
  - Power-on-hours
  - Reallocated sectors
  - Pending sectors

- **Refresh:**
  - Manual refresh button
  - Loading state

##### 6.3 Process List
- **Top Processes:**
  - PID, name, CPU%, Memory%
  - Sorted by CPU usage
  - Limit: Top 10

---

### 7. Audit Logging

**Component:** `src/pages/Logging.tsx`  
**API Client:** `src/api/logging.ts`

#### Implemented Features:
- **Log Display:**
  - Table with timestamp, event type, user, action, resource
  - Color coding by event type

- **Filter:**
  - By event type
  - By user
  - By time period (Placeholder)

- **Pagination:**
  - Next/Previous
  - Configurable limit

- **Details View:**
  - Modal with complete log details
  - JSON-formatted details

- **Export:**
  - Download as JSON (Placeholder)

---

### 8. Layout & Navigation

**Component:** `src/components/Layout.tsx`

#### Implemented Features:
- **Sidebar Navigation:**
  - Logo
  - Navigation links (Dashboard, Files, Users, RAID, Monitor, Logs)
  - Active state highlighting
  - Icons (lucide-react)

- **Header:**
  - Breadcrumb (optional)
  - User menu (Logout)

- **Responsive Design:**
  - Mobile menu (Toggle, Placeholder)
  - Breakpoints via Tailwind

- **Protected Layout:**
  - Checks auth status
  - Redirect to login if needed

---

### 9. API Client

**Module:** `src/lib/api.ts`, `src/api/*.ts`

#### Implemented Features:
- **Base Client:**
  - Axios instance
  - Authorization header automatic
  - Error handling (401 → Logout)
  - Base URL configurable

- **Type-Safe API Calls:**
  - TypeScript interfaces for all requests/responses
  - Auto-complete in IDE

- **Modular Structure:**
  - `api/raid.ts` - RAID endpoints
  - `api/smart.ts` - SMART endpoints
  - `api/logging.ts` - Logging endpoints

---

### 10. Custom Hooks

#### `useSystemTelemetry.ts`
- Polls system telemetry data
- Interval: 5 seconds
- Manages loading/error states

#### `useSmartData.ts`
- Loads SMART data on-demand
- Manual refresh function

---

## 📁 Project Structure

```
Baluhost/
├── backend/                      # Python FastAPI Backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/           # API endpoints
│   │   │   │   ├── auth.py
│   │   │   │   ├── files.py
│   │   │   │   ├── users.py
│   │   │   │   ├── system.py
│   │   │   │   └── logging.py
│   │   │   └── deps.py           # Dependency Injection
│   │   ├── core/
│   │   │   └── config.py         # Konfiguration & Settings
│   │   ├── models/               # DB-Models (Placeholder)
│   │   ├── schemas/              # Pydantic-Schemas
│   │   │   ├── auth.py
│   │   │   ├── files.py
│   │   │   ├── user.py
│   │   │   └── system.py
│   │   ├── services/             # Business logic
│   │   │   ├── auth.py
│   │   │   ├── files.py
│   │   │   ├── users.py
│   │   │   ├── system.py
│   │   │   ├── telemetry.py
│   │   │   ├── disk_monitor.py
│   │   │   ├── raid.py
│   │   │   ├── smart.py
│   │   │   ├── audit_logger.py
│   │   │   ├── permissions.py
│   │   │   ├── file_metadata.py
│   │   │   ├── shares.py           # File sharing
│   │   │   ├── backup.py           # Backup/restore
│   │   │   ├── sync.py             # Sync system
│   │   │   ├── sync_background.py  # Background sync
│   │   │   ├── mobile.py           # Mobile support
│   │   │   ├── network_discovery.py # mDNS/Bonjour
│   │   │   ├── jobs.py
│   │   │   └── seed.py
│   │   └── main.py               # FastAPI App
│   ├── dev-storage/              # Dev-Mode Sandbox
│   ├── dev-tmp/                  # Dev-Mode Temp (Audit Logs)
│   ├── scripts/
│   │   ├── dev_check.py          # API test script
│   │   ├── reset_dev_storage.py
│   │   └── benchmark_telemetry.py
│   ├── tests/                    # Pytest tests
│   ├── pyproject.toml            # Python project config
│   └── README.md
│
├── client/                       # React TypeScript Frontend
│   ├── src/
│   │   ├── api/                  # API client modules
│   │   │   ├── raid.ts
│   │   │   ├── smart.ts
│   │   │   └── logging.ts
│   │   ├── components/
│   │   │   └── Layout.tsx
│   │   ├── hooks/
│   │   │   ├── useSystemTelemetry.ts
│   │   │   └── useSmartData.ts
│   │   ├── lib/
│   │   │   └── api.ts            # Base API client
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── FileManager.tsx
│   │   │   ├── UserManagement.tsx
│   │   │   ├── RaidManagement.tsx
│   │   │   ├── SystemMonitor.tsx
│   │   │   ├── Logging.tsx
│   │   │   └── SettingsPage.tsx   # User settings & preferences
│   │   ├── contexts/
│   │   │   └── ThemeContext.tsx    # Theme management (prepared for future use)
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── README.md
│
├── server/                       # [LEGACY] Express Backend (no longer active)
│
├── start_dev.py                  # Combined dev start
├── TODO.md                       # Global TODO list
├── TECHNICAL_DOCUMENTATION.md    # This file
└── README.md                     # Project README
```

---

## 🚀 Setup & Deployment

### Development

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"

# Frontend
cd client
npm install

# Kombinierter Start
python start_dev.py
```

**URLs:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:3001/api

### Production (Recommended)

```bash
# Backend
cd backend
pip install .
uvicorn app.main:app --host 0.0.0.0 --port 3001

# Frontend (Build)
cd client
npm run build
# Serve dist/ with Nginx or other web server
```

---

## 🧪 Testing

### Backend
```bash
cd backend
python -m pytest
python -m pytest tests/test_permissions.py -v
```

### Frontend
```bash
cd client
npm run test        # Unit tests (Placeholder)
npm run test:e2e    # E2E tests (Placeholder)
```

---

## 📊 Performance

### Telemetry Benchmark (Windows)
- Sample Time: ~3.8ms
- CPU Impact @ 1s interval: 0.38%
- CPU Impact @ 3s interval: 0.13%

**Recommended Configuration:**
- Dev: 2s interval, 90 samples
- Production: 3s interval, 60 samples

### Disk I/O Monitor
- Sample interval: 1s
- History: 120 samples (2 minutes)
- Overhead: ~0.1% CPU

---

## 🔒 Security

### Implemented:
- JWT tokens with expiry
- Password hashing (Placeholder)
- File ownership & permissions
- Role-based access control (RBAC)
- Audit logging of all critical actions
- Quota system for resource limitation

### TODO:
- Rate limiting
- CSRF protection
- Extend input sanitization
- Security headers
- HTTPS in production

---

## 📝 API Documentation

Complete API reference: See `docs/API_REFERENCE.md`.

**FastAPI Docs (automatically generated with custom styling):**
- Swagger UI: http://localhost:3001/docs (Custom BaluHost design)
- ReDoc: http://localhost:3001/redoc

**Custom Swagger Features:**
- Dark theme matching frontend design
- Glassmorphism effects
- Color-coded endpoints by HTTP method
- Enhanced readability and navigation

---

## 🛠 Developer Tools

### Backend
- `scripts/dev_check.py` - API test script
- `scripts/reset_dev_storage.py` - Reset sandbox
- `scripts/benchmark_telemetry.py` - Performance test

### Frontend
- Vite HMR (Hot Module Replacement)
- React DevTools
- Tailwind CSS IntelliSense

---

## 🎨 Frontend Features

### Settings Page (`SettingsPage.tsx`)

Comprehensive user settings interface with multiple tabs:

#### Profile Tab
- Display user information (username, role, member since)
- Avatar upload and management
- Email address update
- Account information overview (ID, role, creation date)

#### Security Tab
- Password change functionality
- Active session management
- Security settings overview

#### Appearance Tab
- Theme preview system (6 color schemes: Light, Dark, Ocean, Forest, Sunset, Midnight)
- Theme selection interface with color previews
- **Note:** Theme switching prepared but currently uses fixed dark theme
- LocalStorage persistence for theme preferences

#### Storage Tab
- Storage quota visualization with progress bars
- Used vs. available space display
- Percentage-based quota tracking
- Auto-updates from backend `/api/system/quota` endpoint

#### Activity Tab
- Recent audit log entries
- Action history with timestamps
- Success/failure status indicators
- Detailed activity information from `/api/logging/audit` endpoint

**Components:**
- `AppearanceSettings.tsx` - Theme selection component with color previews
- `ThemeContext.tsx` - Theme state management (prepared for future theme switching)

**API Integration:**
- `GET /api/auth/me` - User profile data
- `PUT /api/users/{id}` - Update user information
- `GET /api/system/quota` - Storage quota information
- `GET /api/logging/audit` - Activity logs

---

## 📚 Additional Documentation

- `AUDIT_LOGGING.md` - Audit system details
- `DISK_IO_MONITOR.md` - Disk I/O monitor
- `PERFORMANCE_ANALYSIS.md` - Telemetry performance
- `TELEMETRY_CONFIG_RECOMMENDATIONS.md` - Telemetry configuration
- `DEV_CHECKLIST.md` - Dev-Mode checklist

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push branch (`git push origin feature/AmazingFeature`)
5. Open pull request

---

## 📄 License

[License to be added]

---

**Last Updated:** 20. Dezember 2025  
**Version:** 1.3.0  
**Maintainer:** Xveyn
