# Mock-System für Entwicklung

## Übersicht

Da die NAS-Management-Anwendung auf einem Linux-System laufen soll, wurde ein Mock-System implementiert, um die Entwicklung auf Windows zu ermöglichen.

## Features

### 1. Mock Storage (10GB Test-Quota)
- Simuliert ein 10GB großes Storage-System
- Berechnet die tatsächliche Nutzung basierend auf Dateien im `./storage` Verzeichnis
- Zeigt realistische Speicher-Statistiken

### 2. Mock Users
- Admin-User mit 10GB Quota
- Persistent während Server-Laufzeit
- Erweiterbar für mehrere Test-User

### 3. Mock System Info
- CPU-Auslastung (echte Werte vom OS-Modul)
- Speicher-Nutzung (echte Werte)
- Disk-Info (Mock-Daten in Entwicklung, echte `df`-Werte auf Linux)
- Prozess-Liste (Mock-Daten in Entwicklung, echte `ps`-Werte auf Linux)

## Automatische Aktivierung

Das Mock-System wird automatisch aktiviert wenn:
- `NODE_ENV=development` oder
- Das System nicht Linux ist (`process.platform !== 'linux'`)

## Verwendung

### Storage-Quota prüfen
```typescript
import { checkUserQuota, updateUserSpace } from '../utils/mockData';

// Vor Upload prüfen
if (!checkUserQuota(userId, fileSize)) {
  return res.status(413).json({ error: 'Quota exceeded' });
}

// Nach Upload aktualisieren
updateUserSpace(userId, fileSize);
```

### System-Info abrufen
```typescript
// In Entwicklung: Mock-Daten
// Auf Linux: Echte df/ps Befehle
const storageInfo = await getMockDiskInfo(storagePath);
const processes = getMockProcessList();
```

## Konfiguration

In `.env`:
```env
NODE_ENV=development
MOCK_STORAGE_QUOTA=10737418240  # 10GB für Tests
NAS_STORAGE_PATH=./storage
```

## Test-Daten

### Admin User
- Username: `admin`
- Password: `changeme`
- Quota: 10GB
- Role: admin

### Mock Processes
- node server/dist/index.js
- nginx: worker process
- tsx watch src/index.ts
- postgres: main process

### Mock Storage
- Total: 10GB
- Simuliert belegt: ~2GB
- Verfügbar: ~8GB
- Echte Nutzung wird aus ./storage berechnet

## Migration zu Produktion

Auf Linux-Produktionssystem:
1. `NODE_ENV=production` setzen
2. Mock-System wird automatisch deaktiviert
3. Echte Linux-Befehle (`df`, `ps`) werden verwendet
4. Datenbank für User-Verwaltung implementieren

## Vorteile

✅ Entwicklung auf Windows möglich  
✅ Realistische Test-Daten (10GB Limit)  
✅ Keine Code-Änderungen für Produktion nötig  
✅ Automatische Erkennung der Umgebung  
✅ Echte Datei-Operationen werden getestet

## Dateistruktur

```
server/
  src/
    utils/
      mockData.ts          # Mock-System Implementation
    controllers/
      auth.controller.ts   # Nutzt mockUsers
      system.controller.ts # Nutzt Mock-System-Info
  storage/                 # Testdaten (wird berechnet)
```

## Console-Ausgaben

Bei Aktivierung des Mock-Systems:
```
✓ Admin user initialized: admin/changeme (10GB test quota)
✓ Mock storage info: 20% used
✓ Mock process list returned
```

## Nächste Schritte

1. ✅ Mock-System implementiert
2. ⏭️ File Manager UI vervollständigen (Download, Delete, Rename)
3. ⏭️ User Management UI (CRUD Dialogs)
4. ⏭️ Toast Notifications
5. ⏭️ Upload Progress
6. ⏭️ Datenbank-Integration (PostgreSQL/SQLite)
