# BaluHost Production Deployment Notes

**Deployment Date:** January 25, 2026
**Deployment Type:** Native Systemd (Debian 13)
**Status:** ✅ PRODUCTION - RUNNING

---

## 🖥️ Server Specifications

- **Hardware:** Ryzen 5 5600GT, 16GB DDR4 RAM
- **Storage:** 250GB NVMe M.2 SSD (primary)
- **Planned:** 2x 4TB NAS HDDs (RAID1) - pending setup
- **OS:** Debian 13 (Trixie), Linux 6.12.63+deb13-amd64
- **Network:** Gigabit Ethernet, mDNS enabled

---

## 📦 Deployed Components

### Backend Service
- **Service:** `baluhost-backend.service`
- **Status:** Active (running)
- **Workers:** 4 Uvicorn processes
- **Port:** 8000 (internal)
- **Working Dir:** `/home/sven/projects/BaluHost/backend`
- **Virtual Env:** `.venv` (Python 3.13)
- **Logs:** `journalctl -u baluhost-backend -f`
- **Memory Usage:** ~480MB
- **Auto-Start:** Enabled

**Environment:**
- `NAS_MODE=prod`
- `LOG_LEVEL=INFO`
- `LOG_FORMAT=json`
- `DATABASE_URL=postgresql://baluhost:***@localhost:5432/baluhost`

### Frontend Service
- **Service:** `baluhost-frontend.service`
- **Status:** Inactive (not needed - Nginx serves static files)
- **Build Output:** `/var/www/baluhost/`
- **Permissions:** `www-data:www-data` (755)
- **Bundle Size:** 1.1MB (gzipped: 291KB)
- **Update Process:** `npm run build:prod` → `sudo cp -r client/dist/* /var/www/baluhost/`

### Database
- **Engine:** PostgreSQL 17.7 (Debian 17.7-0+deb13u1)
- **Database:** `baluhost`
- **User:** `baluhost`
- **Tables:** 35+ tables (all verified)
- **Status:** Active, enabled on boot
- **Connection:** localhost:5432
- **Auth:** md5 (pg_hba.conf)

### Nginx Reverse Proxy
- **Config:** `/etc/nginx/sites-available/baluhost`
- **Port:** 80 (HTTP)
- **Root:** `/var/www/baluhost/`
- **Upstream:** `127.0.0.1:8000` (backend)
- **Features:**
  - Rate limiting (API: 100r/s, Auth: 10r/s)
  - Security headers (X-Frame-Options, X-XSS-Protection, etc.)
  - Gzip compression
  - WebSocket/SSE support
  - 10GB max upload size
- **Logs:**
  - Access: `/var/log/nginx/baluhost-access.log`
  - Error: `/var/log/nginx/baluhost-error.log`

---

## 🔐 Security Configuration

### Secrets (Auto-Generated)
- `SECRET_KEY`: 64-char secure token (for JWT signing)
- `TOKEN_SECRET`: 64-char secure token (legacy auth)
- `POSTGRES_PASSWORD`: 43-char secure token
- `VPN_ENCRYPTION_KEY`: Fernet key for WireGuard encryption
- `ADMIN_PASSWORD`: `SecureAdmin2026!P3lPPhaBmqA` ⚠️ **CHANGE AFTER FIRST LOGIN**

### Admin Account
- **Username:** `admin`
- **Email:** `admin@example.com` (fixed from `admin@baluhost.local` - Pydantic validation issue)
- **Role:** `admin`
- **First Login:** Change password in Settings immediately

### Rate Limiting
- API endpoints: 100 requests/second (burst 20)
- Auth endpoints: 10 requests/second (burst 5)

### CORS
- Origins: `http://localhost`, `http://baluhost.local`, `http://127.0.0.1`

---

## 🛠️ Deployment Steps Taken

1. **Backup Created:** `/home/sven/baluhost_backup_20260125_220931` (1.1GB)
2. **PostgreSQL Installed:** Version 17.7, configured with dedicated user
3. **Database Initialized:** All tables created, admin user seeded
4. **Production .env Generated:** Secure secrets auto-generated
5. **Systemd Services Created:**
   - Backend service with 4 workers
   - Frontend service (build-only, not used for serving)
6. **Nginx Configured:**
   - HTTP-only reverse proxy
   - Static file serving from `/var/www/baluhost/`
   - Security headers and rate limiting
