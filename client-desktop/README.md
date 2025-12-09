# BaluHost Desktop Sync Client

Desktop synchronization client for BaluHost NAS with real-time file watching.

## Features

- **🔍 Auto-Discovery:** Automatically finds BaluHost servers on your network (mDNS/Bonjour)
- **Real-time File Watching:** Automatically detects file changes using Watchdog
- **Auto-Sync:** Uploads changes to BaluHost server after debounce delay
- **Bi-directional Sync:** Downloads server changes to local folders
- **Conflict Detection:** Handles file conflicts (currently keeps server version)
- **Multiple Folders:** Sync multiple folders simultaneously
- **Modern GUI:** Beautiful interface matching BaluHost web design
- **Persistent Configuration:** Saves settings in `sync_config.json`
- **Logging:** Detailed logs in `baluhost_sync.log`

## Installation

### Prerequisites
- Python 3.8 or higher
- BaluHost server running (backend)
- Valid user account on BaluHost

### Install Dependencies

```bash
cd client-desktop
pip install -r requirements.txt
```

## Usage

### GUI Client (Recommended)

1. **Start the modern GUI client:**
   ```bash
   python sync_client_gui_v2.py
   ```

2. **Auto-discover server** (if on same network):
   - Click **"🔍 Find Servers on Network"**
   - Wait 3 seconds for automatic discovery
   - Server URL will be filled automatically

3. **Or enter manually:**
   - Server URL: `https://192.168.x.x:8000` (your BaluHost server IP)
   - Username: `admin`
   - Password: `changeme` (default dev mode)

4. **Connect and sync:**
   - Click **"🔗 Connect to Server"**
   - Add folders with **"📁 Add Folder"**
   - Enable **"Auto-sync"** for automatic synchronization

### CLI Client

1. **Start the CLI client:**
   ```bash
   python sync_client.py
   ```

2. **Login** with your BaluHost credentials:
   ```
   Server URL: https://localhost:8000
   Username: admin
   Password: changeme
   ```
   
   ⚠️ **Note:** The default dev mode password is `changeme`, not `admin`.

3. **Add sync folders** when prompted:
   ```
   Enter folder path to sync: C:\Users\YourName\Documents
   Enter folder path to sync: done
   ```

### Network Discovery Tool

Test automatic server discovery:

```bash
# Discover BaluHost servers on your network
python discover_server.py

# With custom timeout (seconds)
python discover_server.py 10
```

4. The client will:
   - Register your device with the server
   - Perform an initial sync
   - Start watching for file changes

### Subsequent Runs

Just run the client - it will use saved configuration:
```bash
python sync_client.py
```

## Configuration

Configuration is stored in `sync_config.json`:

```json
{
  "server_url": "http://localhost:8000",
  "device_id": "desktop-MY-COMPUTER",
  "device_name": "Desktop - MY-COMPUTER",
  "token": "your_jwt_token",
  "sync_folders": [
    "C:\\Users\\YourName\\Documents"
  ],
  "auto_sync": true,
  "sync_interval": 60,
  "debounce_delay": 2
}
```

### Configuration Options

- **server_url:** BaluHost server URL
- **device_id:** Unique identifier for this device
- **device_name:** Human-readable device name
- **token:** JWT authentication token (set after login)
- **sync_folders:** List of local folders to sync
- **auto_sync:** Enable/disable automatic sync (true/false)
- **sync_interval:** Seconds between sync checks (default: 60)
- **debounce_delay:** Seconds to wait after file change before syncing (default: 2)

## How It Works

### File Watching
- Uses Watchdog to monitor file system events
- Detects: create, modify, delete, move operations
- Ignores temporary files (`.tmp`, `.swp`, `~`)

### Debouncing
- File changes are queued with timestamps
- After `debounce_delay` seconds of no changes, sync is triggered
- Prevents excessive syncs during rapid file modifications

### Sync Process
1. Calculate SHA256 hash for all local files
2. Send file list to server via `/api/sync/changes`
3. Server compares with its state and returns:
   - Files to download (server has newer version)
   - Files to delete (removed on server)
   - Conflicts (both changed since last sync)
4. Download new/updated files from server
5. Handle conflicts (currently: keep server version)

## Logging

Logs are written to:
- **Console:** INFO level and above
- **baluhost_sync.log:** All levels, detailed information

Example log output:
```
2024-12-05 14:30:15 - BaluHostSync - INFO - Device registered: desktop-MY-COMPUTER
2024-12-05 14:30:16 - BaluHostSync - INFO - Starting sync...
2024-12-05 14:30:17 - BaluHostSync - INFO - Changes detected - Download: 3, Delete: 0, Conflicts: 0
2024-12-05 14:30:18 - BaluHostSync - INFO - Downloaded: documents/report.pdf
2024-12-05 14:30:19 - BaluHostSync - INFO - Sync completed
```

## API Endpoints Used

- **POST /api/auth/login** - User authentication
- **POST /api/sync/register** - Device registration
- **POST /api/sync/changes** - Change detection
- **POST /api/files/upload** - File upload
- **GET /api/files/download** - File download

## Conflict Resolution

Current strategy: **Keep server version**

When both local and server files have changed:
- Server version is downloaded
- Local changes are overwritten
- Conflict is logged as warning

Future improvements:
- User-selectable conflict resolution
- Create versions for both files
- Manual conflict resolution UI

## Troubleshooting

### Login Failed
- Check server URL in `sync_config.json`
- Verify credentials
- Ensure BaluHost server is running

### Files Not Syncing
- Check `baluhost_sync.log` for errors
- Verify sync folders exist
- Check network connection to server
- Ensure sufficient disk space

### High CPU Usage
- Increase `debounce_delay` to reduce sync frequency
- Exclude large/frequently changing folders
- Check for file permission issues

## Development

### Project Structure
```
client-desktop/
├── sync_client.py       # Main sync client
├── requirements.txt     # Python dependencies
├── README.md           # This file
├── sync_config.json    # Generated on first run
└── baluhost_sync.log   # Generated log file
```

### Testing
```bash
# Run in development mode with verbose logging
python sync_client.py
```

### Building Standalone Executable
```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller --onefile --name baluhost-sync sync_client.py

# Executable will be in dist/
```

## Roadmap

- [ ] **GUI Application:** Desktop UI with system tray icon
- [ ] **Selective Sync:** Choose specific files/folders to sync
- [ ] **Bandwidth Throttling:** Limit upload/download speeds
- [ ] **Pause/Resume:** Manual sync control
- [ ] **Conflict Resolution UI:** Interactive conflict handling
- [ ] **Progress Indicators:** Real-time sync progress
- [ ] **Cross-platform:** Test on macOS and Linux
- [ ] **Installation Packages:** MSI/DMG/DEB installers

## License

Part of BaluHost NAS Management System.

## Support

For issues or questions, check the main BaluHost documentation.
