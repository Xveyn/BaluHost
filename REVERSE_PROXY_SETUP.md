# Reverse Proxy & SSL Setup - Quick Reference

Production-grade Nginx reverse proxy with SSL/TLS for BaluHost.

## What's Included

### Configuration Files

✅ **Nginx Configs**:
- `deploy/nginx/baluhost.conf` - Main reverse proxy configuration (263 lines)
- `deploy/nginx/ssl-params.conf` - SSL/TLS best practices (Mozilla Intermediate)
- `deploy/nginx/security-headers.conf` - OWASP security headers

✅ **Automated Scripts**:
- `deploy/scripts/install-nginx.sh` - Nginx installation & setup
- `deploy/ssl/setup-letsencrypt.sh` - Let's Encrypt SSL automation

✅ **Documentation**:
- `docs/SSL_SETUP.md` - Comprehensive SSL/TLS guide (600+ lines)

---

## Features

### SSL/TLS Security
- ✅ Let's Encrypt free certificates
- ✅ TLS 1.2 + 1.3 only (no weak protocols)
- ✅ Modern cipher suites (ECDHE, AES-GCM, ChaCha20-Poly1305)
- ✅ Perfect forward secrecy
- ✅ OCSP stapling
- ✅ HSTS with preload
- ✅ Automatic renewal (systemd timer + cron fallback)
- 🎯 Target: SSL Labs A/A+ grade

### Security Headers (OWASP)
- ✅ X-Frame-Options (clickjacking protection)
- ✅ X-Content-Type-Options (MIME sniffing protection)
- ✅ Content-Security-Policy (XSS prevention)
- ✅ Strict-Transport-Security (HSTS)
- ✅ Referrer-Policy
- ✅ Permissions-Policy
- ✅ Cross-Origin policies (COEP, COOP, CORP)
- 🎯 Target: securityheaders.com A grade

### Rate Limiting
- ✅ API endpoints: 10 req/s (burst: 20)
- ✅ Auth endpoints: 5 req/min (burst: 3)
- ✅ Upload endpoints: 10 req/min (burst: 5)
- ✅ Health checks: unlimited
- ✅ Custom 429 error pages

### Performance
- ✅ HTTP/2 enabled
- ✅ Gzip compression (text, json, svg)
- ✅ Keep-alive connections
- ✅ Static asset caching (1 year)
- ✅ SPA fallback (React Router support)
- ✅ WebSocket/SSE support (for real-time features)
- ✅ Large file uploads (10GB max, configurable)

### Proxy Features
- ✅ Backend API proxy (`/api/*` → `localhost:8000`)
- ✅ Avatar uploads (`/avatars/*` → backend)
- ✅ Frontend serving (Docker container or static files)
- ✅ Health check endpoint (no rate limit)
- ✅ Long-running request support (600s+ timeouts)
- ✅ Request buffering control

---

## Quick Start

### 1. Deploy BaluHost with Docker

```bash
cd /path/to/baluhost
cp .env.production.example .env

# Generate secrets
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('TOKEN_SECRET=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"

# Update .env with generated values
nano .env

# Start BaluHost
docker-compose up -d
```

Verify backend is running:
```bash
curl http://localhost:8000/api/system/health
```

### 2. Install Nginx

```bash
sudo ./deploy/scripts/install-nginx.sh
```

This installs and configures Nginx with all necessary directories and optimizations.

### 3. Setup SSL with Let's Encrypt

```bash
sudo ./deploy/ssl/setup-letsencrypt.sh yourdomain.com admin@yourdomain.com
```

Replace:
- `yourdomain.com` with your actual domain
- `admin@yourdomain.com` with your email

Prerequisites:
- Domain's DNS A record points to your server IP
- Ports 80 and 443 are open in firewall

### 4. Enable BaluHost Site

```bash
# Review config (verify backend upstream)
sudo nano /etc/nginx/sites-available/baluhost.conf

# Enable site
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Test
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

### 5. Verify

```bash
# Test HTTPS
curl -I https://yourdomain.com

# Check certificate
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com | openssl x509 -noout -dates

# Test in browser
open https://yourdomain.com
```

**Security Audits**:
- SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
- Security Headers: https://securityheaders.com/?q=yourdomain.com

---

## Configuration Overview

### Nginx Site Structure

```nginx
# HTTP Server (Port 80)
server {
    listen 80;

    # ACME challenge for Let's Encrypt
    location ^~ /.well-known/acme-challenge/ { ... }

    # Redirect everything else to HTTPS
    location / { return 301 https://$server_name$request_uri; }
}

# HTTPS Server (Port 443)
server {
    listen 443 ssl http2;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/domain/privkey.pem;
    include /etc/nginx/snippets/ssl-params.conf;
    include /etc/nginx/snippets/security-headers.conf;

    # Locations:
    # - /api/ → Backend proxy
    # - /api/auth/* → Stricter rate limiting
    # - /api/files/upload → Upload-specific config
    # - /avatars/ → Backend proxy with caching
    # - / → Frontend (SPA)
    # - Static assets → Caching
}
```

### Backend Upstream

**For Docker Compose deployment**:
```nginx
upstream baluhost_backend {
    server localhost:8000;
    keepalive 32;
}
```

**For systemd deployment**:
```nginx
upstream baluhost_backend {
    server unix:/run/baluhost/backend.sock;
    keepalive 32;
}
```

### Rate Limiting Zones

```nginx
# Define zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=upload_limit:10m rate=10r/m;

# Apply to locations
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    limit_req_status 429;
    # ...
}
```

---

## Customization

### Adjust Rate Limits

Edit `deploy/nginx/baluhost.conf`:

```nginx
# More permissive (for high-traffic sites)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=50r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/m;

