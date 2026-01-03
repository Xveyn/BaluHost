# BaluDesk Frontend Setup

Schnellstart-Anleitung für das Electron Frontend.

## 🚀 Installation

```powershell
# Im Frontend-Verzeichnis
cd frontend

# Dependencies installieren
npm install
```

## ⚙️ Development

### Dev Server starten
```powershell
npm run dev
```

Dies startet:
1. **Vite Dev Server** auf `http://localhost:5173`
2. **Electron App** mit Hot Reload

### Manuelle Schritte (falls npm run dev nicht funktioniert)

**Terminal 1 - Vite:**
```powershell
npm run dev:vite
```

**Terminal 2 - Electron:**
```powershell
npm run dev:electron
```

## 🏗️ Build

### Development Build (mit DevTools)
```powershell
npm run build:dir
```
Output: `dist-electron/win-unpacked/BaluDesk.exe`

### Production Build (Installer)
```powershell
npm run build
```
Output: `dist-electron/BaluDesk Setup 1.0.0.exe`

## 🧪 Testing

### Frontend testen (ohne Backend)
```powershell
npm run dev:vite
```
Dann Browser öffnen: `http://localhost:5173`

### Mit C++ Backend testen

**Voraussetzung:** Backend muss gebaut sein!

```powershell
# 1. Backend bauen (falls noch nicht geschehen)
cd ../backend/build
cmake --build . --config Release

# 2. Zurück zu Frontend
cd ../../frontend

# 3. App starten
npm run dev
```

Die App spawnt automatisch `backend/build/Release/baludesk-backend.exe`.

## 📋 Checklists

### Erstmaliges Setup
- [ ] Node.js 20+ installiert
- [ ] `npm install` ausgeführt
- [ ] Backend erfolgreich gebaut
- [ ] `npm run dev` funktioniert

### Vor jedem Build
- [ ] Backend auf neuestem Stand
- [ ] `npm run lint` keine Fehler
- [ ] Login funktioniert
- [ ] Dashboard lädt

## 🐛 Troubleshooting

### "Cannot find module 'electron'"
```powershell
npm install
```

### "Backend not found"
Backend-Path prüfen in `src/main/main.ts`:
```typescript
const backendPath = path.join(
  app.getAppPath(),
  '..',
  'backend',
  'build',
  'Release',
  'baludesk-backend.exe'
);
```

### Vite Dev Server startet nicht
Port 5173 belegt? Ändern in `vite.config.ts`:
```typescript
server: {
  port: 5174, // Anderen Port
}
```

### Electron startet nicht
DevTools Console checken:
- `Ctrl+Shift+I` in Electron
- Prüfe "Console" Tab für Errors

## 📦 Verzeichnisstruktur nach Build

```
dist-electron/
├── win-unpacked/           # Unpacked App (schnell zu testen)
│   ├── BaluDesk.exe
│   ├── resources/
│   │   └── app.asar       # Gebundelte App
│   └── ...
└── BaluDesk Setup 1.0.0.exe  # Installer
```

## 🔄 Hot Reload

Änderungen werden automatisch neu geladen:
- **React Components:** Instant Reload (HMR)
- **Main Process:** Erfordert Electron-Neustart
- **Preload Script:** Erfordert Electron-Neustart

Tipp: Nach Änderungen in `main.ts` oder `preload.ts`:
1. Electron schließen
2. `npm run dev:electron` neu starten

## 💡 Tipps

### Schnelleres Development
```powershell
# Nur Frontend testen (ohne Electron)
npm run dev:vite
```

### Backend-Logs anzeigen
Im Electron Main Process Console:
```
[Backend]: Log message here
```

### React DevTools verwenden
In Electron DevTools Console:
```javascript
__REACT_DEVTOOLS_GLOBAL_HOOK__
```

---

**Nächste Schritte:**
1. `npm install`
2. `npm run dev`
3. Login mit `admin` / `changeme`
4. Dashboard erkunden 🚀
