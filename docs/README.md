# Dokumentations-Übersicht

Willkommen zur technischen Dokumentation des BaluHost NAS Managers.

## Hauptdokumentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System-Architektur
- **[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)** - Vollständige technische Dokumentation
- **[../README.md](../README.md)** - Projekt-Übersicht und Setup-Anleitung
- **[../TODO.md](../TODO.md)** - Globale TODO-Liste mit Priorisierung

---

## 📁 Verzeichnisstruktur

### [getting-started/](getting-started/) - Einstieg
- **[USER_GUIDE.de.md](getting-started/USER_GUIDE.de.md)** - Benutzerhandbuch
- **[DEV_CHECKLIST.de.md](getting-started/DEV_CHECKLIST.de.md)** - Entwickler-Checkliste

### [deployment/](deployment/) - Deployment & Betrieb
- **[DEPLOYMENT.de.md](deployment/DEPLOYMENT.de.md)** - Deployment-Guide
- **[PRODUCTION_QUICKSTART.de.md](deployment/PRODUCTION_QUICKSTART.de.md)** - Produktion Quick-Start
- **[PRODUCTION_READINESS.de.md](deployment/PRODUCTION_READINESS.de.md)** - Produktionsreife-Checkliste
- **[PRODUCTION_DEPLOYMENT_NOTES.de.md](deployment/PRODUCTION_DEPLOYMENT_NOTES.de.md)** - Deployment-Notizen
- **[FRONTEND_DEPLOYMENT.de.md](deployment/FRONTEND_DEPLOYMENT.de.md)** - Frontend-Deployment
- **[SSL_SETUP.de.md](deployment/SSL_SETUP.de.md)** - SSL/TLS-Konfiguration
- **[REVERSE_PROXY_SETUP.de.md](deployment/REVERSE_PROXY_SETUP.de.md)** - Reverse-Proxy-Setup

### [monitoring/](monitoring/) - Monitoring & Performance
- **[MONITORING.de.md](monitoring/MONITORING.de.md)** - Monitoring-Setup (Prometheus/Grafana)
- **[MONITORING_QUICKSTART.de.md](monitoring/MONITORING_QUICKSTART.de.md)** - Monitoring Quick-Start
- **[DISK_IO_MONITOR.de.md](monitoring/DISK_IO_MONITOR.de.md)** - Disk I/O Monitor
- **[TELEMETRY_CONFIG_RECOMMENDATIONS.de.md](monitoring/TELEMETRY_CONFIG_RECOMMENDATIONS.de.md)** - Telemetrie-Konfiguration

### [security/](security/) - Sicherheit & Logging
- **[SECURITY.de.md](security/SECURITY.de.md)** - Sicherheitsübersicht
- **[AUDIT_LOGGING.de.md](security/AUDIT_LOGGING.de.md)** - Audit-Logging-System
- **[API_RATE_LIMITING.de.md](security/API_RATE_LIMITING.de.md)** - Rate Limiting
- **[RATE_LIMITING_QUICKSTART.de.md](security/RATE_LIMITING_QUICKSTART.de.md)** - Rate Limit Quick-Reference

### [network/](network/) - Netzwerk & Zugriff
- **[VPN_INTEGRATION.de.md](network/VPN_INTEGRATION.de.md)** - WireGuard VPN
- **[WEBDAV_NETWORK_DRIVE.de.md](network/WEBDAV_NETWORK_DRIVE.de.md)** - WebDAV-Setup
- **[NETWORK_DRIVE_SETUP.de.md](network/NETWORK_DRIVE_SETUP.de.md)** - Netzlaufwerk-Mounting
- **[NETWORK_DRIVE_QUICKSTART.de.md](network/NETWORK_DRIVE_QUICKSTART.de.md)** - Netzlaufwerk Quick-Start
- **[CLIENT_MDNS_SETUP.de.md](network/CLIENT_MDNS_SETUP.de.md)** - mDNS-Client-Konfiguration

### [api/](api/) - API-Dokumentation
- **[API_REFERENCE.de.md](api/API_REFERENCE.de.md)** - API-Referenz

### [features/](features/) - Feature-Dokumentation
- **[USER_MANAGEMENT_FEATURES.de.md](features/USER_MANAGEMENT_FEATURES.de.md)** - User-Management
- **[SHARING_FEATURES_PHASE1.de.md](features/SHARING_FEATURES_PHASE1.de.md)** - File-Sharing
- **[UPLOAD_PROGRESS.de.md](features/UPLOAD_PROGRESS.de.md)** - Upload-Progress (SSE)

### Plugins & Smart Devices
- **[../backend/app/plugins/README.md](../backend/app/plugins/README.md)** - Plugin-System (Architektur, Lifecycle, Hooks, Events, Permissions, Anleitung)
- **[plans/Snart_Devices_Plugins.md](plans/Snart_Devices_Plugins.md)** - Smart-Device-Plugin-Konzept

### Analysen & Pläne
- **[CODE_ANALYSIS_2026-03-17.md](CODE_ANALYSIS_2026-03-17.md)** - Codebase-Analyse (März 2026)
- **[plans/](plans/)** - Architektur- und Feature-Pläne

---

## Komponentendokumentation

- **[../backend/README.md](../backend/README.md)** - Backend-Übersicht (FastAPI)
- **[../client/README.md](../client/README.md)** - Frontend-Übersicht (React)

## Quick Links

| Thema | Link |
|-------|------|
| Projekt-Setup | [README.md](../README.md#setup) |
| API-Endpunkte | [API_REFERENCE.de.md](api/API_REFERENCE.de.md) |
| Dev-Mode | [DEV_CHECKLIST.de.md](getting-started/DEV_CHECKLIST.de.md) |
| Produktion | [PRODUCTION_QUICKSTART.de.md](deployment/PRODUCTION_QUICKSTART.de.md) |
| Features | [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) |
| Plugin-System | [backend/app/plugins/README.md](../backend/app/plugins/README.md) |
