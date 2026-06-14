# BaluHost Produktions-Deployment-Notizen

**Deployment-Datum:** 25. Januar 2026
**Deployment-Typ:** Natives Systemd (Debian 13)
**Status:** ✅ PRODUKTION – LÄUFT

---

## 🖥️ Server-Spezifikationen

- **Hardware:** Ryzen 5 5600GT, 16 GB DDR4-RAM
- **Speicher:** 250 GB NVMe-M.2-SSD (primär)
- **Geplant:** 2x 4 TB NAS-HDDs (RAID1) – Einrichtung ausstehend
- **OS:** Debian 13 (Trixie), Linux 6.12.63+deb13-amd64
- **Netzwerk:** Gigabit-Ethernet, mDNS aktiviert

---

## 📦 Bereitgestellte Komponenten

### Backend-Dienst
- **Dienst:** `baluhost-backend.service`
- **Status:** Aktiv (läuft)
- **Worker:** 4 Uvicorn-Prozesse
- **Port:** 8000 (intern)
- **Arbeitsverzeichnis:** `/home/sven/projects/BaluHost/backend`
- **Virtuelle Umgebung:** `.venv` (Python 3.13)
- **Logs:** `journalctl -u baluhost-backend -f`
- **Speicherverbrauch:** ~480 MB
- **Auto-Start:** Aktiviert

**Umgebung:**
- `NAS_MODE=prod`
- `LOG_LEVEL=INFO`
- `LOG_FORMAT=json`
- `DATABASE_URL=postgresql://baluhost:***@localhost:5432/baluhost`

### Frontend-Dienst
- **Dienst:** `baluhost-frontend.service`
- **Status:** Inaktiv (nicht benötigt – Nginx liefert statische Dateien aus)
- **Build-Ausgabe:** `/var/www/baluhost/`
- **Berechtigungen:** `www-data:www-data` (755)
- **Bundle-Größe:** 1,1 MB (gzip: 291 KB)
- **Aktualisierungsprozess:** `npm run build:prod` → `sudo cp -r client/dist/* /var/www/baluhost/`

### Datenbank
- **Engine:** PostgreSQL 17.7 (Debian 17.7-0+deb13u1)
- **Datenbank:** `baluhost`
- **Benutzer:** `baluhost`
- **Tabellen:** 35+ Tabellen (alle verifiziert)
- **Status:** Aktiv, beim Booten aktiviert
- **Verbindung:** localhost:5432
- **Authentifizierung:** md5 (pg_hba.conf)

### Nginx Reverse Proxy
- **Konfiguration:** `/etc/nginx/sites-available/baluhost`
- **Port:** 80 (HTTP)
- **Root:** `/var/www/baluhost/`
- **Upstream:** `127.0.0.1:8000` (Backend)
- **Funktionen:**
  - Rate-Limiting (API: 100 r/s, Auth: 10 r/s)
  - Security-Header (X-Frame-Options, X-XSS-Protection, etc.)
  - Gzip-Komprimierung
  - WebSocket/SSE-Unterstützung
  - 10 GB maximale Upload-Größe
- **Logs:**
  - Zugriff: `/var/log/nginx/baluhost-access.log`
  - Fehler: `/var/log/nginx/baluhost-error.log`

---

## 🔐 Sicherheitskonfiguration

### Secrets (automatisch generiert)
- `SECRET_KEY`: 64-Zeichen-Sicherheitstoken (für JWT-Signierung)
- `TOKEN_SECRET`: 64-Zeichen-Sicherheitstoken (Legacy-Auth)
- `POSTGRES_PASSWORD`: 43-Zeichen-Sicherheitstoken
- `VPN_ENCRYPTION_KEY`: Fernet-Schlüssel für WireGuard-Verschlüsselung
- `ADMIN_PASSWORD`: *(wird beim Setup vergeben)* ⚠️ **Nach erstem Login ändern**

### Admin-Konto
- **Benutzername:** `admin`
- **E-Mail:** `admin@example.com` (korrigiert von `admin@baluhost.local` – Pydantic-Validierungsproblem)
- **Rolle:** `admin`
- **Erster Login:** Passwort umgehend in den Einstellungen ändern

### Rate-Limiting
- API-Endpunkte: 100 Anfragen/Sekunde (Burst 20)
- Auth-Endpunkte: 10 Anfragen/Sekunde (Burst 5)

### CORS
- Origins: `http://localhost`, `http://baluhost.local`, `http://127.0.0.1`

---

## 🛠️ Durchgeführte Deployment-Schritte

1. **Backup erstellt:** `/home/sven/baluhost_backup_20260125_220931` (1,1 GB)
2. **PostgreSQL installiert:** Version 17.7, mit dediziertem Benutzer konfiguriert
3. **Datenbank initialisiert:** Alle Tabellen erstellt, Admin-Benutzer angelegt
4. **Produktions-.env generiert:** Sichere Secrets automatisch erzeugt
5. **Systemd-Dienste erstellt:**
   - Backend-Dienst mit 4 Workern
   - Frontend-Dienst (nur Build, nicht zum Ausliefern verwendet)
6. **Nginx konfiguriert:**
   - HTTP-only Reverse Proxy
   - Auslieferung statischer Dateien aus `/var/www/baluhost/`
   - Security-Header und Rate-Limiting
7. **Frontend gebaut:** Produktions-Build (1,1 MB Bundle)
8. **Dienste gestartet:** Backend läuft, Nginx liefert aus
9. **Health-Check verifiziert:** Login erfolgreich, API antwortet

---

## ⚠️ Bekannte Probleme

