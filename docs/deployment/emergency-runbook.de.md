# Notfall-Runbook

Schnellreferenz für die Reaktion auf Produktionsvorfälle am BaluHost NAS.

## Dienstübersicht

| Dienst | Port | Prüfung |
|--------|------|---------|
| `baluhost-backend` | 8000 | `curl localhost:8000/api/system/health` |
| `baluhost-scheduler` | — | `systemctl status baluhost-scheduler` |
| `baluhost-monitoring` | — | `systemctl status baluhost-monitoring` |
| `baluhost-webdav` | — | `systemctl status baluhost-webdav` |
| `nginx` | 80 | `curl localhost/health` |
| `postgresql` | 5432 | `pg_isready -h localhost` |

## Schnellbefehle

```bash
# Alle Dienste prüfen
sudo systemctl status 'baluhost-*'
sudo systemctl status nginx postgresql

# Backend-Logs anzeigen
sudo journalctl -u baluhost-backend -f
sudo journalctl -u baluhost-backend --since "10 minutes ago"

# Alles neu starten
sudo systemctl restart baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav
sudo systemctl reload nginx
```

## Rollback nach fehlgeschlagenem Deploy

```bash
cd /opt/baluhost

# 1. Prüfen, was deployt wurde
cat .deploy-state
# Zeigt: previous_commit, current_commit, backup_file, db_revision_before/after

# 2. Automatischer Rollback (stellt Code + DB-Revision wieder her)
./deploy/scripts/ci-deploy.sh --rollback

# 3. Verifizieren
curl localhost/api/system/health
```

## Datenbankwiederherstellung (Letzte Option)

Verwenden Sie dies, wenn die Datenbank selbst beschädigt ist oder eine Migration zu Datenverlust geführt hat.

```bash
# 1. Verfügbare Backups auflisten
ls -lt /opt/baluhost/backups/deploys/   # Pre-Deploy-Backups
ls -lt /opt/baluhost/backups/daily/     # Tägliche Cron-Backups

# 2. Wiederherstellen (interaktiv — fragt nach Bestätigung)
/opt/baluhost/deploy/scripts/db-restore.sh /opt/baluhost/backups/deploys/pre-deploy-20260302-143000.sql.gz
```

### Manuelle Datenbankwiederherstellung

Falls das Wiederherstellungsskript fehlschlägt:

```bash
# 1. Dienste stoppen
sudo systemctl stop baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav

# 2. Datenbank löschen und neu erstellen
sudo -u postgres dropdb baluhost
sudo -u postgres createdb -O baluhost baluhost

# 3. Aus Backup wiederherstellen
gunzip -c /opt/baluhost/backups/deploys/<BACKUP>.sql.gz | sudo -u postgres psql baluhost

# 4. Alembic-Revision prüfen
cd /opt/baluhost/backend
.venv/bin/alembic current

# 5. Dienste starten
sudo systemctl start baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav
```

## Häufige Probleme

### Backend startet nicht

```bash
# Logs prüfen
sudo journalctl -u baluhost-backend -n 50

# Häufige Ursachen:
# - Port 8000 belegt: sudo lsof -i :8000
# - .env.production fehlt/defekt: cat /opt/baluhost/.env.production
# - Python venv defekt: cd /opt/baluhost/backend && .venv/bin/python -c "import app"
# - PostgreSQL nicht verfügbar: pg_isready -h localhost
```

### Nginx 502 Bad Gateway

Das Backend antwortet nicht auf Port 8000.

```bash
sudo systemctl status baluhost-backend
sudo systemctl restart baluhost-backend
# 5 Sekunden warten, dann:
curl localhost:8000/api/system/health
```

### Datenbankverbindung verweigert

```bash
# PostgreSQL prüfen
sudo systemctl status postgresql
pg_isready -h localhost -p 5432

# Zugangsdaten prüfen
grep DATABASE_URL /opt/baluhost/.env.production

# PostgreSQL neu starten
sudo systemctl restart postgresql
```

### Festplatte voll

```bash
df -h
# Bei Bedarf alte Backups bereinigen:
ls -la /opt/baluhost/backups/deploys/
ls -la /opt/baluhost/backups/daily/
# Älteste Backups vorsichtig entfernen
```

### Frontend zeigt leere Seite

```bash
# Prüfen, ob dist existiert
ls /opt/baluhost/client/dist/index.html

# Bei Bedarf neu bauen
cd /opt/baluhost/client
sudo -u sven npm run build
sudo systemctl reload nginx
```

## Nützliche Pfade

| Pfad | Zweck |
|------|-------|
| `/opt/baluhost/` | Produktionsanwendung |
| `/opt/baluhost/.env.production` | Umgebungskonfiguration (Geheimnisse) |
| `/opt/baluhost/.deploy-state` | Letzte Deploy-Metadaten |
| `/opt/baluhost/backups/deploys/` | Pre-Deploy-Datenbank-Backups |
| `/opt/baluhost/backups/daily/` | Tägliche Cron-Datenbank-Backups |
| `/var/log/baluhost/deploys/` | Deploy-Logs (JSON) |
| `/var/log/baluhost/db-backup.log` | Tägliches Backup-Cron-Log |
| `/etc/nginx/sites-available/baluhost` | Nginx-Konfiguration |
| `/etc/systemd/system/baluhost-*.service` | Systemd-Service-Dateien |

## Kontakt

- **Repository**: https://github.com/Xveyn/BaluHost
- **Betreuer**: Xveyn
