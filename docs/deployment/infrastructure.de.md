# Infrastrukturübersicht

## Hardware

- **Host**: Debian 13 (Trixie)
- **CPU**: AMD Ryzen 5 5600GT
- **RAM**: 16 GB
- **Speicher**: RAID-Arrays verwaltet durch mdadm
- **Netzwerk**: LAN + WireGuard VPN für Fernzugriff

## Architektur

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
               │ Uvicorn  │ :8000        (Nginx liefert aus)
               │ 4 Worker │
               └────┬─────┘
                    │
               PostgreSQL :5432
               /var/lib/postgresql/
```

## Dienste

### Systemd-Units

| Dienst | Beschreibung | Abhängigkeiten |
|--------|-------------|----------------|
| `baluhost-backend` | FastAPI/Uvicorn (4 Worker, Port 8000) | postgresql |
| `baluhost-scheduler` | Hintergrund-Aufgabenplaner | postgresql, backend |
| `baluhost-monitoring` | Systemmetriken-Kollektor | postgresql, backend |
| `baluhost-webdav` | WebDAV-Protokollserver | postgresql, backend |
| `nginx` | Reverse Proxy + statische Dateien | — |
| `postgresql` | Datenbank | — |

### Dienstabhängigkeiten

```
postgresql
  └── baluhost-backend
        ├── baluhost-scheduler
        ├── baluhost-monitoring
        └── baluhost-webdav

nginx (unabhängig, leitet an Backend weiter)
```

## Deployment-Pipeline

```
Entwickler ──push──> GitHub (main Branch)
                        │
                   CI-Prüfung (GitHub-gehosteter Runner)
                   ├── Backend-Tests (pytest)
                   └── Frontend-Build (npm)
                        │
                   Deploy (Self-hosted Runner auf NAS)
                   ├── Vorab-Prüfungen (PostgreSQL, .env)
                   ├── Datenbank-Backup (pg_dump)
                   ├── Git pull
                   ├── pip install
                   ├── Alembic-Migrationen
                   ├── npm ci + npm run build
                   ├── Dienst-Neustart
                   └── Gesundheitsprüfung
```

### Rollback

Bei fehlgeschlagenem Deploy:
1. Automatisch: `ci-deploy.sh` setzt auf vorherigen Commit zurück + Alembic Downgrade
2. Manuell: `ci-deploy.sh --rollback`
3. Datenbank: `db-restore.sh <backup-datei.sql.gz>`

## Verzeichnisstruktur

```
/opt/baluhost/                    # Produktionsanwendung
├── backend/                      # Python FastAPI
│   ├── .venv/                    # Virtuelle Python-Umgebung
│   ├── app/                      # Anwendungscode
│   ├── scripts/                  # Worker-Skripte
│   └── alembic/                  # Datenbankmigrationen
├── client/                       # React-Frontend
│   └── dist/                     # Gebaute statische Dateien (von Nginx ausgeliefert)
├── deploy/                       # Deployment-Werkzeuge
│   ├── install/                  # Modularer Installer
│   ├── scripts/                  # Deploy-, Backup-, Restore-Skripte
│   └── runner/                   # GitHub Actions Runner-Dokumentation
├── .env.production               # Umgebungskonfiguration (nicht in Git)
├── .deploy-state                 # Letzte Deploy-Metadaten (JSON)
└── backups/
    ├── deploys/                  # Pre-Deploy-Backups (10 aufbewahrt)
    └── daily/                    # Cron-Backups (14 Tage aufbewahrt)

/etc/systemd/system/              # Service-Dateien
├── baluhost-backend.service
├── baluhost-scheduler.service
├── baluhost-monitoring.service
└── baluhost-webdav.service

/etc/nginx/sites-available/       # Nginx-Konfiguration
└── baluhost

/etc/sudoers.d/                   # Passwortloses sudo für Deploys
├── baluhost-update
└── baluhost-deploy

/var/log/baluhost/                # Anwendungslogs
├── deploys/                      # Deploy-Logs (JSON)
└── db-backup.log                 # Tägliches Backup-Cron-Log

/var/lib/postgresql/              # Datenbankdaten (NICHT in /opt/baluhost)

/opt/actions-runner/              # GitHub Actions Self-hosted Runner
```

## Datenbank

- **Engine**: PostgreSQL 17.7
- **Host**: localhost:5432
- **Datenbank**: `baluhost`
- **Benutzer**: `baluhost`
- **Daten**: `/var/lib/postgresql/` (von PostgreSQL verwaltet, unabhängig von der Anwendung)
- **Migrationen**: Alembic (68+ Migrationsdateien in `backend/alembic/`)

### Backup-Strategie

| Typ | Zeitplan | Aufbewahrung | Speicherort |
|-----|----------|--------------|-------------|
| Pre-Deploy | Bei jedem Deploy | Letzte 10 | `/opt/baluhost/backups/deploys/` |
| Täglich | 03:00 Uhr Cron | 14 Tage | `/opt/baluhost/backups/daily/` |

## Netzwerk

| Dienst | Port | Zugriff |
|--------|------|---------|
| Nginx (HTTP) | 80 | LAN + VPN |
| Backend-API | 8000 | Nur localhost (Nginx leitet weiter) |
| PostgreSQL | 5432 | Nur localhost |
| WireGuard VPN | 51820/UDP | Extern |
| mDNS | 5353/UDP | LAN (baluhost.local) |

## Monitoring

- **Integriert**: CPU-, Arbeitsspeicher-, Netzwerk-, Festplatten-I/O-Kollektoren (baluhost-monitoring-Dienst)
- **Prometheus**: Metrik-Export unter `/api/monitoring/prometheus`
- **Grafana**: Dashboard-Vorlagen in `deploy/grafana/`
- **Gesundheitsendpunkt**: `GET /api/system/health`
