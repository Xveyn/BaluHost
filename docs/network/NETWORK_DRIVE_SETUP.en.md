# Network Drive Access for BaluHost NAS

## Overview

This document describes how to access the BaluHost RAID storage as a network drive -- both in dev mode (Windows) and in the production version (Linux).

---

## Dev Mode (Windows)

In dev mode, the storage is a regular local directory:
- **Path:** `D:\Programme (x86)\Baluhost\backend\dev-storage`
- **Size:** 5 GB (simulated)

### Method 1: Direct Access (Simplest Solution)

Since the dev storage is a local directory, you can access it directly:

1. **Open Windows Explorer**
2. **Enter path:** `D:\Programme (x86)\Baluhost\backend\dev-storage`
3. **Add to favorites** for quick access

### Method 2: Mount as Network Drive (Recommended)

Windows can also mount local folders as network drives:

#### Option A: Via GUI (Windows Explorer)

```powershell
# 1. Run as administrator
# 2. Create symbolic link (one-time)
New-Item -ItemType Junction -Path "C:\NAS" -Target "D:\Programme (x86)\Baluhost\backend\dev-storage"

# 3. Map network drive
# Right-click "This PC" -> "Map network drive"
# Letter: Z:
# Folder: \\localhost\C$\NAS
```

#### Option B: Via PowerShell (Automated)

```powershell
# Run as administrator
$devStoragePath = "D:\Programme (x86)\Baluhost\backend\dev-storage"
$driveLetter = "Z:"

# Check if path exists
if (Test-Path $devStoragePath) {
    # Remove old mapping if present
    if (Test-Path $driveLetter) {
        net use $driveLetter /delete /y
    }
    
    # Create symbolic link
    $linkPath = "C:\BaluHost-NAS"
    if (-not (Test-Path $linkPath)) {
        New-Item -ItemType Junction -Path $linkPath -Target $devStoragePath
    }
    
    # Map as network drive
    subst $driveLetter $devStoragePath
    
    Write-Host "Network drive $driveLetter created!"
    Write-Host "   Path: $devStoragePath"
    explorer $driveLetter
} else {
    Write-Host "Dev storage path not found: $devStoragePath"
}
```

#### Option C: Via SMB Share (Like Production)

If you want to test the behavior of the production version:

```powershell
# 1. Create Windows SMB share
# Open PowerShell as administrator:

$shareName = "BaluHostNAS"
$sharePath = "D:\Programme (x86)\Baluhost\backend\dev-storage"

# Create share
New-SmbShare -Name $shareName -Path $sharePath -FullAccess "Everyone"

# Grant access
Grant-SmbShareAccess -Name $shareName -AccountName "Everyone" -AccessRight Full -Force

# 2. Map network drive
net use Z: \\localhost\BaluHostNAS

Write-Host "SMB share created and mounted as Z:"
```

**Remove share:**
```powershell
Remove-SmbShare -Name "BaluHostNAS" -Force
```

---

## Production (Linux with RAID)

In the production environment, the RAID array is shared via Samba (SMB/CIFS).

### Server Configuration (Linux NAS)

#### 1. Mount RAID Array

```bash
# Create RAID array (if not already present)
sudo mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sda1 /dev/sdb1

# Create filesystem
sudo mkfs.ext4 /dev/md0

# Create mount point
sudo mkdir -p /mnt/baluhost-storage

# Mount RAID
sudo mount /dev/md0 /mnt/baluhost-storage

# Add permanent entry to /etc/fstab
echo "/dev/md0 /mnt/baluhost-storage ext4 defaults 0 2" | sudo tee -a /etc/fstab
```

#### 2. Install and Configure Samba

```bash
# Install Samba
sudo apt update
sudo apt install samba samba-common-bin -y

# Edit configuration
sudo nano /etc/samba/smb.conf
```

**Samba configuration (`/etc/samba/smb.conf`):**

