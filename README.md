<div align="center">

# 🌐 BaluHost

**Modern Self-Hosted NAS Management Platform**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node Version](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-teal.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

*A powerful, user-friendly web interface for managing your Network Attached Storage (NAS) system*

[Features](#-features) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 📖 About

BaluHost is a full-stack NAS management application built with modern web technologies. It provides comprehensive file management, RAID monitoring, system telemetry, and user access control - all through an intuitive web interface.

**Perfect for:**
- 🏠 Home lab enthusiasts
- 💼 Small office/home office (SOHO) setups
- 🎓 Learning system administration
- 🛠️ Self-hosted storage solutions

### 🔐 Authentication & Security
- JWT-based authentication with role-based access control (RBAC)
- Admin and user roles with granular permissions
- File ownership and access control
- Comprehensive audit logging

### 🏠 Home Network Integration (iCloud/OneDrive Alternative)
- **Windows Service** - Auto-start on boot, runs in background
- **Network Drive** - Mount as `Z:` drive via WebDAV on all devices
- **Auto-Discovery** - mDNS/Bonjour finds servers automatically
- **Desktop Sync Client** - Real-time folder synchronization
- **Web Interface** - Access from any browser in your network
- **Multi-Platform** - Windows, Mac, Linux, iOS, Android support

### 📁 File Management
- Drag & drop file upload
- Multi-file/folder upload support
- **File preview** - Images, videos, audio, PDFs, text files
- **File sharing** - Public links with expiration & password protection
- Create, rename, move, delete operations
- Storage quota enforcement
- File ownership tracking
- Granular file permissions (per-user access control)

### 💾 RAID Management
- Real-time RAID array status monitoring
- Disk health tracking with SMART data
- Simulate degraded/rebuild scenarios (dev mode)
- Production-ready mdadm integration
- Support for RAID 0, 1, 5, 6, 10

### 📊 System Monitoring
- Live CPU, RAM, disk I/O, and network metrics
- Historical telemetry data with charts (Recharts)
- Process monitoring
- SMART disk health status
- Storage capacity tracking

### 💾 Backup & Restore
- Create full or incremental backups
- Schedule automatic backups
- Restore from backup with integrity verification
- Backup compression and encryption support

### 🔄 Sync System
- Desktop sync client for real-time synchronization
- Selective folder sync with conflict resolution
- Multi-device support
- Mobile camera backup (iOS/Android)
- Network discovery via mDNS/Bonjour

### 🎨 Modern UI/UX
- Responsive design with Tailwind CSS
- Real-time updates
- Intuitive navigation
- Dark-themed interface with glassmorphism effects
- Settings page with user profile, security, storage, and activity logs
- Fast loading with Vite HMR

### 🛠️ Developer-Friendly
- **Dev Mode** - Full simulation environment (Windows-compatible!)
- No database required for prototyping
- Hot reload for both frontend and npmbackend
- Comprehensive test suite (pytest)
- Auto-generated API docs (Swagger/ReDoc)

## 🚀 Phase 1 - Production Readiness (2-3 weeks)

BaluHost is currently ~75% production ready. Phase 1 focuses on critical gaps before deployment:

| Task | Status | Timeline | Details |
|------|--------|----------|---------|
| **PostgreSQL Migration** | 🔄 Ready to Start | 4-5 days | Migrate from SQLite to PostgreSQL |
| **Security Hardening** | 🔄 Ready to Start | 3-4 days | Input validation, file security, OWASP compliance |
| **Structured Logging** | 🔄 Ready to Start | 3-4 days | JSON logging, health checks, monitoring-ready |
| **Deployment Docs** | 🔄 Ready to Start | 3-4 days | Docker, Kubernetes, Linux guides, disaster recovery |

👉 **[Start Phase 1 Now](PHASE1_KICKOFF_CHECKLIST.md)** - Everything is prepared!

### Quick Navigation
- 📋 [Phase 1 Kickoff Checklist](PHASE1_KICKOFF_CHECKLIST.md) - Start here!
- 📊 [Phase 1 Action Plan](PHASE1_ACTION_PLAN.md) - Detailed task breakdown
- 📈 [Production Readiness](PRODUCTION_READINESS.md) - Full status checklist
- 💾 [Execution Summary](PHASE1_EXECUTION_SUMMARY.md) - What's been prepared

### What's Ready for Phase 1
- ✅ PostgreSQL setup script & Docker Compose
- ✅ Comprehensive test framework (TDD approach)
- ✅ Migration tool with backup & verification
- ✅ GitHub Issues templates for all 4 tasks
- ✅ Best practices documentation
- ✅ Quality gates & success criteria

---

## Architecture

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, React Router
- **Backend (active):** FastAPI (Python 3.11+), Pydantic, SQLAlchemy, `uvicorn`, background jobs for telemetry
- **Database:** SQLite (dev) / PostgreSQL (production) with Alembic migrations
- **Legacy Backend:** Express/TypeScript (located in `server/`, no longer actively developed)
- **Start Script:** `python start_dev.py` boots FastAPI (Port 3001) and Vite Dev Server (Port 5173)

## API Overview (FastAPI)

- **Auth**
   - `POST /api/auth/login`
   - `POST /api/auth/logout`
   - `GET /api/auth/me`
- **Files**
   - `GET /api/files/list?path=`
   - `POST /api/files/upload`
   - `GET /api/files/download?path=`
   - `POST /api/files/folder`
   - `PUT /api/files/rename`
   - `PUT /api/files/move`
   - `DELETE /api/files/{path}`
   - `GET /api/files/permissions`
   - `PUT /api/files/permissions`
   - `GET /api/files/mountpoints`
- **Shares**
   - `GET /api/shares`
   - `POST /api/shares`
   - `GET /api/shares/{share_id}`
   - `DELETE /api/shares/{share_id}`
   - `GET /api/shares/public/{token}`
- **Backups**
   - `POST /api/backups`
   - `GET /api/backups`
   - `GET /api/backups/{backup_id}`
   - `POST /api/backups/{backup_id}/restore`
- **Sync**
   - `GET /api/sync/folders`
   - `POST /api/sync/folders`
   - `GET /api/sync/conflicts`
   - `POST /api/sync/conflicts/{conflict_id}/resolve`
- **Mobile**
   - `POST /api/mobile/token/generate`
   - `POST /api/mobile/register`
   - `GET /api/mobile/devices`
   - `GET /api/mobile/camera/settings/{device_id}`
- **Users (Admin)**
   - `GET /api/users`
   - `POST /api/users`
   - `PUT /api/users/{id}`
   - `DELETE /api/users/{id}`
- **System & Monitoring**
   - `GET /api/system/info`
   - `GET /api/system/storage`
   - `GET /api/system/quota`
   - `GET /api/system/processes?limit=`
   - `GET /api/system/telemetry/history`
   - `GET /api/system/smart/status`
   - `GET /api/system/raid/status`
   - `POST /api/system/raid/degrade|rebuild|finalize` (Dev-Mode Simulation, Admin)
   - `POST /api/system/raid/options` (Production/Dev configuration via mdadm or Simulator)
- **Logging**
   - `GET /api/logging/audit`
   - `GET /api/logging/disk-io`
   - `GET /api/logging/file-access`
   - `GET /api/logging/stats`

## Setup

### 1. FastAPI Backend (recommended)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Development-Server
uvicorn app.main:app --reload --port 3001

# Tests
python -m pytest
```

### 2. Frontend

```bash
cd client
npm install
npm run dev

# Build/Test
npm run build
```

### 3. Combined Dev Start (Recommended)

```bash
python start_dev.py
```

This script sets `NAS_MODE=dev`, starts FastAPI on Port 3001 and the Vite server on Port 5173, and maintains a 2x5GB RAID1 sandbox under `backend/dev-storage`.

### 4. Production Deployment (Home Network)

For using BaluHost as your personal cloud in your home network (like iCloud/OneDrive):

```powershell
# Install as Windows Service (requires Administrator)
.\scripts\install_windows_service.ps1
```

This will:
- ✅ Install BaluHost as a Windows Service with auto-start
- ✅ Configure firewall rules for local network access
- ✅ Set up WebDAV server for network drive mapping
- ✅ Display your local IP for connecting other devices

**📖 Full Home Network Setup Guide**: [docs/HEIMNETZ_SETUP.md](docs/HEIMNETZ_SETUP.md)

**Access your private cloud:**
- 🌐 Web Interface: `https://YOUR-PC-IP:5173` (frontend) / `https://YOUR-PC-IP:8000` (backend)
- 💾 Network Drive: `\\YOUR-PC-IP@8080\webdav`
- 📱 Desktop Sync Client: `client-desktop/sync_client_gui_v2.py`

### 5. HTTPS Setup (mkcert for Trusted Certificates)

BaluHost uses **mkcert** for locally-trusted HTTPS certificates (no browser warnings):

**✅ Already installed** - Certificates in `dev-certs/` are valid until March 2028

**For mobile devices** (one-time setup):
```powershell
# Export CA certificate for your phone/tablet
.\scripts\export-ca-for-mobile.ps1
```

Then install the CA certificate on your mobile device:
- **Android**: Settings → Security → Install certificate
- **iOS**: Open file → Install Profile → Trust Certificate

**📖 Full Mobile Setup Guide**: [docs/MKCERT_MOBILE_SETUP.md](docs/MKCERT_MOBILE_SETUP.md)

### Legacy Express Backend (optional)

The `server/` folder contains the former Express server. It is no longer actively used. If you still need to start it:

```bash
cd server
npm install
npm run dev
```

The Express variant only offers basic endpoints without RAID/SMART/Quota features.

## Configuration

### Backend `.env` (FastAPI)

```env
APP_NAME=Baluhost NAS API
NAS_MODE=dev
API_PREFIX=/api
HOST=0.0.0.0
PORT=3001

TOKEN_SECRET=change-me-in-prod
TOKEN_EXPIRE_MINUTES=720

ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
ADMIN_EMAIL=admin@example.com

NAS_STORAGE_PATH=./dev-storage
NAS_TEMP_PATH=./dev-tmp
NAS_QUOTA_BYTES=5368709120  # 5 GB (RAID1: 2x5GB physisch, 5GB effektiv)

TELEMETRY_INTERVAL_SECONDS=3.0
TELEMETRY_HISTORY_SIZE=60
```

> In production mode (`NAS_MODE=prod`), real system values are used. In Dev mode, FastAPI provides mock data and initializes the sandbox storage.

### Frontend `.env`

```env
VITE_API_BASE_URL=http://localhost:3001
```

Alternatively, Vite uses the proxy from `client/vite.config.ts`, which automatically forwards `/api` and `/auth` to Port 3001.

## Usage

- Default login: Username `admin`, Password `changeme`
- Change password after first login
- RAID options only accessible with Admin token

### Typical Dev Workflow

1. `python start_dev.py`
2. Open browser: `http://localhost:5173`
3. Check dashboard (Quota, RAID, SMART)
4. Tests: `cd backend && python -m pytest`, `cd client && npm run build`

### 🗂️ Network Drive Access (Dev Mode)

Access the Dev storage as a Windows network drive:

```powershell
# Automatically mount as drive Z:
.\scripts\mount-dev-storage.ps1

# Disconnect
.\scripts\unmount-dev-storage.ps1
```

Now you can manage files via drag & drop in `Z:\` and they are automatically visible in the frontend!

**Additional Options:**
- With SMB (as in production): `.\scripts\mount-dev-storage.ps1 -UseSMB`
- Different drive letter: `.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"`
- Complete guide: [docs/NETWORK_DRIVE_QUICKSTART.md](docs/NETWORK_DRIVE_QUICKSTART.md)

## Project Structure

```
baluhost/
├── backend/          # FastAPI Backend (active code path)
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── main.py
│   ├── scripts/
│   ├── dev-storage/
│   └── tests/
├── client/           # React Frontend
│   ├── src/
│   └── vite.config.ts
├── server/           # Legacy Express Backend (deprecated)
├── start_dev.py      # Dev orchestration
└── README.md
```

## Express Legacy Migration

- New features are exclusively implemented in the FastAPI backend.
- The React frontend uses the FastAPI proxy (`/api`, `/auth`).
- Deployment documentation should designate FastAPI as standard; Express remains only as an example or short-term comparison baseline.
- As part of the migration, tests, docs, and CI are consolidated on the Python backend.

## 📚 Documentation

### Core Documentation
- **[README.md](README.md)** - This file (project overview, quick start)
- **[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)** - Complete feature documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design decisions
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute (code style, workflow)
- **[TODO.md](TODO.md)** - Roadmap and planned features
- **[SECURITY.md](SECURITY.md)** - Security policy and best practices
- **[LICENSE](LICENSE)** - MIT License

### User Documentation
- **[User Guide](docs/USER_GUIDE.md)** - Complete user manual
- **[API Reference](docs/API_REFERENCE.md)** - Full API documentation

### Feature Documentation
- [Audit Logging](docs/AUDIT_LOGGING.md) - Activity tracking system
- [Disk I/O Monitor](docs/DISK_IO_MONITOR.md) - Real-time disk monitoring
- [RAID Setup Wizard](docs/RAID_SETUP_WIZARD.md) - RAID configuration guide
- [Network Drive Setup](docs/NETWORK_DRIVE_SETUP.md) - Mount as network drive
- [Performance Analysis](docs/PERFORMANCE_ANALYSIS.md) - System optimization
- [Telemetry Configuration](docs/TELEMETRY_CONFIG_RECOMMENDATIONS.md) - Monitoring setup

### Auto-Generated API Documentation

FastAPI provides interactive API documentation with custom BaluHost styling:
- **Swagger UI:** http://localhost:3001/docs (Custom styled to match frontend)
- **ReDoc:** http://localhost:3001/redoc

### Documentation Structure

```
docs/
├── USER_GUIDE.md           # End-user documentation
├── API_REFERENCE.md        # Complete API reference
├── AUDIT_LOGGING.md        # Audit system docs
├── DISK_IO_MONITOR.md      # Disk monitoring
├── RAID_SETUP_WIZARD.md    # RAID configuration
├── NETWORK_DRIVE_SETUP.md  # Network drive mounting
├── PERFORMANCE_ANALYSIS.md # Performance tuning
└── TELEMETRY_CONFIG_RECOMMENDATIONS.md
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
python -m pytest                           # All tests
python -m pytest tests/test_permissions.py # Specific test
python -m pytest -v                        # Verbose output
```

### Frontend Tests
```bash
cd client
npm run test        # Unit Tests (TODO)
npm run test:e2e    # E2E Tests (TODO)
```

## TODO / Improvements

See **[TODO.md](TODO.md)** for the complete, prioritized list.

**High Priority:**
- [ ] Database integration (PostgreSQL/MySQL)
- [ ] Upload progress UI with WebSocket/SSE
- [ ] Backup/Restore functionality

**Medium Priority:**
- [ ] File preview (Images, PDFs, Videos)
- [ ] Dark Mode
- [ ] Email notifications

**Low Priority:**
- [ ] Docker-Compose setup
- [ ] CI/CD Pipeline
- [ ] Internationalization (i18n)

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guidelines
- Development workflow
- Pull request process
- How to report bugs

**Good First Issues:**
- Add tests for existing features
- Improve documentation
- Fix UI/UX issues
- Add file type support in preview

## 📸 Screenshots

_(Coming soon - add screenshots here)_

**Dashboard:**
![Dashboard Screenshot](docs/images/dashboard.png)

**File Manager:**
![File Manager Screenshot](docs/images/filemanager.png)

**RAID Management:**
![RAID Management Screenshot](docs/images/raid.png)

## 🗺️ Roadmap

See [TODO.md](TODO.md) for the complete roadmap.

**Upcoming Features:**
- 🔜 File sharing with public links
- 🔜 Upload progress indicators
- 🔜 Database integration (PostgreSQL/SQLite)
- 🔜 Dark mode toggle
- 🔜 Settings page
- 🔜 Batch operations
- 🔜 Advanced search

## 📊 Project Stats

- **Lines of Code:** ~20,000+
- **Test Coverage:** 80%+ (backend)
- **API Endpoints:** 60+
- **React Components:** 30+
- **Database Tables:** 8+

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Frontend powered by [React](https://react.dev/) and [Vite](https://vitejs.dev/)
- UI styling with [Tailwind CSS](https://tailwindcss.com/)
- Charts by [Recharts](https://recharts.org/)
- Icons from [Heroicons](https://heroicons.com/)

## ⚖️ License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

Created by the BaluHost Team with ❤️ and [GitHub Copilot](https://github.com/features/copilot)

---

<div align="center">

**⭐ Star this repo if you find it helpful!**

[Report Bug](https://github.com/YOUR_USERNAME/BaluHost/issues) · [Request Feature](https://github.com/YOUR_USERNAME/BaluHost/issues) · [Discussions](https://github.com/YOUR_USERNAME/BaluHost/discussions)

</div>
