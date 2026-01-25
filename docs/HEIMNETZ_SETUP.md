# BaluHost als Netzlaufwerk im Heimnetz einrichten

## 🏠 Überblick

BaluHost ist Ihre private Cloud-Lösung - eine echte Alternative zu iCloud, OneDrive oder Google Drive, die komplett in Ihrem Heimnetz läuft. Ihre Daten bleiben bei Ihnen!

### Was Sie bekommen:
- 💾 **Netzlaufwerk** wie bei iCloud Drive - auf allen PCs im Heimnetz
- 📱 **Desktop Sync Client** - automatische Synchronisation wie OneDrive
- 🌐 **Web-Interface** - Zugriff über jeden Browser
- 🔒 **Volle Kontrolle** - Ihre Daten bleiben zuhause

---

## 📋 Voraussetzungen

- **Windows PC** als Server (läuft 24/7 oder nach Bedarf)
- **Heimnetzwerk** (WLAN/LAN)
- **Python 3.11+** installiert
- **Administrator-Rechte** für Installation

---

## 🚀 Schritt 1: Server installieren

### 1.1 Repository herunterladen

```powershell
# In PowerShell (als Administrator):
cd "C:\Programme"
git clone https://github.com/Xveyn/BaluHost.git
cd BaluHost
```

### 1.2 Python-Abhängigkeiten installieren

```powershell
cd backend
pip install -e .
```

### 1.3 Als Windows Service einrichten

```powershell
# Als Administrator ausführen:
.\scripts\install_windows_service.ps1
```

Das Skript wird:
- ✅ BaluHost als Windows Service installieren
- ✅ Automatischen Start beim Booten konfigurieren
- ✅ Firewall-Regeln erstellen
- ✅ Ihre lokale IP-Adresse anzeigen

**Wichtig:** Notieren Sie sich die angezeigte IP-Adresse (z.B. `192.168.1.100`)!

---

## 🏷️ Schritt 2: Hostname einrichten (optional, aber empfohlen!)

Anstatt sich IP-Adressen zu merken, können Sie BaluHost über den Namen `baluhost.local` erreichen!

### Warum ist das nützlich?
- ✅ Einfacher zu merken: `http://baluhost.local` statt `http://192.168.1.100:5173`
- ✅ Funktioniert auch wenn sich die IP-Adresse ändert
- ✅ Professioneller und benutzerfreundlicher

### Voraussetzungen
- **Linux-Server** (für Avahi mDNS-Unterstützung)
- **Oder:** Manuelle hosts-Datei-Konfiguration auf jedem Client

### Server-seitige Einrichtung (Linux)

Wenn Ihr BaluHost-Server auf Linux läuft, führen Sie das Setup-Script aus:

```bash
# Als root/sudo ausführen
cd deploy/scripts
sudo ./setup-hostname.sh
```

Das Script wird:
- ✅ Avahi mDNS installieren und konfigurieren
- ✅ Hostname `baluhost.local` im Netzwerk publizieren
- ✅ Optional Nginx Reverse Proxy einrichten
- ✅ Konfiguration testen und Zugriffsinformationen anzeigen

**Fertig!** Nach wenigen Sekunden ist BaluHost über `baluhost.local` erreichbar.

### Client-seitige Einrichtung

Je nach Betriebssystem sind unterschiedliche Schritte nötig:

#### Mac/Linux Clients
**Funktioniert automatisch!** Keine weitere Konfiguration nötig.

```bash
# Test
ping baluhost.local
```

#### Windows Clients

