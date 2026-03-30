# BaluHost Production Quick Start

**Status:** ✅ DEPLOYED AND RUNNING (since Jan 25, 2026)

---

## 🚀 Access the System

**Web Interface:**
```
http://localhost
http://baluhost.local
http://<your-server-ip>
```

**Admin Login:**
- Username: (configured during installation)
- Password: (configured during installation)
- Change password immediately after first login (Settings → Change Password)

**API Documentation:**
```
http://localhost/docs (Swagger UI)
```

---

## 🛠️ Common Commands

### Check Service Status
```bash
sudo systemctl status baluhost-backend
sudo systemctl status nginx
sudo systemctl status postgresql
```

### View Logs
```bash
# Backend logs (real-time)
sudo journalctl -u baluhost-backend -f

# Backend logs (last 100 lines)
sudo journalctl -u baluhost-backend -n 100

# Nginx access log
sudo tail -f /var/log/nginx/baluhost-access.log

# Nginx error log
sudo tail -f /var/log/nginx/baluhost-error.log
```

### Restart Services
```bash
# Restart backend (brief downtime)
sudo systemctl restart baluhost-backend

# Reload Nginx (no downtime)
sudo systemctl reload nginx
```

### Update Frontend
```bash
cd /home/sven/projects/BaluHost/client
npm run build:prod
sudo cp -r dist/* /var/www/baluhost/
sudo systemctl reload nginx
```

### Database Access
```bash
# Connect to database
sudo -u postgres psql -d baluhost

# List tables
sudo -u postgres psql -d baluhost -c "\dt"

# View users
sudo -u postgres psql -d baluhost -c "SELECT id, username, email, role FROM users;"

# Backup database
sudo -u postgres pg_dump baluhost > ~/baluhost_backup_$(date +%Y%m%d).sql
```

---

## 📂 Important Paths

| Component | Path |
|-----------|------|
| Backend code | `/home/sven/projects/BaluHost/backend` |
| Frontend code | `/home/sven/projects/BaluHost/client` |
| Frontend static files | `/var/www/baluhost/` |
| Nginx config | `/etc/nginx/sites-available/baluhost` |
| Systemd backend service | `/etc/systemd/system/baluhost-backend.service` |
| Production .env | `/home/sven/projects/BaluHost/.env.production` |
| Nginx logs | `/var/log/nginx/baluhost-*.log` |
| Dev backup | `/home/sven/baluhost_backup_20260125_220931/` |

---

## 🔧 Troubleshooting

### Backend won't start
```bash
# Check logs for errors
sudo journalctl -u baluhost-backend -n 50

# Verify database connection
sudo systemctl status postgresql
sudo -u postgres psql -d baluhost -c "SELECT 1;"

# Check .env file
cat /home/sven/projects/BaluHost/.env.production | grep -v PASSWORD
```

### Frontend not loading
```bash
# Check Nginx status
sudo systemctl status nginx

# Verify static files exist
ls -lh /var/www/baluhost/

# Check Nginx error log
sudo tail -n 50 /var/log/nginx/baluhost-error.log

# Test Nginx config
sudo nginx -t
```

### Login fails
```bash
# Verify admin user exists
sudo -u postgres psql -d baluhost -c "SELECT username, email, is_active FROM users WHERE username='admin';"

# Check backend logs during login attempt
sudo journalctl -u baluhost-backend -f
# (then try login in browser)
```

### Database connection error
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
sudo -u postgres psql -d baluhost -c "SELECT version();"

# Verify credentials in .env
grep DATABASE_URL /home/sven/projects/BaluHost/.env.production
```

---

## 🔄 System Maintenance

### Daily
- Monitor disk space: `df -h`
- Check service status: `systemctl status baluhost-backend nginx postgresql`

### Weekly
- Review logs for errors: `sudo journalctl -u baluhost-backend --since "7 days ago" | grep ERROR`
- Database backup: `sudo -u postgres pg_dump baluhost > ~/backup.sql`

### Monthly
- Update system packages: `sudo apt update && sudo apt upgrade`
- Review security logs
- Test database restore procedure

---

## 📊 Performance Monitoring

### Check Resource Usage
```bash
# Memory usage
free -h

# Disk usage
df -h

# CPU usage
top -bn1 | head -n 20

# Service memory usage
systemctl status baluhost-backend | grep Memory
systemctl status postgresql | grep Memory
```

### Monitor Active Connections
```bash
# Nginx connections
ss -tlnp | grep nginx

# Backend connections
ss -tlnp | grep :8000

# PostgreSQL connections
sudo -u postgres psql -d baluhost -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## ⚠️ Known Issues

### 1. Monitoring Integer Overflow (Non-Critical)
**Symptom:** Errors in logs: "integer ist außerhalb des gültigen Bereichs" for memory_samples/network_samples

**Workaround:** Ignore for now (does not affect core functionality)

**Fix:** Will be addressed in next update (BIGINT migration)

---

## 📞 Support

**Documentation:**
- Full deployment notes: `PRODUCTION_DEPLOYMENT_NOTES.md`
- Production readiness: `PRODUCTION_READINESS.md`
- Technical docs: `TECHNICAL_DOCUMENTATION.md`

**System Info:**
- Server: Debian 13, Ryzen 5 5600GT, 16GB RAM
- Backend: Python 3.13, FastAPI, PostgreSQL 17.7
- Frontend: React 18, TypeScript, Vite
- Web Server: Nginx 1.26

**Deployment Date:** January 25, 2026
**Version:** 1.3.0+production
**Status:** ✅ STABLE

---

**Last Updated:** January 25, 2026 23:45 CET
