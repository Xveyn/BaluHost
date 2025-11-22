# NAS Manager - Web Application

Dieses Projekt liefert eine vollständige Verwaltungsoberfläche für ein Linux-basiertes NAS-System. Der aktuelle Fokus liegt auf dem Python/FastAPI-Backend mit realitätsnahen Dev-Mode-Simulationen (Quota, RAID, SMART). Das frühere Express-Backend bleibt als Referenz im Ordner `server/`, ist jedoch als legacy markiert und wird schrittweise entfernt.

## Features

- Authentifizierung mit JWT sowie Admin-Rollenverwaltung
- Datei-Management inklusive Quota-Kontrolle und Sandbox-Speicher
- RAID-Management: Status, Degrade/Rebuild-Simulation, Bitmap/Spares/Write-mostly/Sync-Limits
- System-Monitoring mit Telemetrie-Historie, SMART-Checks und Prozessliste
- Moderne React-Oberfläche mit Tailwind CSS und Vite HMR
- Dev-Mode mit deterministischen Mockdaten und 10 GB Sandbox (Windows-kompatibel)

## Architektur

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, React Router
- **Backend (aktiv):** FastAPI (Python 3.11+), Pydantic, `uvicorn`, Hintergrundjobs für Telemetrie
- **Legacy Backend:** Express/TypeScript (liegt in `server/`, wird nicht mehr aktiv entwickelt)
- **Start-Skript:** `python start_dev.py` bootet FastAPI (Port 3001) und den Vite-Dev-Server (Port 5173)

## API-Überblick (FastAPI)

- **Auth**
   - `POST /api/auth/login`
   - `POST /api/auth/logout`
   - `GET /api/auth/me`
- **Dateien**
   - `GET /api/files/list?path=`
   - `POST /api/files/upload`
   - `GET /api/files/download?path=`
   - `POST /api/files/create-folder`
   - `POST /api/files/rename`
   - `POST /api/files/move`
   - `DELETE /api/files/delete`
- **Benutzer (Admin)**
   - `GET /api/users`
   - `POST /api/users`
   - `PUT /api/users/{id}`
   - `DELETE /api/users/{id}`
- **System & Monitoring**
   - `GET /api/system/info`
   - `GET /api/system/storage`
   - `GET /api/system/quota`
   - `GET /api/system/processes?limit=`
   - `GET /api/system/telemetry/history`
   - `GET /api/system/smart/status`
   - `GET /api/system/raid/status`
   - `POST /api/system/raid/degrade|rebuild|finalize` (Dev-Mode Simulation, Admin)
   - `POST /api/system/raid/options` (Produktiv-/Dev-Konfiguration via mdadm oder Simulator)

## Setup

### 1. FastAPI-Backend (empfohlen)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Development-Server
uvicorn app.main:app --reload --port 3001

# Tests
python -m pytest
```

### 2. Frontend

```bash
cd client
npm install
npm run dev

# Build/Test
npm run build
```

### 3. Kombinierter Dev-Start (Empfehlung)

```bash
python start_dev.py
```

Das Skript setzt `NAS_MODE=dev`, startet FastAPI auf Port 3001 sowie den Vite-Server auf Port 5173 und pflegt eine 10 GB Sandbox unter `backend/dev-storage`.

### Legacy Express Backend (optional)

Der Ordner `server/` enthält den früheren Express-Server. Er wird nicht mehr aktiv genutzt. Falls du ihn dennoch starten musst:

```bash
cd server
npm install
npm run dev
```

Die Express-Variante bietet nur Basisendpunkte ohne RAID-/SMART-/Quota-Funktionen.

## Konfiguration

### Backend `.env` (FastAPI)

```env
APP_NAME=Baluhost NAS API
NAS_MODE=dev
API_PREFIX=/api
HOST=0.0.0.0
PORT=3001

TOKEN_SECRET=change-me-in-prod
TOKEN_EXPIRE_MINUTES=720

ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
ADMIN_EMAIL=admin@example.com

NAS_STORAGE_PATH=./dev-storage
NAS_TEMP_PATH=./dev-tmp
NAS_QUOTA_BYTES=10737418240

TELEMETRY_INTERVAL_SECONDS=3.0
TELEMETRY_HISTORY_SIZE=60
```

> Im Produktivmodus (`NAS_MODE=prod`) werden reale Systemwerte genutzt. In Dev-Mode sorgt FastAPI für Mockdaten und initialisiert den Sandbox-Speicher.

### Frontend `.env`

```env
VITE_API_BASE_URL=http://localhost:3001
```

Alternativ nutzt Vite den Proxy aus `client/vite.config.ts`, der `/api` und `/auth` automatisch an Port 3001 weiterleitet.

## Verwendung

- Standard-Login: Benutzer `admin`, Passwort `changeme`
- Passwort nach der ersten Anmeldung ändern
- RAID-Optionen nur mit Admin-Token erreichbar

### Typischer Dev-Workflow

1. `python start_dev.py`
2. Browser öffnen: `http://localhost:5173`
3. Dashboard prüfen (Quota, RAID, SMART)
4. Tests: `cd backend && python -m pytest`, `cd client && npm run build`

## Projektstruktur

```
baluhost/
├── backend/          # FastAPI Backend (aktiver Codepfad)
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── main.py
│   ├── scripts/
│   ├── dev-storage/
│   └── tests/
├── client/           # React Frontend
│   ├── src/
│   └── vite.config.ts
├── server/           # Legacy Express Backend (deprecated)
├── start_dev.py      # Dev-Orchestrierung
└── README.md
```

## Legacy-Ablösung Express

- Neue Features werden ausschließlich im FastAPI-Backend implementiert.
- Das React-Frontend nutzt den FastAPI-Proxy (`/api`, `/auth`).
- Deployment-Dokumentation sollte FastAPI als Standard ausweisen; Express bleibt nur als Beispiel oder kurzfristige Vergleichsbasis.
- Im Zuge der Ablösung werden Tests, Docs und CI auf das Python-Backend konsolidiert.

## TODO / Verbesserungen

- [ ] Vollständiges Entfernen des Express-Backends und Migration der Restdokumentation
- [ ] Datenbank-Integration (PostgreSQL/MySQL)
- [ ] Datei-Vorschau (Bilder, PDFs)
- [ ] Sharing-Links
- [ ] Drag & Drop Upload mit Progress-Anzeige
- [ ] Suchfunktion und Papierkorb
- [ ] Echtzeit-Updates via WebSocket
- [ ] Docker-Compose Setup

## Lizenz

MIT

## Autor

Erstellt mit GitHub Copilot
