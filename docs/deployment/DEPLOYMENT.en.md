# BaluHost Deployment Guide

Guide for installing BaluHost on a production server.

## Prerequisites

### Hardware
- **CPU:** 2+ cores (4+ recommended)
- **RAM:** 4 GB minimum (8 GB+ recommended)
- **Storage:** 100 GB+ (depends on data volume)
- **OS:** Debian 12+, Ubuntu 22.04+ or compatible Linux distribution

### Software
- Python 3.11+
- Node.js 18+ (for frontend build)
- PostgreSQL 17+
- Nginx
- WireGuard (optional, for VPN)

## Installation

### 1. Prepare System

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nodejs npm \
  postgresql nginx git
```

### 2. Clone Repository

```bash
cd /opt
sudo git clone https://github.com/Xveyn/BaluHost.git baluhost
cd baluhost
```

### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
cd backend
pip install -e ".[prod]"
```

### 4. Set Up PostgreSQL

```bash
sudo -u postgres createuser baluhost
sudo -u postgres createdb baluhost -O baluhost
sudo -u postgres psql -c "ALTER USER baluhost PASSWORD 'secure-password';"
```

### 5. Configure Environment Variables

Create `/opt/baluhost/.env.production`:

```env
NAS_MODE=prod
DATABASE_URL=postgresql://baluhost:secure-password@localhost:5432/baluhost
SECRET_KEY=<64-char-random-string>
TOKEN_SECRET=<64-char-random-string>
VPN_ENCRYPTION_KEY=<fernet-key>
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Generate secrets:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 6. Database Migration

```bash
cd /opt/baluhost/backend
alembic upgrade head
```

### 7. Build Frontend

```bash
cd /opt/baluhost/client
npm install
npm run build
sudo cp -r dist/* /var/www/baluhost/
```

### 8. Set Up Systemd Services

**Backend service** (`/etc/systemd/system/baluhost-backend.service`):

```ini
[Unit]
Description=BaluHost Backend
After=network.target postgresql.service

[Service]
Type=simple
User=baluhost
WorkingDirectory=/opt/baluhost/backend
EnvironmentFile=/opt/baluhost/.env.production
ExecStart=/opt/baluhost/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable baluhost-backend
sudo systemctl start baluhost-backend
```

### 9. Configure Nginx

```nginx
server {
    listen 80;
    server_name baluhost.local;

    root /var/www/baluhost;
    index index.html;

    # Frontend (SPA)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        limit_req zone=api burst=20 nodelay;
    }

    # WebSocket/SSE Support
    location /api/files/upload-progress/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/baluhost /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Management

```bash
# Check status
sudo systemctl status baluhost-backend

# View logs
sudo journalctl -u baluhost-backend -f

# Restart
sudo systemctl restart baluhost-backend

# Stop
sudo systemctl stop baluhost-backend
```

## Updates

```bash
cd /opt/baluhost
sudo git pull
source venv/bin/activate

# Backend
cd backend
pip install -e ".[prod]"
alembic upgrade head

# Frontend
cd ../client
npm install && npm run build
sudo cp -r dist/* /var/www/baluhost/

# Restart
sudo systemctl restart baluhost-backend
```

## Security

- Secrets must be at least 32 characters (app refuses to start with weak secrets)
- Change default passwords from the Setup Wizard immediately
- Firewall: only open port 80 (HTTP) and 51820/UDP (WireGuard)
- External access only via VPN recommended
- For HTTPS see the SSL/TLS Configuration article

---

**Version:** 1.23.0  
**Last updated:** April 2026
