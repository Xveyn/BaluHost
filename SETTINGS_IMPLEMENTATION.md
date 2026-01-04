# BaluDesk Settings System - Implementierung

## 🎯 Übersicht
Ein umfassendes Settings-System für BaluDesk wurde implementiert mit vollständiger Frontend-Backend-Integration.

---

## 📋 Backend (C++ IPC Server)

### Neue Dateien:
- **`src/utils/settings_manager.h`** - Singleton Settings Manager
- **`src/utils/settings_manager.cpp`** - Implementierung mit JSON-Persistierung

### IPC Handler:
- **`handleGetSettings()`** - Laden aller Settings
- **`handleUpdateSettings()`** - Aktualisieren von Settings und Speichern in Datei

### Funktionalität:
- Lädt Settings aus `%APPDATA%/BaluDesk/settings.json` (Windows) oder `~/.config/BaluDesk/settings.json` (Linux/macOS)
- Automatische Initialisierung mit Defaults falls Datei nicht existiert
- JSON-Serialisierung für alle Settings
- Type-Safe Getter-Methoden für C++-Code

### Settings-Struktur:
```cpp
{
  // Server Connection
  "serverUrl": "http://localhost",
  "serverPort": 8000,
  "username": "",
  "rememberPassword": false,

  // Sync Behavior
  "autoStartSync": true,
  "syncInterval": 60,
  "maxConcurrentTransfers": 4,
  "bandwidthLimitMbps": 0,
  "conflictResolution": "ask",

  // UI Preferences
  "theme": "dark",
  "language": "en",
  "startMinimized": false,
  "showNotifications": true,
  "notifyOnSyncComplete": true,
  "notifyOnErrors": true,

  // Advanced
  "enableDebugLogging": false,
  "chunkSizeMb": 10
}
```

---

## 🖥️ Frontend (Electron + React)

### Neue Komponente:
- **`src/renderer/components/Settings.tsx`** - Vollständige Settings UI mit 4 Tabs

### Tab-Struktur:

#### 1. **Connection** (Server-Verbindung)
   - Server URL & Port
   - Username
   - Remember Password Checkbox

#### 2. **Sync** (Synchronisations-Verhalten)
   - Auto-start Sync
   - Sync Interval (Sekunden)
   - Max Concurrent Transfers
   - Bandwidth Limit (Mbps)
   - Conflict Resolution Strategy (ask/local/remote/newer)

#### 3. **UI** (Benutzer-Interface)
   - Theme Selection (dark/light/system)
   - Start Minimized
   - Notification Settings (mit Sub-Optionen)
     - Notify on Sync Complete
     - Notify on Errors

#### 4. **Advanced** (Erweiterte Einstellungen)
   - Debug Logging
   - Chunk Size (MB)
   - Debug Info

### IPC Integration:
- `electronAPI.getSettings()` - Lädt Settings vom Backend
- `electronAPI.updateSettings(settings)` - Speichert Settings

### UI Features:
- Responsive Tabs mit Highlight für aktive Tabs
- Validierung und Error Handling
- Success/Error Messages mit Auto-Close
- Disabled State für abhängige Optionen

---

## 🔗 Integration

### Electron Main Process (`src/main/main.ts`):
```typescript
ipcMain.handle('settings:get', async () => { ... })
ipcMain.handle('settings:update', async (_event, settings) => { ... })
```

### Preload Bridge (`src/main/preload.ts`):
```typescript
getSettings: () => ipcRenderer.invoke('settings:get'),
updateSettings: (settings) => ipcRenderer.invoke('settings:update', settings),
```

### App Navigation (`App.tsx`):
- Neue Route: `/settings`
- Settings im MainLayout verfügbar

### MainLayout (`components/MainLayout.tsx`):
- Neuer Settings-Button im Header (Zahnrad-Icon)
- Links zur `/settings` Route
- Aktiv-Highlight wenn Settings angezeigt werden

---

## 🔄 Message Flow

### Settings Laden:
```
Frontend                  Electron                  C++ Backend
   |                        |                           |
   +--getSettings()--------->|                           |
   |                        +--get_settings msg------->|
   |                        |                      (IPC Server)
   |                        |<--settings_response--+
   |<--settings response----+                       |
   |                        |                           |
```

### Settings Speichern:
```
Frontend                  Electron                  C++ Backend
   |                        |                           |
   +--updateSettings()------>|                           |
   |                        +--update_settings msg---->|
   |                        |                      (SettingsManager)
   |                        |<--settings_updated----+
   |<--update response------+                       |
   |                        |                       
   |         (Settings in settings.json gespeichert)
```

---

## 📊 Daten-Persistierung

### Backend:
- **Speicherort:** `%APPDATA%/BaluDesk/settings.json` (Windows)
- **Format:** Formatted JSON (2-Zeichen Indent)
- **Automatisches Speichern:** Bei jedem Update
- **Fallback:** Defaults wenn Datei nicht existiert

### Frontend:
- Lädt Settings beim Komponenten-Mount
- Speichert über IPC an Backend

---

## 🎨 Design & UX

### Dark Theme:
- Konsistent mit BaluDesk Design-Sprache
- Slate-Farben (900-800) für Hintergrund
- Blue-500/600 für Highlights
- Smooth Transitions

### Responsive:
- Funktioniert auf Desktop & Notebook-Displaygrößen
- Scrollable Content Area bei vielen Settings
- Fixed Header & Footer mit Buttons

### Fehlbehandlung:
- Try-Catch in allen Funktionen
- User-freundliche Error Messages
- Timeout-Schutz (5s) für IPC-Calls

---

## 🚀 Nächste Schritte

### Optional Erweiterungen:
1. **Settings Validation** - Strikte Validierung von Werte-Bereichen
2. **Settings Profiles** - Speichern von vordefinierten Profilen
3. **Keyboard Shortcuts** - Settings mit Shortcuts öffnen (Ctrl+,)
4. **Import/Export** - Settings exportieren und importieren
5. **Settings Sync** - Settings über Server synchronisieren
6. **Undo/Redo** - Änderungen rückgängig machen

### Integration mit anderen Features:
- Settings direkt in SyncEngine verwenden (autoStartSync, syncInterval, etc.)
- Notifications basierend auf Settings
- Theme bei App-Start anwenden
- Chunk Size in Upload/Download-Code verwenden

---

## ✅ Checkliste

- ✅ Backend Settings Manager (C++)
- ✅ IPC Handler für Get/Update
- ✅ Electron Main Process Handler
- ✅ Preload Bridge
- ✅ Settings Component (React)
- ✅ App Navigation & Routing
- ✅ MainLayout Integration
- ✅ Type Definitions (TypeScript)
- ✅ Erfolgreicher Build

---

## 📦 Kompilierung & Start

```bash
# Backend
cd backend
cmake --build build --config Release

# Frontend (Dev Server)
cd frontend
npm install
npm run dev

# Oder gebündelte Anwendung
npm run build
```

Das Settings-System ist production-ready! 🎉