**Option 1: Bonjour installieren** (empfohlen)
1. [Bonjour Print Services](https://support.apple.com/kb/DL999) herunterladen
2. Installieren und PC neu starten
3. Fertig! `ping baluhost.local` sollte jetzt funktionieren

**Option 2: Hosts-Datei** (einfache Alternative)
1. Notepad als Administrator öffnen
2. Datei öffnen: `C:\Windows\System32\drivers\etc\hosts`
3. Folgende Zeile hinzufügen:
   ```
   192.168.1.100  baluhost baluhost.local
   ```
   (Ihre Server-IP einsetzen!)
4. Speichern und schließen

#### Smartphones
- **iOS**: Funktioniert automatisch (native Bonjour-Unterstützung)
- **Android**: Ab Version 5.0 meist unterstützt, ansonsten IP-Adresse verwenden

### Zugriff mit Hostname

Nach der Einrichtung können Sie BaluHost so erreichen:

```
# Web-Interface
http://baluhost.local

# Mit Nginx Reverse Proxy (empfohlen)
http://baluhost.local        → Frontend
http://baluhost.local/api/   → Backend API

# Ohne Reverse Proxy
http://baluhost.local:5173   → Frontend
http://baluhost.local:8000   → Backend API
http://baluhost.local:8080   → WebDAV
```

### Netzlaufwerk mit Hostname

```powershell
# Statt IP-Adresse:
net use Z: \\baluhost.local@8080\webdav /user:admin /persistent:yes
```

**Detaillierte Anleitung:** Siehe [CLIENT_MDNS_SETUP.md](./CLIENT_MDNS_SETUP.md)

---

## 💻 Schritt 3: Netzlaufwerk einbinden (Windows)

### Option A: Explorer GUI (einfach)

1. **Windows Explorer** öffnen
2. **"Dieser PC"** → Rechtsklick → **"Netzlaufwerk verbinden"**
3. **Laufwerksbuchstabe** wählen (z.B. `Z:`)
4. **Ordner** eingeben:
   ```
   \\192.168.1.100@8080\webdav
   ```
   *(Ihre IP-Adresse einsetzen!)*
5. ☑️ **"Verbindung bei Anmeldung wiederherstellen"** aktivieren
6. ☑️ **"Verbindung mit anderen Anmeldeinformationen herstellen"** aktivieren
7. **Fertig stellen** klicken
8. **Anmeldedaten** eingeben:
   - Benutzername: `admin`
   - Passwort: Ihr BaluHost-Passwort

### Option B: PowerShell (schnell)

```powershell
# Netzlaufwerk Z: einbinden
net use Z: \\192.168.1.100@8080\webdav /user:admin /persistent:yes
```

### ✅ Fertig!

Ihr Netzlaufwerk `Z:` ist jetzt verfügbar wie eine externe Festplatte!

---

## 📱 Schritt 4: Desktop Sync Client einrichten

Der Sync Client synchronisiert automatisch ausgewählte Ordner - genau wie OneDrive!

### 3.1 Client starten

```powershell
cd client-desktop
python sync_client_gui_v2.py
```

### 3.2 Verbindung einrichten

1. **Server URL**: `https://192.168.1.100:8000` (Ihre Server-IP einsetzen - dies ist die **Backend API URL**)
2. **Benutzername**: `admin`
3. **Passwort**: Ihr Passwort
4. Klick auf **"🔗 Connect to Server"**

**Hinweis:** Der Sync Client verbindet sich mit Port 8000 (Backend API), nicht mit Port 5173 (Web-Interface).

### 3.3 Ordner zum Synchronisieren hinzufügen

1. Klick auf **"📁 Add Folder"**
2. Wählen Sie einen Ordner (z.B. `C:\Users\IhrName\Dokumente`)
3. Aktivieren Sie **"Auto-sync enabled"** für automatische Synchronisation
4. Fertig! Der Ordner wird jetzt automatisch synchronisiert

### 3.4 Client automatisch starten (optional)

Um den Client beim Windows-Start automatisch zu öffnen:

1. **Windows + R** drücken
2. `shell:startup` eingeben
3. Verknüpfung zur `sync_client_gui_v2.py` erstellen

---

## 🌐 Schritt 5: Web-Interface nutzen

### Vom Server-PC:
```
http://localhost:5173
```

### Von anderen Geräten im Netzwerk:

**Mit Hostname** (wenn konfiguriert):
```
http://baluhost.local
```

**Mit IP-Adresse**:
```
http://192.168.1.100:5173
```
(Ersetzen Sie `192.168.1.100` mit der IP Ihres Servers)

### API-Dokumentation:
```
http://baluhost.local:8000/docs
```
oder
```
http://192.168.1.100:8000/docs
```

Hier können Sie:
- 📁 Dateien hochladen/herunterladen
- 👥 Benutzer verwalten (als Admin)
- 📊 Speicherplatz überwachen
- 💽 RAID-Konfiguration anpassen
- 📈 System-Status einsehen

---

## 📱 Zugriff von anderen Geräten

### Windows PC (gleiche Schritte wie oben)
- Netzlaufwerk: `\\baluhost.local@8080\webdav` (mit Hostname)
- Oder: `\\192.168.1.100@8080\webdav` (mit IP)
- Sync Client installieren

### Mac
1. **Finder** → **Gehe zu** → **Mit Server verbinden**
2. Server-Adresse: `http://baluhost.local:8080/webdav` (mit Hostname)
3. Oder: `http://192.168.1.100:8080/webdav` (mit IP)
4. Anmeldung: `admin` + Passwort

### Linux
```bash
# WebDAV mounten (mit Hostname)
sudo apt-get install davfs2
sudo mount -t davfs http://baluhost.local:8080/webdav /mnt/baluhost

# Oder mit IP-Adresse
sudo mount -t davfs http://192.168.1.100:8080/webdav /mnt/baluhost
```

### Smartphone/Tablet
- **iOS**: Dateien-App → Server verbinden → WebDAV
- **Android**: WebDAV-Apps wie "Solid Explorer" oder "FolderSync"

---

## 🔧 Verwaltung & Wartung

### Service verwalten

```powershell
# Status prüfen
Get-Service BaluHost

# Service starten
Start-Service BaluHost

# Service stoppen
Stop-Service BaluHost

# Service neu starten
Restart-Service BaluHost
```

### Logs anzeigen

```powershell
# Live-Logs anzeigen
Get-Content "F:\Programme (x86)\Baluhost\logs\service.log" -Tail 50 -Wait

# Fehler-Logs
Get-Content "F:\Programme (x86)\Baluhost\logs\service-error.log" -Tail 50
```

### Firewall-Ports

BaluHost benötigt folgende Ports im Heimnetz:
- **8000** - API Server (HTTPS)
- **8080** - WebDAV Server (HTTP)

Diese werden automatisch konfiguriert, aber stellen Sie sicher, dass Ihre Router-Firewall sie im **lokalen Netzwerk** zulässt (externe Zugriffe sollten blockiert bleiben für Sicherheit!).

---

## 🔒 Sicherheit im Heimnetz

### ✅ Empfohlene Einstellungen

1. **Nur Heimnetz**: Server ist nur in Ihrem WLAN/LAN erreichbar
2. **Starke Passwörter**: Ändern Sie das Standard-Passwort!
3. **HTTPS**: API läuft mit SSL-Verschlüsselung
4. **Firewall**: Nur lokale Ports geöffnet, keine externen Zugriffe

### ⚠️ Externe Zugriffe (optional, fortgeschritten)

Wenn Sie von unterwegs zugreifen möchten:
- **VPN** einrichten (z.B. WireGuard) - **Empfohlen!**
- Port-Forwarding im Router (weniger sicher)
- Dynamic DNS Service verwenden

**Wichtig:** Externe Zugriffe erfordern zusätzliche Sicherheitsmaßnahmen!

---

## 🆘 Problembehandlung

### Netzlaufwerk verbindet nicht

1. **Firewall prüfen**:
   ```powershell
   Get-NetFirewallRule -DisplayName "BaluHost*"
   ```

2. **Service-Status prüfen**:
   ```powershell
   Get-Service BaluHost
   ```

3. **Logs prüfen**:
   ```powershell
   Get-Content "F:\Programme (x86)\Baluhost\logs\service-error.log" -Tail 20
   ```

### IP-Adresse hat sich geändert

Wenn Ihr PC eine neue IP bekommt (DHCP):

1. **Feste IP einrichten** (empfohlen):
   - Windows-Einstellungen → Netzwerk → Adapteroptionen
   - IPv4-Eigenschaften → IP-Adresse manuell festlegen

2. **Oder Router-DHCP-Reservation** einrichten

### Sync Client verbindet nicht

1. Prüfen Sie die Server-URL (IP-Adresse korrekt?)
2. Prüfen Sie Benutzername/Passwort
3. Prüfen Sie Firewall (Port 8000)

---

## 📚 Weiterführende Dokumentation

- **Hostname Setup (mDNS)**: `docs/CLIENT_MDNS_SETUP.md` - Detaillierte Anleitung für baluhost.local
- **API Reference**: `docs/API_REFERENCE.md`
- **Technische Dokumentation**: `TECHNICAL_DOCUMENTATION.md`
- **RAID Setup**: `docs/RAID_SETUP_WIZARD.md`
- **Backup & Restore**: `docs/BACKUP_RESTORE.md`

---

## 💡 Tipps & Tricks

### Speicherplatz erhöhen

1. **Externe Festplatten** hinzufügen
2. **RAID konfigurieren** für Redundanz (Web-Interface → RAID Management)
3. **Quotas einstellen** pro Benutzer (Web-Interface → Users)

### Performance optimieren

- SSD für Betriebssystem verwenden
- Große Dateien über Netzlaufwerk (schneller als Upload im Browser)
- Auto-Sync nur für wichtige Ordner aktivieren

### Backup einrichten

Automatische Backups aktivieren:
```powershell
# In backend/
python scripts/backup.py --schedule daily
```

---

## ✨ Sie haben es geschafft!

Ihre private Cloud läuft jetzt! 🎉

**Genießen Sie:**
- Unbegrenzten Speicher (nur durch Ihre Festplatten begrenzt)
- Keine monatlichen Abo-Kosten
- Volle Kontrolle über Ihre Daten
- Zugriff von allen Geräten im Heimnetz

Bei Fragen: GitHub Issues oder Dokumentation durchsuchen!
