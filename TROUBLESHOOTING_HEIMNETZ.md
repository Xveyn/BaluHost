# Problemlösung: Heimnetz-Zugriff funktioniert nicht

## Das Problem

Dein Netzwerk ist auf **"Public"** eingestellt. Windows blockiert bei Public Networks alle eingehenden Verbindungen aus Sicherheitsgründen.

## Die Lösung (3 Schritte)

### Schritt 1: PowerShell als Administrator öffnen

1. **Windows-Taste** drücken
2. **"PowerShell"** eingeben
3. **Rechtsklick** auf "Windows PowerShell"
4. **"Als Administrator ausführen"** wählen

### Schritt 2: Fix-Skript ausführen

```powershell
cd "F:\Programme (x86)\Baluhost"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\heimnetz_fix.ps1
```

**Das Skript wird:**
- ✅ Netzwerkprofil zu "Private" ändern
- ✅ Firewall-Regeln erstellen (Ports 5173, 8000, 8080, 5353)
- ✅ Deine IP-Adresse anzeigen

**Folge den Anweisungen im Skript!**

### Schritt 3: Von anderem Gerät testen

**Deine IP:** (wird vom Skript angezeigt, z.B. 192.168.178.42)

**Im Browser des anderen Geräts:**
```
https://192.168.178.42:5173
```

**Für API-Dokumentation:**
```
https://192.168.178.42:8000/docs
```

**Zertifikatswarnung:**
- Klicke "Erweitert" oder "Details"
- Dann "Weiter zu 192.168.178.42" oder "Trotzdem fortfahren"
- Das ist normal bei selbst-signierten Zertifikaten!

**Login:**
- Username: `admin`
- Password: `changeme`

---

## Alternative: Manuell ohne Skript

### 1. Netzwerkprofil ändern

**Windows 11:**
1. **Einstellungen** öffnen (Windows + I)
2. **Netzwerk & Internet** → Dein Netzwerk (z.B. "Eivor")
3. **Netzwerkprofil-Typ** → **"Privat"** wählen

**Windows 10:**
1. **Einstellungen** → **Netzwerk und Internet**
2. **Eigenschaften** → **Netzwerkprofil** → **"Privat"**

### 2. Firewall-Regel erstellen (als Administrator)

**PowerShell:**
```powershell
# Port 5173 (Frontend/Web UI)
New-NetFirewallRule -DisplayName "BaluHost-Frontend" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Private,Domain

# Port 8000 (Backend API/HTTPS)
New-NetFirewallRule -DisplayName "BaluHost-API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Domain

# Port 8080 (WebDAV)
New-NetFirewallRule -DisplayName "BaluHost-WebDAV" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private,Domain

# Port 5353 (mDNS)
New-NetFirewallRule -DisplayName "BaluHost-mDNS" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Private,Domain
```

**Oder Windows Firewall GUI:**
1. **Windows Defender Firewall** öffnen
2. **Erweiterte Einstellungen**
3. **Eingehende Regeln** → **Neue Regel**
4. **Port** → **TCP** → **5173** (für Frontend)
5. **Verbindung zulassen** → **Nur für Private/Domänennetzwerke**
6. Name: "BaluHost-Frontend"
7. Wiederholen für Port 8000 (TCP, Backend), 8080 (TCP, WebDAV) und 5353 (UDP, mDNS)

### 3. Deine IP-Adresse herausfinden

**PowerShell:**
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | Select-Object IPAddress
```

**Oder Windows-Einstellungen:**
1. **Einstellungen** → **Netzwerk & Internet**
2. **Eigenschaften** → Suche nach "IPv4-Adresse"

---

## Häufige Probleme

### Problem: "Seite kann nicht erreicht werden"

**Ursachen:**
1. ❌ Server läuft nicht
   - **Lösung:** `python start_dev.py` ausführen
   
2. ❌ Netzwerk ist "Public"
   - **Lösung:** Zu "Private" ändern (siehe oben)
   
3. ❌ Firewall blockiert
   - **Lösung:** Regeln erstellen (siehe oben)
   
4. ❌ Falsche IP-Adresse
   - **Lösung:** IP erneut prüfen (siehe oben)

### Problem: "Zertifikatsfehler" / "Nicht sicher"

**Das ist NORMAL!** Selbst-signierte Zertifikate werden vom Browser als unsicher markiert.

**Lösung:**
- Chrome/Edge: "Erweitert" → "Weiter zu IP-Adresse"
- Firefox: "Erweitert" → "Risiko akzeptieren und fortfahren"

### Problem: "Verbindung wurde zurückgesetzt"

**Ursache:** Server bindet nur auf localhost (127.0.0.1)

**Lösung:** Server wurde bereits gepatcht für 0.0.0.0 (alle Interfaces)
- Prüfe ob du die neueste Version hast
- Server neu starten

### Problem: Funktioniert nur auf dem Server-PC

**Ursache:** Netzwerk ist auf "Public"

**Lösung:** 
```powershell
# Als Administrator
Set-NetConnectionProfile -NetworkCategory Private
```

---

## Testen ob alles funktioniert

### Vom Server-PC aus:

```powershell
# 1. Prüfe ob Server läuft
netstat -ano | findstr :8000

# 2. Prüfe Firewall-Regeln
Get-NetFirewallRule -DisplayName "BaluHost*"

# 3. Prüfe Netzwerkprofil
Get-NetConnectionProfile

# 4. Teste lokalen Zugriff
Start-Process "https://localhost:8000"
```

### Von anderem Gerät:

1. **Verbinde mit gleichem WLAN/LAN**
2. **Öffne Browser**
3. **Gehe zu:** `https://SERVER-IP:8000`
4. **Akzeptiere Zertifikatswarnung**
5. **Login:** admin / changeme

---

## Zusammenfassung

**Checklist:**
- [ ] Server läuft (`python start_dev.py`)
- [ ] Server bindet auf 0.0.0.0 (nicht nur localhost)
- [ ] Netzwerkprofil ist "Private" (NICHT Public!)
- [ ] Firewall-Regeln existieren (Ports 8000, 8080, 5353)
- [ ] Richtige IP-Adresse verwenden
- [ ] Beide Geräte im selben Netzwerk
- [ ] Zertifikatswarnung akzeptieren

**Wenn alles grün:** Du solltest jetzt zugreifen können! 🎉

**Wenn nicht:** Führe `heimnetz_fix.ps1` als Administrator aus!
