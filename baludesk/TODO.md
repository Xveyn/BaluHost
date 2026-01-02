# BaluDesk - Desktop Client Entwicklungsplan

## 📋 Projektübersicht

**BaluDesk** ist ein plattformübergreifender Desktop-Client für BaluHost NAS mit Hintergrund-Synchronisation und moderner GUI.

### Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                     BaluDesk Application                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Electron Frontend (JavaScript/TypeScript)   │    │
│  │  - React 18 + TypeScript                            │    │
│  │  - Electron IPC für Backend-Kommunikation           │    │
│  │  - System Tray Integration                          │    │
│  │  - Modern UI (Tailwind CSS)                         │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ↕ IPC                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         C++ Backend (Core Sync Engine)              │    │
│  │  - libcurl für HTTP/HTTPS Kommunikation             │    │
│  │  - SQLite für lokale Metadaten                      │    │
│  │  - Filesystem Watcher (inotify/FSEvents/ReadDirCh.) │    │
│  │  - Multi-threaded Sync Engine                       │    │
│  │  - Conflict Resolution Engine                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ↕ REST API                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              BaluHost NAS Backend                   │    │
│  │  - FastAPI (Python)                                 │    │
│  │  - File API, Share API, Sync API                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Hauptfunktionen

### Phase 1: Core Sync Engine (C++ Backend)
- [ ] **Projekt-Setup**
  - [ ] CMake Build-System einrichten
  - [ ] Cross-Platform Build (Windows, macOS, Linux)
  - [ ] Dependencies: libcurl, SQLite, spdlog, nlohmann/json
  - [ ] Unit Test Framework (Google Test)

- [ ] **HTTP Client**
  - [ ] libcurl Wrapper für REST API Calls
  - [ ] JWT Token Management
  - [ ] Automatic Token Refresh
  - [ ] SSL/TLS Certificate Validation
  - [ ] Connection Pooling
  - [ ] Retry Logic mit Exponential Backoff

- [ ] **Lokale Datenbank (SQLite)**
  - [ ] Schema: sync_folders, file_metadata, sync_state, conflicts
  - [ ] Prepared Statements für Performance
  - [ ] Transaktionale Updates
  - [ ] Database Migrations

- [ ] **Filesystem Watcher**
  - [ ] Windows: ReadDirectoryChangesW
  - [ ] macOS: FSEvents API
  - [ ] Linux: inotify
  - [ ] Abstraction Layer für plattformübergreifende API
  - [ ] Event Debouncing (keine Duplikate bei schnellen Änderungen)

- [ ] **Sync Engine**
  - [ ] Bidirektionale Synchronisation
  - [ ] Change Detection (Local + Remote)
  - [ ] Chunked Upload für große Dateien
  - [ ] Resume bei Abbruch (Checkpoints)
  - [ ] Bandwidth Limiting (optional)
  - [ ] Conflict Detection & Resolution
  - [ ] Selective Sync (Ordner-Whitelist)

- [ ] **Conflict Resolution**
  - [ ] Last-Write-Wins Strategie
  - [ ] Keep Both Versions (Rename)
  - [ ] Manual Resolution (UI Notification)
  - [ ] Conflict History Log

### Phase 2: Electron Frontend
- [ ] **Projekt-Setup**
  - [ ] Electron + React + TypeScript + Vite
  - [ ] Electron Forge für Packaging
  - [ ] IPC Bridge (Main <-> Renderer Process)
  - [ ] Auto-Update Integration (electron-updater)

- [ ] **Main Process (Node.js)**
  - [ ] Spawn C++ Backend als Child Process
  - [ ] IPC Bridge zu C++ (stdin/stdout JSON Messages)
  - [ ] System Tray Integration
  - [ ] App Lifecycle Management
  - [ ] Startup auf System Boot (optional)