7. **Frontend Built:** Production build (1.1MB bundle)
8. **Services Started:** Backend running, Nginx serving
9. **Health Check Verified:** Login successful, API responding

---

## ⚠️ Known Issues

### 1. Monitoring Integer Overflow (Non-Critical)
**Symptom:** Memory and network sample inserts fail with "integer out of range"
**Cause:** `memory_samples.used_bytes` and `network_samples.bytes_sent/received` use INTEGER (max ~2GB) instead of BIGINT
**Impact:** Telemetry/monitoring data not saved (does not affect core functionality)
**Fix:** Alembic migration to change column types to BIGINT
**Priority:** Medium (fix when convenient)

### 2. Email Validation Issue (RESOLVED)
**Symptom:** Login failed with 500 error
**Cause:** Pydantic rejects `.local` TLD as invalid email
**Fix:** Changed admin email from `admin@baluhost.local` to `admin@example.com`
**Status:** ✅ Resolved

---

## 📊 System Performance

**Startup Time:**
- Backend: ~30 seconds (4 workers + DB connection)
- Frontend build: ~21 seconds
- Database: <5 seconds

**Memory Usage (Idle):**
- Backend: 480MB
- PostgreSQL: 60MB
- Nginx: 20MB
- Total: ~560MB

**CPU Usage (Idle):** <5%

**Disk Usage:**
- Backend: 250MB
- Frontend dist: 2MB
- PostgreSQL data: 15MB
- Total: ~300MB

---

## 🔄 Maintenance Procedures

### View Logs
```bash
# Backend logs (JSON format)
sudo journalctl -u baluhost-backend -f

# Nginx access logs
sudo tail -f /var/log/nginx/baluhost-access.log

# Nginx error logs
sudo tail -f /var/log/nginx/baluhost-error.log
```

### Restart Services
```bash
# Restart backend
sudo systemctl restart baluhost-backend

# Reload Nginx (no downtime)
sudo systemctl reload nginx

# Full restart (brief downtime)
sudo systemctl restart nginx
```

### Update Frontend
```bash
cd /home/sven/projects/BaluHost/client
npm run build:prod
sudo cp -r dist/* /var/www/baluhost/
sudo systemctl reload nginx
```

### Database Backup
```bash
sudo -u postgres pg_dump baluhost > /path/to/backup/baluhost_$(date +%Y%m%d_%H%M%S).sql
```

### Check Service Status
```bash
systemctl status baluhost-backend
systemctl status nginx
systemctl status postgresql
```

---

## 📋 Pending Tasks

### Critical
- [ ] None - system is production-ready

### Important
- [ ] **Task #7:** Production storage setup (2x 4TB HDDs → RAID1)
- [ ] Fix monitoring integer overflow (BIGINT migration)
- [ ] **Task #10:** Automated backup configuration (cronjob)

### Optional
- [ ] SSL/HTTPS setup (Let's Encrypt)
- [ ] **Task #9:** Prometheus + Grafana monitoring
- [ ] Frontend performance optimization (code splitting)
- [ ] Load testing (locust, k6)

---

## 🎯 Next Steps

1. **Immediate (After First Login):**
   - Change admin password in Settings
   - Test file upload/download
   - Verify dashboard metrics

2. **Short Term (This Week):**
   - Install 2x 4TB HDDs
   - Create RAID1 array
   - Configure storage mountpoints
   - Fix monitoring integer overflow

3. **Long Term (This Month):**
   - Set up automated backups
   - Configure SSL/HTTPS (if needed)
   - Deploy monitoring stack (optional)

---

## 📞 Access Information

**Web UI:**
- Local: `http://localhost`
- Network: `http://baluhost.local` (if mDNS configured)
- IP: `http://<server-ip>` (check with `hostname -I`)

**API Documentation:**
- Swagger UI: `http://localhost/docs`
- OpenAPI JSON: `http://localhost/openapi.json`

**Admin Credentials:**
- Username: `admin`
- Password: `SecureAdmin2026!P3lPPhaBmqA` ⚠️ **CHANGE IMMEDIATELY**

---

**Last Updated:** January 25, 2026 23:40 CET
**Deployment Status:** ✅ PRODUCTION - STABLE
**Uptime Target:** 99.9%
