# 🧪 BaluHost Heimnetz-Features Testen

## 🚀 Quick Start (Einfachste Methode)

### PowerShell (Als Administrator):
```powershell
cd "F:\Programme (x86)\Baluhost"
.\scripts\start_network.ps1
```

**Dieser Befehl:**
- ✅ Konfiguriert Firewall automatisch
- ✅ Zeigt deine IP-Adresse an
- ✅ Startet den Server für Netzwerk-Zugriff
- ✅ Zeigt alle Zugriffs-URLs

---

## 📋 Manuelle Setup-Schritte

### Vorbereitung

1. **Terminal 1** - Server
2. **Terminal 2** - Discovery Test
3. **Terminal 3** - GUI Client

---

## Test 1: Firewall konfigurieren (einmalig)

### Als Administrator:
```powershell
cd "F:\Programme (x86)\Baluhost"
.\scripts\configure_firewall.ps1
```

**Öffnet Ports:**
- 8000 (API/HTTPS)
- 8080 (WebDAV)
- 5353 (mDNS Discovery)

---

## Test 2: Server mit Network Discovery starten

### Terminal 1:
```powershell
cd "F:\Programme (x86)\Baluhost"
python start_dev.py
```

**Erwartete Ausgabe:**
```
[info] Backend running with HTTPS
[info] - Local: https://localhost:8000
[info] - Network: https://192.168.x.x:8000

✓ mDNS service started:
  - API: https://192.168.x.x:8000
  - WebDAV: http://192.168.x.x:8080/webdav
  - Service name: BaluHost on HOSTNAME._baluhost._tcp.local.
  - Discovery enabled for local network
```

**Was passiert:**
- Backend startet auf Port 8000
- Frontend startet auf Port 5173 (oder 5174)
- mDNS Broadcasting beginnt
- Server ist im Netzwerk sichtbar

---

## Test 3: Network Discovery testen

### Terminal 2 (während Server läuft):
```powershell
cd "F:\Programme (x86)\Baluhost\client-desktop"
python discover_server.py 5
```

**Erwartete Ausgabe:**
```
🔍 Searching for BaluHost servers on local network...
   (Waiting 5 seconds for responses)

✅ Found BaluHost Server!
   Name: BaluHost on SVEN-PC._baluhost._tcp.local.
   Hostname: SVEN-PC
   IP Address: 192.168.1.100
   API: https://192.168.1.100:8000
   WebDAV: http://192.168.1.100:8080/webdav
   Description: BaluHost - Private Cloud Storage

==================================================
Discovery Complete - Found 1 server(s)
==================================================

📋 Available Servers:

1. SVEN-PC
   API URL: https://192.168.1.100:8000
   WebDAV: http://192.168.1.100:8080/webdav
```

**Troubleshooting:**
- Wenn "No servers found": Server läuft noch nicht oder Firewall blockiert Port 5353 (mDNS)
- Timeout erhöhen: `python discover_server.py 10`

---

## Test 4: GUI Client mit Auto-Discovery

### Terminal 3:
```powershell
cd "F:\Programme (x86)\Baluhost\client-desktop"
python sync_client_gui_v2.py
```

**Test-Schritte:**

1. **Auto-Discovery testen:**
   - Klick auf **"🔍 Find Servers on Network"**
   - Warte 3 Sekunden
   - Server URL sollte automatisch ausgefüllt werden
   - Status sollte zeigen: "✓ Found: HOSTNAME"

2. **Verbindung testen:**
   - Server URL: `https://localhost:8000` (oder die gefundene IP)
   - Username: `admin`
   - Password: `changeme`
   - Klick auf **"🔗 Connect to Server"**
   - Status sollte "Connected" zeigen (grüner Punkt)

3. **Sync testen:**
   - Klick auf **"📁 Add Folder"**
   - Wähle einen Test-Ordner (z.B. `C:\Temp\test-sync`)
   - Aktiviere **"Auto-sync enabled"**
   - Klick auf **"⟳ Sync Now"**
   - Activity Log sollte "✓ Sync completed" zeigen

---

## Test 5: Zugriff von anderem Gerät im Netzwerk

### Von einem anderen PC/Laptop/Tablet:

1. **Notiere deine IP-Adresse** vom Server (z.B. 192.168.1.100)

2. **Browser öffnen:**
   ```
   https://192.168.1.100:8000
   ```

3. **Zertifikat-Warnung akzeptieren:**
   - "Erweitert" → "Weiter zu 192.168.1.100"

4. **Login:**
   - Username: admin
   - Password: changeme

5. **Funktioniert?** ✅ Heimnetz-Zugriff erfolgreich!

---

## Test 6: WebDAV Network Drive (Optional)

### Windows:
```powershell
# Temporär einbinden
net use Z: \\localhost@8080\webdav /user:admin changeme

# Testen
dir Z:

# Abmelden
net use Z: /delete
```

