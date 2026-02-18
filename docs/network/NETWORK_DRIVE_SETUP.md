# Netzlaufwerk-Zugriff auf BaluHost NAS

## Übersicht

Dieses Dokument beschreibt, wie du auf das BaluHost RAID-Storage als Netzlaufwerk zugreifen kannst - sowohl im Dev-Mode (Windows) als auch in der Live-Version (Linux).

---

## 🖥️ Dev-Mode (Windows)

Im Dev-Mode liegt der Storage als normales Verzeichnis vor:
- **Pfad:** `F:\Programme (x86)\Baluhost\backend\dev-storage`
- **Größe:** 5 GB (simuliert)

### Methode 1: Direkter Zugriff (Einfachste Lösung)

Da der Dev-Storage ein lokales Verzeichnis ist, kannst du direkt darauf zugreifen:

1. **Windows Explorer öffnen**
2. **Pfad eingeben:** `F:\Programme (x86)\Baluhost\backend\dev-storage`
3. **Favoriten hinzufügen** für schnellen Zugriff

### Methode 2: Als Netzlaufwerk mounten (Empfohlen)

Windows kann auch lokale Ordner als Netzlaufwerk einbinden:

#### Option A: Per GUI (Windows Explorer)

```powershell
# 1. Als Administrator ausführen
# 2. Symbolischen Link erstellen (einmalig)
New-Item -ItemType Junction -Path "C:\NAS" -Target "F:\Programme (x86)\Baluhost\backend\dev-storage"

# 3. Netzlaufwerk verbinden
# Rechtsklick auf "Dieser PC" → "Netzlaufwerk verbinden"
# Buchstabe: Z:
# Ordner: \\localhost\C$\NAS
```

#### Option B: Per PowerShell (Automatisiert)

```powershell
# Als Administrator ausführen
$devStoragePath = "F:\Programme (x86)\Baluhost\backend\dev-storage"
$driveLetter = "Z:"

# Prüfe ob Pfad existiert
if (Test-Path $devStoragePath) {
    # Entferne altes Mapping falls vorhanden
    if (Test-Path $driveLetter) {
        net use $driveLetter /delete /y
    }
    
    # Erstelle symbolischen Link
    $linkPath = "C:\BaluHost-NAS"
    if (-not (Test-Path $linkPath)) {
        New-Item -ItemType Junction -Path $linkPath -Target $devStoragePath
    }
    
    # Mappe als Netzlaufwerk
    subst $driveLetter $devStoragePath
    
    Write-Host "✅ Netzlaufwerk $driveLetter erstellt!"
    Write-Host "   Pfad: $devStoragePath"
    explorer $driveLetter
} else {
    Write-Host "❌ Dev-Storage Pfad nicht gefunden: $devStoragePath"
}
```

#### Option C: Per SMB-Freigabe (Wie in Produktion)

Wenn du das Verhalten der Live-Version testen möchtest:

```powershell
# 1. Windows SMB-Freigabe erstellen
# Als Administrator PowerShell öffnen:

$shareName = "BaluHostNAS"
$sharePath = "F:\Programme (x86)\Baluhost\backend\dev-storage"

# Freigabe erstellen
New-SmbShare -Name $shareName -Path $sharePath -FullAccess "Everyone"

# Zugriff gewähren
Grant-SmbShareAccess -Name $shareName -AccountName "Everyone" -AccessRight Full -Force

# 2. Netzlaufwerk verbinden
net use Z: \\localhost\BaluHostNAS

Write-Host "✅ SMB-Freigabe erstellt und gemountet als Z:"
```

**Freigabe wieder entfernen:**
```powershell
Remove-SmbShare -Name "BaluHostNAS" -Force
```

---

## 🐧 Live-Version (Linux mit RAID)

In der Produktionsumgebung wird das RAID-Array über Samba (SMB/CIFS) freigegeben.

### Server-Konfiguration (Linux NAS)

#### 1. RAID-Array mounten

```bash
# RAID-Array erstellen (falls noch nicht vorhanden)
sudo mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sda1 /dev/sdb1

# Dateisystem erstellen
sudo mkfs.ext4 /dev/md0

# Mount-Point erstellen
sudo mkdir -p /mnt/baluhost-storage

# RAID mounten
sudo mount /dev/md0 /mnt/baluhost-storage

# Permanent in /etc/fstab eintragen
echo "/dev/md0 /mnt/baluhost-storage ext4 defaults 0 2" | sudo tee -a /etc/fstab
```

#### 2. Samba installieren und konfigurieren

```bash
# Samba installieren
sudo apt update
sudo apt install samba samba-common-bin -y

# Konfiguration bearbeiten
sudo nano /etc/samba/smb.conf
```

**Samba-Konfiguration (`/etc/samba/smb.conf`):**

