# SSL/TLS-Konfigurationsanleitung für BaluHost

Vollständige Anleitung zur Einrichtung einer produktionsreifen SSL/TLS-Verschlüsselung mit Let's Encrypt.

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Voraussetzungen](#voraussetzungen)
3. [Schnellstart (Automatisiert)](#schnellstart-automatisiert)
4. [Manuelle Einrichtung](#manuelle-einrichtung)
5. [Konfigurationsreferenz](#konfigurationsreferenz)
6. [Bewährte Sicherheitspraktiken](#bewährte-sicherheitspraktiken)
7. [Fehlerbehebung](#fehlerbehebung)
8. [Wartung](#wartung)

---

## Überblick

Diese Anleitung behandelt die Einrichtung von:
- **Let's Encrypt SSL-Zertifikaten** (kostenlos, automatische Verlängerung)
- **Nginx Reverse Proxy** mit SSL-Terminierung
- **Moderne TLS-Konfiguration** (TLS 1.2, TLS 1.3)
- **Sicherheitsheader** (HSTS, CSP usw.)
- **Rate Limiting** und DDoS-Schutz
- **Automatische Zertifikatsverlängerung**

Angestrebte SSL-Bewertung: **A oder A+** auf [SSL Labs](https://www.ssllabs.com/ssltest/)

---

## Voraussetzungen

### Systemanforderungen

- **Betriebssystem**: Ubuntu 20.04+, Debian 11+, RHEL 8+ oder kompatibel
- **RAM**: Mindestens 512 MB (1 GB empfohlen)
- **Festplatte**: 2 GB freier Speicherplatz
- **Zugriff**: Root- oder Sudo-Berechtigungen

### Netzwerkanforderungen

1. **Domainname**, der auf Ihren Server zeigt
   - DNS-A-Eintrag konfigurieren: `yourdomain.com → Ihre-Server-IP`
   - Auf DNS-Propagierung warten (bis zu 48 Stunden)
   - Überprüfen mit: `host yourdomain.com`

2. **Offene Firewall-Ports**:
   - Port 80 (HTTP) – erforderlich für die Let's Encrypt-Validierung
   - Port 443 (HTTPS) – für verschlüsselten Datenverkehr
   - Port 22 (SSH) – für den Serverzugriff

3. **BaluHost bereitgestellt**:
   - Docker Compose: Backend läuft auf `localhost:8000`
   - Systemd: Backend-Dienst aktiv

---

## Schnellstart (Automatisiert)

### Schritt 1: Nginx installieren

```bash
cd /path/to/baluhost
sudo ./deploy/scripts/install-nginx.sh
```

Dieses Skript:
- Installiert Nginx
- Konfiguriert die Firewall (ufw/firewalld)
- Erstellt notwendige Verzeichnisse
- Optimiert nginx.conf
- Installiert BaluHost-Konfigurationsvorlagen

### Schritt 2: SSL mit Let's Encrypt einrichten

```bash
sudo ./deploy/ssl/setup-letsencrypt.sh yourdomain.com admin@yourdomain.com
```

Ersetzen Sie:
- `yourdomain.com` durch Ihre tatsächliche Domain
- `admin@yourdomain.com` durch Ihre E-Mail-Adresse (für Verlängerungsbenachrichtigungen)

Dieses Skript:
- Prüft die DNS-Konfiguration
- Installiert Certbot
- Beschafft das SSL-Zertifikat
- Generiert dhparam.pem (2048-Bit)
- Konfiguriert die automatische Verlängerung
- Aktualisiert die Nginx-Konfiguration mit Ihrer Domain

### Schritt 3: BaluHost-Seite aktivieren

```bash
# Konfiguration überprüfen
sudo nano /etc/nginx/sites-available/baluhost.conf

# Backend-Upstream verifizieren:
# - Docker: server localhost:8000;
# - Systemd: server unix:/run/baluhost/backend.sock;

# Seite aktivieren
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Konfiguration testen
sudo nginx -t

# Nginx neu laden
sudo systemctl reload nginx
```

### Schritt 4: Überprüfen

```bash
# SSL-Zertifikat prüfen
curl -I https://yourdomain.com

# Im Browser testen
open https://yourdomain.com
```

**Überprüfungstests**:
- SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
- Security Headers: https://securityheaders.com/?q=yourdomain.com

Zielbewertungen: SSL Labs A/A+, Security Headers A

---

## Manuelle Einrichtung

Falls die automatisierten Skripte fehlschlagen oder Sie manuelle Kontrolle bevorzugen:

### 1. Nginx installieren

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
# oder
sudo dnf install nginx

sudo systemctl enable nginx
sudo systemctl start nginx
```

### 2. Firewall konfigurieren

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

### 3. Certbot installieren

**Ubuntu/Debian**:
```bash
sudo apt install certbot python3-certbot-nginx
```

**RHEL/CentOS**:
```bash
sudo yum install certbot python3-certbot-nginx
# oder
sudo dnf install certbot python3-certbot-nginx
```

### 4. Zertifikat beschaffen

**Methode A: Nginx-Plugin (empfohlen)**:
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

**Methode B: Webroot-Methode**:
```bash
# Webroot erstellen
sudo mkdir -p /var/www/certbot

# Zertifikat beschaffen
sudo certbot certonly --webroot -w /var/www/certbot \
  -d yourdomain.com -d www.yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos
```

### 5. dhparam generieren

```bash
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048
```

*Hinweis: Dies dauert 5–10 Minuten. Für schnellere Generierung (weniger sicher):*
```bash
sudo openssl dhparam -out /etc/nginx/dhparam.pem 1024
```

### 6. Konfigurationsdateien installieren

```bash
# Snippets-Verzeichnis erstellen
sudo mkdir -p /etc/nginx/snippets

# Konfigurationsdateien kopieren
sudo cp deploy/nginx/ssl-params.conf /etc/nginx/snippets/
sudo cp deploy/nginx/security-headers.conf /etc/nginx/snippets/
sudo cp deploy/nginx/baluhost.conf /etc/nginx/sites-available/

# Domain in der Konfiguration aktualisieren
sudo sed -i 's/YOUR_DOMAIN_HERE/yourdomain.com/g' /etc/nginx/sites-available/baluhost.conf
```

### 7. Seite aktivieren

```bash
# Standard-Seite deaktivieren
sudo rm /etc/nginx/sites-enabled/default

# BaluHost aktivieren
sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/

# Testen
sudo nginx -t

# Neu laden
sudo systemctl reload nginx
```

### 8. Automatische Verlängerung einrichten

Certbot installiert normalerweise automatisch einen Systemd-Timer. Überprüfen Sie dies:

```bash
sudo systemctl list-timers | command grep certbot
```

Falls nicht vorhanden, fügen Sie einen Cron-Job hinzu:

```bash
sudo crontab -e
```

Fügen Sie diese Zeile hinzu:
```
0 */12 * * * certbot renew --quiet --post-hook "systemctl reload nginx"
```

Verlängerung testen:
```bash
sudo certbot renew --dry-run
```

---

## Konfigurationsreferenz

### SSL-Zertifikatsspeicherorte

```
/etc/letsencrypt/live/yourdomain.com/
├── fullchain.pem       # Vollständige Zertifikatskette
├── privkey.pem         # Privater Schlüssel
├── cert.pem            # Nur Zertifikat
└── chain.pem           # Zwischenzertifikate
```

### Nginx-Konfigurationsdateien

```
/etc/nginx/
├── nginx.conf                          # Hauptkonfiguration
├── sites-available/
│   └── baluhost.conf                   # BaluHost-Seitenkonfiguration
├── sites-enabled/
│   └── baluhost.conf -> ../sites-available/baluhost.conf
├── snippets/
│   ├── ssl-params.conf                 # SSL/TLS-Einstellungen
│   └── security-headers.conf           # Sicherheitsheader
├── dhparam.pem                         # DH-Parameter
└── conf.d/                             # Zusätzliche Konfigurationen
```

### Rate-Limiting-Zonen

Konfiguriert in `baluhost.conf`:

| Zone | Rate | Burst | Endpunkte |
|------|------|-------|-----------|
| `api_limit` | 10 Anf./s | 20 | `/api/*` |
| `auth_limit` | 5 Anf./min | 3 | Anmeldung, Registrierung, Aktualisierung |
| `upload_limit` | 10 Anf./min | 5 | Datei-Uploads |

Passen Sie die Raten nach Bedarf an:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=20r/s;
```

---

## Bewährte Sicherheitspraktiken

### 1. SSL/TLS-Konfiguration

Aktiviert:
- TLS 1.2, TLS 1.3 (kein SSLv3, TLS 1.0, TLS 1.1)
- Forward Secrecy (ECDHE-Chiffren)
- Perfect Forward Secrecy (DHE)
- OCSP Stapling
- Session Resumption

Deaktiviert:
- Schwache Chiffren (RC4, 3DES, MD5)
- SSL-Komprimierung (CRIME-Angriff)
- TLS Early Data (0-RTT) – optional, standardmäßig deaktiviert

### 2. Sicherheitsheader

| Header | Wert | Zweck |
|--------|------|-------|
| `Strict-Transport-Security` | `max-age=31536000` | HTTPS für 1 Jahr erzwingen |
| `X-Frame-Options` | `SAMEORIGIN` | Clickjacking verhindern |
| `X-Content-Type-Options` | `nosniff` | MIME-Sniffing verhindern |
| `Content-Security-Policy` | Restriktiv | XSS verhindern |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer-Informationen kontrollieren |
| `Permissions-Policy` | Restriktiv | Ungenutzte Funktionen deaktivieren |

### 3. Zertifikatsverwaltung

- **Vor Ablauf verlängern**: Certbot verlängert automatisch bei 30 verbleibenden Tagen
- **Ablauf überwachen**: Prüfen Sie `/var/log/letsencrypt/letsencrypt.log`
- **Zertifikate sichern**: Fügen Sie `/etc/letsencrypt/` in Backups ein
- **Verlängerung testen**: `sudo certbot renew --dry-run` monatlich

### 4. Zugriffskontrolle

**Admin-Endpunkte einschränken** (optional):
```nginx
location /api/admin {
    allow 192.168.1.0/24;  # Lokales Netzwerk
    deny all;

    proxy_pass http://baluhost_backend;
}
```

**Bösartige Bots blockieren**:
```nginx
if ($http_user_agent ~* (bot|crawler|scanner)) {
    return 403;
}
```

### 5. DDoS-Schutz

In `nginx.conf` aktivieren:
```nginx
# Verbindungslimits
limit_conn_zone $binary_remote_addr zone=addr:10m;
limit_conn addr 10;

# Anfrage-Timeouts
client_body_timeout 10s;
client_header_timeout 10s;
keepalive_timeout 30s;
send_timeout 10s;
```

---

## Fehlerbehebung

### Fehler bei der Zertifikatsausstellung

**Fehler: DNS löst nicht auf**
```bash
# DNS prüfen
host yourdomain.com

# Von externer Quelle prüfen
dig @8.8.8.8 yourdomain.com +short
```

**Fehler: Port 80 nicht erreichbar**
```bash
# Firewall prüfen
sudo ufw status
sudo iptables -L -n

# Prüfen ob Nginx läuft
sudo systemctl status nginx

# Port testen
curl http://yourdomain.com/.well-known/acme-challenge/test
```

**Fehler: Zu viele fehlgeschlagene Versuche**
- Let's Encrypt hat Ratenlimits (5 Fehlschläge/Stunde, 50 Zertifikate/Woche)
- Verwenden Sie das `--dry-run`-Flag zum Testen
- Warten Sie 1 Stunde vor dem nächsten Versuch

### Nginx-Konfigurationsfehler

**Konfiguration testen**:
```bash
sudo nginx -t
```

**Häufige Probleme**:
- Fehlende Semikolons
- Doppelte Server-Blöcke
- Falsche Dateipfade
- Berechtigungsfehler

**Detaillierte Logs anzeigen**:
```bash
sudo tail -f /var/log/nginx/error.log
```

### SSL-Handshake-Fehler

**Zertifikatskette prüfen**:
```bash
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com
```

**Zertifikat überprüfen**:
```bash
sudo certbot certificates
```

**Mit verschiedenen Browsern testen**:
- Chrome/Edge: Funktioniert mit den meisten Konfigurationen
- Firefox: Strenger, erfordert vollständige Kette
- Safari: Kompatibilität prüfen

### Mixed-Content-Warnungen

**Ursache**: HTTP-Ressourcen werden auf HTTPS-Seite geladen

**Lösung**:
1. Frontend auf relative URLs umstellen
2. API-Aufrufe auf HTTPS aktualisieren
3. Automatische HTTPS-Weiterleitungen aktivieren

### Leistungsprobleme

**Caching aktivieren**:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m;

location /api/ {
    proxy_cache api_cache;
    proxy_cache_valid 200 60s;
    add_header X-Cache-Status $upstream_cache_status;
}
```

**HTTP/2 aktivieren**:
Bereits in `baluhost.conf` aktiviert:
```nginx
listen 443 ssl http2;
```

---

## Wartung

### Zertifikatsablauf prüfen

```bash
# Über Certbot
sudo certbot certificates

# Über OpenSSL
echo | openssl s_client -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
```

### Manuelle Verlängerung

```bash
sudo certbot renew
sudo systemctl reload nginx
```

### Zertifikat widerrufen

```bash
sudo certbot revoke --cert-path /etc/letsencrypt/live/yourdomain.com/cert.pem
```

### Nginx-Konfiguration aktualisieren

```bash
# Konfiguration bearbeiten
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

# Certbot-Logs
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

### Sicherheitsaudits

**SSL-Konfiguration testen**:
```bash
# SSL Labs (online)
https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com

# testssl.sh (lokal)
git clone https://github.com/drwetter/testssl.sh.git
cd testssl.sh
./testssl.sh yourdomain.com
```

**Sicherheitsheader testen**:
```bash
curl -I https://yourdomain.com | command grep -E "(Strict-Transport|X-Frame|X-Content|Content-Security)"

# Oder online:
https://securityheaders.com/?q=yourdomain.com
```

### Konfiguration sichern

```bash
# Backup-Verzeichnis erstellen
sudo mkdir -p /backups/nginx

# Nginx-Konfiguration sichern
sudo tar czf /backups/nginx/nginx-$(date +%Y%m%d).tar.gz \
    /etc/nginx/sites-available \
    /etc/nginx/snippets \
    /etc/nginx/nginx.conf

# Let's Encrypt sichern
sudo tar czf /backups/nginx/letsencrypt-$(date +%Y%m%d).tar.gz \
    /etc/letsencrypt
```

### Chiffren und Protokolle aktualisieren

Da sich kryptographische Standards weiterentwickeln, aktualisieren Sie `ssl-params.conf`:

```bash
# Mozilla SSL Configuration Generator prüfen
https://ssl-config.mozilla.org/

# ssl-params.conf aktualisieren
sudo nano /etc/nginx/snippets/ssl-params.conf

# Testen und neu laden
sudo nginx -t && sudo systemctl reload nginx
```

---

## Fortgeschrittene Themen

### Wildcard-Zertifikate

Für Subdomains (`*.yourdomain.com`):

```bash
sudo certbot certonly --manual \
    --preferred-challenges dns \
    -d yourdomain.com \
    -d *.yourdomain.com
```

Erfordert DNS-TXT-Eintrag-Verifizierung.

### Mehrere Domains

```bash
sudo certbot --nginx \
    -d yourdomain.com \
    -d www.yourdomain.com \
    -d nas.yourdomain.com
```

### Benutzerdefiniertes Zertifikat (nicht Let's Encrypt)

Wenn Sie ein kommerzielles Zertifikat verwenden:

```nginx
ssl_certificate /path/to/certificate.crt;
ssl_certificate_key /path/to/private.key;
ssl_trusted_certificate /path/to/ca-bundle.crt;
```

---

## Selbstsigniertes Zertifikat (nur LAN)

Für reine LAN- oder VPN-Bereitstellungen ohne öffentliche Domain verwenden Sie ein selbstsigniertes Zertifikat anstelle von Let's Encrypt.

### Schnellstart

```bash
cd /opt/baluhost
sudo ./deploy/ssl/setup-selfsigned.sh --ip 192.168.178.53
```

Das Skript:
1. Generiert ein selbstsigniertes Zertifikat (10 Jahre, RSA 2048, SHA-256)
2. Fügt SANs hinzu: `baluhost.local`, `baluhost`, `localhost`, LAN-IP, `127.0.0.1`
3. Generiert DH-Parameter (falls nicht vorhanden)
4. Installiert HTTPS-Nginx-Konfiguration (`baluhost-https.conf`)
5. Aktiviert HTTP-zu-HTTPS-Weiterleitung
6. Öffnet Port 443 in der Firewall
7. Fügt `https://`-CORS-Origins zu `.env.production` hinzu
8. Testet und lädt Nginx neu + startet Backend neu

Optionen:
```bash
sudo ./deploy/ssl/setup-selfsigned.sh --ip <IP> --hostname <NAME> --cert-days <DAYS>
sudo ./deploy/ssl/setup-selfsigned.sh --dry-run     # Vorschau ohne Änderungen
sudo ./deploy/ssl/setup-selfsigned.sh --skip-backend # Backend nicht neu starten
```

### Client-Vertrauenseinrichtung

Browser zeigen beim ersten Besuch eine Zertifikatswarnung an. Vertrauen Sie dem Zertifikat einmalig pro Gerät:

#### Browser (Windows/Mac/Linux)

1. Öffnen Sie `https://<LAN_IP>` (z. B. `https://192.168.178.53`)
2. Klicken Sie auf **Erweitert** -> **Weiter** (Chrome) oder **Risiko akzeptieren** (Firefox)
3. Fertig -- die Warnung erscheint für diese Seite nicht mehr

Für dauerhaftes Vertrauen (ohne Warnung) importieren Sie das Zertifikat in den OS-Vertrauensspeicher:

**Windows:**
1. Kopieren Sie `baluhost.crt` vom Server: `scp sven@<LAN_IP>:/etc/nginx/ssl/baluhost.crt .`
2. Doppelklicken Sie auf `baluhost.crt` -> **Zertifikat installieren** -> **Lokaler Computer** -> **Vertrauenswürdige Stammzertifizierungsstellen**

**macOS:**
1. Kopieren Sie `baluhost.crt` vom Server
2. Öffnen Sie **Schlüsselbundverwaltung** -> ziehen Sie `baluhost.crt` in den **System**-Schlüsselbund -> setzen Sie auf **Immer vertrauen**

**Linux:**
```bash
scp sven@<LAN_IP>:/etc/nginx/ssl/baluhost.crt /tmp/
sudo cp /tmp/baluhost.crt /usr/local/share/ca-certificates/baluhost.crt
sudo update-ca-certificates
```

#### BaluApp (Android)

**Option A -- Systemweites Vertrauen:**
1. Kopieren Sie `baluhost.crt` auf das Telefon (per USB, AirDrop oder E-Mail)
2. Gehen Sie zu **Einstellungen** -> **Sicherheit** -> **Verschlüsselung & Anmeldedaten** -> **Zertifikat installieren** -> **CA-Zertifikat**
3. Wählen Sie `baluhost.crt`

**Option B -- Nur App-Vertrauen (empfohlen):**
Fügen Sie in `res/xml/network_security_config.xml` hinzu:
```xml
<network-security-config>
    <domain-config>
        <domain includeSubdomains="true">192.168.178.53</domain>
        <domain includeSubdomains="true">baluhost.local</domain>
        <trust-anchors>
            <certificates src="@raw/baluhost"/>
        </trust-anchors>
    </domain-config>
</network-security-config>
```
Speichern Sie `baluhost.crt` als `res/raw/baluhost.pem`.

#### BaluDesk (Electron)

Setzen Sie die Umgebungsvariable `NODE_EXTRA_CA_CERTS` vor dem Start:
```bash
# Linux/macOS
export NODE_EXTRA_CA_CERTS=/path/to/baluhost.crt

# Windows (PowerShell)
$env:NODE_EXTRA_CA_CERTS = "C:\path\to\baluhost.crt"
```

Oder importieren Sie das Zertifikat in den OS-Vertrauensspeicher (siehe Abschnitt Browser oben).

### Zertifikat überprüfen

```bash
# Zertifikatsdetails anzeigen
openssl x509 -in /etc/nginx/ssl/baluhost.crt -noout -text

# Ablauf von remote prüfen
echo | openssl s_client -connect <LAN_IP>:443 -servername baluhost.local 2>/dev/null | openssl x509 -noout -dates

# HTTPS-Verbindung testen
curl -sk https://<LAN_IP>/health
```

### Erneuern / Neu generieren

Um das Zertifikat neu zu generieren (z. B. nach IP-Änderung):
```bash
sudo ./deploy/ssl/setup-selfsigned.sh --ip <NEW_IP>
# Skript erkennt vorhandenes Zertifikat und fragt, ob es überschrieben werden soll
```

Nach der Neugenerierung müssen Clients dem neuen Zertifikat erneut vertrauen.

---

## Support

- **Let's Encrypt Community**: https://community.letsencrypt.org/
- **Nginx-Dokumentation**: https://nginx.org/en/docs/
- **Mozilla SSL Config**: https://ssl-config.mozilla.org/
- **BaluHost Issues**: Siehe Repository-Issues-Seite

---

**Zuletzt aktualisiert**: 29. März 2026
**Getestet mit**: Nginx 1.24+, Certbot 2.0+, Debian 13, Ubuntu 22.04 LTS