### Oder via Explorer:
1. Explorer öffnen
2. "Dieser PC" → Rechtsklick → "Netzlaufwerk verbinden"
3. Laufwerk: `Z:`
4. Ordner: `\\localhost@8080\webdav`
5. Anmeldedaten: `admin` / `changeme`

---

## Test 7: Web Interface (Lokal)

### Browser:
```
https://localhost:8000
```

**Login:**
- Username: `admin`
- Password: `changeme`

**Testen:**
- Dashboard sollte laden
- System-Stats sollten angezeigt werden
- FileManager sollte funktionieren

---

## 🐛 Troubleshooting

### Server startet nicht
```powershell
# Prüfe ob Port 8000 belegt ist
netstat -ano | findstr :8000

# Process beenden falls nötig
taskkill /PID <PID> /F

# Dependencies prüfen
cd backend
pip install -e .
```

### Discovery funktioniert nicht
```powershell
# Firewall-Regel prüfen
Get-NetFirewallRule -DisplayName "BaluHost*"

# Manuell Port 5353 öffnen (mDNS)
New-NetFirewallRule -DisplayName "BaluHost-mDNS" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Private,Domain
```

### GUI Client verbindet nicht
- **SSL-Fehler**: Erwartet - selbst-signiertes Zertifikat (wird ignoriert)
- **Connection Refused**: Server läuft nicht
- **Wrong Credentials**: Passwort ist `changeme`, nicht `admin`

### WebDAV funktioniert nicht
```powershell
# WebDAV Client Service prüfen
Get-Service WebClient
Start-Service WebClient

# Registry-Fix (falls nötig)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "BasicAuthLevel" -Value 2
Restart-Service WebClient
```

---

## ✅ Success Checklist

- [ ] Server startet ohne Fehler
- [ ] mDNS Broadcasting aktiviert
- [ ] Discovery findet Server
- [ ] GUI Client verbindet erfolgreich
- [ ] Auto-Discovery Button funktioniert
- [ ] Sync funktioniert
- [ ] WebDAV mountbar (optional)
- [ ] Web Interface erreichbar

---

## 📊 Expected Performance

### Network Discovery:
- **Scan Zeit**: 3-5 Sekunden
- **Erfolgsrate**: >95% im gleichen Netzwerk
- **Latenz**: <100ms

### Sync Performance:
- **Kleine Dateien** (<1MB): <1 Sekunde
- **Mittlere Dateien** (1-10MB): 1-5 Sekunden
- **Große Dateien** (>10MB): Abhängig von Festplatte

### WebDAV:
- **Transfer-Rate**: LAN-Geschwindigkeit (~100-1000 Mbps)
- **Latenz**: <50ms im lokalen Netzwerk

---

## 🎯 Quick Test Workflow (3 Minuten)

```powershell
# Terminal 1: Server starten
cd "F:\Programme (x86)\Baluhost"
python start_dev.py

# Terminal 2: Discovery testen (nach 10 Sekunden)
cd "F:\Programme (x86)\Baluhost\client-desktop"
python discover_server.py 3

# Terminal 3: GUI Client starten
python sync_client_gui_v2.py
# Dann in der GUI: "🔍 Find Servers" → Connect → Add Folder → Sync
```

**Ergebnis nach 3 Minuten:**
- ✅ Server läuft
- ✅ Discovery funktioniert
- ✅ Client verbunden
- ✅ Sync aktiv

---

## 📝 Test-Protokoll

Kopiere und fülle aus:

```
Test-Datum: __________
Tester: __________

[ ] Test 1: Server Start - OK / FAIL
    Fehler: ____________________

[ ] Test 2: Discovery - OK / FAIL
    Gefundene Server: ____
    Zeit: ____ Sekunden

[ ] Test 3: GUI Client - OK / FAIL
    Auto-Discovery: OK / FAIL
    Connection: OK / FAIL
    Sync: OK / FAIL

[ ] Test 4: WebDAV - OK / FAIL / SKIP
    Mount: OK / FAIL
    Read: OK / FAIL
    Write: OK / FAIL

[ ] Test 5: Web Interface - OK / FAIL
    Login: OK / FAIL
    Dashboard: OK / FAIL
    FileManager: OK / FAIL

Gesamtergebnis: PASS / FAIL
Notizen: ____________________
```

---

## 🚀 Production Test (optional)

Wenn du die Windows Service Installation testen willst:

```powershell
# Als Administrator
.\scripts\install_windows_service.ps1

# Service Status
Get-Service BaluHost

# Service starten
Start-Service BaluHost

# Logs prüfen
Get-Content "F:\Programme (x86)\Baluhost\logs\service.log" -Tail 50 -Wait
```

**Achtung:** Dies ändert System-Einstellungen!
