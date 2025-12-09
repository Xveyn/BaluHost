# WebDAV Network Drive - Complete Setup Guide

**Status:** ✅ **READY FOR TESTING**  
**Date:** December 5, 2024  
**Component:** WebDAV Server for Network Drive Mounting

## Overview

Mount your BaluHost NAS as a network drive on Windows, macOS, and Linux using the WebDAV protocol.

## Quick Start

### 1. Start WebDAV Server

```bash
cd backend
python start_webdav.py
```

Output:
```
============================================================
BaluHost WebDAV Server
============================================================

Network Drive Mount Points:
  Windows:  \\localhost:8080\
  macOS:    http://localhost:8080/
  Linux:    http://localhost:8080/

Default Credentials:
  Username: admin
  Password: password

============================================================

Starting WebDAV server on http://0.0.0.0:8080
```

### 2. Mount on Your OS

Choose your operating system below for detailed instructions.

---

## Windows - Map Network Drive

### Method 1: File Explorer (GUI)

1. **Open File Explorer** (Win + E)

2. **Click "This PC"** in left sidebar

3. **Click "Map network drive"** in toolbar

4. **Configure:**
   - **Drive letter:** Z: (or any available)
   - **Folder:** `\\localhost@8080\DavWWWRoot`
   - ✅ **Check:** "Reconnect at sign-in"
   - ✅ **Check:** "Connect using different credentials"

5. **Click "Finish"**

6. **Enter credentials:**
   - Username: `admin`
   - Password: `password`
   - ✅ **Check:** "Remember my credentials"

7. **Click "OK"**

### Method 2: Command Line

```cmd
net use Z: \\localhost@8080\DavWWWRoot /user:admin password /persistent:yes
```

### Method 3: PowerShell

```powershell
$cred = Get-Credential -UserName admin -Message "BaluHost WebDAV"
New-PSDrive -Name "Z" -PSProvider FileSystem -Root "\\localhost@8080\DavWWWRoot" -Credential $cred -Persist
```

### Troubleshooting Windows

#### Error: "The network path was not found"
**Fix:** Ensure WebDAV Client service is running
```powershell
# Check service status
Get-Service WebClient

# Start service if stopped
Start-Service WebClient

# Set to auto-start
Set-Service WebClient -StartupType Automatic
```

#### Error: "The folder you entered does not appear to be valid"
**Fix:** Use `\\localhost@8080\DavWWWRoot` format (note `@` instead of `:`)

#### Error: "Windows cannot access..."
**Fix:** Disable Basic Auth restriction (Windows 10/11)
```powershell
# Run as Administrator
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "BasicAuthLevel" -Value 2
Restart-Service WebClient
```

#### Slow Performance
**Fix:** Increase file size limit
```powershell
# Allow larger files (50MB default → 500MB)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "FileSizeLimitInBytes" -Value 524288000
Restart-Service WebClient
```

---

## macOS - Connect to Server

### Method 1: Finder (GUI)

1. **Open Finder**

2. **Press Cmd + K** or **Go → Connect to Server**

3. **Enter server address:**
   ```
   http://localhost:8080/
   ```

4. **Click "Connect"**

5. **Choose "Registered User"**

6. **Enter credentials:**
   - Name: `admin`
   - Password: `password`
   - ✅ **Check:** "Remember this password in my keychain"

7. **Click "Connect"**

8. **Volume mounts** at `/Volumes/localhost`

### Method 2: Command Line

```bash
# Create mount point
sudo mkdir -p /Volumes/baluhost

# Mount WebDAV
mount -t webdav http://localhost:8080/ /Volumes/baluhost
# Enter password when prompted
```

### Method 3: Auto-mount at Login

```bash
# Edit /etc/fstab (requires sudo)
echo "http://admin:password@localhost:8080/ /Volumes/baluhost webdav rw,noauto 0 0" | sudo tee -a /etc/fstab

# Create mount script
cat > ~/mount-baluhost.sh << 'EOF'
#!/bin/bash
mkdir -p /Volumes/baluhost
mount -t webdav http://localhost:8080/ /Volumes/baluhost
EOF

chmod +x ~/mount-baluhost.sh
```

