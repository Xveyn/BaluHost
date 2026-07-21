# Production

## Status

**Deployed**: January 25, 2026 on Debian 13 (Ryzen 5 5600GT, 16GB RAM)

**Completed:**
- PostgreSQL 17.7 migration
- Security hardening (OWASP, rate limiting, security headers)
- Structured JSON logging
- Systemd deployment with 4 Uvicorn workers
- Nginx reverse proxy with rate limiting
- Test suite (size: see the Testing row in `README.md` — machine-maintained by `scripts/generate_readme_stats.py`, so it is not restated here)
- CI/CD pipeline (GitHub Actions)
- Comprehensive monitoring (Prometheus/Grafana ready)
- Localization (i18n) — i18next with `de` + `en`, 19 namespaces each (`client/src/i18n/locales/`), switcher in Settings and the setup wizard. Remaining hardcoded English strings are tracked in #406

**Optional/Future:**
- SSL/HTTPS (currently HTTP on port 80)
- Email notifications
- PWA support

See `docs/deployment/PRODUCTION_READINESS.en.md` (German: `PRODUCTION_READINESS.de.md`, same directory) for complete checklist.

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
- Feature/fix branches branch off from `main` and PR directly back into `main`. Merging the PR creates a Pre-Release tag and deploys to production. Stable releases are a deliberate two-phase process: `/release-prepare` opens a CHANGELOG/docs-only PR (a hand-curated `## [Unreleased]` CHANGELOG section + any README/CLAUDE.md updates, no code, no version bump) which must be merged with an overridden `chore: release vX.Y.Z` commit message (squash merge is disabled on this repo) so the merge itself doesn't trigger a redundant deploy or a mislabeled pre-release tag; `/release-stable` then promotes it via `release-stable.yml` workflow_dispatch (finalizes the CHANGELOG section, bumps the version, tags).
- The `development` branch was retired 2026-05-06; do not push to it or target it as a PR base.
