# BaluHost Produktions-Schnellstart

**Status:** DEPLOYED AND RUNNING (seit 25. Jan. 2026)

---

## Zugriff auf das System

**Weboberfläche:**
```
http://localhost
http://baluhost.local
http://<Ihre-Server-IP>
```

**Admin-Anmeldung:**
- Benutzername: (wurde bei der Installation konfiguriert)
- Passwort: (wurde bei der Installation konfiguriert)
- Ändern Sie das Passwort sofort nach der ersten Anmeldung (Einstellungen → Passwort ändern)

**API-Dokumentation:**
```
http://localhost/docs (Swagger UI)
```

---

## Häufige Befehle

### Dienststatus prüfen
```bash
sudo systemctl status baluhost-backend
sudo systemctl status nginx
sudo systemctl status postgresql
```

### Logs anzeigen
```bash
# Backend-Logs (Echtzeit)
sudo journalctl -u baluhost-backend -f

# Backend-Logs (letzte 100 Zeilen)
sudo journalctl -u baluhost-backend -n 100

# Nginx-Zugriffslog
sudo tail -f /var/log/nginx/baluhost-access.log

# Nginx-Fehlerlog
sudo tail -f /var/log/nginx/baluhost-error.log
```

### Dienste neustarten
```bash
# Backend neustarten (kurze Ausfallzeit)
sudo systemctl restart baluhost-backend

# Nginx neu laden (keine Ausfallzeit)
sudo systemctl reload nginx
```

### Frontend aktualisieren
```bash
cd /home/sven/projects/BaluHost/client
npm run build:prod
sudo cp -r dist/* /var/www/baluhost/
sudo systemctl reload nginx
```

### Datenbankzugriff
```bash
# Mit Datenbank verbinden
sudo -u postgres psql -d baluhost

# Tabellen auflisten
sudo -u postgres psql -d baluhost -c "\dt"

# Benutzer anzeigen
sudo -u postgres psql -d baluhost -c "SELECT id, username, email, role FROM users;"

# Datenbank sichern
sudo -u postgres pg_dump baluhost > ~/baluhost_backup_$(date +%Y%m%d).sql
```

---

## Wichtige Pfade

| Komponente | Pfad |
|-----------|------|
| Backend-Code | `/home/sven/projects/BaluHost/backend` |
| Frontend-Code | `/home/sven/projects/BaluHost/client` |
| Statische Frontend-Dateien | `/var/www/baluhost/` |
| Nginx-Konfiguration | `/etc/nginx/sites-available/baluhost` |
| Systemd-Backend-Dienst | `/etc/systemd/system/baluhost-backend.service` |
| Produktions-.env | `/home/sven/projects/BaluHost/.env.production` |
| Nginx-Logs | `/var/log/nginx/baluhost-*.log` |
| Entwicklungs-Backup | `/home/sven/baluhost_backup_20260125_220931/` |

---

## Fehlerbehebung

### Backend startet nicht
```bash
# Logs auf Fehler prüfen
sudo journalctl -u baluhost-backend -n 50

# Datenbankverbindung überprüfen
sudo systemctl status postgresql
sudo -u postgres psql -d baluhost -c "SELECT 1;"

# .env-Datei prüfen
cat /home/sven/projects/BaluHost/.env.production | grep -v PASSWORD
```

### Frontend lädt nicht
```bash
# Nginx-Status prüfen
sudo systemctl status nginx

# Statische Dateien vorhanden?
ls -lh /var/www/baluhost/

# Nginx-Fehlerlog prüfen
sudo tail -n 50 /var/log/nginx/baluhost-error.log

# Nginx-Konfiguration testen
sudo nginx -t
```

### Anmeldung schlägt fehl
```bash
# Admin-Benutzer vorhanden?
sudo -u postgres psql -d baluhost -c "SELECT username, email, is_active FROM users WHERE username='admin';"

# Backend-Logs während des Anmeldeversuchs prüfen
sudo journalctl -u baluhost-backend -f
# (dann Anmeldung im Browser versuchen)
```

### Datenbankverbindungsfehler
```bash
# Läuft PostgreSQL?
sudo systemctl status postgresql

# Verbindung testen
sudo -u postgres psql -d baluhost -c "SELECT version();"

# Zugangsdaten in .env überprüfen
grep DATABASE_URL /home/sven/projects/BaluHost/.env.production
```

---

## Systemwartung

### Täglich
- Speicherplatz überwachen: `df -h`
- Dienststatus prüfen: `systemctl status baluhost-backend nginx postgresql`

### Wöchentlich
- Logs auf Fehler prüfen: `sudo journalctl -u baluhost-backend --since "7 days ago" | grep ERROR`
- Datenbank-Backup: `sudo -u postgres pg_dump baluhost > ~/backup.sql`

### Monatlich
- Systempakete aktualisieren: `sudo apt update && sudo apt upgrade`
- Sicherheitslogs prüfen
- Datenbank-Wiederherstellungsverfahren testen

---

## Leistungsüberwachung

### Ressourcenverbrauch prüfen
```bash
# Arbeitsspeicher
free -h

# Festplattennutzung
df -h

# CPU-Auslastung
top -bn1 | head -n 20

# Speicherverbrauch der Dienste
systemctl status baluhost-backend | grep Memory
systemctl status postgresql | grep Memory
```

### Aktive Verbindungen überwachen
```bash
# Nginx-Verbindungen
ss -tlnp | grep nginx

# Backend-Verbindungen
ss -tlnp | grep :8000

# PostgreSQL-Verbindungen
sudo -u postgres psql -d baluhost -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## Bekannte Probleme

### 1. Monitoring Integer-Überlauf (Unkritisch)
**Symptom:** Fehler in den Logs: "integer ist außerhalb des gültigen Bereichs" für memory_samples/network_samples

**Workaround:** Vorerst ignorieren (beeinträchtigt nicht die Kernfunktionalität)

**Lösung:** Wird im nächsten Update behoben (BIGINT-Migration)

---

## Support

**Dokumentation:**
- Vollständige Deployment-Notizen: `PRODUCTION_DEPLOYMENT_NOTES.md`
- Produktionsbereitschaft: `PRODUCTION_READINESS.md`
- Technische Dokumentation: `TECHNICAL_DOCUMENTATION.md`

**Systeminfo:**
- Server: Debian 13, Ryzen 5 5600GT, 16GB RAM
- Backend: Python 3.13, FastAPI, PostgreSQL 17.7
- Frontend: React 18, TypeScript, Vite
- Webserver: Nginx 1.26

**Deployment-Datum:** 25. Januar 2026
**Version:** 1.3.0+production
**Status:** STABIL

---

**Zuletzt aktualisiert:** 25. Januar 2026, 23:45 CET