### Troubleshooting macOS

#### Error: "Connection failed"
**Fix:** Check server is running on port 8080
```bash
curl http://localhost:8080/
# Should return WebDAV response
```

#### Error: "The operation can't be completed"
**Fix:** Try with IP address instead of localhost
```
http://127.0.0.1:8080/
```

#### Unmount Volume
```bash
diskutil unmount /Volumes/localhost
# or
umount /Volumes/baluhost
```

---

## Linux - mount.davfs

### Install davfs2

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install davfs2
```

**Fedora/RHEL:**
```bash
sudo dnf install davfs2
```

**Arch Linux:**
```bash
sudo pacman -S davfs2
```

### Configure davfs2

1. **Add user to davfs2 group:**
   ```bash
   sudo usermod -a -G davfs2 $USER
   # Logout and login for changes to take effect
   ```

2. **Create secrets file:**
   ```bash
   sudo nano /etc/davfs2/secrets
   # Add line:
   http://localhost:8080/ admin password
   
   # Secure the file
   sudo chmod 600 /etc/davfs2/secrets
   ```

### Mount WebDAV

**Temporary Mount:**
```bash
# Create mount point
sudo mkdir -p /mnt/baluhost

# Mount
sudo mount -t davfs http://localhost:8080/ /mnt/baluhost
# Password will be read from secrets file
```

**Permanent Mount (fstab):**
```bash
# Edit /etc/fstab
sudo nano /etc/fstab

# Add line:
http://localhost:8080/ /mnt/baluhost davfs user,noauto,uid=1000,gid=1000 0 0

# Mount
mount /mnt/baluhost
```

**User-space Mount (no sudo):**
```bash
# Create user config
mkdir -p ~/.davfs2
echo "http://localhost:8080/ admin password" > ~/.davfs2/secrets
chmod 600 ~/.davfs2/secrets

# Create mount point in home
mkdir -p ~/baluhost

# Add to fstab (one-time, requires sudo)
echo "http://localhost:8080/ $HOME/baluhost davfs user,noauto,uid=$UID,gid=$UID 0 0" | sudo tee -a /etc/fstab

# Mount (no sudo needed after fstab entry)
mount ~/baluhost
```

### Troubleshooting Linux

#### Error: "mount.davfs: mounting failed"
**Fix:** Check davfs2 is installed and user is in davfs2 group
```bash
groups $USER
# Should include: davfs2
```

#### Error: "Network is unreachable"
**Fix:** Ensure server is accessible
```bash
ping localhost
curl http://localhost:8080/
```

#### Unmount
```bash
fusermount -u /mnt/baluhost
# or
umount /mnt/baluhost
```

#### Mount on Boot
```bash
# Enable systemd mount
sudo systemctl daemon-reload
sudo systemctl enable mnt-baluhost.mount
sudo systemctl start mnt-baluhost.mount
```

---

## Testing the Mount

### Windows
```cmd
Z:
dir
type test.txt
echo "Hello from Windows" > windows_test.txt
```

### macOS
```bash
cd /Volumes/localhost
ls -la
cat test.txt
echo "Hello from macOS" > mac_test.txt
```

### Linux
```bash
cd /mnt/baluhost
ls -la
cat test.txt
echo "Hello from Linux" > linux_test.txt
```

### Verify in Web UI

1. Open http://localhost:3000
2. Login as admin
3. Navigate to File Manager
4. You should see `windows_test.txt`, `mac_test.txt`, `linux_test.txt`

---

## Advanced Configuration

### Custom Port

Edit `backend/start_webdav.py`:
```python
server = wsgi.Server(
    bind_addr=('0.0.0.0', 9090),  # Change port
    wsgi_app=app
)
```

Update mount points accordingly:
- Windows: `\\localhost@9090\DavWWWRoot`
- macOS: `http://localhost:9090/`
- Linux: `http://localhost:9090/`

