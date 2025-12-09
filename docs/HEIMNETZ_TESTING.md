# BaluHost Heimnetz-Setup - Schnelltest

## ✅ Implementierte Features

### 1. Windows Service Installation
- **Datei**: `scripts/install_windows_service.ps1`
- **Funktion**: Installiert BaluHost als Windows Service mit Auto-Start
- **Features**:
  - Automatischer Download und Installation von NSSM (Service Manager)
  - Konfiguration für automatischen Start beim Booten
  - Windows Firewall-Regeln für Ports 8000 und 8080
  - Log-Rotation (10MB pro Datei)
  - Zeigt lokale IP-Adresse für Netzwerk-Zugriff

### 2. Network Discovery (mDNS/Bonjour)
- **Datei**: `backend/app/services/network_discovery.py`
- **Funktion**: Broadcastet BaluHost-Server im lokalen Netzwerk
- **Features**:
  - mDNS/Bonjour Service Broadcasting
  - Service-Name: `_baluhost._tcp.local.`
  - WebDAV Service: `_webdav._tcp.local.`
  - Automatische IP-Erkennung
  - Startet automatisch mit dem Server

### 3. Client Auto-Discovery
- **Datei**: `client-desktop/discover_server.py` (CLI)
- **Datei**: `client-desktop/sync_client_gui_v2.py` (GUI integriert)
- **Funktion**: Findet automatisch BaluHost-Server im Netzwerk
- **Features**:
  - "🔍 Find Servers on Network" Button in der GUI
  - Automatisches Ausfüllen der Server-URL
  - Zeigt Hostname und IP-Adresse an
  - CLI-Tool für Debugging

### 4. Heimnetz Setup-Guide
- **Datei**: `docs/HEIMNETZ_SETUP.md`
- **Inhalt**: Schritt-für-Schritt Anleitung für nicht-technische Nutzer
- **Abdeckt**:
  - Server-Installation als Windows Service
  - Netzlaufwerk einbinden (Windows/Mac/Linux)
  - Desktop Sync Client einrichten
  - Web-Interface Zugriff
  - Troubleshooting
  - Sicherheits-Tipps

## 🧪 Testing

### Test 1: Windows Service Installation (requires Admin)
```powershell
# Als Administrator ausführen
.\scripts\install_windows_service.ps1

# Service Status prüfen
Get-Service BaluHost

# Service starten
Start-Service BaluHost

# Logs ansehen
Get-Content "F:\Programme (x86)\Baluhost\logs\service.log" -Tail 20
```

### Test 2: Network Discovery (Server muss laufen)
```powershell
# Server starten (wenn nicht als Service)
python start_dev.py

# In anderem Terminal: Discovery Test
cd client-desktop
python discover_server.py 5
```

**Erwartete Ausgabe:**
```
✅ Found BaluHost Server!
   Name: BaluHost on HOSTNAME._baluhost._tcp.local.
   Hostname: HOSTNAME
   IP Address: 192.168.x.x
   API: https://192.168.x.x:8000
   WebDAV: http://192.168.x.x:8080/webdav
```

### Test 3: GUI Auto-Discovery
```powershell
# Server muss laufen
cd client-desktop
python sync_client_gui_v2.py

# In der GUI:
# 1. Klick auf "🔍 Find Servers on Network"
# 2. Warte 3 Sekunden
# 3. Server-URL wird automatisch ausgefüllt
```

### Test 4: Netzlaufwerk einbinden (Server muss laufen)

**Windows:**
```powershell
# Manuelle Einbindung
net use Z: \\192.168.x.x@8080\webdav /user:admin /persistent:yes

# Oder via Explorer:
# Netzlaufwerk verbinden → \\192.168.x.x@8080\webdav
```

**Mac:**
```bash
# Finder → Gehe zu → Mit Server verbinden
# http://192.168.x.x:8080/webdav
```

**Linux:**
```bash
sudo apt-get install davfs2
sudo mount -t davfs http://192.168.x.x:8080/webdav /mnt/baluhost
```

## 📋 Checkliste für Production Deployment

- [ ] Server als Windows Service installiert
- [ ] Service läuft und startet automatisch
- [ ] Firewall-Regeln konfiguriert
- [ ] Lokale IP-Adresse notiert
- [ ] mDNS Discovery funktioniert (andere PCs finden Server)
- [ ] Netzlaufwerk erfolgreich eingebunden
- [ ] Desktop Sync Client verbindet automatisch
- [ ] Web-Interface erreichbar von anderen Geräten
- [ ] Standard-Passwort geändert
- [ ] Backup-Strategie eingerichtet

## 🔒 Sicherheits-Hinweise

### ✅ Richtig (nur Heimnetz)
- Server nur im lokalen Netzwerk erreichbar (192.168.x.x)
- Firewall-Regeln nur für "Private" und "Domain" Profile
- Starke Passwörter verwenden
- HTTPS für API (selbst-signiertes Zertifikat OK)

### ⚠️ Erweiterte Zugriffe (fortgeschritten)
- Externe Zugriffe nur via VPN (WireGuard empfohlen)
- Kein direktes Port-Forwarding ohne zusätzliche Sicherheit
- Bei External-Zugriff: Let's Encrypt Zertifikat verwenden
- Fail2Ban oder ähnliche Brute-Force-Protection

## 📊 Technische Details

### Ports
- **8000**: FastAPI Backend (HTTPS)
- **8080**: WebDAV Server (HTTP)
- **5353**: mDNS/Bonjour (UDP, automatisch)

### Dependencies
- `zeroconf>=0.132.0` - mDNS/Bonjour Support
- `nssm` - Windows Service Manager (auto-download)

### Service-Namen
- mDNS Service: `_baluhost._tcp.local.`
- WebDAV Service: `_webdav._tcp.local.`
- Windows Service: `BaluHost`

## 🎯 Use Cases

### 1. Familiennetzwerk
- **Szenario**: Gemeinsamer Speicher für Fotos, Dokumente, Videos
- **Setup**: Ein PC als Server (24/7 oder bei Bedarf), alle Geräte verbinden
- **Vorteil**: Keine Cloud-Kosten, volle Kontrolle, unbegrenzter Speicher

### 2. Home Office
- **Szenario**: Dokumenten-Sync zwischen Desktop und Laptop
- **Setup**: Desktop als Server, Laptop mit Sync Client
- **Vorteil**: Offline-Zugriff, automatische Synchronisation

### 3. Media Center
- **Szenario**: Zentrale Medien-Bibliothek
- **Setup**: NAS-PC mit großen Festplatten, Netzlaufwerk auf allen Geräten
- **Vorteil**: Streaming von jedem Gerät, kein Upload-Limit

## 📈 Nächste Schritte

1. **Mobile Apps** (zukünftig):
   - iOS App mit Files-Integration
   - Android App mit automatischem Upload

2. **Erweiterte Features**:
   - Datei-Versioning
   - Papierkorb-Funktion
   - Sharing-Links mit Ablaufdatum
   - Collaborative Editing

3. **Performance**:
   - Caching-Layer
   - Thumbnail-Generierung
   - Progressive Upload/Download

## 💡 Tipps

- **Performance**: SSD für System, HDDs für Speicher
- **Redundanz**: RAID 1 oder 5 für wichtige Daten
- **Backup**: Externe Festplatte oder zweiter Server
- **Monitoring**: Web-Interface → System Monitor für Überwachung
- **Quotas**: Pro-User Limits setzen für fairen Speicher

---

**Status**: ✅ Heimnetz-Features vollständig implementiert und bereit für Production!
