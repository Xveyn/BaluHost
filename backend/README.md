# Baluhost Python Backend

FastAPI-basierter Prototyp für das NAS-Management. Alle kritischen Subsysteme (Auth, Dateiverwaltung, Systemmonitoring) werden zunächst gemockt, damit die React-Oberfläche unabhängig von echter NAS-Hardware entwickelt werden kann.

## Features (Mock)
- JWT-ähnliche Tokenprüfung mit statischen Secrets
- Benutzer-/Rollenverwaltung aus In-Memory-Daten
- Dateioperationen gegen ein Sandbox-Verzeichnis
- Systemmetriken via psutil oder Mockdaten bei fehlender Plattformunterstützung
- Quota-, RAID- und SMART-Simulation im Dev-Mode (Windows-tauglich)

## Quickstart
```bash
# optional: py -3.11 -m venv .venv
#          .venv\Scripts\activate
# PowerShell: pip install -e ".\[dev]"
# CMD/Git Bash: pip install -e .[dev]
pip install -e ".\[dev]"

# Dev mode defaults (Windows sandbox, 10 GB Quota)
echo "NAS_MODE=dev" >> .env
echo "NAS_QUOTA_BYTES=10737418240" >> .env

# Backend alleine starten
python -m uvicorn app.main:app --reload --port 3001

# Kombinierter Start (Frontend + Backend): im Projektstamm
python ../start_dev.py

# Dev-Test-Script (prüft System-/Quota-/SMART-/RAID-Endpunkte)
python scripts/dev_check.py --raid-cycle
```

## Struktur
```
app/
  api/
    routes/        # FastAPI Router
    deps.py        # Abhängigkeiten (Auth, DB Session)
  core/
    config.py      # Settings & Logging Setup
  services/
    auth.py        # Mock-Auth und Token-Helfer
    files.py       # Sandbox-Dateioperationen
    system.py      # psutil- oder Mock-Metriken
  schemas/         # Pydantic-Modelle für Requests/Responses
  main.py          # FastAPI Application
```

## Nächste Schritte
- SQLite/PostgreSQL anbinden und Mock-Daten ablösen
- Persistente File-Metadaten und Quotas modellieren
- Upload-Progress, Sharing und Websocket-Events ergänzen
- Express-Backend mittelfristig ablösen und FastAPI auch produktiv einsetzen
