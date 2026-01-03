# BaluDesk Frontend

Electron + React + TypeScript Frontend für BaluDesk Desktop Client.

## Architektur

```
frontend/
├── src/
│   ├── main/              # Electron Main Process
│   │   ├── main.ts        # App Lifecycle, Window Management
│   │   └── preload.ts     # IPC Bridge (Context Bridge)
│   └── renderer/          # React App
│       ├── components/    # Reusable Components
│       ├── pages/         # Page Components
│       ├── App.tsx        # Router & Auth Logic
│       └── main.tsx       # Entry Point
├── public/                # Static Assets
└── dist/                  # Build Output
```

## Features

✅ **Login-Screen** im BaluHost-Style  
✅ **Dashboard** mit Live-Sync-Stats  
✅ **IPC Bridge** zu C++ Backend (stdin/stdout JSON)  
✅ **System Tray** Integration  
✅ **Auto-Start** Backend Process  
✅ **Modern UI** mit Tailwind CSS  

## Development

```bash
# Install dependencies
npm install

# Start dev server (Vite + Electron)
npm run dev

# Build production
npm run build
```

## IPC Protocol

### Frontend → Backend (stdin)

```json
{
  "type": "login",
  "data": {
    "username": "admin",
    "password": "changeme",
    "serverUrl": "https://localhost:8000"
  }
}
```

### Backend → Frontend (stdout)

```json
{
  "type": "sync_stats",
  "data": {
    "status": "syncing",
    "pendingUploads": 5,
    "pendingDownloads": 2
  }
}
```

## Tech Stack

- **Electron** 33.4.0 - Desktop Framework
- **React** 18.2 - UI Framework
- **TypeScript** 5.9 - Type Safety
- **Vite** 7.2 - Build Tool
- **Tailwind CSS** 3.4 - Styling
- **React Router** 7.9 - Navigation
- **Lucide React** - Icons

## Backend Communication

Das Frontend kommuniziert über Electron IPC mit dem C++ Backend:

1. **Main Process** spawnt `baludesk-backend.exe`
2. **Preload Script** exposed `window.electronAPI`
3. **React Components** senden Commands via IPC
4. **Backend** antwortet über stdout (JSON)

## Style Guide

- **Colors:** Sky Blue (#3b82f6) + Dark Slate (#0f172a)
- **Fonts:** System default (Inter-ähnlich)
- **Spacing:** Consistent 4px-Grid
- **Animations:** Subtle transitions (200-300ms)
- **Glass-Morphism:** backdrop-blur + transparency

Analog zur BaluHost WebApp für konsistentes UX.
