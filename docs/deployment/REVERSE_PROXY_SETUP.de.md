# Reverse Proxy & SSL-Einrichtung -- Kurzreferenz

Produktionsreifer Nginx Reverse Proxy mit SSL/TLS für BaluHost.

## Enthaltene Komponenten

### Konfigurationsdateien

**Nginx-Konfigurationen**:
- `deploy/nginx/baluhost.conf` -- Hauptkonfiguration des Reverse Proxy (263 Zeilen)
- `deploy/nginx/ssl-params.conf` -- SSL/TLS Best Practices (Mozilla Intermediate)
- `deploy/nginx/security-headers.conf` -- OWASP-Sicherheitsheader

**Automatisierte Skripte**:
- `deploy/scripts/install-nginx.sh` -- Nginx-Installation & -Einrichtung
- `deploy/ssl/setup-letsencrypt.sh` -- Let's Encrypt SSL-Automatisierung

**Dokumentation**:
- `docs/SSL_SETUP.md` -- Umfassende SSL/TLS-Anleitung (600+ Zeilen)

---

## Funktionen

### SSL/TLS-Sicherheit
- Let's Encrypt kostenlose Zertifikate
- Nur TLS 1.2 + 1.3 (keine schwachen Protokolle)
- Moderne Cipher-Suites (ECDHE, AES-GCM, ChaCha20-Poly1305)
- Perfect Forward Secrecy
- OCSP Stapling
- HSTS mit Preload
- Automatische Verlängerung (Systemd-Timer + Cron-Fallback)
- Ziel: SSL Labs A/A+ Bewertung

### Sicherheitsheader (OWASP)
- X-Frame-Options (Clickjacking-Schutz)
- X-Content-Type-Options (MIME-Sniffing-Schutz)
- Content-Security-Policy (XSS-Prävention)
- Strict-Transport-Security (HSTS)
- Referrer-Policy
- Permissions-Policy
- Cross-Origin-Richtlinien (COEP, COOP, CORP)
- Ziel: securityheaders.com A-Bewertung

### Rate Limiting
- API-Endpunkte: 10 Anf./s (Burst: 20)
- Auth-Endpunkte: 5 Anf./min (Burst: 3)
- Upload-Endpunkte: 10 Anf./min (Burst: 5)
- Health Checks: unbegrenzt
- Benutzerdefinierte 429-Fehlerseiten

### Leistung
- HTTP/2 aktiviert
- Gzip-Komprimierung (Text, JSON, SVG)
- Keep-Alive-Verbindungen
- Statisches Asset-Caching (1 Jahr)
- SPA-Fallback (React Router-Unterstützung)
- WebSocket/SSE-Unterstützung (für Echtzeitfunktionen)
- Große Datei-Uploads (10 GB max, konfigurierbar)

### Proxy-Funktionen
- Backend-API-Proxy (`/api/*` -> `localhost:8000`)
- Avatar-Uploads (`/avatars/*` -> Backend)
- Frontend-Bereitstellung (Docker-Container oder statische Dateien)
- Health-Check-Endpunkt (kein Rate Limit)
- Unterstützung für langlebige Anfragen (600s+ Timeouts)
- Steuerung der Anfragepufferung

---

## Schnellstart

### 1. BaluHost mit Docker bereitstellen

```bash
cd /path/to/baluhost
cp .env.production.example .env

# Geheimnisse generieren
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('TOKEN_SECRET=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"

# .env mit generierten Werten aktualisieren
nano .env

# BaluHost starten
docker-compose up -d
```

Überprüfen Sie, ob das Backend läuft:
```bash
curl http://localhost:8000/api/system/health
```

### 2. Nginx installieren

```bash
sudo ./deploy/scripts/install-nginx.sh
```

Dies installiert und konfiguriert Nginx mit allen erforderlichen Verzeichnissen und Optimierungen.

### 3. SSL mit Let's Encrypt einrichten

```bash
sudo ./deploy/ssl/setup-letsencrypt.sh yourdomain.com admin@yourdomain.com
```

Ersetzen Sie:
- `yourdomain.com` durch Ihre tatsächliche Domain
- `admin@yourdomain.com` durch Ihre E-Mail-Adresse

Voraussetzungen:
- Der DNS-A-Eintrag der Domain zeigt auf Ihre Server-IP
- Ports 80 und 443 sind in der Firewall geöffnet

### 4. BaluHost-Seite aktivieren

```bash
# Konfiguration überprüfen (Backend-Upstream verifizieren)
sudo nano /etc/nginx/sites-available/baluhost.conf

# Seite aktivieren
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Testen
sudo nginx -t

# Neu laden
sudo systemctl reload nginx
```

