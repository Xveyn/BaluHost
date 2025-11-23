# BaluHost NAS Manager - Technical Documentation

## Project Overview

**BaluHost** is a full-stack NAS management web application with React TypeScript frontend and Python FastAPI backend. The system provides comprehensive file, user, and system management with a focus on security, performance, and developer-friendliness.

### Technology Stack

**Frontend:**
- React 18 mit TypeScript
- Vite (Build-Tool & Dev-Server)
- Tailwind CSS (Styling)
- React Router (Navigation)
- Recharts (Visualisierung)

**Backend:**
- Python 3.11+ mit FastAPI
- Pydantic (Data Validation)
- Uvicorn (ASGI Server)
- psutil (System-Monitoring)
- JWT (Authentication)

---

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
```

#### Seed Data (Dev-Mode):
- Admin: `admin` / `admin123`
- User: `user` / `user123`

---

### 2. File Management

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

### 3. User Management

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

### 4. System Monitoring & Telemetry

**Services:** `app/services/system.py`, `app/services/telemetry.py`, `app/services/disk_monitor.py`  
**API Route:** `app/api/routes/system.py`  
**Schemas:** `app/schemas/system.py`

#### Implemented Features:

##### 4.1 System Info
- CPU usage (psutil)
- RAM usage (Total, Used, Free)
- Network statistics (Sent/Received)
- Uptime & operating system info

##### 4.2 Telemetry History
- **Background Task** collects metrics every N seconds
- Configurable: `TELEMETRY_INTERVAL_SECONDS` (Default: 3s)
- History size: `TELEMETRY_HISTORY_SIZE` (Default: 60 Samples)
- Metrics: CPU%, RAM%, Network TX/RX

##### 4.3 Disk I/O Monitor
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

##### 4.4 Storage Info
- Total storage & usage
- Available storage
- Quota information

##### 4.5 Process List
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

### 5. RAID Management

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

### 6. SMART Monitoring

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

### 7. Audit Logging

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

### 8. Background Jobs

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

### 9. Dev-Mode Simulation

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

Complete API reference: See `README.md` in root directory.

**FastAPI Docs (automatically generated):**
- Swagger UI: http://localhost:3001/docs
- ReDoc: http://localhost:3001/redoc

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

**Last Updated:** November 2025  
**Version:** 1.0.0  
**Maintainer:** Xveyn