- [ ] **Renderer Process (React UI)**
  - [ ] **Login Screen**
    - [ ] Server URL Configuration
    - [ ] Username/Password Login
    - [ ] Token Storage (encrypted)
  
  - [ ] **Dashboard**
    - [ ] Sync Status Overview (Idle/Syncing/Paused/Error)
    - [ ] Upload/Download Speed
    - [ ] Last Sync Time
    - [ ] Storage Quota Display

  - [ ] **Folder Management**
    - [ ] Add Sync Folder Dialog
    - [ ] Folder List mit Status Icons
    - [ ] Remove/Pause Sync Folder
    - [ ] Selective Sync (Subfolder-Auswahl)
  
  - [ ] **Settings**
    - [ ] Bandwidth Limit
    - [ ] Auto-Start on Boot
    - [ ] Notification Preferences
    - [ ] Conflict Resolution Strategy
    - [ ] Sync Interval

  - [ ] **Activity Log**
    - [ ] Recent File Changes
    - [ ] Sync History
    - [ ] Error Messages
    - [ ] Conflict Notifications

  - [ ] **System Tray**
    - [ ] Status Icon (Idle/Syncing/Error)
    - [ ] Quick Actions Menu
    - [ ] Pause/Resume Sync
    - [ ] Open Folder
    - [ ] Quit App

### Phase 3: Advanced Features
- [ ] **Performance**
  - [ ] Delta Sync (nur geänderte Chunks übertragen)
  - [ ] Compression (zlib/gzip)
  - [ ] Parallel Upload/Download (Thread Pool)
  - [ ] Smart Retry bei Netzwerkfehlern

- [ ] **Security**
  - [ ] Encrypted Token Storage (OS Keychain)
  - [ ] SSL Pinning (optional)
  - [ ] Secure IPC Communication
  - [ ] Memory Protection für Credentials

- [ ] **Monitoring & Logging**
  - [ ] Structured Logging (spdlog)
  - [ ] Log Rotation
  - [ ] Crash Reports (Sentry Integration)
  - [ ] Performance Metrics

- [ ] **Packaging & Distribution**
  - [ ] Windows: MSI Installer (WiX Toolset)
  - [ ] macOS: DMG + Code Signing
  - [ ] Linux: AppImage/deb/rpm
  - [ ] Auto-Update Mechanism

---

## 🛠️ Technologie-Stack

### C++ Backend
| Komponente | Technologie | Version |
|------------|-------------|---------|
| Build System | CMake | 3.20+ |
| HTTP Client | libcurl | 8.5+ |
| JSON Parser | nlohmann/json | 3.11+ |
| Database | SQLite3 | 3.40+ |
| Logging | spdlog | 1.12+ |
| Testing | Google Test | 1.14+ |
| Cross-Platform | C++17 Standard | - |

### Electron Frontend
| Komponente | Technologie | Version |
|------------|-------------|---------|
| Framework | Electron | 28.x |
| UI Library | React | 18.x |
| Language | TypeScript | 5.x |
| Build Tool | Vite | 5.x |
| Styling | Tailwind CSS | 3.x |
| State Management | Zustand | 4.x |
| IPC | electron-ipc | - |
| Packaging | Electron Forge | 7.x |
| Auto-Update | electron-updater | 6.x |

---

## 📁 Projektstruktur

