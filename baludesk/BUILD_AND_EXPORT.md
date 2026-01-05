# BaluDesk - Build & Export für Multiple Platforms

**Status**: Ready to Export  
**Datum**: 2025-01-05

---

## 🎯 Ziele

Exportiere BaluDesk als:
- ✅ **Windows**: `.exe` (NSIS Installer + Portable)
- ✅ **Linux**: `AppImage` + `.deb` package
- ✅ **macOS**: `.dmg` (optional)

---

## 📋 Voraussetzungen

### ✅ Windows Build
```bash
# Bereits erfüllt:
✓ Visual Studio 2022 (C++ Backend Compiler)
✓ Node.js 18+ (npm)
✓ electron-builder
✓ C++ Backend kompiliert (Release)
✓ React Frontend vorbereitet
```

### ✅ Linux Build (auf Windows möglich)
```bash
# Für Linux-Builds von Windows aus:
# Brauchen WSL2 oder Docker (optional)
# Oder später auf Linux-Machine bauen
```

---

## 🔨 Build-Prozess

### **Step 1: Vorbereitung** (Frontend Dependencies)

```bash
cd baludesk/frontend

# Install dependencies
npm install

# Falls nicht bereits geschehen
npm install --save-dev electron-builder
```

### **Step 2: C++ Backend kompilieren** (Release)

```bash
cd baludesk/backend

# CMake konfigurieren (falls nicht schon geschehen)
cmake -S . -B build -G "Visual Studio 17 2022" -A x64

# Release bauen
cmake --build build --config Release

# Überprüfen, ob .exe vorhanden ist:
ls build/Release/baludesk-backend.exe
```

**Wichtig:** `electron-builder` sucht Backend unter:
```
../backend/build/Release/baludesk-backend.exe
../backend/build/Release/*.dll
```

### **Step 3: TypeScript kompilieren** (Electron Main)

```bash
cd baludesk/frontend

# TypeScript für Electron Main Process
npm run compile
```

### **Step 4: Vite Frontend bauen**

```bash
cd baludesk/frontend

# React Vite Build
vite build
# Output: dist/

# Überprüfen:
ls dist/
```

### **Step 5: Electron-Builder ausführen**

```bash
cd baludesk/frontend

# Für ALLE Plattformen (Windows/Linux/macOS):
npm run build

# ODER nur für spezifische Plattform:

# Nur Windows:
npm run build -- --win

# Nur Linux:
npm run build -- --linux

# Nur macOS (nur auf macOS möglich):
npm run build -- --mac
```

---

## 📦 Output-Verzeichnisse

Nach `npm run build`, findest du die Executables hier:

```
baludesk/frontend/dist-electron/

Windows:
├─ BaluDesk-1.0.0.exe              (Standalone Portable)
├─ BaluDesk Setup 1.0.0.exe        (NSIS Installer)
└─ BaluDesk-1.0.0-x64-nsis.exe     (Alternative Installer)

Linux:
├─ BaluDesk-1.0.0.AppImage         (Portable AppImage)
└─ baludesk-1.0.0-x86_64.AppImage  (Alternative)
└─ baludesk_1.0.0_amd64.deb        (Debian Package)

macOS:
├─ BaluDesk-1.0.0.dmg              (DMG Installer)
└─ BaluDesk-1.0.0.zip              (Portable ZIP)
```

---

## 🎯 Empfohlene Export-Varianten

### **Windows Benutzer** (Einfachste Installation)
```
→ BaluDesk Setup 1.0.0.exe (NSIS Installer)
  
  Vorteile:
  ✓ Einfache Installation (nächster Button)
  ✓ Start Menu Integration
  ✓ Automatische Updates vorbereitet
  ✓ Einfaches Deinstallieren
```

### **Windows Power-User** (Portable)
```
→ BaluDesk-1.0.0.exe (Portable)

  Vorteile:
  ✓ Keine Installation nötig
  ✓ USB-Stick kompatibel
  ✓ Weniger Speicher
  ✓ Sofort einsatzbereit
```

### **Linux Benutzer**