```ini
[global]
   workgroup = WORKGROUP
   server string = BaluHost NAS Server
   security = user
   map to guest = bad user
   dns proxy = no
   
   # Performance optimizations
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

#### 3. Set Up Users

```bash
# Create system user
sudo useradd -m -s /bin/bash baluhost
sudo passwd baluhost

# Create Samba user
sudo smbpasswd -a baluhost

# Set permissions
sudo chown -R baluhost:baluhost /mnt/baluhost-storage
sudo chmod -R 775 /mnt/baluhost-storage

# Restart Samba
sudo systemctl restart smbd
sudo systemctl enable smbd
```

#### 4. Configure Firewall

```bash
# UFW (Ubuntu Firewall)
sudo ufw allow samba

# Or specific ports
sudo ufw allow 445/tcp
sudo ufw allow 139/tcp
sudo ufw allow 138/udp
sudo ufw allow 137/udp
```

### Client Configuration (Windows)

#### Method 1: Windows Explorer GUI

1. **Open Windows Explorer**
2. **Right-click "This PC"** -> "Map network drive"
3. **Drive letter:** `Z:`
4. **Folder:** `\\<NAS-IP-ADDRESS>\BaluHostStorage`
   - Example: `\\192.168.1.100\BaluHostStorage`
5. **Check "Connect using different credentials"**
6. **Enter credentials:**
   - Username: `baluhost`
   - Password: `<your-password>`
7. **Check "Remember my credentials"**
8. **Click "Finish"**

#### Method 2: PowerShell/CMD

```powershell
# Map network drive
$nasIP = "192.168.1.100"  # Your NAS IP address
$shareName = "BaluHostStorage"
$driveLetter = "Z:"
$username = "baluhost"
$password = "your-password"

# With credentials
net use $driveLetter \\$nasIP\$shareName /user:$username $password /persistent:yes

# Or with interactive prompt
net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost /persistent:yes
# Password will be prompted interactively

Write-Host "Network drive Z: connected!"
```

#### Method 3: Automatic Mapping on Login

Create a PowerShell script `mount-baluhost-nas.ps1`:

```powershell
# mount-baluhost-nas.ps1
$nasIP = "192.168.1.100"
$shareName = "BaluHostStorage"
$driveLetter = "Z:"
$username = "baluhost"

# Check if already connected
if (Test-Path $driveLetter) {
    Write-Host "Network drive $driveLetter already connected"
    exit 0
}

# Connect network drive
try {
    net use $driveLetter "\\$nasIP\$shareName" /user:$username /persistent:yes
    Write-Host "Network drive $driveLetter connected successfully!"
} catch {
    Write-Host "Error connecting: $_"
    exit 1
}
```

**Add to Windows Task Scheduler:**
1. Open Task Scheduler
2. "Create Task"
3. Trigger: "At log on"
4. Action: Run PowerShell script

---

## BaluHost Backend Integration

To integrate network access into the application:

### 1. API Endpoint for Network Info

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
            "instructions": "Use local path or create SMB share for testing"
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
            "instructions": "Connect network drive via Windows Explorer"
        }
```

### 2. Frontend Integration (Display Mount Info)

Display network information in the UI (e.g., Dashboard or Settings).

---

## Quick Setup Scripts

### Dev Mode: Automatic Mount Script

**`scripts/mount-dev-storage.ps1`:**

