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
- **[USER_GUIDE.md](getting-started/USER_GUIDE.md)** - Benutzerhandbuch
- **[DEV_CHECKLIST.md](getting-started/DEV_CHECKLIST.md)** - Entwickler-Checkliste

### [deployment/](deployment/) - Deployment & Betrieb
- **[DEPLOYMENT.md](deployment/DEPLOYMENT.md)** - Deployment-Guide
- **[PRODUCTION_QUICKSTART.md](deployment/PRODUCTION_QUICKSTART.md)** - Produktion Quick-Start
- **[PRODUCTION_READINESS.md](deployment/PRODUCTION_READINESS.md)** - Produktionsreife-Checkliste
- **[PRODUCTION_DEPLOYMENT_NOTES.md](deployment/PRODUCTION_DEPLOYMENT_NOTES.md)** - Deployment-Notizen
- **[FRONTEND_DEPLOYMENT.md](deployment/FRONTEND_DEPLOYMENT.md)** - Frontend-Deployment
- **[SSL_SETUP.md](deployment/SSL_SETUP.md)** - SSL/TLS-Konfiguration
- **[REVERSE_PROXY_SETUP.md](deployment/REVERSE_PROXY_SETUP.md)** - Reverse-Proxy-Setup

### [monitoring/](monitoring/) - Monitoring & Performance
- **[MONITORING.md](monitoring/MONITORING.md)** - Monitoring-Setup (Prometheus/Grafana)
- **[MONITORING_QUICKSTART.md](monitoring/MONITORING_QUICKSTART.md)** - Monitoring Quick-Start
- **[DISK_IO_MONITOR.md](monitoring/DISK_IO_MONITOR.md)** - Disk I/O Monitor
- **[TELEMETRY_CONFIG_RECOMMENDATIONS.md](monitoring/TELEMETRY_CONFIG_RECOMMENDATIONS.md)** - Telemetrie-Konfiguration

### [security/](security/) - Sicherheit & Logging
- **[SECURITY.md](security/SECURITY.md)** - Sicherheitsübersicht
- **[AUDIT_LOGGING.md](security/AUDIT_LOGGING.md)** - Audit-Logging-System
- **[API_RATE_LIMITING.md](security/API_RATE_LIMITING.md)** - Rate Limiting
- **[RATE_LIMITING_QUICKSTART.md](security/RATE_LIMITING_QUICKSTART.md)** - Rate Limit Quick-Reference

### [network/](network/) - Netzwerk & Zugriff
- **[VPN_INTEGRATION.md](network/VPN_INTEGRATION.md)** - WireGuard VPN
- **[WEBDAV_NETWORK_DRIVE.md](network/WEBDAV_NETWORK_DRIVE.md)** - WebDAV-Setup
- **[NETWORK_DRIVE_SETUP.md](network/NETWORK_DRIVE_SETUP.md)** - Netzlaufwerk-Mounting
- **[NETWORK_DRIVE_QUICKSTART.md](network/NETWORK_DRIVE_QUICKSTART.md)** - Netzlaufwerk Quick-Start
- **[CLIENT_MDNS_SETUP.md](network/CLIENT_MDNS_SETUP.md)** - mDNS-Client-Konfiguration

### [api/](api/) - API-Dokumentation
- **[API_REFERENCE.md](api/API_REFERENCE.md)** - API-Referenz

### [features/](features/) - Feature-Dokumentation
- **[USER_MANAGEMENT_FEATURES.md](features/USER_MANAGEMENT_FEATURES.md)** - User-Management
- **[SHARING_FEATURES_PHASE1.md](features/SHARING_FEATURES_PHASE1.md)** - File-Sharing
- **[UPLOAD_PROGRESS.md](features/UPLOAD_PROGRESS.md)** - Upload-Progress (SSE)

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
| API-Endpunkte | [API_REFERENCE.md](api/API_REFERENCE.md) |
| Dev-Mode | [DEV_CHECKLIST.md](getting-started/DEV_CHECKLIST.md) |
| Produktion | [PRODUCTION_QUICKSTART.md](deployment/PRODUCTION_QUICKSTART.md) |
| Features | [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) |
| Plugin-System | [backend/app/plugins/README.md](../backend/app/plugins/README.md) |
