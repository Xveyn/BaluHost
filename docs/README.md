# Dokumentations-Übersicht

Willkommen zur technischen Dokumentation des BaluHost NAS Managers.

## 📚 Hauptdokumentation

- **[TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md)** - Vollständige technische Dokumentation aller Features
- **[TODO.md](../TODO.md)** - Globale TODO-Liste mit Priorisierung
- **[README.md](../README.md)** - Projekt-Übersicht und Setup-Anleitung

## 🔧 Feature-Dokumentation

### System-Monitoring
- **[DISK_IO_MONITOR.md](DISK_IO_MONITOR.md)** - Disk I/O Monitor Implementierung
- **[PERFORMANCE_ANALYSIS.md](PERFORMANCE_ANALYSIS.md)** - Telemetrie Performance-Analyse
- **[TELEMETRY_CONFIG_RECOMMENDATIONS.md](TELEMETRY_CONFIG_RECOMMENDATIONS.md)** - Telemetrie-Konfiguration

### Sicherheit & Logging
- **[AUDIT_LOGGING.md](AUDIT_LOGGING.md)** - Audit-Logging-System

### Development
- **[DEV_CHECKLIST.md](DEV_CHECKLIST.md)** - Backend Dev-Mode Checkliste

## 📁 Legacy-Dokumentation

- **[legacy/MOCK_SYSTEM.md](legacy/MOCK_SYSTEM.md)** - Express-Backend Mock-System (veraltet)

## 🏗️ Komponentendokumentation

### Backend (FastAPI)
Siehe `../backend/README.md` für Backend-spezifische Informationen.

### Frontend (React)
Siehe `../client/README.md` für Frontend-spezifische Informationen.

## 🚀 Quick Links

- [API-Endpunkte](../README.md#api-überblick-fastapi)
- [Setup-Anleitung](../README.md#setup)
- [Dev-Mode Konfiguration](DEV_CHECKLIST.md)
- [Features-Übersicht](../TECHNICAL_DOCUMENTATION.md)

## 📝 Dokumentations-Standards

Bei der Erstellung neuer Dokumentation:
- Feature-Dokumentation → `docs/`
- API-Dokumentation → Im Haupt-README oder als OpenAPI/Swagger
- Code-Kommentare → Direkt im Code (JSDoc/Docstrings)
- Legacy-Dokumentation → `docs/legacy/`
