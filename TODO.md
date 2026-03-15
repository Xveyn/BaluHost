# BaluHost NAS Manager - TODO List

## 🚀 Production Deployment Status (25. Januar 2026)

BaluHost ist **LIVE IN PRODUCTION**:
- ✅ Debian 13 Server (Ryzen 5 5600GT, 16GB RAM, 250GB NVMe SSD)
- ✅ PostgreSQL 17.7 Datenbank
- ✅ Nginx Reverse Proxy (Port 80, HTTP)
- ✅ Systemd Services (4 Uvicorn Workers)
- ✅ 82 Test Files, 1465 Test Functions
- ✅ Prometheus/Grafana Ready Monitoring
- ✅ Structured JSON Logging

---

## 📋 Task Overview

| Priority | Area | Task | Status | Notes |
|----------|------|------|--------|-------|
| 🔴 High | Backend | Update telemetry/logging to surface unauthorized access attempts | ✅ Done | Security event logging implemented |
| 🔴 High | Backend | SQLite/PostgreSQL anbinden und Mock-Daten ablösen | ✅ Done | Database Models & Session Management, PostgreSQL fully supported with docker-compose.postgres.yml |
| 🔴 High | Backend | Database Sessions in API Routes injizieren | ✅ Done | auth.py, users.py, files.py migriert |
| 🔴 High | Backend | File Metadata Service auf Database migrieren | ✅ Done | file_metadata_db.py Service erstellt |
| 🔴 High | Backend | Alembic Migrations Setup | ✅ Done | Schema Versionierung konfiguriert |
| 🔴 High | Backend | Seed Data für Database | ✅ Done | scripts/seed.py erstellt |
| 🔴 High | Backend | Tests für Database Rollback | ✅ Done | conftest.py mit DB Fixtures |
| 🔴 High | Backend | Integration: Files Service mit DB verbinden | ✅ Done | files.py vollständig migriert |
| 🔴 High | Backend | Files API Integration Tests | ✅ Done | test_files_api_integration.py |
| 🔴 High | Backend | Audit Logs → Database (statt JSON-Files) | ✅ Done | Database Migration |
| 🔴 High | Backend | Upload-Progress Events (WebSocket/SSE) | ✅ Done | Real-time Updates |
| 🔴 High | Backend | Backup/Restore Funktionalität | ✅ Done | Data Protection |
| 🔴 High | Backend | Share-Links System (Public Links mit Passwort & Ablaufdatum) | ✅ Done | File Sharing |
| 🔴 High | Backend | Benutzerfreigaben Backend (Dateien mit anderen Benutzern teilen, granular Rechte-UI, Multi-User-Permissions) | ✅ Done | Collaboration, granular permissions |
| 🔴 High | Backend | RAID-Management auf echte mdadm-Befehle erweitern | ✅ Implemented (dev-mode + UI); mdadm extension pending | Production Mode |
| 🔴 High | Backend | Heimnetz-Setup (Windows Service, mDNS, Auto-Discovery) | ✅ Done | iCloud/OneDrive Alternative |
| 🔴 High | Backend | Power Management System (CPU Frequency Scaling) | ✅ Done | AMD Ryzen & Intel support, 4 profiles |
| 🔴 High | Backend | Fan Control System (PWM mit Temperaturkurven) | ✅ Done | 3 modes: auto/manual/emergency |
| 🔴 High | Backend | Network Discovery (mDNS/Bonjour) | ✅ Done | Local network auto-discovery |
| 🔴 High | Backend | Monitoring Orchestrator | ✅ Done | Unified monitoring with collectors |
| 🔴 High | Backend | Service Status Monitoring | ✅ Done | Health check dashboard |
| 🔴 High | Backend | Admin Database Inspection | ✅ Done | Read-only DB browser |
| 🔴 High | Backend | Tapo Smart Plug Integration | ✅ Done | P115/P110 energy monitoring |
| 🔴 High | Backend | Energy Statistics Service | ✅ Done | kWh calculations, cost estimates |
| 🔴 High | Frontend | Exercise manual test plan in dev mode | ⏳ Pending | Testing |
| 🔴 High | Frontend | Upload-Progress-UI mit Fortschrittsanzeige | ✅ Done | UX Enhancement |
| 🔴 High | Frontend | Datei-Vorschau Modal (PDF, Bilder, Videos, Audio, Text) | ✅ Done | Completed |
| 🔴 High | Frontend | Shares-Seite & FileManager: Public Links, Benutzerfreigaben, granular Rechte-UI, Multi-User-Permissions | ✅ Done | File Sharing UI, granular permissions (alle Regeln pro Datei werden immer vollständig übertragen und im Backend ersetzt) |
| 🔴 High | Frontend | Shares-Seite: Edit-Dialoge für Links & Shares | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Public Share Landing Page (/share/:token) | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Shares: Filter & Suche Funktionalität | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Settings-Seite (User-Profil, Avatar, Passwort ändern) | ✅ Done | User Management |
| 🔴 High | Frontend | Datei-Sharing (Public Links / Benutzerfreigaben) | ✅ Done | Collaboration |
| 🔴 High | Frontend | Batch-Operationen (Multi-Select für Dateien) | ✅ Done | Bulk Actions (UserManagement) |
| 🔴 High | Frontend | Drag & Drop für Upload | ✅ Done | Completed |
| 🔴 High | Frontend | Mobile-Optimierung (Responsive Design verbessern) | ⏳ Pending | Responsive |
| 🟡 Medium | Backend | Scheduled Health Checks Background Jobs erweitern | ✅ Done | Monitoring |
| 🟡 Medium | Backend | Email-Benachrichtigungen bei kritischen Ereignissen | ⏳ Pending | Notifications |
| 🟡 Medium | Backend | In-App Notification System (WebSocket/SSE) | 🟡 Partial | notification_scheduler.py implemented for mobile device expiration warnings |
| 🟡 Medium | Backend | VPN-Integration (WireGuard/OpenVPN) für Remote Access | ✅ Done | WireGuard implemented |
| 🟡 Medium | Backend | Mobile Apps (iOS + Android) | ✅ Done | Android: Full app (175+ Kotlin files), iOS: Complete implementation guide (1059 lines) |
| 🟡 Medium | Backend | Netzlaufwerk-Management Backend (SMB/CIFS, NFS Shares) | ⏳ Pending | Network Shares |
| 🟡 Medium | Backend | API-Rate-Limiting implementieren | ✅ Done | slowapi integrated with per-endpoint limits (auth, files, shares) |
| 🟡 Medium | Backend | Backup von Audit Logs | ⏳ Pending | Data Protection |
| 🟡 Medium | Backend | SMART-Warnungen automatisiert verarbeiten | ⏳ Pending | Disk Health |
| 🟡 Medium | Backend | Disk-Scrubbing initiieren/überwachen | ✅ Implemented (trigger via RAID options) | Data Integrity |
| 🟡 Medium | Backend | Datei-Versionierung Backend (Snapshots, Rollback) | ✅ Done | VCL implemented (Phases 1-7) |
| 🟡 Medium | Frontend | Dark Mode implementieren | ✅ Done | 6 Themes implemented (light, dark, ocean, forest, sunset, midnight) |
| 🟡 Medium | Frontend | Notifications-Seite mit Notification Center & Badge | ⏳ Pending | Notifications UI |
| 🟡 Medium | Frontend | NetworkShares-Seite: SMB/CIFS/NFS Shares verwalten | ⏳ Pending | Network Shares UI |
| 🟡 Medium | Frontend | Erweiterte Suchfunktion (Volltext, Filter) | ⏳ Pending | Search |
| 🟡 Medium | Frontend | Tag-System für Dateien (Tags hinzufügen, filtern) | ⏳ Pending | Organization |
| 🟡 Medium | Frontend | Sortierung und Filteroptionen | ✅ Done | Logging-Seite |
| 🟡 Medium | Frontend | Benutzer-Avatar-Upload | ⏳ Pending | User Profile |
| 🟡 Medium | Frontend | Dashboard-Widgets konfigurierbar machen | ⏳ Pending | Customization |
| 🟡 Medium | Frontend | Activity Feed Seite (Timeline aller Dateiaktivitäten) | ⏳ Pending | Activity Log |
| 🟢 Low | Backend | Media-Server Integration (DLNA/Plex API) | ⏳ Pending | Media Streaming |
| 🟢 Low | Backend | Video-Transcoding Service | ⏳ Pending | Media Processing |
| 🟢 Low | Backend | Datei-Versionierung mit Diff-Ansicht | ⏳ Pending | Advanced Versioning |
| 🔴 High | Backend | Containerization (Docker / Docker Compose) | ✅ Done | Systemd deployment active, Docker configs available |
| 🟢 Low | Backend | Kubernetes Deployment-Manifest | ⏳ Pending | Orchestration |
| 🟢 Low | Backend | CI/CD Pipeline (GitHub Actions) | ✅ Done | 7 workflows active |
| 🟢 Low | Backend | API-Versionierung (v1, v2) | ⏳ Pending | API Evolution |
| 🟢 Low | Backend | GraphQL-Alternative zu REST | ⏳ Pending | API Alternative |
| 🟢 Low | Backend | Webhooks für externe Integrationen | ⏳ Pending | Integration |
| 🟢 Low | Frontend | Media-Seite: Musik/Video-Bibliothek mit Player | ⏳ Pending | Media Library |
| 🟢 Low | Frontend | Mobile App (React Native/Flutter) für iOS/Android | ⏳ Pending | Mobile Platform |
| 🟢 Low | Frontend | Mobile App (React Native) oder Progressive Web App | ⏳ Pending | Mobile |
| � Medium | Frontend | VPN-Konfiguration UI (WireGuard/OpenVPN Setup) | ⏳ Pending | Remote Access UI (Backend ready, frontend pending) |
| 🟢 Low | Frontend | Datei-Versionierung UI (History, Rollback, Diff) | 🟡 Partial | Version History Modal done, FileManager integration pending |
| 🟢 Low | Frontend | Keyboard-Shortcuts (Vim-Mode im FileManager) | ⏳ Pending | Power User |
| 🟢 Low | Frontend | Mehrsprachigkeit (i18n - EN/DE) | ⏳ Pending | Localization |
| 🟢 Low | Frontend | Accessibility (ARIA, Screen-Reader) | ⏳ Pending | A11y |
| 🟢 Low | Frontend | Offline-Modus (Service Worker) | ⏳ Pending | PWA |
| 🟢 Low | Frontend | PWA-Support (installierbar) | ⏳ Pending | Progressive Web App |
| 📝 Docs | Documentation | README.md für Open-Source optimiert | ✅ Done | Completed |
| 📝 Docs | Documentation | CONTRIBUTING.md erstellt | ✅ Done | Code Style, PR-Prozess |
| 📝 Docs | Documentation | ARCHITECTURE.md erstellt | ✅ Done | System-Design |
| 📝 Docs | Documentation | USER_GUIDE.md erstellt | ✅ Done | End-User Docs |
| 📝 Docs | Documentation | API_REFERENCE.md erstellt | ✅ Done | API Documentation |
| 📝 Docs | Documentation | LICENSE hinzugefügt (MIT) | ✅ Done | Open Source |
| 📝 Docs | Documentation | SECURITY.md erstellt | ✅ Done | Security Policy |
| 📝 Docs | Documentation | Screenshots für README.md erstellen | ⏳ Pending | Visual Documentation |
| 🔴 High | Documentation | Deployment-Guide für Production | ✅ Done | DEPLOYMENT.md, setup scripts, systemd services complete |
| 📝 Docs | Documentation | Video-Tutorials aufnehmen | ⏳ Pending | Video Content |
| 📝 Docs | Documentation | Code-Kommentare standardisieren | ⏳ Pending | Docstrings, JSDoc |
| 📝 Docs | Documentation | Changelog.md für Versionshistorie | ✅ Done | CHANGELOG.md complete through v1.4.x |
| 📝 Docs | Documentation | Badges aktualisieren | ⏳ Pending | Test-Coverage, Build |
| 🧪 Test | Backend Testing | Integration Tests für alle API-Endpunkte | ✅ Done | 82 test files, 1465 test functions including integration, security, RAID, upload progress, sync tests |
| 🧪 Test | Backend Testing | Unit Tests für alle Services erweitern | ✅ Done | Excellent test coverage across all services |
| 🧪 Test | Backend Testing | Load Testing (Performance unter Last) | ⏳ Pending | Performance |
| 🧪 Test | Backend Testing | Security Testing (Penetration Tests) | ⏳ Pending | Security |
| 🧪 Test | Frontend Testing | Unit Tests mit Vitest | ⏳ Pending | Component Testing |
| 🧪 Test | Frontend Testing | E2E-Tests mit Playwright/Cypress | ⏳ Pending | E2E Testing |
| 🧪 Test | Frontend Testing | Visual Regression Tests | ⏳ Pending | Visual Testing |
| 🧪 Test | Frontend Testing | Accessibility Testing | ⏳ Pending | A11y Testing |
| 🔧 Tech Debt | Backend Refactoring | Express-Backend komplett entfernen (legacy) | ⏳ Pending | Cleanup |
| 🔧 Tech Debt | Backend Refactoring | Error-Handling vereinheitlichen | ⏳ Pending | Consistency |
| 🔧 Tech Debt | Backend Refactoring | Logging-Strategie überarbeiten | ✅ Done | JSON structured logging implemented |
| 🔧 Tech Debt | Backend Refactoring | Type Hints in allen Python-Modulen vervollständigen | ⏳ Pending | Type Safety |
| 🔧 Tech Debt | Backend Refactoring | Code-Coverage auf 80%+ erhöhen | ⏳ Pending | Testing |
| 🔧 Tech Debt | Frontend Refactoring | Komponenten in kleinere Units aufteilen | ⏳ Pending | Component Design |
| 🔧 Tech Debt | Frontend Refactoring | Shared Utilities extrahieren | ⏳ Pending | Code Reuse |
| 🔧 Tech Debt | Frontend Refactoring | API-Client-Layer refactoren | ⏳ Pending | API Layer |
| 🔧 Tech Debt | Frontend Refactoring | State-Management evaluieren (Zustand/Redux) | ⏳ Pending | State Management |
| 🔧 Tech Debt | Frontend Refactoring | CSS-Klassen reduzieren (Tailwind optimieren) | ⏳ Pending | CSS Optimization |

