# WebDAV Network Drive

Mount your BaluHost storage as a network drive on Windows, macOS, and Linux.

## Architecture

The WebDAV server runs as a **separate worker process** alongside the main backend:

```
┌─────────────────────┐     ┌─────────────────────────┐
│  FastAPI Backend     │     │  WebDAV Worker           │
│  (Uvicorn, Port 8000)│     │  (cheroot WSGI, Port 8080)│
│                     │     │                         │
│  /api/webdav/status ─┼──── │  webdav_state (DB)      │
│  /api/webdav/        │ IPC │                         │
│    connection-info   │     │  WsgiDAV + BaluHost Auth│
└─────────────────────┘     └─────────────────────────┘
```

- **Server**: cheroot WSGI hosting a WsgiDAV application
- **Authentication**: HTTP Basic Auth verified against the BaluHost user database (bcrypt)
- **User Isolation**: Admin sees entire storage, regular users see only `<storage>/<username>/`
- **IPC**: Worker writes heartbeat to `webdav_state` table every 10s; web API reads it for status
- **SSL**: Self-signed certificate auto-generated on first start (enabled by default)

## Configuration

Environment variables (or `Settings` in `backend/app/core/config.py`):

| Variable | Default | Description |
|---|---|---|
| `WEBDAV_ENABLED` | `true` | Enable/disable the WebDAV server |
| `WEBDAV_PORT` | `8080` | Listening port |
| `WEBDAV_SSL_ENABLED` | `true` | HTTPS with self-signed certificate |
| `WEBDAV_VERBOSE_LOGGING` | `false` | Log every request (method, path, auth) |

## Starting the Server

### Development

```bash
python start_dev.py
# Starts backend, scheduler, webdav worker, and frontend
```

The WebDAV worker is launched automatically as a subprocess.

### Production

**Systemd service** (`deploy/systemd/baluhost-webdav.service`):

```bash
sudo systemctl enable baluhost-webdav
sudo systemctl start baluhost-webdav

# Check status
sudo systemctl status baluhost-webdav
sudo journalctl -u baluhost-webdav -f
```

Or via the launcher:

```bash
python start_prod.py    # Starts backend + scheduler + webdav
python kill_prod.py     # Stops all
```

## Connecting from Clients

Use your **BaluHost login credentials** (username + password). The WebDAV tab in the BaluHost UI (System Control Page) shows the exact commands for your username.

Default connection URL: `https://<NAS-IP>:8080/`

### Windows

#### Method 1: Command Line

```cmd
net use Z: https://192.168.178.53:8080/ /user:admin *
```

#### Method 2: File Explorer (GUI)

1. Open File Explorer (Win+E) → "This PC"
2. Click "Map network drive" in toolbar
3. Drive letter: `Z:` (or any available)
4. Folder: `https://192.168.178.53:8080/`
5. Check "Connect using different credentials" → Finish
6. Enter BaluHost username and password

#### Windows: SSL Certificate Trust

With self-signed certificates, Windows requires you to import the cert:

1. Copy `backend/webdav-certs/webdav.crt` from the NAS to your Windows PC
2. Double-click the `.crt` file → "Install Certificate"
3. Store Location: **Local Machine**
4. Place in: **Trusted Root Certification Authorities**
5. Finish → restart `WebClient` service:

```powershell
Restart-Service WebClient
```

#### Windows: WebClient Service

The `WebClient` service must be running:

```powershell
# Check status
Get-Service WebClient

# Start and set to auto-start
Start-Service WebClient
Set-Service WebClient -StartupType Automatic
```

#### Windows: Performance Tuning

```powershell
# Increase file size limit (default 50 MB → 4 GB)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" `
  -Name "FileSizeLimitInBytes" -Value 4294967295

Restart-Service WebClient
```

### macOS

#### Finder (GUI)

1. Finder → Go → Connect to Server (Cmd+K)
2. Enter: `https://192.168.178.53:8080/`
3. Click "Connect"
4. Choose "Registered User" → enter BaluHost credentials
5. Volume mounts at `/Volumes/<hostname>`

#### Command Line

```bash
sudo mkdir -p /Volumes/baluhost
mount -t webdav https://192.168.178.53:8080/ /Volumes/baluhost
```

#### Disable .DS_Store on Network Volumes

```bash
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
```

### Linux

#### Install davfs2

```bash
# Debian/Ubuntu
sudo apt install davfs2

# Fedora/RHEL
sudo dnf install davfs2

# Arch
sudo pacman -S davfs2
```

#### Mount

```bash
sudo mkdir -p /mnt/baluhost
sudo mount -t davfs https://192.168.178.53:8080/ /mnt/baluhost
# Enter username + password when prompted
```

#### Self-Signed Certificate Trust

Add to `/etc/davfs2/davfs2.conf`:

```
trust_server_cert /path/to/webdav.crt
```

Or copy the cert to the system trust store:

```bash
sudo cp webdav.crt /usr/local/share/ca-certificates/baluhost-webdav.crt
sudo update-ca-certificates
```

#### Permanent Mount (fstab)

