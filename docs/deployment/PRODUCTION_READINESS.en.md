# Production Readiness Checklist

## Status

**In production since:** January 25, 2026  
**Server:** Debian 13, Ryzen 5 5600GT, 16 GB RAM, 250 GB NVMe SSD  
**Version:** 1.23.0

## Infrastructure

| Component | Status | Details |
|-----------|--------|---------|
| Backend | Active | FastAPI/Uvicorn, 4 workers, port 8000 |
| Frontend | Active | Vite build, static files via Nginx |
| Database | Active | PostgreSQL 17.7, localhost:5432 |
| Reverse Proxy | Active | Nginx, port 80 (HTTP) |
| Auto-Start | Active | Systemd services enabled |
| Logging | Active | Structured JSON logging |

## Security

| Measure | Status |
|---------|--------|
| CORS configuration | Configured |
| Rate limiting | Active (API: 100/s, Auth: 10/s) |
| SQL injection protection | SQLAlchemy ORM |
| Security headers | CSP, X-Frame-Options, HSTS, X-Content-Type-Options |
| Password policy | 8+ chars, upper/lower/digit, blacklist |
| Token management | Access (15 min) + Refresh (7 days) with JTI |
| Audit logging | DB-backed, all security-relevant actions |
| VPN keys | Fernet encrypted |
| Sensitive data | Redaction in admin DB inspection |

## Tests

- **82 test files**, 1465 test functions
- CI/CD pipeline via GitHub Actions
- Automatic tests on push/PR

## Services

| Service | Function |
|---------|----------|
| Monitoring Orchestrator | Collect CPU, RAM, network, disk I/O |
| Scheduler | Scheduled tasks (backups, cleanup) |
| WebDAV | Network file access |
| Power Management | CPU frequency scaling |
| Fan Control | PWM fan control with temperature curves |
| Service Status | Health monitoring of all services |

## Optional Enhancements

| Enhancement | Status |
|-------------|--------|
| SSL/HTTPS | Not configured (access via VPN) |
| Email notifications | Not implemented |
| Database replication | Not configured (single instance) |

## Maintenance

### Regular Tasks

- **Daily:** Check RAID status (automatic via monitoring)
- **Weekly:** Check SMART data, monitor storage space
- **Monthly:** System updates, PostgreSQL VACUUM
- **As needed:** Alembic migrations after updates

### Backup

PostgreSQL backup:
```bash
pg_dump -U baluhost baluhost > backup_$(date +%Y%m%d).sql
```

Files:
```bash
rsync -av /opt/baluhost/storage/ /backup/storage/
```

---

**Last updated:** April 2026