```
baludesk/
├── README.md
├── TODO.md (diese Datei)
├── ARCHITECTURE.md
│
├── backend/                  # C++ Sync Engine
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp
│   │   ├── sync/
│   │   │   ├── sync_engine.h/cpp
│   │   │   ├── file_watcher.h/cpp
│   │   │   ├── conflict_resolver.h/cpp
│   │   │   └── change_detector.h/cpp
│   │   ├── api/
│   │   │   ├── http_client.h/cpp
│   │   │   ├── auth_manager.h/cpp
│   │   │   └── api_models.h
│   │   ├── db/
│   │   │   ├── database.h/cpp
│   │   │   ├── models.h
│   │   │   └── migrations.h/cpp
│   │   ├── fs/
│   │   │   ├── file_watcher_win.cpp
│   │   │   ├── file_watcher_mac.cpp
│   │   │   ├── file_watcher_linux.cpp
│   │   │   └── file_utils.h/cpp
│   │   ├── ipc/
│   │   │   └── ipc_server.h/cpp
│   │   └── utils/
│   │       ├── logger.h/cpp
│   │       ├── config.h/cpp
│   │       └── crypto.h/cpp
│   ├── tests/
│   │   ├── sync_engine_test.cpp
│   │   ├── http_client_test.cpp
│   │   └── conflict_resolver_test.cpp
│   └── third_party/          # Git Submodules
│       ├── curl/
│       ├── sqlite3/
│       ├── json/
│       └── spdlog/
│
├── frontend/                 # Electron + React UI
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── forge.config.js
│   ├── src/
│   │   ├── main/             # Electron Main Process
│   │   │   ├── index.ts
│   │   │   ├── ipc-bridge.ts
│   │   │   ├── tray.ts
│   │   │   ├── backend-manager.ts
│   │   │   └── auto-updater.ts
│   │   ├── renderer/         # React UI
│   │   │   ├── index.html
│   │   │   ├── main.tsx
│   │   │   ├── App.tsx
│   │   │   ├── components/
│   │   │   │   ├── Dashboard.tsx
│   │   │   │   ├── FolderList.tsx
│   │   │   │   ├── AddFolderDialog.tsx
│   │   │   │   ├── Settings.tsx
│   │   │   │   └── ActivityLog.tsx
│   │   │   ├── hooks/
│   │   │   │   ├── useSyncState.ts
│   │   │   │   └── useIPC.ts
│   │   │   └── store/
│   │   │       └── syncStore.ts
│   │   └── preload/
│   │       └── index.ts      # Electron Preload Script
│   └── assets/
│       ├── icons/
│       └── images/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── BUILD.md
│   └── CONTRIBUTING.md
│
└── scripts/
    ├── build.sh
    ├── package-win.sh
    ├── package-mac.sh
    └── package-linux.sh
```

---

## 🚀 Entwicklungsphasen

### Sprint 1 (2 Wochen): C++ Core Setup
- CMake Build-System
- libcurl HTTP Client Wrapper
- SQLite Database Layer
- Basic Sync Logic (One-Way: Local → Remote)
- Unit Tests

### Sprint 2 (2 Wochen): Filesystem Watcher
- Cross-Platform Filesystem Watcher
- Event Debouncing
- Change Detection
- Integration mit Sync Engine

### Sprint 3 (2 Wochen): Bidirektionale Sync
- Remote Change Detection
- Two-Way Sync Logic
- Conflict Detection
- Basic Conflict Resolution

### Sprint 4 (2 Wochen): Electron Frontend
- Electron + React Setup
- IPC Bridge zu C++ Backend
- Login Screen
- Dashboard UI

### Sprint 5 (2 Wochen): Folder Management
- Add/Remove Sync Folders
- Folder Status Display
- Pause/Resume Sync
- Settings Screen

### Sprint 6 (2 Wochen): Polish & Packaging
- System Tray Integration
- Activity Log
- Error Handling & User Notifications
- Packaging für Windows/macOS/Linux

---

## 🔒 Security Best Practices

1. **Token Storage**
   - Windows: Windows Credential Manager
   - macOS: Keychain
   - Linux: libsecret (GNOME Keyring)

2. **Secure Communication**
   - HTTPS Only (TLS 1.2+)
   - Certificate Validation
   - Optional: SSL Pinning

3. **Secure IPC**
   - JSON Messages mit Schema Validation
   - No Direct Filesystem Access von Renderer
   - Sandboxed Renderer Process

4. **Code Signing**
   - Windows: Authenticode Signature
   - macOS: Apple Developer Certificate
   - Linux: GPG Signature

---

## 📊 API Kommunikation

### IPC Messages (Frontend ↔ Backend)

```typescript
// Frontend → C++ Backend
interface IPC_AddSyncFolder {
  type: "add_sync_folder";
  payload: {
    localPath: string;
    remotePath: string;
  };
}

interface IPC_GetSyncState {
  type: "get_sync_state";
}

interface IPC_PauseSync {
  type: "pause_sync";
  payload: { folderId: string };
}

// C++ Backend → Frontend
interface IPC_SyncStateUpdate {
  type: "sync_state_update";
  payload: {
    status: "idle" | "syncing" | "paused" | "error";
    uploadSpeed: number; // bytes/sec
    downloadSpeed: number;
    lastSync: string; // ISO timestamp
  };
}

interface IPC_FileChange {
  type: "file_change";
  payload: {
    path: string;
    action: "added" | "modified" | "deleted";
    size: number;
  };
}

interface IPC_Conflict {
  type: "conflict_detected";
  payload: {
    path: string;
    localModified: string;
    remoteModified: string;
  };
}
```

