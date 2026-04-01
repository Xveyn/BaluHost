# BaluHost Deployment Guide

Anleitung zur Installation von BaluHost auf einem Produktionsserver.

## Voraussetzungen

### Hardware
- **CPU:** 2+ Kerne (4+ empfohlen)
- **RAM:** 4 GB Minimum (8 GB+ empfohlen)
- **Speicher:** 100 GB+ (je nach Datenvolumen)
- **OS:** Debian 12+, Ubuntu 22.04+ oder kompatible Linux-Distribution

### Software
- Python 3.11+
- Node.js 18+ (für Frontend-Build)
- PostgreSQL 17+
- Nginx
- WireGuard (optional, für VPN)

## Installation

### 1. System vorbereiten

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nodejs npm \
  postgresql nginx git
```

### 2. Repository klonen

```bash
cd /opt
sudo git clone https://github.com/Xveyn/BaluHost.git baluhost
cd baluhost
```

### 3. Python-Umgebung einrichten

```bash
python3 -m venv venv
source venv/bin/activate
cd backend
pip install -e ".[prod]"
```

### 4. PostgreSQL einrichten

```bash
sudo -u postgres createuser baluhost
sudo -u postgres createdb baluhost -O baluhost
sudo -u postgres psql -c "ALTER USER baluhost PASSWORD 'sicheres-passwort';"
```

### 5. Umgebungsvariablen konfigurieren

Erstellen Sie `/opt/baluhost/.env.production`:

```env
NAS_MODE=prod
DATABASE_URL=postgresql://baluhost:sicheres-passwort@localhost:5432/baluhost
SECRET_KEY=<64-zeichen-zufallsstring>
TOKEN_SECRET=<64-zeichen-zufallsstring>
VPN_ENCRYPTION_KEY=<fernet-schlüssel>
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Secrets generieren:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 6. Datenbank-Migration

```bash
cd /opt/baluhost/backend
alembic upgrade head
```

### 7. Frontend bauen

```bash
cd /opt/baluhost/client
npm install
npm run build
sudo cp -r dist/* /var/www/baluhost/
```

### 8. Systemd-Services einrichten

**Backend-Service** (`/etc/systemd/system/baluhost-backend.service`):

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

Services aktivieren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable baluhost-backend
sudo systemctl start baluhost-backend
```

### 9. Nginx konfigurieren

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

## Verwaltung

```bash
# Status prüfen
sudo systemctl status baluhost-backend

# Logs anzeigen
sudo journalctl -u baluhost-backend -f

# Neustart
sudo systemctl restart baluhost-backend

# Stoppen
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

# Neustart
sudo systemctl restart baluhost-backend
```

## Sicherheit

- Secrets müssen mindestens 32 Zeichen lang sein (App verweigert Start mit schwachen Secrets)
- Standardpasswörter im Setup-Wizard sofort ändern
- Firewall: nur Port 80 (HTTP) und 51820/UDP (WireGuard) öffnen
- Zugang von außen nur über VPN empfohlen
- Für HTTPS siehe den SSL/TLS-Konfigurationsartikel

---

**Version:** 1.23.0  
**Letzte Aktualisierung:** April 2026
