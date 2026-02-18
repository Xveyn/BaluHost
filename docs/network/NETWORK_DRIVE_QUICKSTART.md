# 🗂️ Netzlaufwerk-Zugriff - Quick Start

Schnellanleitung zum Einbinden des BaluHost Storage als Netzlaufwerk in Windows.

---

## 🚀 Dev-Mode (Lokale Entwicklung)

### Automatisch (Empfohlen)

```powershell
# Netzlaufwerk Z: erstellen (SUBST-Methode)
.\scripts\mount-dev-storage.ps1

# Oder mit SMB (wie in Produktion)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Netzlaufwerk wieder trennen
.\scripts\unmount-dev-storage.ps1
```

### Manuell (Windows Explorer)

1. **Explorer öffnen**
2. **Pfad eingeben:** `F:\Programme (x86)\Baluhost\backend\dev-storage`
3. **Als Favorit speichern**

### Manuell (PowerShell)

```powershell
# Einfaches virtuelles Laufwerk erstellen
subst Z: "F:\Programme (x86)\Baluhost\backend\dev-storage"

# Entfernen
subst Z: /d
```

---

## 🐧 Produktion (Linux NAS mit RAID)

### Windows Client

#### Option 1: Windows Explorer

1. **Rechtsklick auf "Dieser PC"**
2. **"Netzlaufwerk verbinden"**
3. **Laufwerk:** `Z:`
4. **Ordner:** `\\192.168.1.100\BaluHostStorage` (ersetze IP)
5. **Anmeldedaten:** 
   - Benutzername: `baluhost`
   - Passwort: `<dein-passwort>`
6. **"Anmeldedaten speichern"** aktivieren

#### Option 2: PowerShell

```powershell
# Mit interaktiver Passwort-Abfrage
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost /persistent:yes

# Trennen
net use Z: /delete
```

### Linux Server Setup (einmalig)

```bash
# 1. Samba installieren
sudo apt install samba -y

# 2. Konfiguration bearbeiten
sudo nano /etc/samba/smb.conf

# 3. Freigabe hinzufügen (siehe docs/NETWORK_DRIVE_SETUP.md)

# 4. Benutzer erstellen
sudo useradd baluhost
sudo smbpasswd -a baluhost

# 5. Samba starten
sudo systemctl restart smbd
```

---

## 📋 Verfügbare Scripts

| Script | Beschreibung |
|--------|--------------|
| `mount-dev-storage.ps1` | Dev-Storage als Z: mounten |
| `unmount-dev-storage.ps1` | Netzlaufwerk Z: trennen |

### Script-Optionen

```powershell
# Anderen Laufwerksbuchstaben verwenden
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"

# SMB-Modus (wie in Produktion)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Ohne automatisches Öffnen des Explorers
.\scripts\mount-dev-storage.ps1 -OpenExplorer:$false
```

---

## 🔍 Troubleshooting

### "Zugriff verweigert"
```powershell
# Als Administrator ausführen
```

### "Laufwerk bereits belegt"
```powershell
# Zuerst trennen
.\scripts\unmount-dev-storage.ps1

# Oder anderen Buchstaben verwenden
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"
```

### SMB funktioniert nicht
```powershell
# Prüfe Windows-Dienste
Get-Service LanmanWorkstation, LanmanServer | Start-Service

# Verwende SUBST-Methode
.\scripts\mount-dev-storage.ps1
```

---

## 📚 Vollständige Dokumentation

Siehe [`docs/NETWORK_DRIVE_SETUP.md`](../docs/NETWORK_DRIVE_SETUP.md) für:
- Detaillierte Samba-Konfiguration
- Linux RAID-Setup
- Firewall-Einstellungen
- Performance-Optimierung
- Erweiterte Troubleshooting-Tipps

---

## ⚡ Quick Commands

```powershell
# Dev-Mode: Mount
.\scripts\mount-dev-storage.ps1

# Dev-Mode: Unmount
.\scripts\unmount-dev-storage.ps1

# Produktion: Mount
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost

# Status anzeigen
net use

# Alle Netzlaufwerke anzeigen
Get-PSDrive -PSProvider FileSystem
```
