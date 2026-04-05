# Network Drive Access - Quick Start

Quick guide for mounting BaluHost storage as a network drive on Windows.

---

## Dev Mode (Local Development)

### Automatic (Recommended)

```powershell
# Create network drive Z: (SUBST method)
.\scripts\mount-dev-storage.ps1

# Or with SMB (like production)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Disconnect network drive
.\scripts\unmount-dev-storage.ps1
```

### Manual (Windows Explorer)

1. **Open Explorer**
2. **Enter path:** `D:\Programme (x86)\Baluhost\backend\dev-storage`
3. **Save as favorite**

### Manual (PowerShell)

```powershell
# Create simple virtual drive
subst Z: "D:\Programme (x86)\Baluhost\backend\dev-storage"

# Remove
subst Z: /d
```

---

## Production (Linux NAS with RAID)

### Windows Client

#### Option 1: Windows Explorer

1. **Right-click "This PC"**
2. **"Map network drive"**
3. **Drive:** `Z:`
4. **Folder:** `\\192.168.1.100\BaluHostStorage` (replace IP)
5. **Credentials:**
   - Username: `baluhost`
   - Password: `<your-password>`
6. **Check "Remember my credentials"**

#### Option 2: PowerShell

```powershell
# With interactive password prompt
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost /persistent:yes

# Disconnect
net use Z: /delete
```

### Linux Server Setup (One-Time)

```bash
# 1. Install Samba
sudo apt install samba -y

# 2. Edit configuration
sudo nano /etc/samba/smb.conf

# 3. Add share (see docs/NETWORK_DRIVE_SETUP.md)

# 4. Create user
sudo useradd baluhost
sudo smbpasswd -a baluhost

# 5. Start Samba
sudo systemctl restart smbd
```

---

## Available Scripts

| Script | Description |
|--------|-------------|
| `mount-dev-storage.ps1` | Mount dev storage as Z: |
| `unmount-dev-storage.ps1` | Disconnect network drive Z: |

### Script Options

```powershell
# Use a different drive letter
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"

# SMB mode (like production)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Without automatically opening Explorer
.\scripts\mount-dev-storage.ps1 -OpenExplorer:$false
```

---

## Troubleshooting

### "Access denied"
```powershell
# Run as administrator
```

### "Drive already in use"
```powershell
# Disconnect first
.\scripts\unmount-dev-storage.ps1

# Or use a different letter
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"
```

### SMB not working
```powershell
# Check Windows services
Get-Service LanmanWorkstation, LanmanServer | Start-Service

# Use SUBST method instead
.\scripts\mount-dev-storage.ps1
```

---

## Full Documentation

See [`docs/NETWORK_DRIVE_SETUP.md`](../docs/NETWORK_DRIVE_SETUP.md) for:
- Detailed Samba configuration
- Linux RAID setup
- Firewall settings
- Performance optimization
- Advanced troubleshooting tips

---

## Quick Commands

```powershell
# Dev Mode: Mount
.\scripts\mount-dev-storage.ps1

# Dev Mode: Unmount
.\scripts\unmount-dev-storage.ps1

# Production: Mount
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost

# Show status
net use

# Show all network drives
Get-PSDrive -PSProvider FileSystem
```
