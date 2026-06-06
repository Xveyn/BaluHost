<div align="center">

# BaluHost

**Self-Hosted Home Server Platform**

[![Version](https://img.shields.io/github/v/release/Xveyn/BaluHost?color=blue&label=version)](https://github.com/Xveyn/BaluHost/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-18+-339933.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Manage your home server end to end — file & RAID storage at the core, plus system & power monitoring, VPN and networking, and a plugin marketplace to extend it — all from one web UI, with production-grade deployment built in.

[Features](#features) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Documentation](#documentation)

</div>

---

## Reference System

BaluHost is developed, tested, and run in production on a single reference machine — the maintainer's box, in service since January 25, 2026. There is no separate production environment: this same machine is both the dev/test reference and the live deployment.

| Hardware | Detail |
|----------|--------|
| **OS / Kernel** | Debian 13 · `6.12.74+deb13+1-amd64` (x86_64) |
| **CPU** | AMD Ryzen 5 5600GT |
| **Memory** | 16 GB RAM |
| **GPU** | AMD Radeon RX 7900 XT (20 GB VRAM) |

The same machine doubles as a KDE Plasma desktop and — thanks to the Radeon GPU — an optional Linux gaming rig / "Steam Machine" (Proton). That gaming use case is not part of this repository; it simply shares the reference hardware.

| Production Stack | Detail |
|------------------|--------|
| **Database** | PostgreSQL 17.7 with Alembic migrations |
| **Proxy** | Nginx (port 80, rate limiting, security headers) |
| **Backend** | systemd-managed, 4 Uvicorn workers on port 8000, auto-restart |
| **Testing** | <!-- STATS:TEST_COUNT:START -->3064 tests<!-- STATS:TEST_COUNT:END --> across <!-- STATS:TEST_FILES:START -->248 test files<!-- STATS:TEST_FILES:END -->, CI/CD via GitHub Actions |
| **Monitoring** | Prometheus / Grafana ready |

---

## Features

### File Management
- Drag & drop upload with chunked transfer (32MB chunks)
- File preview (images, videos, audio, PDFs, text)
- File sharing with public links, expiration & password protection
- Per-user storage quotas and ownership tracking
- Multi-mountpoint support (multiple RAID arrays)

### RAID & Storage
- Real-time RAID array status (RAID 0, 1, 5, 6, 10)
- SMART disk health monitoring
- RAID setup wizard with guided array creation
- OS-disk protection (prevents formatting boot drives)
- Dev-mode simulation for testing without hardware

### System Monitoring
- Per-thread CPU usage (Task Manager-style)
- Memory, network throughput, disk I/O metrics
- Historical telemetry with Recharts visualizations
- Monitoring orchestrator with configurable collectors
- Prometheus metrics export

### Power & Hardware
- CPU frequency scaling (AMD Ryzen & Intel)
- PWM fan control with custom temperature curves
- Fan scheduling (time-based curve selection)
- Energy monitoring via Tapo smart plugs (P110/P115)
- Sleep mode management

### Networking & Access
- WireGuard VPN server with client management
- WebDAV server for network drive mounting
- Samba/SMB sharing
- mDNS/Bonjour auto-discovery
- Pi-hole DNS integration

### Security
- JWT authentication with role-based access (admin/user)
- Rate limiting on all endpoints (slowapi)
- Security headers (CSP, HSTS, X-Frame-Options)
- Path jailing for user file isolation
- Audit logging for all security-relevant actions
- Encrypted VPN/SSH keys (Fernet AES)

### Administration
- Scheduler dashboard with execution history
- Service health monitoring
- Secure read-only database inspection (sensitive fields redacted)
- Cloud import (rclone integration)
- Self-hosted update mechanism
- System benchmarking

### Plugins & Extensibility
- Plugin marketplace — browse, install, update & remove plugins from a UI tab
- Plugins distributed from a separate Git repo, installed in one click
- Isolated per-plugin Python dependencies (no pollution of the core environment)
- Frontend SDK (`window.BaluHost`) for plugin dashboard panels & UI bundles
- Inter-plugin event bus and lifecycle hooks
- SmartDevice framework for hardware-device plugins (e.g. Tapo smart plugs)

### Multi-Platform
- **BaluHost** — Web UI (this repo)
- **[BaluDesk](https://github.com/Xveyn/BaluDesk)** — Desktop sync client (C++/Electron)
- **[BaluApp](https://github.com/Xveyn/BaluApp)** — Android app (Kotlin)
- **TUI** — Terminal UI via [Textual](https://textual.textualize.io/) (`baluhost-tui`)

---

## Quick Start

### Development (recommended)

```bash
# Start both backend (port 3001) and frontend (port 5173)
python start_dev.py
```

This sets `NAS_MODE=dev`, creates a simulated RAID1 sandbox in `backend/dev-storage/`, and provides mock system data. Works on Windows, macOS, and Linux.

**Default dev credentials:** `admin` / `DevMode2024`

Open http://localhost:5173 in your browser.

### Manual Setup

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 3001

# Frontend (separate terminal)
cd client
npm install
npm run dev
```

### Production Deployment

See [Production Quickstart](docs/deployment/PRODUCTION_QUICKSTART.md) for full instructions.

```bash
# Fresh install (modular installer)
sudo ./deploy/install/install.sh

# Or via systemd (if already installed)
sudo systemctl start baluhost-backend
```

Production runs at `/opt/baluhost` with:
- **4 Uvicorn workers** on port 8000 (behind Nginx)
- **Nginx** serves static frontend (`client/dist/`) and proxies `/api/*`
- **PostgreSQL 17.7** for data persistence
- **Auto-deploy** on push to `main` via GitHub Actions (self-hosted runner)

### Deployment Pipeline

```
push to main → CI checks (GitHub-hosted) → Deploy (self-hosted on NAS)
                                            ├── DB backup (pg_dump)
                                            ├── git pull + pip install
                                            ├── Alembic migrations
                                            ├── Frontend build (npm)
                                            ├── Service restart
                                            └── Health check (auto-rollback on failure)
```

See [Infrastructure](docs/deployment/infrastructure.md) and [Emergency Runbook](docs/deployment/emergency-runbook.md) for operational details.

---

## Architecture

```
BaluHost/
├── backend/                 # Python FastAPI
│   ├── app/
│   │   ├── api/routes/      # API route modules
│   │   ├── services/        # Service modules
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── core/            # Config, security, database
│   │   └── middleware/      # Security headers, rate limiting
│   ├── baluhost_tui/        # Terminal UI (Textual)
│   ├── tests/               # Pytest suite
│   └── alembic/             # Database migrations
├── client/                  # React + TypeScript + Vite
│   └── src/
│       ├── pages/           # Page components
│       ├── components/      # Reusable components
│       ├── api/             # Typed API clients
│       ├── hooks/           # Custom React hooks
│       ├── contexts/        # Auth context
│       └── lib/             # Utilities, formatters
├── deploy/                  # Deployment configs
│   ├── nginx/               # Reverse proxy configs
│   ├── systemd/             # Service files
│   ├── samba/               # SMB configuration
│   ├── prometheus/          # Metrics scraping
│   └── grafana/             # Dashboard templates
├── docs/                    # Documentation
├── .github/workflows/       # CI/CD pipelines
├── start_dev.py             # Dev launcher
└── start_prod.py            # Production launcher
```

**Tech Stack:**
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts, Lucide icons
- **Backend:** FastAPI, SQLAlchemy 2.0, Pydantic, Uvicorn
- **Database:** SQLite (dev) / PostgreSQL (prod), Alembic migrations
- **Testing:** Pytest (backend), Vitest + Playwright (frontend)

---

## API Overview

Interactive API docs at http://localhost:3001/docs (Swagger UI) or `/redoc`.

All routes prefixed with `/api`:

| Area | Endpoints | Description |
|------|-----------|-------------|
| **Auth** | `/auth/login`, `/auth/register`, `/auth/me`, `/auth/refresh` | JWT authentication |
| **Files** | `/files/list`, `/files/upload`, `/files/download`, ... | File CRUD operations |
| **Shares** | `/shares`, `/shares/public/{token}` | Public link sharing |
| **Users** | `/users` (admin) | User management |
| **System** | `/system/info`, `/system/storage`, `/system/raid/*`, `/system/smart/*` | System & RAID info |
| **Monitoring** | `/monitoring/cpu`, `/monitoring/memory`, `/monitoring/network`, ... | Real-time metrics |
| **Power** | `/power/profile`, `/power/presets` | CPU frequency scaling |
| **Fans** | `/fans/config`, `/fans/status` | Fan control & curves |
| **Energy** | `/energy/stats` | Power consumption |
| **Tapo** | `/tapo/plugs`, `/tapo/readings` | Smart plug integration |
| **VPN** | `/vpn/clients`, `/vpn/config` | WireGuard management |
| **Backup** | `/backup`, `/backup/{id}/restore` | Backup & restore |
| **Sync** | `/sync/folders`, `/sync/conflicts` | Desktop sync |
| **Mobile** | `/mobile/register`, `/mobile/devices` | Mobile device pairing |
| **Schedulers** | `/schedulers`, `/schedulers/{name}/run-now` | Scheduler control |
| **Admin** | `/admin-db/*`, `/admin/*` | Database inspection, services |
| **Logging** | `/logging/audit`, `/logging/disk-io` | Audit trail |
| **Pi-hole** | `/pihole/*` | DNS management |
| **Plugins** | `/plugins/*`, `/plugins/marketplace/*` | Plugin runtime & marketplace |

---

## Configuration

### Backend `.env`

```env
NAS_MODE=dev              # dev or prod
SECRET_KEY=...            # 32+ chars required in prod
TOKEN_SECRET=...          # 32+ chars required in prod
DATABASE_URL=...          # PostgreSQL URL (prod)

NAS_STORAGE_PATH=./dev-storage
NAS_QUOTA_BYTES=5368709120
TELEMETRY_INTERVAL_SECONDS=3.0
```

### Frontend `.env`

```env
VITE_API_BASE_URL=http://localhost:3001
```

The Vite dev server proxies `/api` requests to port 3001 automatically (see `client/vite.config.ts`).

---

## Testing

```bash
# Backend
cd backend
python -m pytest                            # All tests
python -m pytest tests/test_permissions.py   # Specific test
python -m pytest -v                          # Verbose

# Frontend
cd client
npm run test          # Vitest unit tests
npm run test:e2e      # Playwright E2E tests
npm run build         # Type-check + production build
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md) | Complete feature reference |
| [Architecture](docs/ARCHITECTURE.md) | System design & patterns |
| [Production Readiness](docs/deployment/PRODUCTION_READINESS.md) | Deployment checklist |
| [Production Quickstart](docs/deployment/PRODUCTION_QUICKSTART.md) | Getting started in prod |
| [User Guide](docs/getting-started/USER_GUIDE.md) | End-user manual |
| [API Reference](docs/api/API_REFERENCE.md) | Full API documentation |
| [Security Policy](docs/security/SECURITY.md) | Security guidelines |
| [Contributing](CONTRIBUTING.md) | Contribution workflow |
| [Changelog](CHANGELOG.md) | Version history |
| [TODO](TODO.md) | Roadmap |

```
docs/
├── api/              # API documentation
├── deployment/       # Deployment & ops guides
├── features/         # Feature-specific docs
├── getting-started/  # User guide & dev checklist
├── monitoring/       # Monitoring & telemetry setup
├── network/          # Network & VPN configuration
├── security/         # Security & audit logging
└── storage/          # RAID & backup guides
```

---

## Project Stats

<!-- STATS:PROJECT:START -->
| Metric | Count |
|--------|-------|
| **Version** | ![Latest Release](https://img.shields.io/github/v/release/Xveyn/BaluHost?label=) |
| **Backend code** | 171,911 lines across 868 Python files |
| &nbsp;&nbsp;↳ Application (`app/`) | 106,226 lines / 446 files |
| &nbsp;&nbsp;↳ Tests (`tests/`) | 49,338 lines / 248 files |
| &nbsp;&nbsp;↳ Scripts (`scripts/`) | 6,291 lines / 48 files |
| &nbsp;&nbsp;↳ Alembic migrations | 6,722 lines / 105 files |
| &nbsp;&nbsp;↳ Terminal UI (`baluhost_tui/`) | 3,334 lines / 21 files |
| **Frontend code** | 85,276 lines across 498 source files (`client/src/`, .ts/.tsx/.js/.jsx/.css) |
| **Test functions** | 3064 |
| **API route modules** | 63 |
| **Service modules** | 191 |
| **Database models** | 50 |
| **Database migrations** | 104 |
| **Frontend pages** | 33 |
| **CI/CD workflows** | 8 |

<sub>LOC counted via `git ls-files` (respects `.gitignore`, excludes virtualenvs, `node_modules/`, `dist/`, caches, dev-storage). Last measured 2026-06-02.</sub>
<!-- STATS:PROJECT:END -->

---

## License

[MIT License](LICENSE)

## Author

Created by [Xveyn](https://github.com/Xveyn)

---

<div align="center">

[Report Bug](https://github.com/Xveyn/BaluHost/issues) · [Request Feature](https://github.com/Xveyn/BaluHost/issues)

</div>