```ini
[global]
   workgroup = WORKGROUP
   server string = BaluHost NAS Server
   security = user
   map to guest = bad user
   dns proxy = no
   
   # Performance-Optimierungen
   socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=524288 SO_SNDBUF=524288
   read raw = yes
   write raw = yes
   oplocks = yes
   max xmit = 65535
   dead time = 15
   getwd cache = yes

[BaluHostStorage]
   comment = BaluHost RAID Storage
   path = /mnt/baluhost-storage
   browseable = yes
   read only = no
   guest ok = no
   valid users = @baluhost
   force user = baluhost
   force group = baluhost
   create mask = 0664
   directory mask = 0775
   vfs objects = recycle
   recycle:repository = .recycle
   recycle:keeptree = yes
   recycle:versions = yes
```

#### 3. Benutzer einrichten

```bash
# System-Benutzer erstellen
sudo useradd -m -s /bin/bash baluhost
sudo passwd baluhost

# Samba-Benutzer erstellen
sudo smbpasswd -a baluhost

# Berechtigungen setzen
sudo chown -R baluhost:baluhost /mnt/baluhost-storage
sudo chmod -R 775 /mnt/baluhost-storage

# Samba neu starten
sudo systemctl restart smbd
sudo systemctl enable smbd
```

#### 4. Firewall konfigurieren

```bash
# UFW (Ubuntu Firewall)
sudo ufw allow samba

# Oder spezifische Ports
sudo ufw allow 445/tcp
sudo ufw allow 139/tcp
sudo ufw allow 138/udp
sudo ufw allow 137/udp
```

### Client-Konfiguration (Windows)

#### Methode 1: Windows Explorer GUI

1. **Windows Explorer öffnen**
2. **Rechtsklick auf "Dieser PC"** → "Netzlaufwerk verbinden"
3. **Laufwerksbuchstabe:** `Z:`
4. **Ordner:** `\\<NAS-IP-ADRESSE>\BaluHostStorage`
   - Beispiel: `\\192.168.1.100\BaluHostStorage`
5. **"Verbindung mit anderen Anmeldeinformationen herstellen"** aktivieren
6. **Anmeldedaten eingeben:**
   - Benutzername: `baluhost`
   - Passwort: `<dein-passwort>`
7. **"Anmeldedaten speichern"** aktivieren
8. **"Fertig stellen"** klicken

#### Methode 2: PowerShell/CMD

```powershell
# Netzlaufwerk verbinden
$nasIP = "192.168.1.100"  # Deine NAS IP-Adresse
$shareName = "BaluHostStorage"
$driveLetter = "Z:"
$username = "baluhost"
$password = "dein-passwort"

# Mit Anmeldedaten
net use $driveLetter \\$nasIP\$shareName /user:$username $password /persistent:yes

# Oder mit Abfrage
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost /persistent:yes
# Passwort wird interaktiv abgefragt

Write-Host "✅ Netzlaufwerk Z: verbunden!"
```

#### Methode 3: Automatisches Mapping beim Login

Erstelle ein PowerShell-Script `mount-baluhost-nas.ps1`:

```powershell
# mount-baluhost-nas.ps1
$nasIP = "192.168.1.100"
$shareName = "BaluHostStorage"
$driveLetter = "Z:"
$username = "baluhost"

# Prüfe ob bereits verbunden
if (Test-Path $driveLetter) {
    Write-Host "✅ Netzlaufwerk $driveLetter bereits verbunden"
    exit 0
}

# Verbinde Netzlaufwerk
try {
    net use $driveLetter "\\$nasIP\$shareName" /user:$username /persistent:yes
    Write-Host "✅ Netzlaufwerk $driveLetter erfolgreich verbunden!"
} catch {
    Write-Host "❌ Fehler beim Verbinden: $_"
    exit 1
}
```

**Im Windows Task Scheduler hinzufügen:**
1. Task Scheduler öffnen
2. "Aufgabe erstellen"
3. Trigger: "Bei Anmeldung"
4. Aktion: PowerShell-Script ausführen

---

## 🔧 Integration in BaluHost Backend

Um den Netzwerk-Zugriff in die Anwendung zu integrieren:

### 1. API-Endpunkt für Netzwerk-Info

```python
# backend/app/api/routes/system.py

@router.get("/network/share-info")
async def get_network_share_info(
    current_user: UserPublic = Depends(deps.get_current_user)
) -> dict:
    """Get information about network share configuration."""
    import socket
    
    if settings.is_dev_mode:
        return {
            "mode": "dev",
            "share_type": "local",
            "path": os.path.abspath(settings.nas_storage_path),
            "instructions": "Verwende lokalen Pfad oder erstelle SMB-Freigabe für Tests"
        }
    else:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        
        return {
            "mode": "production",
            "share_type": "smb",
            "server": ip_address,
            "share_name": "BaluHostStorage",
            "mount_path": f"\\\\{ip_address}\\BaluHostStorage",
            "instructions": "Netzlaufwerk über Windows Explorer verbinden"
        }
```

### 2. Frontend-Integration (Anzeige der Mount-Info)

Zeige in der UI (z.B. Dashboard oder Settings) die Netzwerk-Informationen an.

---

## 📋 Schnell-Setup Scripts

### Dev-Mode: Automatisches Mount-Script

**`scripts/mount-dev-storage.ps1`:**