```bash
# Add credentials
echo "https://192.168.178.53:8080/ admin yourpassword" | sudo tee -a /etc/davfs2/secrets
sudo chmod 600 /etc/davfs2/secrets

# Add to fstab
echo "https://192.168.178.53:8080/ /mnt/baluhost davfs user,noauto,uid=1000,gid=1000 0 0" | sudo tee -a /etc/fstab

# Mount (no sudo needed after fstab entry)
mount /mnt/baluhost
```

## SSL / HTTPS

SSL is **enabled by default**. On first start, the WebDAV worker auto-generates a self-signed certificate:

- **Location**: `backend/webdav-certs/webdav.crt` + `webdav.key`
- **Validity**: 10 years
- **SAN**: `localhost`, `127.0.0.1`, and the server's detected LAN IP
- **Algorithm**: RSA 2048-bit, SHA256

To regenerate the certificate (e.g., after IP change):

```bash
rm -rf backend/webdav-certs/
sudo systemctl restart baluhost-webdav
```

To disable SSL:

```bash
export WEBDAV_SSL_ENABLED=false
```

## User Isolation

Storage access is enforced per-request in `BaluHostDAVProvider`:

| Role | Sees | Path |
|---|---|---|
| `admin` | Entire storage | `<NAS_STORAGE_PATH>/` |
| `user` | Home directory only | `<NAS_STORAGE_PATH>/<username>/` |

- Home directories are created automatically on first WebDAV access
- Path traversal is prevented via `os.path.normpath()` validation
- Thread-safe: user context is read from the WSGI environ per request

## API Endpoints

### `GET /api/webdav/status` (Admin only)

Returns detailed server status including heartbeat and PID.

```json
{
  "is_running": true,
  "port": 8080,
  "ssl_enabled": true,
  "started_at": "2026-02-14T10:30:00+00:00",
  "worker_pid": 12345,
  "last_heartbeat": "2026-02-14T10:35:45+00:00",
  "error_message": null,
  "connection_url": "https://192.168.178.53:8080/"
}
```

### `GET /api/webdav/connection-info` (Authenticated users)

Returns OS-specific mount instructions with the current user's username.

```json
{
  "is_running": true,
  "port": 8080,
  "ssl_enabled": true,
  "username": "admin",
  "connection_url": "https://192.168.178.53:8080/",
  "instructions": [
    {
      "os": "windows",
      "label": "Windows",
      "command": "net use Z: https://192.168.178.53:8080/ /user:admin *",
      "notes": "Or use File Explorer..."
    }
  ]
}
```

## Health Monitoring

The WebDAV server registers with BaluHost's service status system:

- Heartbeat interval: **10 seconds**
- Staleness threshold: **30 seconds** (no heartbeat = considered offline)
- Visible in: Admin Dashboard → Services tab
- Systemd: auto-restart on crash (`Restart=always`, `RestartSec=10s`)

## Frontend UI

The WebDAV tab is part of the **System Control Page** (`client/src/pages/SystemControlPage.tsx`):

- `WebdavConnectionCard` — shows status, connection URL, and OS-specific mount instructions with copy buttons
- Fetches data from `/api/webdav/connection-info`
- i18n keys: `system.webdav.*` (English + German)

## Key Files

| File | Purpose |
|---|---|
| `backend/app/core/config.py` | Configuration (port, SSL, enabled) |
| `backend/scripts/webdav_worker.py` | Worker entry point |
| `backend/app/services/webdav_service.py` | cheroot server, SSL cert generation, heartbeat |
| `backend/app/compat/webdav_asgi.py` | WsgiDAV app, auth controller |
| `backend/app/compat/webdav_provider.py` | Storage provider with user isolation |
| `backend/app/api/routes/webdav.py` | REST API endpoints |
| `backend/app/schemas/webdav.py` | Pydantic response models |
| `backend/app/models/webdav_state.py` | Database model |
| `deploy/systemd/baluhost-webdav.service` | Systemd unit file |
| `client/src/components/webdav/WebdavConnectionCard.tsx` | Frontend component |
| `client/src/api/webdav.ts` | Frontend API client |

## Troubleshooting

### Server won't start

```bash
# Check if port 8080 is already in use
ss -tlnp | grep 8080

# Check worker logs
journalctl -u baluhost-webdav --no-pager -n 50
```

### Windows Error 67: "The network name was not found"

1. Ensure the WebDAV worker is running on the NAS
2. Ensure the `WebClient` service is running on Windows
3. If using HTTP (not HTTPS): set `BasicAuthLevel` to `2`:
   ```powershell
   Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "BasicAuthLevel" -Value 2
   Restart-Service WebClient
   ```

### Windows: Certificate error with self-signed cert

Import `webdav.crt` into Trusted Root Certification Authorities (see [SSL Certificate Trust](#windows-ssl-certificate-trust) above).

### macOS: "Connection failed"

Try IP address instead of hostname. Check the server is reachable:

```bash
curl -k https://192.168.178.53:8080/
```

### Linux: mount.davfs fails with SSL error

Add `trust_server_cert` directive to davfs2.conf or install the cert system-wide (see [Linux SSL section](#self-signed-certificate-trust) above).

### Stale status in UI (shows "Not Running" even though worker runs)

The heartbeat may be stale. Restart the worker:

```bash
sudo systemctl restart baluhost-webdav
```

### Regenerate SSL certificate

```bash
rm -rf backend/webdav-certs/
sudo systemctl restart baluhost-webdav
# New cert generated with current LAN IP in SAN
```