### 1. Monitoring-Integer-Überlauf (unkritisch)
**Symptom:** Einfügen von Memory- und Network-Samples schlägt mit „integer out of range" fehl
**Ursache:** `memory_samples.used_bytes` und `network_samples.bytes_sent/received` nutzen INTEGER (max. ~2 GB) statt BIGINT
**Auswirkung:** Telemetrie-/Monitoring-Daten werden nicht gespeichert (beeinträchtigt die Kernfunktionalität nicht)
**Fix:** Alembic-Migration, um die Spaltentypen auf BIGINT zu ändern
**Priorität:** Mittel (bei Gelegenheit beheben)

### 2. E-Mail-Validierungsproblem (BEHOBEN)
**Symptom:** Login schlug mit 500-Fehler fehl
**Ursache:** Pydantic lehnt `.local`-TLD als ungültige E-Mail ab
**Fix:** Admin-E-Mail von `admin@baluhost.local` auf `admin@example.com` geändert
**Status:** ✅ Behoben

---

## 📊 Systemleistung

**Startzeit:**
- Backend: ~30 Sekunden (4 Worker + DB-Verbindung)
- Frontend-Build: ~21 Sekunden
- Datenbank: <5 Sekunden

**Speicherverbrauch (Leerlauf):**
- Backend: 480 MB
- PostgreSQL: 60 MB
- Nginx: 20 MB
- Gesamt: ~560 MB

**CPU-Auslastung (Leerlauf):** <5 %

**Speicherplatz:**
- Backend: 250 MB
- Frontend-dist: 2 MB
- PostgreSQL-Daten: 15 MB
- Gesamt: ~300 MB

---

## 🔄 Wartungsprozeduren

### Logs anzeigen
```bash
# Backend-Logs (JSON-Format)
sudo journalctl -u baluhost-backend -f

# Nginx-Zugriffslogs
sudo tail -f /var/log/nginx/baluhost-access.log

# Nginx-Fehlerlogs
sudo tail -f /var/log/nginx/baluhost-error.log
```

### Dienste neustarten
```bash
# Backend neustarten
sudo systemctl restart baluhost-backend

# Nginx neu laden (keine Ausfallzeit)
sudo systemctl reload nginx

# Vollständiger Neustart (kurze Ausfallzeit)
sudo systemctl restart nginx
```

### Frontend aktualisieren
```bash
cd /home/sven/projects/BaluHost/client
npm run build:prod
sudo cp -r dist/* /var/www/baluhost/
sudo systemctl reload nginx
```

### Datenbank-Backup
```bash
sudo -u postgres pg_dump baluhost > /path/to/backup/baluhost_$(date +%Y%m%d_%H%M%S).sql
```

### Dienststatus prüfen
```bash
systemctl status baluhost-backend
systemctl status nginx
systemctl status postgresql
```

---

## 📋 Ausstehende Aufgaben

### Kritisch
- [ ] Keine – System ist produktionsbereit

### Wichtig
- [ ] **Aufgabe #7:** Produktiv-Speicher-Setup (2x 4 TB HDDs → RAID1)
- [ ] Monitoring-Integer-Überlauf beheben (BIGINT-Migration)
- [ ] **Aufgabe #10:** Automatisierte Backup-Konfiguration (Cronjob)

### Optional
- [ ] SSL/HTTPS-Setup (Let's Encrypt)
- [ ] **Aufgabe #9:** Prometheus + Grafana Monitoring
- [ ] Frontend-Performance-Optimierung (Code-Splitting)
- [ ] Lasttests (locust, k6)

---

## 🎯 Nächste Schritte

1. **Sofort (nach erstem Login):**
   - Admin-Passwort in den Einstellungen ändern
   - Datei-Upload/-Download testen
   - Dashboard-Metriken verifizieren

2. **Kurzfristig (diese Woche):**
   - 2x 4 TB HDDs einbauen
   - RAID1-Array erstellen
   - Speicher-Mountpoints konfigurieren
   - Monitoring-Integer-Überlauf beheben

3. **Langfristig (diesen Monat):**
   - Automatisierte Backups einrichten
   - SSL/HTTPS konfigurieren (falls benötigt)
   - Monitoring-Stack bereitstellen (optional)

---

## 📞 Zugriffsinformationen

**Weboberfläche:**
- Lokal: `http://localhost`
- Netzwerk: `http://baluhost.local` (falls mDNS konfiguriert)
- IP: `http://<server-ip>` (mit `hostname -I` ermitteln)

**API-Dokumentation:**
- Swagger UI: `http://localhost/docs`
- OpenAPI JSON: `http://localhost/openapi.json`

**Admin-Zugangsdaten:**
- Benutzername: `admin`
- Passwort: *(wird beim Setup vergeben — hier nicht dokumentiert)* ⚠️ **Sofort ändern**

---

**Zuletzt aktualisiert:** 25. Januar 2026, 23:40 CET
**Deployment-Status:** ✅ PRODUKTION – STABIL
**Verfügbarkeitsziel:** 99,9 %

## Legacy-Frontend-Unit (BaluNode)

Stand 2026-06-10 läuft auf BaluNode noch eine Legacy-`baluhost-frontend.service`,
die `/home/sven/projects/BaluHost` referenziert. Sie ist redundant: nginx
serviert das statische Frontend aus `/opt/baluhost/client/dist`. Empfohlene
Bereinigung auf der Box:

    sudo systemctl disable --now baluhost-frontend.service
    sudo rm /etc/systemd/system/baluhost-frontend.service
    sudo systemctl daemon-reload

Die Repo-Kopien der Legacy-Units (`deploy/systemd/`) wurden mit #207 entfernt.