### 5. Überprüfen

```bash
# HTTPS testen
curl -I https://yourdomain.com

# Zertifikat prüfen
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com | openssl x509 -noout -dates

# Im Browser testen
open https://yourdomain.com
```

**Sicherheitsaudits**:
- SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
- Security Headers: https://securityheaders.com/?q=yourdomain.com

---

## Konfigurationsübersicht

### Nginx-Seitenstruktur

```nginx
# HTTP-Server (Port 80)
server {
    listen 80;

    # ACME-Challenge für Let's Encrypt
    location ^~ /.well-known/acme-challenge/ { ... }

    # Alles andere auf HTTPS umleiten
    location / { return 301 https://$server_name$request_uri; }
}

# HTTPS-Server (Port 443)
server {
    listen 443 ssl http2;

    # SSL-Konfiguration
    ssl_certificate /etc/letsencrypt/live/domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/domain/privkey.pem;
    include /etc/nginx/snippets/ssl-params.conf;
    include /etc/nginx/snippets/security-headers.conf;

    # Locations:
    # - /api/ -> Backend-Proxy
    # - /api/auth/* -> Strengeres Rate Limiting
    # - /api/files/upload -> Upload-spezifische Konfiguration
    # - /avatars/ -> Backend-Proxy mit Caching
    # - / -> Frontend (SPA)
    # - Statische Assets -> Caching
}
```

### Backend-Upstream

**Für Docker-Compose-Bereitstellung**:
```nginx
upstream baluhost_backend {
    server localhost:8000;
    keepalive 32;
}
```

**Für Systemd-Bereitstellung**:
```nginx
upstream baluhost_backend {
    server unix:/run/baluhost/backend.sock;
    keepalive 32;
}
```

### Rate-Limiting-Zonen

```nginx
# Zonen definieren
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=upload_limit:10m rate=10r/m;

# Auf Locations anwenden
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    limit_req_status 429;
    # ...
}
```

---

## Anpassung

### Rate Limits anpassen

Bearbeiten Sie `deploy/nginx/baluhost.conf`:

```nginx
# Großzügiger (für stark frequentierte Seiten)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=50r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/m;

# Restriktiver (für private Bereitstellungen)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=5r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=3r/m;
```

### Upload-Größenlimit anpassen

```nginx
# Maximale Upload-Größe auf 50 GB erhöhen
client_max_body_size 50G;
```

### Admin-Endpunkte einschränken

```nginx
location /api/admin {
    # Nur aus dem lokalen Netzwerk erlauben
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;

    proxy_pass http://baluhost_backend;
}
```

### Benutzerdefinierte Fehlerseiten

```nginx
error_page 404 /404.html;
error_page 500 502 503 504 /50x.html;

location = /50x.html {
    root /usr/share/nginx/html;
}
```

### Caching aktivieren

```nginx
# Cache definieren
proxy_cache_path /var/cache/nginx/baluhost levels=1:2 keys_zone=baluhost_cache:10m max_size=1g inactive=60m;

# Cache verwenden
location /api/ {
    proxy_cache baluhost_cache;
    proxy_cache_valid 200 5m;
    proxy_cache_methods GET HEAD;
    proxy_cache_key "$scheme$request_method$host$request_uri";
    add_header X-Cache-Status $upstream_cache_status;
    # ...
}
```

---

## Wartung

### Zertifikatsverlängerung

Automatisch über Systemd-Timer. Manuelle Verlängerung:

```bash
sudo certbot renew
sudo systemctl reload nginx
```

Verlängerung testen:
```bash
sudo certbot renew --dry-run
```

### Nginx-Konfiguration aktualisieren

```bash
# Bearbeiten
sudo nano /etc/nginx/sites-available/baluhost.conf

# Testen
sudo nginx -t

# Anwenden
sudo systemctl reload nginx
```

### Logs überwachen

```bash
# Zugriffslogs
sudo tail -f /var/log/nginx/baluhost_access.log

# Fehlerlogs
sudo tail -f /var/log/nginx/baluhost_error.log

# Nach IP filtern
sudo command grep "192.168.1.100" /var/log/nginx/baluhost_access.log

# Nur Fehler anzeigen
sudo command grep "error" /var/log/nginx/baluhost_error.log
```

### SSL-Zertifikat prüfen

```bash
# Ablaufdatum
sudo certbot certificates

# Über OpenSSL
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>/dev/null | openssl x509 -noout -dates
```

---

## Fehlerbehebung

### Häufige Probleme

