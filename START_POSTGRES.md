# PostgreSQL Quick Start - Nach Docker Installation

## Schritt 1: PostgreSQL starten

```powershell
# Im Hauptverzeichnis von BaluHost
docker-compose -f docker-compose.postgres.yml --env-file .env.postgres up -d
```

**Was passiert:**
- PostgreSQL Container startet auf Port 5432
- pgAdmin Web-UI startet auf Port 5050
- Dauert ~30 Sekunden beim ersten Mal (Download Images)

**Erwartete Ausgabe:**
```
[+] Running 3/3
 ✔ Network baluhost_baluhost-network  Created
 ✔ Container baluhost-postgres        Started
 ✔ Container baluhost-pgadmin         Started
```

---

## Schritt 2: Prüfen ob PostgreSQL läuft

```powershell
docker-compose -f docker-compose.postgres.yml ps
```

**Erwartete Ausgabe:**
```
NAME                    STATUS              PORTS
baluhost-postgres       Up X seconds        0.0.0.0:5432->5432/tcp
baluhost-pgadmin        Up X seconds        0.0.0.0:5050->80/tcp
```

---

## Schritt 3: Verbindung testen

```powershell
cd backend
python scripts/test_postgres_connection.py --url "postgresql://baluhost:baluhost_dev_password_123@localhost:5432/baluhost"
```

**Erwartete Ausgabe:**
```
PostgreSQL Connection Test
✓ Connection successful!
PostgreSQL Version: PostgreSQL 16.x
```

---

## Schritt 4: Migration durchführen

```powershell
# Noch im backend/ Verzeichnis
python scripts/migrate_to_postgres.py --sqlite-path baluhost.db --postgres-url "postgresql://baluhost:baluhost_dev_password_123@localhost:5432/baluhost"
```

**Was passiert:**
- Backup von SQLite wird erstellt (in backups/)
- Schema wird mit Alembic migriert
- 11.056 Zeilen werden kopiert (~30 Sekunden)
- Verification läuft automatisch

---

## Schritt 5: Backend mit PostgreSQL starten

```powershell
# backend/.env aktualisieren (oder per Environment Variable)
$env:DATABASE_URL="postgresql://baluhost:baluhost_dev_password_123@localhost:5432/baluhost"
$env:NAS_MODE="prod"

uvicorn app.main:app --reload --port 3001
```

**Im Log sollte stehen:**
```
INFO: Using PostgreSQL database with connection pooling
INFO: PostgreSQL Pool: size=10, max_overflow=20
```

---

## Optional: pgAdmin Web-UI öffnen

- URL: http://localhost:5050
- Email: admin@baluhost.local
- Password: admin

Server hinzufügen:
- Host: postgres (Docker network) oder localhost
- Port: 5432
- Username: baluhost
- Password: baluhost_dev_password_123

---

## Bei Problemen:

**PostgreSQL Logs anzeigen:**
```powershell
docker-compose -f docker-compose.postgres.yml logs postgres
```

**PostgreSQL neustarten:**
```powershell
docker-compose -f docker-compose.postgres.yml restart postgres
```

**PostgreSQL stoppen:**
```powershell
docker-compose -f docker-compose.postgres.yml down
```

**PostgreSQL stoppen + Daten löschen:**
```powershell
docker-compose -f docker-compose.postgres.yml down -v
```
