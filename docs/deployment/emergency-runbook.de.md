# Emergency Runbook

Quick reference for production incident response on the BaluHost NAS.

## Service Overview

| Service | Port | Check |
|---------|------|-------|
| `baluhost-backend` | 8000 | `curl localhost:8000/api/system/health` |
| `baluhost-scheduler` | — | `systemctl status baluhost-scheduler` |
| `baluhost-monitoring` | — | `systemctl status baluhost-monitoring` |
| `baluhost-webdav` | — | `systemctl status baluhost-webdav` |
| `nginx` | 80 | `curl localhost/health` |
| `postgresql` | 5432 | `pg_isready -h localhost` |

## Quick Commands

```bash
# Check all services
sudo systemctl status 'baluhost-*'
sudo systemctl status nginx postgresql

# View backend logs
sudo journalctl -u baluhost-backend -f
sudo journalctl -u baluhost-backend --since "10 minutes ago"

# Restart everything
sudo systemctl restart baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav
sudo systemctl reload nginx
```

## Rollback After Bad Deploy

```bash
cd /opt/baluhost

# 1. Check what was deployed
cat .deploy-state
# Shows: previous_commit, current_commit, backup_file, db_revision_before/after

# 2. Automatic rollback (restores code + DB revision)
./deploy/scripts/ci-deploy.sh --rollback

# 3. Verify
curl localhost/api/system/health
```

## Database Restore (Nuclear Option)

Use this if the database itself is corrupted or a migration caused data loss.

```bash
# 1. List available backups
ls -lt /opt/baluhost/backups/deploys/   # Pre-deploy backups
ls -lt /opt/baluhost/backups/daily/     # Daily cron backups

# 2. Restore (interactive — asks for confirmation)
/opt/baluhost/deploy/scripts/db-restore.sh /opt/baluhost/backups/deploys/pre-deploy-20260302-143000.sql.gz
```

### Manual Database Restore

If the restore script fails:

```bash
# 1. Stop services
sudo systemctl stop baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav

# 2. Drop and recreate
sudo -u postgres dropdb baluhost
sudo -u postgres createdb -O baluhost baluhost

# 3. Restore from backup
gunzip -c /opt/baluhost/backups/deploys/<BACKUP>.sql.gz | sudo -u postgres psql baluhost

# 4. Verify alembic revision
cd /opt/baluhost/backend
.venv/bin/alembic current

# 5. Restart services
sudo systemctl start baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav
```

## Common Issues

### Backend won't start

```bash
# Check logs
sudo journalctl -u baluhost-backend -n 50

# Common causes:
# - Port 8000 in use: sudo lsof -i :8000
# - .env.production missing/broken: cat /opt/baluhost/.env.production
# - Python venv broken: cd /opt/baluhost/backend && .venv/bin/python -c "import app"
# - PostgreSQL down: pg_isready -h localhost
```

### Nginx 502 Bad Gateway

Backend isn't responding on port 8000.

```bash
sudo systemctl status baluhost-backend
sudo systemctl restart baluhost-backend
# Wait 5s, then:
curl localhost:8000/api/system/health
```

### Database connection refused

```bash
# Check PostgreSQL
sudo systemctl status postgresql
pg_isready -h localhost -p 5432

# Check credentials
grep DATABASE_URL /opt/baluhost/.env.production

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Disk full

```bash
df -h
# Clean up old backups if needed:
ls -la /opt/baluhost/backups/deploys/
ls -la /opt/baluhost/backups/daily/
# Remove oldest backups carefully
```

### Frontend shows blank page

```bash
# Check if dist exists
ls /opt/baluhost/client/dist/index.html

# Rebuild if needed
cd /opt/baluhost/client
sudo -u sven npm run build
sudo systemctl reload nginx
```

## Useful Paths

| Path | Purpose |
|------|---------|
| `/opt/baluhost/` | Production application |
| `/opt/baluhost/.env.production` | Environment config (secrets) |
| `/opt/baluhost/.deploy-state` | Last deploy metadata |
| `/opt/baluhost/backups/deploys/` | Pre-deploy database backups |
| `/opt/baluhost/backups/daily/` | Daily cron database backups |
| `/var/log/baluhost/deploys/` | Deploy logs (JSON) |
| `/var/log/baluhost/db-backup.log` | Daily backup cron log |
| `/etc/nginx/sites-available/baluhost` | Nginx config |
| `/etc/systemd/system/baluhost-*.service` | Systemd service files |

## Contacts

- **Repository**: https://github.com/Xveyn/BaluHost
- **Maintainer**: Xveyn
