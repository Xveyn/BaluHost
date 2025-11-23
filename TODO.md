# BaluHost NAS Manager - TODO List

## 📋 Task Overview

| Priority | Area | Task | Status | Notes |
|----------|------|------|--------|-------|
| 🔴 High | Backend | Update telemetry/logging to surface unauthorized access attempts | ✅ Done | Security event logging implemented |
| 🔴 High | Backend | SQLite/PostgreSQL anbinden und Mock-Daten ablösen | ✅ Done | Database Models & Session Management |
| 🔴 High | Backend | Database Sessions in API Routes injizieren | ✅ Done | auth.py, users.py, files.py migriert |
| 🔴 High | Backend | File Metadata Service auf Database migrieren | ✅ Done | file_metadata_db.py Service erstellt |
| 🔴 High | Backend | Alembic Migrations Setup | ✅ Done | Schema Versionierung konfiguriert |
| 🔴 High | Backend | Seed Data für Database | ✅ Done | scripts/seed.py erstellt |
| 🔴 High | Backend | Tests für Database Rollback | ✅ Done | conftest.py mit DB Fixtures |
| 🔴 High | Backend | Integration: Files Service mit DB verbinden | ✅ Done | files.py vollständig migriert |
| 🔴 High | Backend | Files API Integration Tests | ✅ Done | test_files_api_integration.py |
| 🔴 High | Backend | Audit Logs → Database (statt JSON-Files) | ✅ Done | Database Migration |
| 🔴 High | Backend | Upload-Progress Events (WebSocket/SSE) | ✅ Done | Real-time Updates |
| 🔴 High | Backend | Backup/Restore Funktionalität | ⏳ Pending | Data Protection |
| 🔴 High | Backend | Share-Links System (Public Links mit Passwort & Ablaufdatum) | ✅ Done | File Sharing |
| 🔴 High | Backend | Benutzerfreigaben Backend (Dateien mit anderen Benutzern teilen) | ✅ Done | Collaboration |
| 🔴 High | Backend | RAID-Management auf echte mdadm-Befehle erweitern | ⏳ Pending | Production Mode |
| 🔴 High | Frontend | Exercise manual test plan in dev mode | ⏳ Pending | Testing |
| 🔴 High | Frontend | Upload-Progress-UI mit Fortschrittsanzeige | ✅ Done | UX Enhancement |
| 🔴 High | Frontend | Datei-Vorschau Modal (PDF, Bilder, Videos, Audio, Text) | ✅ Done | Completed |
| 🔴 High | Frontend | Shares-Seite: Public Links & Benutzerfreigaben verwalten | ✅ Done | File Sharing UI |
| 🔴 High | Frontend | Shares-Seite: Edit-Dialoge für Links & Shares | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Public Share Landing Page (/share/:token) | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Shares: Filter & Suche Funktionalität | ✅ Done | Phase 1 Complete |
| 🔴 High | Frontend | Settings-Seite (User-Profil, Avatar, Passwort ändern) | ✅ Done | User Management |
| 🔴 High | Frontend | Datei-Sharing (Public Links / Benutzerfreigaben) | ✅ Done | Collaboration |
| 🔴 High | Frontend | Batch-Operationen (Multi-Select für Dateien) | ⏳ Pending | Bulk Actions |
| 🔴 High | Frontend | Drag & Drop für Upload | ✅ Done | Completed |
| 🔴 High | Frontend | Mobile-Optimierung (Responsive Design verbessern) | ⏳ Pending | Responsive |
| 🟡 Medium | Backend | Scheduled Health Checks Background Jobs erweitern | ⏳ Pending | Monitoring |
| 🟡 Medium | Backend | Email-Benachrichtigungen bei kritischen Ereignissen | ⏳ Pending | Notifications |
| 🟡 Medium | Backend | In-App Notification System (WebSocket/SSE) | ⏳ Pending | Real-time Notifications |
| 🟡 Medium | Backend | VPN-Integration (WireGuard/OpenVPN) für Remote Access | ⏳ Pending | Remote Access |
| 🟡 Medium | Backend | Netzlaufwerk-Management Backend (SMB/CIFS, NFS Shares) | ⏳ Pending | Network Shares |
| 🟡 Medium | Backend | API-Rate-Limiting implementieren | ⏳ Pending | Security |
| 🟡 Medium | Backend | Backup von Audit Logs | ⏳ Pending | Data Protection |
| 🟡 Medium | Backend | SMART-Warnungen automatisiert verarbeiten | ⏳ Pending | Disk Health |
| 🟡 Medium | Backend | Disk-Scrubbing initiieren/überwachen | ⏳ Pending | Data Integrity |
| 🟡 Medium | Backend | Datei-Versionierung Backend (Snapshots, Rollback) | ⏳ Pending | Version Control |
| 🟡 Medium | Frontend | Dark Mode implementieren | ⏳ Pending | UI Enhancement |
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
| 🟢 Low | Backend | Containerization (Docker / Docker Compose) | ⏳ Pending | Deployment |
| 🟢 Low | Backend | Kubernetes Deployment-Manifest | ⏳ Pending | Orchestration |
| 🟢 Low | Backend | CI/CD Pipeline (GitHub Actions) | ⏳ Pending | Automation |
| 🟢 Low | Backend | API-Versionierung (v1, v2) | ⏳ Pending | API Evolution |
| 🟢 Low | Backend | GraphQL-Alternative zu REST | ⏳ Pending | API Alternative |
| 🟢 Low | Backend | Webhooks für externe Integrationen | ⏳ Pending | Integration |
| 🟢 Low | Frontend | Media-Seite: Musik/Video-Bibliothek mit Player | ⏳ Pending | Media Library |
| 🟢 Low | Frontend | Mobile App (React Native/Flutter) für iOS/Android | ⏳ Pending | Mobile Platform |
| 🟢 Low | Frontend | Mobile App (React Native) oder Progressive Web App | ⏳ Pending | Mobile |
| 🟢 Low | Frontend | VPN-Konfiguration UI (WireGuard/OpenVPN Setup) | ⏳ Pending | Remote Access UI |
| 🟢 Low | Frontend | Datei-Versionierung UI (History, Rollback, Diff) | ⏳ Pending | Version Control UI |
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
| 📝 Docs | Documentation | Deployment-Guide für Production | ⏳ Pending | Linux/NAS |
| 📝 Docs | Documentation | Video-Tutorials aufnehmen | ⏳ Pending | Video Content |
| 📝 Docs | Documentation | Code-Kommentare standardisieren | ⏳ Pending | Docstrings, JSDoc |
| 📝 Docs | Documentation | Changelog.md für Versionshistorie | ⏳ Pending | Version Tracking |
| 📝 Docs | Documentation | Badges aktualisieren | ⏳ Pending | Test-Coverage, Build |
| 🧪 Test | Backend Testing | Integration Tests für alle API-Endpunkte | ⏳ Pending | API Testing |
| 🧪 Test | Backend Testing | Unit Tests für alle Services erweitern | ⏳ Pending | Service Testing |
| 🧪 Test | Backend Testing | Load Testing (Performance unter Last) | ⏳ Pending | Performance |
| 🧪 Test | Backend Testing | Security Testing (Penetration Tests) | ⏳ Pending | Security |
| 🧪 Test | Frontend Testing | Unit Tests mit Vitest | ⏳ Pending | Component Testing |
| 🧪 Test | Frontend Testing | E2E-Tests mit Playwright/Cypress | ⏳ Pending | E2E Testing |
| 🧪 Test | Frontend Testing | Visual Regression Tests | ⏳ Pending | Visual Testing |
| 🧪 Test | Frontend Testing | Accessibility Testing | ⏳ Pending | A11y Testing |
| 🔧 Tech Debt | Backend Refactoring | Express-Backend komplett entfernen (legacy) | ⏳ Pending | Cleanup |
| 🔧 Tech Debt | Backend Refactoring | Error-Handling vereinheitlichen | ⏳ Pending | Consistency |
| 🔧 Tech Debt | Backend Refactoring | Logging-Strategie überarbeiten | ⏳ Pending | Structured Logging |
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