**1. SSL-Zertifikat kann nicht bezogen werden**
- DNS prüfen: `host yourdomain.com`
- Port 80 prüfen: `curl http://yourdomain.com/.well-known/acme-challenge/test`
- Firewall prüfen: `sudo ufw status` oder `sudo iptables -L -n`
- Logs ansehen: `sudo tail -f /var/log/letsencrypt/letsencrypt.log`

**2. 502 Bad Gateway**
- Backend läuft nicht: `docker-compose ps` oder `systemctl status baluhost-backend`
- Falscher Upstream: `upstream baluhost_backend` in der Konfiguration prüfen
- Backend hört auf falscher Schnittstelle: Sollte `0.0.0.0:8000` sein

**3. Rate-Limit-Fehler (429)**
- Rate Limits in der Konfiguration anpassen
- Client-IP prüfen: `$binary_remote_addr` in den Logs
- IP-Whitelisting für vertrauenswürdige Quellen erwägen

**4. Mixed-Content-Warnungen**
- Frontend auf relative URLs umstellen
- CORS_ORIGINS in .env enthält https:// prüfen
- Sicherstellen, dass alle API-Aufrufe HTTPS verwenden

**5. Großer Upload schlägt fehl**
- `client_max_body_size` erhöhen
- Timeouts erhöhen: `client_body_timeout`, `proxy_read_timeout`
- Festplattenspeicher auf dem Server prüfen

### Debug-Befehle

```bash
# Nginx-Konfiguration testen
sudo nginx -t

# Nginx neu laden
sudo systemctl reload nginx

# Nginx neu starten
sudo systemctl restart nginx

# Nginx-Status prüfen
sudo systemctl status nginx

# SSL-Handshake testen
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Zertifikatskette prüfen
openssl s_client -connect yourdomain.com:443 -showcerts

# Von anderem Standort testen (Cache umgehen)
curl -H "Cache-Control: no-cache" https://yourdomain.com/api/system/health

# Rate Limiting prüfen
for i in {1..20}; do curl -s -o /dev/null -w "%{http_code}\n" https://yourdomain.com/api/; done
```

---

## Sicherheitscheckliste

Vor der Inbetriebnahme:

- [ ] SSL-Zertifikat gültig und automatisch verlängernd
- [ ] HTTPS erzwungen (HTTP leitet auf HTTPS um)
- [ ] Sicherheitsheader konfiguriert (A-Bewertung auf securityheaders.com)
- [ ] Rate Limiting auf allen Endpunkten aktiv
- [ ] Firewall konfiguriert (nur Ports 80, 443, 22 offen)
- [ ] Admin-Endpunkte eingeschränkt (optional)
- [ ] Serverversion verborgen (`server_tokens off`)
- [ ] Logs überwacht und rotiert
- [ ] Backup der Nginx-Konfiguration und SSL-Zertifikate
- [ ] DNS-CAA-Einträge konfiguriert (optional, aber empfohlen)
- [ ] DNSSEC aktiviert (optional)

---

## Leistungscheckliste

- [ ] HTTP/2 aktiviert
- [ ] Gzip-Komprimierung aktiviert
- [ ] Statisches Asset-Caching konfiguriert
- [ ] Keep-Alive-Verbindungen aktiviert
- [ ] Worker-Verbindungen optimiert (2048+)
- [ ] Connection Pooling zum Backend (Keepalive)
- [ ] Slow Log konfiguriert (optional)
- [ ] Monitoring eingerichtet (optional: Prometheus, Grafana)

---

## Ressourcen

- **Vollständige Anleitung**: Siehe `docs/SSL_SETUP.md` für umfassende Dokumentation
- **Produktionsbereitschaft**: Siehe `PRODUCTION_READINESS.md`
- **Nginx-Dokumentation**: https://nginx.org/en/docs/
- **Let's Encrypt**: https://letsencrypt.org/docs/
- **Mozilla SSL Config**: https://ssl-config.mozilla.org/
- **OWASP Headers**: https://owasp.org/www-project-secure-headers/

---

## Support

Probleme? Prüfen Sie:
1. `docs/SSL_SETUP.md` -- Umfassende Fehlerbehebung
2. Nginx-Fehlerlogs: `/var/log/nginx/baluhost_error.log`
3. Let's Encrypt-Logs: `/var/log/letsencrypt/letsencrypt.log`
4. BaluHost-Logs: `docker-compose logs backend`

---

**Erstellt**: 13. Januar 2026
**Status**: Produktionsreifer Reverse Proxy mit SSL/TLS
**Zielbewertungen**: SSL Labs A+, Security Headers A
