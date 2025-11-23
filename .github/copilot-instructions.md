# GitHub Copilot Instructions für BaluHost

## Projekt-Übersicht
Full-stack NAS Management Webanwendung mit:
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **Backend:** Python FastAPI (aktiv) + Legacy Express/TypeScript (deprecated)

## Architektur-Kontext

### Aktuelle Technologie
- **Backend:** FastAPI (Python 3.11+) in `backend/`
- **Frontend:** React 18 mit TypeScript in `client/`
- **Legacy:** Express Backend in `server/` (nicht mehr aktiv entwickelt)

### Wichtige Hinweise für Code-Generierung
1. **Backend-Änderungen nur in FastAPI** (`backend/app/`)
2. **Keine Änderungen im Express-Backend** (`server/`) - Legacy-Code
3. **Python-Code:** Type Hints verwenden, Pydantic für Schemas
4. **Frontend-Code:** TypeScript strict mode, Tailwind für Styling

## Code-Standards

### Python (FastAPI)
- Async/await für I/O-Operationen
- Pydantic Models für Request/Response
- Type Hints in allen Funktionen
- Docstrings für Services
- Services in `app/services/`, Routes in `app/api/routes/`

### TypeScript (React)
- Functional Components mit Hooks
- TypeScript strict mode
- Tailwind CSS für Styling (keine inline styles)
- Custom Hooks in `src/hooks/`
- API-Client in `src/lib/api.ts` und `src/api/`

## Implementierte Features

### Backend (FastAPI)
- JWT-Authentifizierung
- File Ownership & Permissions
- RAID-Management (Dev-Mode Simulation)
- SMART-Monitoring
- Disk I/O Monitor
- Audit Logging System
- System Telemetrie
- Quota-System

### Frontend (React)
- Dashboard mit Live-Charts
- FileManager mit CRUD
- UserManagement (Admin)
- RAID-Management-Seite
- System-Monitor
- Audit-Logging-Anzeige

## Dokumentations-Struktur
- `README.md` - Projekt-Übersicht
- `TECHNICAL_DOCUMENTATION.md` - Vollständige Feature-Dokumentation
- `TODO.md` - Globale TODO-Liste
- `docs/` - Zusätzliche Feature-Dokumentation

## Dev-Mode
- `NAS_MODE=dev` aktiviert Sandbox-Speicher (2x5GB RAID1, effektiv 5 GB)
- Automatische Seed-Daten
- Mock-Daten für RAID/SMART
- Windows-kompatibel

## Wichtige Befehle
```bash
# Kombinierter Start
python start_dev.py

# Backend Tests
cd backend && python -m pytest

# Frontend Build
cd client && npm run build
```