### REST API Endpoints (Backend ↔ NAS)

```
GET    /api/files/list?path={path}
POST   /api/files/upload
GET    /api/files/download/{path}
DELETE /api/files/{path}
GET    /api/sync/changes?since={timestamp}
POST   /api/sync/resolve-conflict
```

---

## 🧪 Testing Strategie

### C++ Backend
- **Unit Tests**: Google Test für alle Core-Komponenten
- **Integration Tests**: Mock HTTP Server für API Tests
- **Performance Tests**: Benchmark für Sync-Engine

### Electron Frontend
- **Unit Tests**: Vitest für React Components
- **E2E Tests**: Playwright für User Flows
- **IPC Tests**: Mock Backend für Renderer Tests

---

## 📦 Distribution

### Windows
- **Installer**: MSI via WiX Toolset
- **Auto-Update**: Squirrel.Windows oder electron-updater
- **Signature**: Authenticode Certificate

### macOS
- **Package**: DMG mit App Bundle
- **Auto-Update**: Sparkle oder electron-updater
- **Signature**: Apple Developer Certificate + Notarization

### Linux
- **Formats**: AppImage (universal), .deb (Debian/Ubuntu), .rpm (Fedora/RHEL)
- **Auto-Update**: AppImageUpdate oder Manual Download
- **Repository**: Optional: PPA (Ubuntu), AUR (Arch)

---

## 🎨 UI/UX Konzept

### Design Principles
1. **Minimalistisch**: Clean, moderne Oberfläche
2. **Intuitiv**: Selbsterklärende Icons und Labels
3. **Performance**: Smooth Animations, keine Lags
4. **Native Feel**: OS-spezifische UI-Patterns

### System Tray States
- 🟢 Grün: Sync erfolgreich, alles aktuell
- 🔵 Blau: Synchronisierung läuft
- 🟡 Gelb: Konflikt erkannt
- 🔴 Rot: Fehler (Netzwerk, Auth, etc.)
- ⚪ Grau: Pausiert

---

## 🐛 Bekannte Herausforderungen

1. **Cross-Platform Filesystem Watcher**
   - Lösung: Abstraction Layer + Platform-Specific Implementations

2. **Large File Handling**
   - Lösung: Chunked Upload mit Resume-Capability

3. **Conflict Resolution**
   - Lösung: Last-Write-Wins + Manual Resolution UI

4. **Performance bei vielen Dateien**
   - Lösung: Batch-Operations, Database Indexing

5. **Electron App Size**
   - Lösung: ASAR Packaging, Tree-Shaking, Native Modules

---

## 📚 Referenzen & Inspiration

- **Dropbox**: Selective Sync, System Tray UI
- **Google Drive**: Conflict Resolution
- **OneDrive**: Bandwidth Throttling
- **Syncthing**: Conflict Handling, Open Source
- **Resilio Sync**: P2P Architecture (Inspiration für Future)

---

## ✅ Definition of Done

**MVP (Minimum Viable Product)**
- [x] User kann sich einloggen
- [x] User kann Sync-Ordner hinzufügen/entfernen
- [x] Bidirektionale Synchronisation funktioniert
- [x] System Tray zeigt Sync-Status
- [x] Basic Conflict Resolution (Keep Both)
- [x] Installer für Windows/macOS/Linux

**v1.0 Release Criteria**
- [x] Alle MVP Features stabil
- [x] Unit Test Coverage >80%
- [x] E2E Tests für Critical Paths
- [x] Dokumentation vollständig
- [x] Performance Tests bestanden
- [x] Security Audit abgeschlossen
- [x] Beta Testing mit 50+ Users

---

**Letzte Aktualisierung**: 2. Januar 2026  
**Status**: 🔴 Planning Phase  
**Next Milestone**: Sprint 1 Start