```powershell
# Automatic mounting of dev storage as network drive
param(
    [string]$DriveLetter = "Z:",
    [switch]$UseSMB = $false
)

$devStoragePath = "D:\Programme (x86)\Baluhost\backend\dev-storage"

Write-Host "BaluHost Dev Storage Mounting..."
Write-Host "   Path: $devStoragePath"
Write-Host "   Drive: $DriveLetter"

# Check if path exists
if (-not (Test-Path $devStoragePath)) {
    Write-Host "Dev storage not found!"
    exit 1
}

# Remove existing mapping
if (Test-Path $DriveLetter) {
    Write-Host "Drive $DriveLetter already exists - removing..."
    subst $DriveLetter /d
}

if ($UseSMB) {
    # Method 1: SMB share (like production)
    $shareName = "BaluHostNAS-Dev"
    
    # Create share
    try {
        New-SmbShare -Name $shareName -Path $devStoragePath -FullAccess "Everyone" -ErrorAction Stop
        Grant-SmbShareAccess -Name $shareName -AccountName "Everyone" -AccessRight Full -Force
        net use $DriveLetter "\\localhost\$shareName"
        Write-Host "SMB share '$shareName' created and mounted as $DriveLetter"
    } catch {
        Write-Host "SMB error: $_"
        exit 1
    }
} else {
    # Method 2: SUBST (simpler)
    subst $DriveLetter $devStoragePath
    if ($?) {
        Write-Host "Dev storage mounted as $DriveLetter"
        explorer $DriveLetter
    } else {
        Write-Host "Error mounting"
        exit 1
    }
}
```

**Usage:**

```powershell
# Simple mounting (SUBST)
.\scripts\mount-dev-storage.ps1

# With SMB (like production)
.\scripts\mount-dev-storage.ps1 -UseSMB

# Different drive letter
.\scripts\mount-dev-storage.ps1 -DriveLetter "Y:"
```

### Dev Mode: Unmount Script

**`scripts/unmount-dev-storage.ps1`:**

```powershell
param([string]$DriveLetter = "Z:")

Write-Host "Disconnecting network drive $DriveLetter..."

# Remove SUBST
subst $DriveLetter /d 2>$null

# Disconnect SMB connection
net use $DriveLetter /delete /y 2>$null

# Remove SMB share
Remove-SmbShare -Name "BaluHostNAS-Dev" -Force 2>$null

Write-Host "Network drive disconnected"
```

---

## Recommended Workflows

### Development (Dev Mode)

```powershell
# 1. Start server
python start_dev.py

# 2. Mount dev storage as network drive
.\scripts\mount-dev-storage.ps1

# 3. Manage files via drag & drop in Z:\
# 4. Work in frontend (http://localhost:5173)

# 5. After work: Unmount
.\scripts\unmount-dev-storage.ps1
```

### Production (Live NAS)

```bash
# Server setup (one-time)
# 1. Create and mount RAID
# 2. Install and configure Samba
# 3. Set firewall rules

# Client (Windows)
# 1. Map network drive Z:
# 2. Set up automatic mapping on login
```

---

## Troubleshooting

### Windows: "Network path not found"

```powershell
# Check SMB service
Get-Service LanmanWorkstation, LanmanServer | Start-Service

# Check firewall
Test-NetConnection -ComputerName 192.168.1.100 -Port 445

# Enable SMB1 (if needed, only for legacy NAS)
Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol
```

### Linux: Samba won't start

```bash
# Check configuration
testparm

# View logs
sudo tail -f /var/log/samba/log.smbd

# Service status
sudo systemctl status smbd
```

### Dev Mode: Access denied

```powershell
# Run as administrator
# Check permissions
icacls "D:\Programme (x86)\Baluhost\backend\dev-storage"
```

---

## Additional Resources

- **Samba Documentation:** https://www.samba.org/samba/docs/
- **Windows Network Drives:** https://support.microsoft.com/de-de/windows/
- **mdadm RAID:** https://raid.wiki.kernel.org/

---

## Quick Reference

| Scenario | Command |
|----------|---------|
| **Dev: Simple Mount** | `subst Z: "D:\Programme (x86)\Baluhost\backend\dev-storage"` |
| **Dev: Unmount** | `subst Z: /d` |
| **Prod: Network Drive** | `net use Z: \\192.168.1.100\BaluHostStorage /user:baluhost` |
| **Prod: Disconnect** | `net use Z: /delete` |
| **Prod: Show All** | `net use` |
