# Infrastructure Overview

## Hardware

- **Host**: Debian 13 (Trixie)
- **CPU**: AMD Ryzen 5 5600GT
- **RAM**: 16 GB
- **Storage**: RAID arrays managed by mdadm
- **Network**: LAN + WireGuard VPN for remote access

## Architecture

```
Internet ──[WireGuard VPN]──> NAS (LAN)
                                │
                           ┌────┴────┐
                           │  Nginx  │ :80
                           └────┬────┘
                      ┌─────────┼──────────┐
                      │         │          │
                 /api/*    /api/ws    /* (static)
                      │         │          │
                      ▼         ▼          ▼
               ┌──────────┐              client/dist/
               │ Uvicorn  │ :8000        (Nginx serves)
               │ 4 workers│
               └────┬─────┘
                    │
               PostgreSQL :5432
               /var/lib/postgresql/
```

## Services

### Systemd Units

| Service | Description | Dependencies |
|---------|-------------|--------------|
| `baluhost-backend` | FastAPI/Uvicorn (4 workers, port 8000) | postgresql |
| `baluhost-scheduler` | Background job scheduler | postgresql, backend |
| `baluhost-monitoring` | System metrics collector | postgresql, backend |
| `baluhost-webdav` | WebDAV protocol server | postgresql, backend |
| `nginx` | Reverse proxy + static files | — |
| `postgresql` | Database | — |

### Service Dependencies

```
postgresql
  └── baluhost-backend
        ├── baluhost-scheduler
        ├── baluhost-monitoring
        └── baluhost-webdav

nginx (independent, proxies to backend)
```

## Deployment Pipeline

```
Developer ──push──> GitHub (main branch)
                        │
                   CI Check (GitHub-hosted runner)
                   ├── Backend tests (pytest)
                   └── Frontend build (npm)
                        │
                   Deploy (self-hosted runner on NAS)
                   ├── Pre-checks (PostgreSQL, .env)
                   ├── Database backup (pg_dump)
                   ├── Git pull
                   ├── pip install
                   ├── Alembic migrations
                   ├── npm ci + npm run build
                   ├── Service restart
                   └── Health check
```

### Rollback

On deploy failure:
1. Automatic: `ci-deploy.sh` rolls back to previous commit + alembic downgrade
2. Manual: `ci-deploy.sh --rollback`
3. Database: `db-restore.sh <backup-file.sql.gz>`

## Directory Layout

```
/opt/baluhost/                    # Production application
├── backend/                      # Python FastAPI
│   ├── .venv/                    # Python virtual environment
│   ├── app/                      # Application code
│   ├── scripts/                  # Worker scripts
│   └── alembic/                  # Database migrations
├── client/                       # React frontend
│   └── dist/                     # Built static files (served by Nginx)
├── deploy/                       # Deployment tooling
│   ├── install/                  # Modular installer
│   ├── scripts/                  # Deploy, backup, restore scripts
│   └── runner/                   # GitHub Actions runner docs
├── .env.production               # Environment config (not in git)
├── .deploy-state                 # Last deploy metadata (JSON)
└── backups/
    ├── deploys/                  # Pre-deploy backups (10 retained)
    └── daily/                    # Cron backups (14 days retained)

/etc/systemd/system/              # Service files
├── baluhost-backend.service
├── baluhost-scheduler.service
├── baluhost-monitoring.service
└── baluhost-webdav.service

/etc/nginx/sites-available/       # Nginx configuration
└── baluhost

/etc/sudoers.d/                   # Passwordless sudo for deploys
├── baluhost-update
└── baluhost-deploy

/var/log/baluhost/                # Application logs
├── deploys/                      # Deploy logs (JSON)
└── db-backup.log                 # Daily backup cron log

/var/lib/postgresql/              # Database data (NOT in /opt/baluhost)

/opt/actions-runner/              # GitHub Actions self-hosted runner
```

## Database

- **Engine**: PostgreSQL 17.7
- **Host**: localhost:5432
- **Database**: `baluhost`
- **User**: `baluhost`
- **Data**: `/var/lib/postgresql/` (managed by PostgreSQL, independent of app)
- **Migrations**: Alembic (68+ migration files in `backend/alembic/`)

### Backup Strategy

| Type | Schedule | Retention | Location |
|------|----------|-----------|----------|
| Pre-deploy | Every deploy | Last 10 | `/opt/baluhost/backups/deploys/` |
| Daily | 03:00 cron | 14 days | `/opt/baluhost/backups/daily/` |

## Network

| Service | Port | Access |
|---------|------|--------|
| Nginx (HTTP) | 80 | LAN + VPN |
| Backend API | 8000 | localhost only (Nginx proxies) |
| PostgreSQL | 5432 | localhost only |
| WireGuard VPN | 51820/UDP | External |
| mDNS | 5353/UDP | LAN (baluhost.local) |

## Monitoring

- **Built-in**: CPU, memory, network, disk I/O collectors (baluhost-monitoring service)
- **Prometheus**: Metrics export at `/api/monitoring/prometheus`
- **Grafana**: Dashboard templates in `deploy/grafana/`
- **Health endpoint**: `GET /api/system/health`
