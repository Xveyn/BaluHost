# BaluHost Production Deployment Guide

This guide covers deploying BaluHost to production using Docker Compose (recommended) or native systemd installation.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (5 Minutes)](#quick-start-5-minutes)
3. [Detailed Docker Deployment](#detailed-docker-deployment)
4. [SSL/TLS Configuration](#ssltls-configuration)
5. [Monitoring Setup](#monitoring-setup)
6. [Backup Configuration](#backup-configuration)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance](#maintenance)

---

## Prerequisites

### Hardware Requirements
- **CPU**: 2+ cores (4+ recommended)
- **RAM**: 4GB minimum (8GB+ recommended)
- **Storage**: 100GB+ (depends on user data)
- **OS**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+, or compatible)

### Software Requirements
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **Domain name** with DNS configured (A record pointing to your server)
- **Ports**: 80 (HTTP), 443 (HTTPS) open in firewall

### Installation of Dependencies
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git

# Start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to docker group (logout/login required)
sudo usermod -aG docker $USER
```

---

## Quick Start (5 Minutes)

### 1. Clone Repository
```bash
git clone https://github.com/your-org/baluhost.git
cd baluhost
```

### 2. Configure Environment
```bash
# Copy environment template
cp .env.production.example .env

# Generate secure secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('TOKEN_SECRET=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(16))"

# Edit .env file with your values
nano .env
```

**Required changes in `.env`**:
- `SECRET_KEY`: Use generated value above
- `TOKEN_SECRET`: Use generated value above
- `POSTGRES_PASSWORD`: Use generated value above
- `DOMAIN`: Your domain (e.g., `nas.example.com`)
- `CORS_ORIGINS`: `https://nas.example.com` (your domain)

### 3. Deploy
```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
```

### 4. Setup SSL (Let's Encrypt)
```bash
# Run automated SSL setup
sudo ./deploy/ssl/setup-letsencrypt.sh nas.example.com admin@example.com
```

### 5. Access BaluHost
- **Web UI**: https://nas.example.com
- **API Docs**: https://nas.example.com/api/docs
- **Default Login**: `admin` / `admin123` (change immediately!)

---

## Detailed Docker Deployment

### Architecture Overview
```
┌─────────────────────────────────┐
│    Nginx Reverse Proxy (Host)  │
│  SSL Termination + Rate Limit  │
└────────────┬────────────────────┘
             │
    ┌────────┴─────────┐
    │                  │
┌───▼────────┐  ┌──────▼──────┐
│  Frontend  │  │   Backend   │
│  (Nginx)   │  │  (Uvicorn)  │
│  Port 80   │  │  Port 8000  │
└────────────┘  └──────┬───────┘
                       │
                ┌──────▼────────┐
                │  PostgreSQL   │
                │   Port 5432   │
                └───────────────┘
```

### Step-by-Step Deployment

#### 1. Prepare Server
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx

# Configure firewall
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

#### 2. Clone and Configure
```bash
# Clone repository
cd /opt
sudo git clone https://github.com/your-org/baluhost.git
cd baluhost

# Set permissions
sudo chown -R $USER:$USER .

# Copy environment file
cp .env.production.example .env
```

#### 3. Edit Environment Variables
```bash
nano .env
```

**Critical Settings**:
```bash
# Application
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
SECRET_KEY=<generated-32-char-secret>
TOKEN_SECRET=<generated-32-char-secret>

# Database
POSTGRES_DB=baluhost
POSTGRES_USER=baluhost
POSTGRES_PASSWORD=<generated-password>
DATABASE_URL=postgresql://baluhost:<password>@postgres:5432/baluhost

# Domain
DOMAIN=nas.example.com
CORS_ORIGINS=https://nas.example.com

# Admin user (change password after first login!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# Backup automation (recommended)
BACKUP_AUTO_ENABLED=true
BACKUP_AUTO_INTERVAL_HOURS=24
BACKUP_AUTO_TYPE=full
```

#### 4. Start Services
```bash
# Build and start containers
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output:
# NAME                STATUS    PORTS
# baluhost-backend    Up        0.0.0.0:8000->8000/tcp
# baluhost-frontend   Up        0.0.0.0:80->80/tcp
# baluhost-postgres   Up        5432/tcp
```

#### 5. Check Logs
```bash
# Backend logs
docker-compose logs -f backend

# Frontend logs
docker-compose logs -f frontend

# All services
docker-compose logs -f
```

#### 6. Verify Deployment
```bash
# Check backend health
curl http://localhost:8000/api/system/health

# Expected response:
# {"status":"healthy","version":"1.4.0","database":"connected"}

# Check frontend
curl http://localhost/

# Should return HTML
```

---

## SSL/TLS Configuration

### Automated Setup (Recommended)

```bash
# Run Let's Encrypt setup script
sudo ./deploy/ssl/setup-letsencrypt.sh nas.example.com admin@example.com

# This script will:
# 1. Install certbot
# 2. Obtain SSL certificate
# 3. Configure nginx
# 4. Setup auto-renewal
```

### Manual Setup

#### 1. Install Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
```

#### 2. Obtain Certificate
```bash
sudo certbot --nginx -d nas.example.com --email admin@example.com --agree-tos --no-eff-email
```

#### 3. Configure Nginx
```bash
# Copy BaluHost nginx config
sudo cp deploy/nginx/baluhost.conf /etc/nginx/sites-available/baluhost.conf

# Update domain in config
sudo sed -i 's/your-domain.com/nas.example.com/g' /etc/nginx/sites-available/baluhost.conf

# Enable site
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

#### 4. Verify SSL
```bash
# Test SSL configuration
curl -I https://nas.example.com

# Check certificate
openssl s_client -connect nas.example.com:443 -servername nas.example.com
```

### Auto-Renewal

Certbot automatically sets up renewal. Verify:
```bash
# Check renewal timer (systemd)
sudo systemctl status certbot.timer

# Test renewal (dry run)
sudo certbot renew --dry-run
```

---

## Monitoring Setup

BaluHost includes Prometheus + Grafana for monitoring.

### Enable Monitoring
```bash
# Start with monitoring profile
docker-compose --profile monitoring up -d

# Verify services
docker-compose ps

# Expected additional services:
# baluhost-prometheus   Up   9090/tcp
# baluhost-grafana      Up   0.0.0.0:3000->3000/tcp
```

### Access Dashboards

**Grafana**: http://nas.example.com:3000
- Username: `admin`
- Password: `admin` (change on first login)

**Prometheus**: http://nas.example.com:9090

### Pre-configured Dashboards

1. **System Overview** - CPU, Memory, Disk, Network
2. **RAID Health** - RAID status, disk count, resync progress
3. **Application Metrics** - HTTP requests, file operations

### Configure Alerts

Edit alert rules:
```bash
nano deploy/prometheus/alerts.yml
```

Example alert for low disk space:
```yaml
- alert: LowDiskSpace
  expr: baluhost_disk_free_percent < 10
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Low disk space on {{ $labels.mountpoint }}"
    description: "Only {{ $value }}% free space remaining"
```

Reload Prometheus:
```bash
docker-compose restart prometheus
```

---

## Backup Configuration

### Automated Backups (Recommended)

Configured via `.env`:
```bash
# Enable automatic backups
BACKUP_AUTO_ENABLED=true

# Backup interval (hours)
BACKUP_AUTO_INTERVAL_HOURS=24  # Daily

# Backup type
BACKUP_AUTO_TYPE=full  # full|incremental|database_only|files_only

# Retention policy
NAS_BACKUP_MAX_COUNT=10  # Keep 10 backups
NAS_BACKUP_RETENTION_DAYS=30  # Delete after 30 days
```

Restart backend to apply:
```bash
docker-compose restart backend
```

### Manual Backups

Use the deployment script:
```bash
# Full backup
./deploy/scripts/backup.sh

# Database only
./deploy/scripts/backup.sh --type database_only

# Files only
./deploy/scripts/backup.sh --type files_only

# Without Docker
cd backend
python -c "
from app.core.database import SessionLocal
from app.services.backup import BackupService
from app.schemas.backup import BackupCreate
db = SessionLocal()
service = BackupService(db)
backup = service.create_backup(
    BackupCreate(backup_type='full'),
    creator_id=1,
    creator_username='admin'
)
print(f'Backup created: {backup.filename}')
db.close()
"
```

### Backup Location

Backups are stored in:
- **Docker**: `./backups/` (mounted volume)
- **Native**: `/var/lib/baluhost/backups/`

### Off-site Backup Strategy

**Recommended**: Copy backups to external storage
```bash
# Sync to S3
aws s3 sync ./backups/ s3://my-bucket/baluhost-backups/

# Sync to remote server
rsync -avz ./backups/ user@backup-server:/backups/baluhost/

# Setup cron job
crontab -e
# Add:
0 3 * * * aws s3 sync /opt/baluhost/backups/ s3://my-bucket/baluhost-backups/
```

---

## Troubleshooting

### Backend Won't Start

**Check logs**:
```bash
docker-compose logs backend
```

**Common issues**:
1. **Database connection failed**
   - Verify `DATABASE_URL` in `.env`
   - Check PostgreSQL is running: `docker-compose ps postgres`
   - Check PostgreSQL logs: `docker-compose logs postgres`

2. **Port already in use**
   ```bash
   # Find process using port 8000
   sudo lsof -i :8000
   # Kill process or change BACKEND_PORT in .env
   ```

3. **Permission errors**
   ```bash
   # Fix volume permissions
   sudo chown -R 1000:1000 ./storage ./backups ./logs
   ```

### Frontend Not Accessible

**Check nginx status**:
```bash
docker-compose logs frontend
```

**Verify proxy configuration**:
```bash
# Test backend from frontend container
docker exec baluhost-frontend curl http://backend:8000/api/system/health
```

### SSL Certificate Issues

**Certificate not obtained**:
```bash
# Check DNS propagation
dig nas.example.com

# Verify port 80 is accessible
curl http://nas.example.com/.well-known/acme-challenge/test
```

**Certificate renewal failing**:
```bash
# Check certbot logs
sudo journalctl -u certbot

# Manual renewal
sudo certbot renew --force-renewal
```

### Database Issues

**Connection refused**:
```bash
# Check PostgreSQL container
docker-compose ps postgres

# Enter PostgreSQL container
docker exec -it baluhost-postgres psql -U baluhost

# Test connection from backend
docker exec baluhost-backend python -c "
from app.core.database import engine
conn = engine.connect()
print('Connected successfully')
conn.close()
"
```

**Slow queries**:
```bash
# Enable query logging in docker-compose.yml
# Add under postgres service:
command: postgres -c log_statement=all -c log_min_duration_statement=1000
```

### Performance Issues

**High CPU usage**:
```bash
# Check resource usage
docker stats

# Reduce telemetry frequency in .env
TELEMETRY_INTERVAL_SECONDS=5.0  # Default: 2.0
```

**Out of memory**:
```bash
# Increase Docker memory limit
# Edit /etc/docker/daemon.json
{
  "default-ulimits": {
    "memlock": {"Hard": -1, "Soft": -1}
  }
}

# Restart Docker
sudo systemctl restart docker
```

---

## Maintenance

### Update BaluHost

```bash
# Pull latest code
cd /opt/baluhost
git pull

# Backup current database
./deploy/scripts/backup.sh --type database_only

# Rebuild and restart
docker-compose build
docker-compose up -d

# Run database migrations (if any)
docker exec baluhost-backend alembic upgrade head
```

### Database Backup & Restore

**Backup**:
```bash
# Via Docker
docker exec baluhost-postgres pg_dump -U baluhost baluhost > backup.sql

# Compressed
docker exec baluhost-postgres pg_dump -U baluhost baluhost | gzip > backup.sql.gz
```

**Restore**:
```bash
# Stop backend
docker-compose stop backend

# Restore database
cat backup.sql | docker exec -i baluhost-postgres psql -U baluhost baluhost

# Or from compressed
gunzip -c backup.sql.gz | docker exec -i baluhost-postgres psql -U baluhost baluhost

# Start backend
docker-compose start backend
```

### Log Rotation

Configure log rotation to prevent disk space issues:
```bash
# Create logrotate config
sudo nano /etc/logrotate.d/baluhost

# Add:
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  missingok
  delaycompress
  copytruncate
}
```

### Security Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker-compose pull
docker-compose up -d

# Remove old images
docker image prune -a
```

### Monitoring Disk Space

```bash
# Check disk usage
df -h

# Check Docker volumes
docker system df

# Clean up unused resources
docker system prune -a --volumes
```

---

## Production Checklist

Before going live, verify:

- [ ] `.env` configured with secure secrets
- [ ] `ADMIN_PASSWORD` changed from default
- [ ] `DEBUG=false` in production
- [ ] SSL certificate installed and valid
- [ ] Firewall configured (ports 80, 443 open)
- [ ] Backup automation enabled
- [ ] Off-site backup configured
- [ ] Monitoring dashboards accessible
- [ ] Alert rules configured
- [ ] Domain DNS configured correctly
- [ ] CORS origins set to production domain
- [ ] PostgreSQL password changed from default
- [ ] Log rotation configured
- [ ] Tested backup restore procedure
- [ ] Documented admin credentials securely

---

## Support & Resources

- **Documentation**: [TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md)
- **Production Readiness**: [PRODUCTION_READINESS.md](./PRODUCTION_READINESS.md)
- **Monitoring Guide**: [MONITORING.md](../monitoring/MONITORING.md)
- **Security Policy**: [SECURITY.md](../security/SECURITY.md)
- **GitHub Issues**: https://github.com/your-org/baluhost/issues

---

**Last Updated**: January 2026
**Version**: 1.4.0
