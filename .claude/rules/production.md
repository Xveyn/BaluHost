# Production

## Status

**Deployed**: January 25, 2026 on Debian 13 (Ryzen 5 5600GT, 16GB RAM)

**Completed:**
- PostgreSQL 17.7 migration
- Security hardening (OWASP, rate limiting, security headers)
- Structured JSON logging
- Systemd deployment with 4 Uvicorn workers
- Nginx reverse proxy with rate limiting
- 68 test files, 1121 test functions
- CI/CD pipeline (GitHub Actions)
- Comprehensive monitoring (Prometheus/Grafana ready)

**Optional/Future:**
- SSL/HTTPS (currently HTTP on port 80)
- Email notifications
- PWA support
- Localization (i18n)

See `PRODUCTION_READINESS.md` for complete checklist.

## Deployment

### Systemd Services
- `baluhost-backend.service` - FastAPI/Uvicorn (4 workers, port 8000)
- `baluhost-frontend.service` - Optional (Nginx serves static files)

### Production Commands
```bash
# Start/Stop Services
sudo systemctl start baluhost-backend
sudo systemctl stop baluhost-backend
sudo systemctl status baluhost-backend

# View Logs
sudo journalctl -u baluhost-backend -f

# Production Launcher (Alternative)
python start_prod.py    # Start backend + optional frontend
python kill_prod.py     # Stop all BaluHost processes
```

### Configuration
- **Environment**: `.env.production` (auto-generated secrets)
- **Nginx**: `/etc/nginx/sites-available/baluhost`
- **Database**: PostgreSQL on localhost:5432

## Performance

- Telemetry: 3s interval (prod), 2s (dev)
- Telemetry history: 60 samples (3 minutes at 3s interval)
- Disk I/O: 1s sampling, 120 samples history
- API response caching: Storage info cached 30s

## Git Workflow

- **Main branch**: `main` (production deployments)
- **Development branch**: `development` (active development)
- Features branch off from `development`, PRs merge to `main`
