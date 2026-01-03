# BaluDesk - Desktop Sync Client

**Electron + React Frontend** für das BaluDesk NAS Sync System.

## ✨ Features

- 🔐 **Secure Login** - JWT Authentication via C++ Backend
- 📁 **Folder Sync** - Bidirektionale Synchronisation
- 🔄 **Live Status** - Echtzeit-Updates über IPC
- 🎨 **Modern UI** - BaluHost-Style mit Tailwind CSS
- 🖥️ **System Tray** - Minimize to Tray
- ⚡ **Fast** - C++ Backend für Performance

## 🏗️ Architektur

```
┌─────────────────────────────────────────┐
│     Electron Frontend (TypeScript)      │
│  ┌────────────────────────────────────┐ │
│  │   React UI (Login, Dashboard)      │ │
│  │   - Tailwind CSS Styling           │ │
│  │   - React Router Navigation        │ │
│  └──────────────┬─────────────────────┘ │
│                 │ IPC Bridge            │
│  ┌──────────────▼─────────────────────┐ │
│  │   Electron Main Process            │ │
│  │   - Spawn C++ Backend              │ │
│  │   - System Tray                    │ │
│  │   - Window Management              │ │
│  └──────────────┬─────────────────────┘ │
└─────────────────┼───────────────────────┘
                  │ stdin/stdout JSON
┌─────────────────▼─────────────────────────┐
│     C++ Backend (baludesk-backend.exe)    │
│  - File Watcher (inotify/FSEvents)        │
│  - HTTP Client (libcurl)                  │
│  - SQLite Database                        │
│  - Conflict Resolution                    │
└───────────────────────────────────────────┘
```

## 🚀 Quick Start

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Start development server
npm run dev

# 3. Build production
npm run build
```

## 📋 Development

### Start Dev Server
```bash
npm run dev
```
Startet Vite Dev Server (Port 5173) und Electron mit Hot Reload.

### Build Application
```bash
npm run build        # Build for all platforms
npm run build:dir    # Build without installer (faster)
```

### Lint Code
```bash
npm run lint
```

## 🎨 Style Guide

### Colors
- **Primary:** Sky Blue (`#3b82f6`)
- **Background:** Dark Slate (`#0f172a`, `#1e293b`)
- **Text:** Slate (`#f1f5f9`, `#cbd5e1`, `#64748b`)

### Components
- **Card:** `card` class - Rounded mit border + backdrop-blur
- **Button:** `btn` + `btn-primary`/`btn-secondary`
- **Input:** `input` - Focus ring mit sky-500

### Layout
- **Spacing:** 4px-Grid (Tailwind spacing scale)
- **Border Radius:** `rounded-xl` (0.75rem)
- **Shadows:** Subtle `shadow-lg` für depth

## 📡 IPC Protocol

### Commands (Frontend → Backend)

#### Login
```typescript
{
  type: 'login',
  data: {
    username: string,
    password: string,
    serverUrl: string
  }
}
```

#### Get Sync State
```typescript
{
  type: 'get_sync_state'
}
```

#### Add Sync Folder
```typescript
{
  type: 'add_sync_folder',
  data: {
    localPath: string,
    remotePath: string
  }
}
```

### Messages (Backend → Frontend)

#### Sync Stats Update
```typescript
{
  type: 'sync_stats',
  data: {
    status: 'idle' | 'syncing' | 'paused' | 'error',
    uploadSpeed: number,
    downloadSpeed: number,
    pendingUploads: number,
    pendingDownloads: number,
    lastSync: string
  }
}
```

#### File Event
```typescript
{
  type: 'file_event',
  data: {
    type: 'created' | 'modified' | 'deleted',
    path: string,
    timestamp: number
  }
}
```

## 🔧 Configuration

### Electron Builder
Konfiguration in `package.json` unter `build`:
- **AppId:** `com.baluhost.baludesk`
- **Targets:** Windows (NSIS, Portable), macOS (DMG), Linux (AppImage, deb)

### Vite
Konfiguration in `vite.config.ts`:
- **Port:** 5173
- **Base:** `./` (relative paths für Electron)
- **Aliases:** `@`, `@renderer`, `@main`

## 📦 Dependencies

### Runtime
- `electron` - Desktop Framework
- `react` + `react-dom` - UI Library
- `react-router-dom` - Navigation
- `lucide-react` - Icons
- `react-hot-toast` - Notifications

### Build Tools
- `vite` - Build Tool & Dev Server
- `typescript` - Type Safety
- `tailwindcss` - CSS Framework
- `electron-builder` - Packaging

## 🐛 Debugging

### Chrome DevTools
Öffnet automatisch im Dev Mode (`Ctrl+Shift+I`)

### Backend Logs
```bash
# Main Process Console zeigt Backend stdout/stderr
[Backend]: Sync started for folder: /path/to/folder
```

### IPC Messages
```typescript
// In Renderer
window.electronAPI.onBackendMessage((msg) => {
  console.log('Backend:', msg);
});
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── main/
│   │   ├── main.ts          # Electron Main Process
│   │   └── preload.ts       # IPC Bridge
│   └── renderer/
│       ├── pages/
│       │   ├── Login.tsx    # Login Screen
│       │   └── Dashboard.tsx # Main Dashboard
│       ├── components/      # Reusable Components
│       ├── App.tsx          # Router & Auth
│       ├── main.tsx         # Entry Point
│       ├── index.css        # Tailwind Imports
│       └── types.ts         # TypeScript Types
├── public/
│   └── baluhost-logo.svg    # App Icon
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 🔐 Security

- **Context Isolation:** Enabled (Preload Script)
- **Node Integration:** Disabled in Renderer
- **Content Security Policy:** Default Electron CSP
- **HTTPS Only:** Backend connections über TLS

## 📝 TODO

- [ ] Folder Selection Dialog (Native File Picker)
- [ ] Settings Page (Preferences, Auto-Start)
- [ ] Conflict Resolution UI
- [ ] File Browser (Local + Remote)
- [ ] Bandwidth Limiting UI
- [ ] Notification System
- [ ] Auto-Update Implementation
- [ ] macOS/Linux Testing

## 🤝 Integration mit Backend

Das Frontend kommuniziert mit dem C++ Backend via:
1. **Electron Main Process** spawnt `baludesk-backend.exe`
2. **stdin** - JSON Commands vom Frontend
3. **stdout** - JSON Responses/Events vom Backend
4. **stderr** - Error Logs

Siehe [Backend README](../backend/README.md) für IPC Protocol Details.

---

**Built with ❤️ for BaluHost NAS System**