### HTTPS/SSL

For secure connections, use reverse proxy (nginx/Apache):

**nginx configuration:**
```nginx
server {
    listen 443 ssl;
    server_name baluhost.local;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then mount using `https://baluhost.local/`

### External Access

To access from other computers on network:

1. **Get your IP address:**
   ```bash
   # Windows
   ipconfig
   
   # macOS/Linux
   ifconfig
   # or
   ip addr show
   ```

2. **Start WebDAV on all interfaces** (already configured in `start_webdav.py`):
   ```python
   bind_addr=('0.0.0.0', 8080)  # Listen on all IPs
   ```

3. **Mount from remote computer:**
   - Windows: `\\192.168.1.100@8080\DavWWWRoot`
   - macOS: `http://192.168.1.100:8080/`
   - Linux: `http://192.168.1.100:8080/`

4. **Configure firewall** to allow port 8080:
   ```bash
   # Windows (Run as Administrator)
   netsh advfirewall firewall add rule name="BaluHost WebDAV" dir=in action=allow protocol=TCP localport=8080
   
   # Linux (ufw)
   sudo ufw allow 8080/tcp
   
   # Linux (firewalld)
   sudo firewall-cmd --add-port=8080/tcp --permanent
   sudo firewall-cmd --reload
   ```

---

## Performance Tuning

### WebDAV Server (backend/app/compat/webdav_asgi.py)

```python
config.update({
    "verbose": 1,  # Reduce logging (0-5, lower = less verbose)
    "dir_browser": {
        "enable": True,  # Web interface
        "response_trailer": "",
    },
    "chunked_write": True,  # Better for large files
    "block_size": 8192,  # Read/write block size (bytes)
})
```

### Windows Performance

Increase buffer sizes:
```powershell
# Registry tweaks (Run as Administrator)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "FileAttributesLimitInBytes" -Value 10000000 -PropertyType DWord -Force
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "FileSizeLimitInBytes" -Value 4294967295 -PropertyType DWord -Force

Restart-Service WebClient
```

---

## Security Considerations

### Production Deployment

1. **Change default credentials** in `backend/app/compat/webdav_asgi.py`:
   ```python
   "simple_dc": {
       "user_mapping": {
           "*": {
               "your_username": {"password": "strong_password"},
           }
       }
   }
   ```

2. **Enable HTTPS** using reverse proxy

3. **Restrict access** by IP:
   ```python
   # In start_webdav.py
   bind_addr=('192.168.1.100', 8080)  # Specific IP only
   ```

4. **Use JWT authentication** instead of basic auth (future enhancement)

---

## Known Issues

### Windows

- **Issue:** Large files (>50MB) fail to upload
  - **Fix:** Increase `FileSizeLimitInBytes` registry key

- **Issue:** Slow directory listing
  - **Fix:** Disable Windows Search indexing for network drives

### macOS

- **Issue:** ".DS_Store" files created everywhere
  - **Fix:** Disable for network volumes:
    ```bash
    defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
    ```

### Linux

- **Issue:** Permission denied errors
  - **Fix:** Ensure correct UID/GID in fstab mount options

---

## Next Steps

- [ ] **JWT Authentication:** Replace basic auth with JWT tokens
- [ ] **Multi-user Support:** Per-user home directories
- [ ] **Quota Enforcement:** Integrate with BaluHost quota system
- [ ] **Audit Logging:** Log all WebDAV operations
- [ ] **Encryption:** Built-in TLS/SSL support
- [ ] **Caching:** Improve performance with client-side caching

---

## Support

For issues or questions, check:
- WebDAV server logs in terminal
- Backend logs in `backend/tmp/audit/`
- System logs (Event Viewer/Console.app/syslog)

## References

- [WsgiDAV Documentation](https://wsgidav.readthedocs.io/)
- [WebDAV RFC 4918](https://tools.ietf.org/html/rfc4918)
- [Windows WebClient Service](https://docs.microsoft.com/en-us/windows-server/storage/webdav/)