# More restrictive (for private deployments)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=5r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=3r/m;
```

### Adjust Upload Size Limit

```nginx
# Increase max upload size to 50GB
client_max_body_size 50G;
```

### Restrict Admin Endpoints

```nginx
location /api/admin {
    # Only allow from local network
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;

    proxy_pass http://baluhost_backend;
}
```

### Custom Error Pages

```nginx
error_page 404 /404.html;
error_page 500 502 503 504 /50x.html;

location = /50x.html {
    root /usr/share/nginx/html;
}
```

### Enable Caching

```nginx
# Define cache
proxy_cache_path /var/cache/nginx/baluhost levels=1:2 keys_zone=baluhost_cache:10m max_size=1g inactive=60m;

# Use cache
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

## Maintenance

### Certificate Renewal

Automatic via systemd timer. Manual renewal:

```bash
sudo certbot renew
sudo systemctl reload nginx
```

Test renewal:
```bash
sudo certbot renew --dry-run
```

### Update Nginx Config

```bash
# Edit
sudo nano /etc/nginx/sites-available/baluhost.conf

# Test
sudo nginx -t

# Apply
sudo systemctl reload nginx
```

### Monitor Logs

```bash
# Access logs
sudo tail -f /var/log/nginx/baluhost_access.log

# Error logs
sudo tail -f /var/log/nginx/baluhost_error.log

# Filter by IP
sudo grep "192.168.1.100" /var/log/nginx/baluhost_access.log

# Show only errors
sudo grep "error" /var/log/nginx/baluhost_error.log
```

### Check SSL Certificate

```bash
# Expiry date
sudo certbot certificates

# Via OpenSSL
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>/dev/null | openssl x509 -noout -dates
```

---

## Troubleshooting

### Common Issues

**1. SSL Certificate Fails to Obtain**
- Check DNS: `host yourdomain.com`
- Check port 80: `curl http://yourdomain.com/.well-known/acme-challenge/test`
- Check firewall: `sudo ufw status` or `sudo iptables -L -n`
- View logs: `sudo tail -f /var/log/letsencrypt/letsencrypt.log`

**2. 502 Bad Gateway**
- Backend not running: `docker-compose ps` or `systemctl status baluhost-backend`
- Wrong upstream: Check `upstream baluhost_backend` in config
- Backend listening on wrong interface: Should be `0.0.0.0:8000`

**3. Rate Limit Errors (429)**
- Adjust rate limits in config
- Check client IP: `$binary_remote_addr` in logs
- Consider IP whitelisting for trusted sources

**4. Mixed Content Warnings**
- Update frontend to use relative URLs
- Check CORS_ORIGINS in .env includes https://
- Verify all API calls use HTTPS

**5. Large Upload Fails**
- Increase `client_max_body_size`
- Increase timeouts: `client_body_timeout`, `proxy_read_timeout`
- Check disk space on server

### Debug Commands

```bash
# Test Nginx config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Restart Nginx
sudo systemctl restart nginx

# Check Nginx status
sudo systemctl status nginx

# Test SSL handshake
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Check certificate chain
openssl s_client -connect yourdomain.com:443 -showcerts

# Test from different location (bypass cache)
curl -H "Cache-Control: no-cache" https://yourdomain.com/api/system/health

# Check rate limiting
for i in {1..20}; do curl -s -o /dev/null -w "%{http_code}\n" https://yourdomain.com/api/; done
```

---

## Security Checklist

Before going live:

- [ ] SSL certificate valid and auto-renewing
- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] Security headers configured (A grade on securityheaders.com)
- [ ] Rate limiting active on all endpoints
- [ ] Firewall configured (only 80, 443, 22 open)
- [ ] Admin endpoints restricted (optional)
- [ ] Server version hidden (`server_tokens off`)
- [ ] Logs monitored and rotated
- [ ] Backup of Nginx config and SSL certificates
- [ ] DNS CAA records configured (optional but recommended)
- [ ] DNSSEC enabled (optional)

---

## Performance Checklist

- [ ] HTTP/2 enabled
- [ ] Gzip compression enabled
- [ ] Static asset caching configured
- [ ] Keep-alive connections enabled
- [ ] Worker connections optimized (2048+)
- [ ] Connection pooling to backend (keepalive)
- [ ] Slow log configured (optional)
- [ ] Monitoring setup (optional: Prometheus, Grafana)

---

## Resources

- **Full Guide**: See `docs/SSL_SETUP.md` for comprehensive documentation
- **Docker Deployment**: See `DOCKER_QUICKSTART.md`
- **Production Readiness**: See `PRODUCTION_READINESS.md`
- **Nginx Docs**: https://nginx.org/en/docs/
- **Let's Encrypt**: https://letsencrypt.org/docs/
- **Mozilla SSL Config**: https://ssl-config.mozilla.org/
- **OWASP Headers**: https://owasp.org/www-project-secure-headers/

---

## Support

Issues? Check:
1. `docs/SSL_SETUP.md` - Comprehensive troubleshooting
2. Nginx error logs: `/var/log/nginx/baluhost_error.log`
3. Let's Encrypt logs: `/var/log/letsencrypt/letsencrypt.log`
4. BaluHost logs: `docker-compose logs backend`

---

**Created**: January 13, 2026
**Status**: Production-ready reverse proxy with SSL/TLS
**Grade Targets**: SSL Labs A+, Security Headers A
