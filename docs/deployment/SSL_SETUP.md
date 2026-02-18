# SSL/TLS Configuration Guide for BaluHost

Complete guide for setting up production-grade SSL/TLS encryption with Let's Encrypt.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start (Automated)](#quick-start-automated)
4. [Manual Setup](#manual-setup)
5. [Configuration Reference](#configuration-reference)
6. [Security Best Practices](#security-best-practices)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance](#maintenance)

---

## Overview

This guide covers setting up:
- **Let's Encrypt SSL certificates** (free, auto-renewing)
- **Nginx reverse proxy** with SSL termination
- **Modern TLS configuration** (TLS 1.2, TLS 1.3)
- **Security headers** (HSTS, CSP, etc.)
- **Rate limiting** and DDoS protection
- **Automatic certificate renewal**

Target SSL grade: **A or A+** on [SSL Labs](https://www.ssllabs.com/ssltest/)

---

## Prerequisites

### System Requirements

- **OS**: Ubuntu 20.04+, Debian 11+, RHEL 8+, or compatible
- **RAM**: 512MB minimum (1GB recommended)
- **Disk**: 2GB free space
- **Access**: Root or sudo privileges

### Network Requirements

1. **Domain name** pointing to your server
   - Configure DNS A record: `yourdomain.com → your-server-ip`
   - Wait for DNS propagation (up to 48 hours)
   - Verify with: `host yourdomain.com`

2. **Open firewall ports**:
   - Port 80 (HTTP) - required for Let's Encrypt validation
   - Port 443 (HTTPS) - for encrypted traffic
   - Port 22 (SSH) - for server access

3. **BaluHost deployed**:
   - Docker Compose: Backend running on `localhost:8000`
   - Systemd: Backend service active

---

## Quick Start (Automated)

### Step 1: Install Nginx

```bash
cd /path/to/baluhost
sudo ./deploy/scripts/install-nginx.sh
```

This script:
- Installs Nginx
- Configures firewall (ufw/firewalld)
- Creates necessary directories
- Optimizes nginx.conf
- Installs BaluHost config templates

### Step 2: Setup SSL with Let's Encrypt

```bash
sudo ./deploy/ssl/setup-letsencrypt.sh yourdomain.com admin@yourdomain.com
```

Replace:
- `yourdomain.com` with your actual domain
- `admin@yourdomain.com` with your email (for renewal notifications)

This script:
- Checks DNS configuration
- Installs Certbot
- Obtains SSL certificate
- Generates dhparam.pem (2048-bit)
- Configures auto-renewal
- Updates Nginx config with your domain

### Step 3: Enable BaluHost Site

```bash
# Review configuration
sudo nano /etc/nginx/sites-available/baluhost.conf

# Verify backend upstream is correct:
# - Docker: server localhost:8000;
# - Systemd: server unix:/run/baluhost/backend.sock;

# Enable site
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Step 4: Verify

```bash
# Check SSL certificate
curl -I https://yourdomain.com

# Test in browser
open https://yourdomain.com
```

**Verification Tests**:
- SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
- Security Headers: https://securityheaders.com/?q=yourdomain.com

Target grades: SSL Labs A/A+, Security Headers A

---

## Manual Setup

If automated scripts fail or you prefer manual control:

### 1. Install Nginx

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

**RHEL/CentOS/Fedora**:
```bash
sudo yum install nginx
# or
sudo dnf install nginx

sudo systemctl enable nginx
sudo systemctl start nginx
```

### 2. Configure Firewall

**UFW (Ubuntu/Debian)**:
```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status
```

**Firewalld (RHEL/CentOS)**:
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo firewall-cmd --list-all
```

### 3. Install Certbot

**Ubuntu/Debian**:
```bash
sudo apt install certbot python3-certbot-nginx
```

**RHEL/CentOS**:
```bash
sudo yum install certbot python3-certbot-nginx
# or
sudo dnf install certbot python3-certbot-nginx
```

### 4. Obtain Certificate

**Method A: Nginx plugin (recommended)**:
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

**Method B: Webroot method**:
```bash
# Create webroot
sudo mkdir -p /var/www/certbot

# Obtain certificate
sudo certbot certonly --webroot -w /var/www/certbot \
  -d yourdomain.com -d www.yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos
```

### 5. Generate dhparam

```bash
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048
```

*Note: This takes 5-10 minutes. For faster generation (less secure):*
```bash
sudo openssl dhparam -out /etc/nginx/dhparam.pem 1024
```

### 6. Install Configuration Files

```bash
# Create snippets directory
sudo mkdir -p /etc/nginx/snippets

# Copy config files
sudo cp deploy/nginx/ssl-params.conf /etc/nginx/snippets/
sudo cp deploy/nginx/security-headers.conf /etc/nginx/snippets/
sudo cp deploy/nginx/baluhost.conf /etc/nginx/sites-available/

# Update domain in config
sudo sed -i 's/YOUR_DOMAIN_HERE/yourdomain.com/g' /etc/nginx/sites-available/baluhost.conf
```

### 7. Enable Site

```bash
# Disable default site
sudo rm /etc/nginx/sites-enabled/default

# Enable BaluHost
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Test
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

### 8. Setup Auto-Renewal

Certbot usually installs a systemd timer automatically. Verify:

```bash
sudo systemctl list-timers | grep certbot
```

If not found, add a cron job:

```bash
sudo crontab -e
```

Add this line:
```
0 */12 * * * certbot renew --quiet --post-hook "systemctl reload nginx"
```

Test renewal:
```bash
sudo certbot renew --dry-run
```

---

## Configuration Reference

### SSL Certificate Locations

```
/etc/letsencrypt/live/yourdomain.com/
├── fullchain.pem       # Full certificate chain
├── privkey.pem         # Private key
├── cert.pem            # Certificate only
└── chain.pem           # Intermediate certificates
```

### Nginx Configuration Files

```
/etc/nginx/
├── nginx.conf                          # Main config
├── sites-available/
│   └── baluhost.conf                   # BaluHost site config
├── sites-enabled/
│   └── baluhost.conf -> ../sites-available/baluhost.conf
├── snippets/
│   ├── ssl-params.conf                 # SSL/TLS settings
│   └── security-headers.conf           # Security headers
├── dhparam.pem                         # DH parameters
└── conf.d/                             # Additional configs
```

### Rate Limiting Zones

Configured in `baluhost.conf`:

| Zone | Rate | Burst | Endpoints |
|------|------|-------|-----------|
| `api_limit` | 10 req/s | 20 | `/api/*` |
| `auth_limit` | 5 req/min | 3 | Login, register, refresh |
| `upload_limit` | 10 req/min | 5 | File uploads |

Adjust rates based on your needs:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=20r/s;
```

---

## Security Best Practices

### 1. SSL/TLS Configuration

✅ **Enabled**:
- TLS 1.2, TLS 1.3 (no SSLv3, TLS 1.0, TLS 1.1)
- Forward secrecy (ECDHE ciphers)
- Perfect forward secrecy (DHE)
- OCSP stapling
- Session resumption

❌ **Disabled**:
- Weak ciphers (RC4, 3DES, MD5)
- SSL compression (CRIME attack)
- TLS early data (0-RTT) - optional, disabled by default

### 2. Security Headers

| Header | Value | Purpose |
|--------|-------|---------|
| `Strict-Transport-Security` | `max-age=31536000` | Force HTTPS for 1 year |
| `X-Frame-Options` | `SAMEORIGIN` | Prevent clickjacking |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `Content-Security-Policy` | Restrictive | Prevent XSS |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer info |
| `Permissions-Policy` | Restrictive | Disable unused features |

### 3. Certificate Management

- **Renew before expiry**: Certbot auto-renews at 30 days remaining
- **Monitor expiry**: Check `/var/log/letsencrypt/letsencrypt.log`
- **Backup certificates**: Include `/etc/letsencrypt/` in backups
- **Test renewals**: `sudo certbot renew --dry-run` monthly

### 4. Access Control

**Restrict Admin Endpoints** (optional):
```nginx
location /api/admin {
    allow 192.168.1.0/24;  # Local network
    deny all;

    proxy_pass http://baluhost_backend;
}
```

**Block Bad Bots**:
```nginx
if ($http_user_agent ~* (bot|crawler|scanner)) {
    return 403;
}
```

### 5. DDoS Protection

Enable in `nginx.conf`:
```nginx
# Connection limits
limit_conn_zone $binary_remote_addr zone=addr:10m;
limit_conn addr 10;

# Request timeouts
client_body_timeout 10s;
client_header_timeout 10s;
keepalive_timeout 30s;
send_timeout 10s;
```

---

## Troubleshooting

### Certificate Issuance Failures

**Error: DNS doesn't resolve**
```bash
# Check DNS
host yourdomain.com

# Check from external source
dig @8.8.8.8 yourdomain.com +short
```

**Error: Port 80 not accessible**
```bash
# Check firewall
sudo ufw status
sudo iptables -L -n

# Check if Nginx is running
sudo systemctl status nginx

# Test port
curl http://yourdomain.com/.well-known/acme-challenge/test
```

**Error: Too many failed attempts**
- Let's Encrypt has rate limits (5 failures/hour, 50 certs/week)
- Use `--dry-run` flag for testing
- Wait 1 hour before retrying

### Nginx Configuration Errors

**Test configuration**:
```bash
sudo nginx -t
```

**Common issues**:
- Missing semicolons
- Duplicate server blocks
- Wrong file paths
- Permission errors

**View detailed logs**:
```bash
sudo tail -f /var/log/nginx/error.log
```

### SSL Handshake Failures

**Check certificate chain**:
```bash
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com
```

**Verify certificate**:
```bash
sudo certbot certificates
```

**Test with different browsers**:
- Chrome/Edge: Works with most configs
- Firefox: More strict, requires full chain
- Safari: Check compatibility

### Mixed Content Warnings

**Cause**: HTTP resources loaded on HTTPS page

**Fix**:
1. Update frontend to use relative URLs
2. Update API calls to use HTTPS
3. Enable automatic HTTPS redirects

### Performance Issues

**Enable caching**:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m;

location /api/ {
    proxy_cache api_cache;
    proxy_cache_valid 200 60s;
    add_header X-Cache-Status $upstream_cache_status;
}
```

**Enable HTTP/2**:
Already enabled in `baluhost.conf`:
```nginx
listen 443 ssl http2;
```

---

## Maintenance

### Check Certificate Expiry

```bash
# Via certbot
sudo certbot certificates

# Via openssl
echo | openssl s_client -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
```

### Manual Renewal

```bash
sudo certbot renew
sudo systemctl reload nginx
```

### Revoke Certificate

```bash
sudo certbot revoke --cert-path /etc/letsencrypt/live/yourdomain.com/cert.pem
```

### Update Nginx Configuration

```bash
# Edit config
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

# Certbot logs
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

### Security Audits

**Test SSL Configuration**:
```bash
# SSL Labs (online)
https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com

# testssl.sh (local)
git clone https://github.com/drwetter/testssl.sh.git
cd testssl.sh
./testssl.sh yourdomain.com
```

**Test Security Headers**:
```bash
curl -I https://yourdomain.com | grep -E "(Strict-Transport|X-Frame|X-Content|Content-Security)"

# Or online:
https://securityheaders.com/?q=yourdomain.com
```

### Backup Configuration

```bash
# Create backup directory
sudo mkdir -p /backups/nginx

# Backup Nginx config
sudo tar czf /backups/nginx/nginx-$(date +%Y%m%d).tar.gz \
    /etc/nginx/sites-available \
    /etc/nginx/snippets \
    /etc/nginx/nginx.conf

# Backup Let's Encrypt
sudo tar czf /backups/nginx/letsencrypt-$(date +%Y%m%d).tar.gz \
    /etc/letsencrypt
```

### Update Ciphers and Protocols

As cryptographic standards evolve, update `ssl-params.conf`:

```bash
# Check Mozilla SSL Configuration Generator
https://ssl-config.mozilla.org/

# Update ssl-params.conf
sudo nano /etc/nginx/snippets/ssl-params.conf

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

---

## Advanced Topics

### Wildcard Certificates

For subdomains (`*.yourdomain.com`):

```bash
sudo certbot certonly --manual \
    --preferred-challenges dns \
    -d yourdomain.com \
    -d *.yourdomain.com
```

Requires DNS TXT record verification.

### Multiple Domains

```bash
sudo certbot --nginx \
    -d yourdomain.com \
    -d www.yourdomain.com \
    -d nas.yourdomain.com
```

### Custom Certificate (Not Let's Encrypt)

If using a commercial certificate:

```nginx
ssl_certificate /path/to/certificate.crt;
ssl_certificate_key /path/to/private.key;
ssl_trusted_certificate /path/to/ca-bundle.crt;
```

---

## Support

- **Let's Encrypt Community**: https://community.letsencrypt.org/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Mozilla SSL Config**: https://ssl-config.mozilla.org/
- **BaluHost Issues**: See repository issues page

---

**Last Updated**: January 13, 2026
**Tested with**: Nginx 1.24+, Certbot 2.0+, Ubuntu 22.04 LTS
