# BaluDesk Backend - Quick Start Guide

## 🚀 Schnellstart

### Voraussetzungen

**Windows:**
```powershell
# vcpkg installieren (falls noch nicht vorhanden)
git clone https://github.com/Microsoft/vcpkg.git
cd vcpkg
.\\bootstrap-vcpkg.bat

# Dependencies installieren
.\\vcpkg install curl:x64-windows sqlite3:x64-windows
```

**macOS:**
```bash
# Homebrew Dependencies
brew install cmake curl sqlite3
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install build-essential cmake git
sudo apt install libcurl4-openssl-dev libsqlite3-dev
```

---

## 📦 Build

```bash
cd baludesk/backend
mkdir build && cd build
cmake ..
make -j$(nproc)
```

**Hinweis:** Bei Problemen mit nlohmann/json oder spdlog werden diese automatisch von CMake heruntergeladen (FetchContent).

---

## ⚙️ Konfiguration

1. **Config-Datei erstellen:**
```bash
cp config.json.example config.json
```

2. **config.json bearbeiten:**
```json
{
  "server_url": "http://localhost:8000",
  "database_path": "baludesk.db",
  "log_file": "baludesk.log",
  "sync_interval": 30,
  "timeout": 30
}
```

**Wichtig:** `server_url` muss auf deine BaluHost NAS Instanz zeigen!

---

## 🏃 Starten

```bash
# Normal Mode
./baludesk-backend

# Verbose Mode (mehr Logs)
./baludesk-backend --verbose

# Custom Config
./baludesk-backend --config /path/to/config.json

# Hilfe anzeigen
./baludesk-backend --help
```

---

## 🧪 Testen

### 1. Backend Test (manuell)

**Terminal 1 - Backend starten:**
```bash
./baludesk-backend --verbose
```

**Terminal 2 - IPC Commands senden:**
```bash
# Ping Test
echo '{"type":"ping"}' | ./baludesk-backend

# Login (erfordert laufendes Backend)
echo '{"type":"login","payload":{"username":"admin","password":"admin"}}' | ./baludesk-backend

# Sync Folder hinzufügen
echo '{"type":"add_sync_folder","payload":{"local_path":"/tmp/test","remote_path":"/remote"}}' | ./baludesk-backend

# Status abfragen
echo '{"type":"get_sync_state"}' | ./baludesk-backend
```

### 2. Mit BaluHost Backend verbinden

**Voraussetzung:** BaluHost NAS Backend läuft auf `http://localhost:8000`

1. Backend starten:
   ```bash
   cd ../../backend  # BaluHost Backend
   python -m uvicorn app.main:app --reload
   ```

2. BaluDesk Backend starten:
   ```bash
   cd baludesk/backend/build
   ./baludesk-backend --verbose
   ```

3. Login testen (via IPC):
   ```json
   {
     "type": "login",
     "payload": {
       "username": "admin",
       "password": "admin123"
     }
   }
   ```

---

## 📁 Projektstruktur

```
backend/
├── build/                    # Build-Artefakte (generiert)
│   └── baludesk-backend     # Executable
├── src/
│   ├── main.cpp             # Entry Point
│   ├── stubs.cpp            # Noch nicht implementierte Komponenten
│   ├── api/
│   │   ├── http_client.h    # REST API Client
│   │   └── http_client.cpp
│   ├── db/
│   │   ├── database.h       # SQLite Wrapper
│   │   └── database.cpp
│   ├── ipc/
│   │   ├── ipc_server.h     # IPC für Electron
│   │   └── ipc_server.cpp
│   ├── sync/
│   │   ├── sync_engine.h    # Core Sync Logic
│   │   ├── sync_engine.cpp
│   │   ├── file_watcher.h   # (TODO: Sprint 2)
│   │   └── ...
│   └── utils/
│       ├── logger.h         # spdlog Wrapper
│       ├── logger.cpp
│       ├── config.h         # Config Parser
│       └── config.cpp
├── CMakeLists.txt           # Build Config
├── config.json.example      # Beispiel-Config
└── baludesk.db              # SQLite DB (generiert)
```

---

## 🐛 Troubleshooting

### Problem: "Cannot open database"
**Lösung:** Stelle sicher, dass der `database_path` in config.json schreibbar ist.

```bash
# Permissions prüfen
ls -la baludesk.db

# Neu erstellen
rm baludesk.db
./baludesk-backend
```

### Problem: "Failed to initialize libcurl"
**Lösung:** libcurl nicht installiert oder nicht gefunden.

```bash
# vcpkg (Windows)
vcpkg install curl:x64-windows

# Homebrew (macOS)
brew install curl

# apt (Linux)
sudo apt install libcurl4-openssl-dev
```

### Problem: "Connection refused" beim Login
**Lösung:** BaluHost Backend läuft nicht oder falsche URL.

```bash
# 1. BaluHost Backend starten
cd ../../backend
python -m uvicorn app.main:app --reload

# 2. URL in config.json prüfen
cat config.json | grep server_url
# Sollte sein: "server_url": "http://localhost:8000"
```

### Problem: Build-Fehler mit nlohmann/json
**Lösung:** CMake lädt es automatisch herunter (erfordert Internet).

```bash
# Build-Cache löschen und neu versuchen
rm -rf build
mkdir build && cd build
cmake ..
make
```

---

## 📝 Logs

Logs werden geschrieben nach:
- **Console:** Alle Levels (abhängig von --verbose)
- **File:** `baludesk.log` (definiert in config.json)

**Log-Rotation:** Automatisch bei 10 MB, max. 3 Dateien:
- `baludesk.log`
- `baludesk.log.1`
- `baludesk.log.2`

**Log anzeigen:**
```bash
# Live-Ansicht
tail -f baludesk.log

# Letzte 100 Zeilen
tail -n 100 baludesk.log

# Nach Errors filtern
grep "ERROR" baludesk.log
```

---

## 🔍 Debugging

### GDB (Linux/macOS)
```bash
gdb ./baludesk-backend
(gdb) run --verbose
(gdb) backtrace  # Bei Crash
```

### LLDB (macOS)
```bash
lldb ./baludesk-backend
(lldb) run --verbose
(lldb) bt  # Bei Crash
```

### Visual Studio (Windows)
1. Projekt in VS öffnen: `File > Open > CMake...`
2. `CMakeLists.txt` auswählen
3. F5 zum Debuggen

---

## 🎯 Nächste Schritte

1. **Backend funktioniert?** ✅  
   → Weiter zu **Sprint 2: Filesystem Watcher**

2. **Build-Probleme?** ❌  
   → Siehe [BUILD.md](BUILD.md) für detaillierte Anleitung

3. **API-Tests?**  
   → Siehe [SPRINT1_COMPLETE.md](../SPRINT1_COMPLETE.md) für IPC Examples

---

**Viel Erfolg! 🚀**

Bei Fragen: Siehe [README.md](../README.md) oder [ARCHITECTURE.md](../ARCHITECTURE.md)