---

## ✅ Completed Tasks

| Area | Task | Completion Date |
|------|------|-----------------|
| Backend | JWT-Authentifizierung mit FastAPI | ✅ |
| Backend | Benutzer-/Rollenverwaltung (Admin, User) | ✅ |
| Backend | Datei-Upload/Download mit Quota-Kontrolle | ✅ |
| Backend | RAID-Status-Simulation (Dev-Mode) | ✅ |
| Backend | SMART-Monitoring (Dev-Mode) | ✅ |
| Backend | System-Telemetrie mit Historie | ✅ |
| Backend | Disk I/O Monitor | ✅ |
| Backend | Audit-Logging-System | ✅ |
| Backend | File Ownership & Permissions | ✅ |
| Backend | Dev-Mode mit 2x5GB RAID1 Sandbox | ✅ |
| Backend | Extend file persistence with ownerId field | ✅ |
| Backend | Authentication middleware with user context | ✅ |
| Backend | Authorization helpers for ownership and roles | ✅ |
| Backend | Upload endpoints assign file owner | ✅ |
| Backend | Restrict endpoints to owners or privileged roles | ✅ |
| Backend | Automated tests for permissions | ✅ |
| Backend | Upload-Progress Events (WebSocket/SSE) | ✅ |
| Frontend | React + TypeScript + Vite Setup | ✅ |
| Frontend | Tailwind CSS Integration | ✅ |
| Frontend | Login-Seite mit JWT-Handling | ✅ |
| Frontend | Dashboard mit System-Übersicht | ✅ |
| Frontend | FileManager mit CRUD-Operationen | ✅ |
| Frontend | UserManagement (Admin) | ✅ |
| Frontend | RAID-Management-Seite | ✅ |
| Frontend | System-Monitor mit Live-Charts | ✅ |
| Frontend | Logging-Seite (Audit Logs) | ✅ |
| Frontend | Responsive Layout mit Navigation | ✅ |
| Frontend | API client types with owner metadata | ✅ |
| Frontend | Gate file actions based on ownership/role | ✅ |
| Frontend | Surface owner information and error feedback | ✅ |
| Frontend | Upload-Progress-UI mit Fortschrittsanzeige | ✅ |