```powershell
# Automatisches Mounting des Dev-Storage als Netzlaufwerk
param(
    [string]$DriveLetter = "Z:",
    [switch]$UseSMB = $false
)

$devStoragePath = "F:\Programme (x86)\Baluhost\backend\dev-storage"

Write-Host "🚀 BaluHost Dev-Storage Mounting..."
Write-Host "   Pfad: $devStoragePath"
Write-Host "   Laufwerk: $DriveLetter"

# Prüfe ob Pfad existiert
if (-not (Test-Path $devStoragePath)) {
    Write-Host "❌ Dev-Storage nicht gefunden!"
    exit 1
}

# Entferne existierendes Mapping
if (Test-Path $DriveLetter) {
    Write-Host "⚠️  Laufwerk $DriveLetter bereits vorhanden - entferne..."
    subst $DriveLetter /d
}

if ($UseSMB) {
    # Methode 1: SMB-Freigabe (wie in Produktion)
    $shareName = "BaluHostNAS-Dev"
    
    # Erstelle Freigabe
    try {
        New-SmbShare -Name $shareName -Path $devStoragePath -FullAccess "Everyone" -ErrorAction Stop
        Grant-SmbShareAccess -Name $shareName -AccountName "Everyone" -AccessRight Full -Force
        net use $DriveLetter "\\localhost\$shareName"
        Write-Host "✅ SMB-Freigabe '$shareName' erstellt und gemountet als $DriveLetter"
    } catch {
        Write-Host "❌ SMB-Fehler: $_"
        exit 1
    }
} else {
    # Methode 2: SUBST (einfacher)
    subst $DriveLetter $devStoragePath
    if ($?) {
        Write-Host "✅ Dev-Storage gemountet als $DriveLetter"
        explorer $DriveLetter
    } else {
        Write-Host "❌ Fehler beim Mounten"
        exit 1
    }
}
```

**Verwendung:**

```powershell
# Einfaches Mounting (SUBST)
.\scripts\mount-dev-storage.ps1

# Mit SMB (wie in Produktion)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Anderer Laufwerksbuchstabe
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"
```

### Dev-Mode: Unmount-Script

**`scripts/unmount-dev-storage.ps1`:**

```powershell
param([string]$DriveLetter = "Z:")

Write-Host "🔌 Trenne Netzlaufwerk $DriveLetter..."

# SUBST entfernen
subst $DriveLetter /d 2>$null

# SMB-Verbindung trennen
net use $DriveLetter /delete /y 2>$null

# SMB-Freigabe entfernen
Remove-SmbShare -Name "BaluHostNAS-Dev" -Force 2>$null

Write-Host "✅ Netzlaufwerk getrennt"
```

---

## 🎯 Empfohlene Workflows

### Entwicklung (Dev-Mode)

```powershell
# 1. Server starten
python start_dev.py

# 2. Dev-Storage als Netzlaufwerk mounten
.\scripts\mount-dev-storage.ps1

# 3. Dateien per Drag & Drop in Z:\ verwalten
# 4. Im Frontend (http://localhost:5173) arbeiten

# 5. Nach der Arbeit: Unmount
.\scripts\unmount-dev-storage.ps1
```

### Produktion (Live NAS)

```bash
# Server-Setup (einmalig)
# 1. RAID erstellen und mounten
# 2. Samba installieren und konfigurieren
# 3. Firewall-Regeln setzen

# Client (Windows)
# 1. Netzlaufwerk Z: verbinden
# 2. Automatisches Mapping beim Login einrichten
```

---

## 🔍 Troubleshooting

### Windows: "Netzwerkpfad nicht gefunden"

```powershell
# Prüfe SMB-Dienst
Get-Service LanmanWorkstation, LanmanServer | Start-Service

# Prüfe Firewall
Test-NetConnection -ComputerName 192.168.1.100 -Port 445

# Aktiviere SMB1 (falls nötig, nur für alte NAS)
Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol
```

### Linux: Samba startet nicht

```bash
# Prüfe Konfiguration
testparm

# Logs anzeigen
sudo tail -f /var/log/samba/log.smbd

# Service Status
sudo systemctl status smbd
```

### Dev-Mode: Zugriff verweigert

```powershell
# Als Administrator ausführen
# Berechtigungen prüfen
icacls "F:\Programme (x86)\Baluhost\backend\dev-storage"
```

---

## 📚 Zusätzliche Ressourcen

- **Samba Dokumentation:** https://www.samba.org/samba/docs/
- **Windows Netzlaufwerke:** https://support.microsoft.com/de-de/windows/
- **mdadm RAID:** https://raid.wiki.kernel.org/

---

## ⚡ Quick Reference

| Szenario | Befehl |
|----------|--------|
| **Dev: Einfaches Mount** | `subst Z: "F:\Programme (x86)\Baluhost\backend\dev-storage"` |
| **Dev: Unmount** | `subst Z: /d` |
| **Prod: Netzlaufwerk** | `net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost` |
| **Prod: Trennen** | `net use Z: /delete` |
| **Prod: Alle anzeigen** | `net use` |