**Option 1: AppImage (Einfachste)**
```
→ BaluDesk-1.0.0.AppImage

  Vorteile:
  ✓ Distro-unabhängig
  ✓ Keine Installation nötig
  ✓ chmod +x && ./BaluDesk-1.0.0.AppImage
  ✓ Überall funktioniert
```

**Option 2: Debian/Ubuntu**
```
→ baludesk_1.0.0_amd64.deb

  Installation:
  sudo apt install ./baludesk_1.0.0_amd64.deb
  
  Vorteile:
  ✓ Native Integration
  ✓ Automatische Updates über apt
  ✓ Abhängigkeiten automatic resolving
```

---

## 📝 Schritt-für-Schritt Build (Powershell)

```powershell
# 1. Zum Frontend wechseln
cd f:\Programme (x86)\Baluhost\baludesk\frontend

# 2. Dependencies installieren (einmalig)
npm install

# 3. TypeScript kompilieren
npm run compile

# 4. Vite Frontend bauen
npm run build

# 5. Electron-Builder ausführen
npm run build

# 6. Output überprüfen
ls dist-electron/
```

---

## 🔍 Überprüfung & Debugging

### Wenn Build fehlschlägt:

**Problem: Backend .exe nicht gefunden**
```
Error: File not found: ../backend/build/Release/baludesk-backend.exe

Lösung:
1. Überprüfe, ob C++ Backend kompiliert wurde
2. cd baludesk\backend
3. cmake --build build --config Release
```

**Problem: Vite Build Error**
```
Lösung:
1. npm install
2. npm run compile
3. npm run build
```

**Problem: TypeScript Errors**
```
Lösung:
1. npm run compile
2. Überprüfe tsconfig.main.json
3. Überprüfe Frontend-Typen in src/
```

### Build-Logs prüfen:
```
cd baludesk/frontend
npm run build -- --verbose
```

---

## 📊 Build Konfiguration Übersicht

### **Windows (NSIS + Portable)**
```javascript
"win": {
  "target": ["nsis", "portable"],
  "icon": "public/icon.ico"
}
```

- **NSIS**: Professioneller Windows Installer
- **Portable**: Standalone .exe ohne Installation

### **Linux (AppImage + DEB)**
```javascript
"linux": {
  "target": ["AppImage", "deb"],
  "category": "Utility"
}
```

- **AppImage**: Universal Linux portable app
- **DEB**: Debian/Ubuntu package

### **Included Resources**
```javascript
"extraResources": [
  {
    "from": "../backend/build/Release/",
    "to": "backend",
    "filter": ["*.exe", "*.dll"]
  }
]
```

Backend wird automatisch mitgepackt! ✅

---

## 🚀 Schnellstart

```bash
# Alles in einem Befehl (Windows):
cd f:\Programme (x86)\Baluhost\baludesk\frontend && npm install && npm run compile && npm run build

# Output:
# → dist-electron/BaluDesk Setup 1.0.0.exe (Windows Installer)
# → dist-electron/BaluDesk-1.0.0.AppImage (Linux)
# → dist-electron/baludesk_1.0.0_amd64.deb (Debian)
```

---

## ✅ Finale Checklist vor Export

- [ ] C++ Backend kompiliert (Release)
- [ ] `baludesk-backend.exe` existiert
- [ ] `npm install` erfolgreich
- [ ] `npm run compile` erfolgreich
- [ ] `npm run build` (Vite) erfolgreich
- [ ] Icon vorhanden (`public/icon.ico`)
- [ ] Version in package.json korrekt
- [ ] CHANGELOG aktualisiert

---

## 📂 Verteilung

Nach erfolgreichem Build:

```
dist-electron/ enthält:
├─ Executables (direkt nutzbar)
├─ Installer (für Installation)
└─ Packages (für Paketmanager)
```

Diese können dann:
1. ✅ Hochgeladen auf GitHub Releases
2. ✅ Zu Website hinzugefügt
3. ✅ An Benutzer verteilt
4. ✅ In Paketmanagern eingetragen

---

**Status**: ✅ Ready to Build & Export