---

**Legend:**
- 🔴 High Priority - Critical features for MVP
- 🟡 Medium Priority - Important enhancements
- 🟢 Low Priority - Nice to have features
- 📝 Documentation - Documentation tasks
- 🧪 Testing - Testing & QA tasks
- 🔧 Technical Debt - Refactoring & cleanup
- ⏳ Pending - Not started
- ✅ Done - Completed

---

## Review Notes (20. Dezember 2025)

- `TECHNICAL_DOCUMENTATION.md` was rewritten and improved (ASCII diagram fenced) — ✅ Completed 2025-12-20
- `.gitignore` updated to ignore local DB files and `backend/baluhost.db*` were untracked from Git — ✅ Completed 2025-12-20
- Local branch `chore/commit-all-2025-12-20` changes merged into `main` and pushed to `origin/main` — ✅ Completed 2025-12-20

Note: I scanned the repository for remaining in-code `TODO` markers. Several implementation TODO comments remain (e.g. in `backend/app/services/sync_scheduler.py`, `backup.py`); these are kept as development TODOs and are not moved to this global list.

---

## 🔎 Scanned Actionable TODOs (20. Dezember 2025)

Below are the most relevant, actionable TODOs found in the repository (excluded virtualenv / third-party packages). These are recommended to be tracked in the global roadmap or converted into GitHub Issues.

- **High**: `backend/app/services/sync_scheduler.py` — Implement scheduled sync trigger and `_execute_sync` (critical for scheduled syncs / background sync worker).
- **Medium**: `backend/app/services/backup.py` — Add config files to backup and implement restore flow for full-system restores.
- **Medium**: `backend/app/api/routes/files.py` — Implement accurate per-file/per-array usage tracking (replace placeholder `used_bytes = 0`).
- **Low**: `client/src/pages/PublicSharePage.tsx` — Implement preview functionality for shared files.
- **Low**: `docs/STORAGE_MOUNTPOINTS.md` — Implement actual per-array usage tracking documentation and examples.
- **Low**: `CONTRIBUTING.md` — Add community link (Discord/Matrix) and update contact points.
- **Low**: `README.md` — Add runnable `npm run test` and `npm run test:e2e` instructions or CI configuration.

Suggested next steps:

- Create GitHub issues for each **High** and **Medium** item and assign priorities.
- For development TODOs inside `backend/app/*`, keep them as in-code TODOs but reference the newly created GitHub issues.
- Optionally, create a `TODO:dev` section in this file linking to issue IDs for tracking.

