# BaluDesk Architecture

## High-Level Overview

BaluDesk follows a **three-tier architecture** with clear separation of concerns:

```
┌────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                      │
│                    (Electron + React Frontend)                 │
│                                                                │
│  • User Interface (React Components)                           │
│  • System Tray Integration                                     │
│  • IPC Client (communicates with Main Process)                 │
│  • State Management (Zustand)                                  │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         │ Electron IPC (JSON Messages)
                         │
┌────────────────────────┴───────────────────────────────────────┐
│                      Application Layer                         │
│                   (Electron Main Process)                      │
│                                                                │
│  • IPC Bridge (Frontend ↔ C++ Backend)                         │
│  • Process Manager (spawns C++ backend)                        │
│  • System Tray Controller                                      │
│  • Auto-Update Manager                                         │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         │ stdin/stdout JSON Messages
                         │
┌────────────────────────┴───────────────────────────────────────┐
│                         Business Logic Layer                   │
│                         (C++ Sync Engine)                      │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Sync Engine                                             │  │
│  │  • Change Detection (Local + Remote)                     │  │
│  │  • Conflict Resolution                                   │  │
│  │  • Upload/Download Manager                               │  │
│  │  • Queue Management                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Filesystem Watcher                                      │  │
│  │  • Platform-Specific Implementations                     │  │
│  │  • Event Debouncing                                      │  │
│  │  • Change Notification                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  HTTP Client                                             │  │
│  │  • REST API Calls (libcurl)                              │  │
│  │  • JWT Token Management                                  │  │
│  │  • Connection Pooling                                    │  │
│  │  • Retry Logic                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Local Database (SQLite)                                 │  │
│  │  • Sync State                                            │  │
│  │  • File Metadata                                         │  │
│  │  • Conflict History                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         │ HTTPS REST API
                         │
┌────────────────────────┴───────────────────────────────────────┐
│                         Data Layer                             │
│                     (BaluHost NAS Backend)                     │
│                                                                │
│  • File Storage (FastAPI)                                      │
│  • User Management                                             │
│  • Sync Endpoints                                              │
│  • Conflict Resolution API                                     │
└────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Electron Frontend (Presentation Layer)

**Technology**: React 18 + TypeScript + Electron Renderer Process

**Responsibilities**:
- Display UI (Dashboard, Folder List, Settings, Activity Log)
- Handle user input
- Communicate with Main Process via IPC
- Display notifications

**Key Components**:
- `Dashboard.tsx`: Overview of sync status
- `FolderList.tsx`: List of sync folders
- `AddFolderDialog.tsx`: Add new sync folder
- `Settings.tsx`: User preferences
- `ActivityLog.tsx`: Recent file changes

**Communication Pattern**:
```typescript
// Send message to Main Process
window.electron.ipcRenderer.send('add-sync-folder', {
  localPath: '/path/to/local',
  remotePath: '/remote/path'
});

// Listen for response
window.electron.ipcRenderer.on('sync-state-update', (event, data) => {
  updateSyncState(data);
});
```

---

### 2. Electron Main Process (Application Layer)

**Technology**: Node.js + TypeScript

**Responsibilities**:
- Spawn C++ backend as child process
- Bridge communication between Frontend and Backend
- System tray integration
- Window management
- Auto-update logic

**Key Modules**:
- `backend-manager.ts`: Manages C++ backend lifecycle
- `ipc-bridge.ts`: Translates IPC messages to backend commands
- `tray.ts`: System tray icon and menu
- `auto-updater.ts`: Checks for updates

**Communication Pattern**:
```typescript
// Receive from Renderer
ipcMain.on('add-sync-folder', (event, data) => {
  // Forward to C++ Backend via stdin
  backendProcess.stdin.write(JSON.stringify({
    type: 'add_sync_folder',
    payload: data
  }) + '\n');
});

// Receive from C++ Backend via stdout
backendProcess.stdout.on('data', (data) => {
  const message = JSON.parse(data.toString());
  // Forward to Renderer
  mainWindow.webContents.send(message.type, message.payload);
});
```

---

### 3. C++ Sync Engine (Business Logic Layer)

**Technology**: C++17, CMake, libcurl, SQLite, spdlog

**Responsibilities**:
- Monitor local filesystem for changes
- Fetch remote changes from NAS
- Upload/Download files
- Resolve conflicts
- Manage sync state in SQLite

**Core Classes**:

#### `SyncEngine`
```cpp
class SyncEngine {
public:
  void start();
  void stop();
  void addSyncFolder(const std::string& localPath, const std::string& remotePath);
  void removeSyncFolder(const std::string& folderId);
  void pauseSync(const std::string& folderId);
  void resumeSync(const std::string& folderId);
  
private:
  std::unique_ptr<FileWatcher> fileWatcher_;
  std::unique_ptr<HttpClient> httpClient_;
  std::unique_ptr<Database> database_;
  std::unique_ptr<ConflictResolver> conflictResolver_;
};
```

#### `FileWatcher`
```cpp
class FileWatcher {
public:
  virtual void watch(const std::string& path) = 0;
  virtual void stop() = 0;
  void setCallback(std::function<void(const FileEvent&)> callback);
  
protected:
  std::function<void(const FileEvent&)> callback_;
};

// Platform-specific implementations
class FileWatcherWindows : public FileWatcher { /* ... */ };
class FileWatcherMac : public FileWatcher { /* ... */ };
class FileWatcherLinux : public FileWatcher { /* ... */ };
```

#### `HttpClient`
```cpp
class HttpClient {
public:
  HttpClient(const std::string& baseUrl);
  
  // Authentication
  bool login(const std::string& username, const std::string& password);
  void setAuthToken(const std::string& token);
  
  // File Operations
  std::vector<RemoteFile> listFiles(const std::string& path);
  bool uploadFile(const std::string& localPath, const std::string& remotePath);
  bool downloadFile(const std::string& remotePath, const std::string& localPath);
  bool deleteFile(const std::string& remotePath);
  
  // Sync Operations
  std::vector<Change> getChanges(const std::string& since);
  
private:
  CURL* curl_;
  std::string baseUrl_;
  std::string authToken_;
};
```

#### `Database`
```cpp
class Database {
public:
  Database(const std::string& dbPath);
  
  // Sync Folders
  void addSyncFolder(const SyncFolder& folder);
  std::vector<SyncFolder> getSyncFolders();
  void removeSyncFolder(const std::string& folderId);
  
  // File Metadata
  void upsertFileMetadata(const FileMetadata& metadata);
  FileMetadata getFileMetadata(const std::string& path);
  std::vector<FileMetadata> getChangedFilesSince(const std::string& timestamp);
  
  // Sync State
  void updateSyncState(const std::string& folderId, const SyncState& state);
  SyncState getSyncState(const std::string& folderId);
  
  // Conflicts
  void logConflict(const Conflict& conflict);
  std::vector<Conflict> getPendingConflicts();
  
private:
  sqlite3* db_;
};
```

#### `ConflictResolver`
```cpp
class ConflictResolver {
public:
  enum Strategy {
    LAST_WRITE_WINS,
    KEEP_BOTH,
    MANUAL
  };
  
  void setStrategy(Strategy strategy);
  ConflictResolution resolve(const Conflict& conflict);
  
private:
  Strategy strategy_;
};
```

**Database Schema**:
```sql
-- Sync Folders Configuration
CREATE TABLE sync_folders (
  id TEXT PRIMARY KEY,
  local_path TEXT NOT NULL,
  remote_path TEXT NOT NULL,
  status TEXT NOT NULL, -- active, paused, error
  created_at TEXT NOT NULL,
  last_sync TEXT
);

-- File Metadata Cache
CREATE TABLE file_metadata (
  path TEXT PRIMARY KEY,
  folder_id TEXT NOT NULL,
  size INTEGER NOT NULL,
  modified_at TEXT NOT NULL,
  checksum TEXT,
  is_directory INTEGER NOT NULL,
  sync_status TEXT NOT NULL, -- synced, pending_upload, pending_download
  FOREIGN KEY (folder_id) REFERENCES sync_folders(id)
);

-- Sync State Tracking
CREATE TABLE sync_state (
  folder_id TEXT PRIMARY KEY,
  last_local_scan TEXT,
  last_remote_scan TEXT,
  pending_uploads INTEGER DEFAULT 0,
  pending_downloads INTEGER DEFAULT 0,
  FOREIGN KEY (folder_id) REFERENCES sync_folders(id)
);

-- Conflict History
CREATE TABLE conflicts (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  folder_id TEXT NOT NULL,
  local_modified TEXT,
  remote_modified TEXT,
  resolution TEXT, -- last_write_wins, keep_both, manual_local, manual_remote
  resolved_at TEXT,
  FOREIGN KEY (folder_id) REFERENCES sync_folders(id)
);

-- Activity Log
CREATE TABLE activity_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  folder_id TEXT NOT NULL,
  action TEXT NOT NULL, -- uploaded, downloaded, deleted, conflict
  path TEXT NOT NULL,
  details TEXT,
  FOREIGN KEY (folder_id) REFERENCES sync_folders(id)
);
```

---

## Sync Algorithm

### Two-Way Synchronization

```
1. Local Change Detection (Filesystem Watcher)
   ↓
2. Remote Change Detection (API Poll)
   ↓
3. Conflict Detection
   ↓
4. Conflict Resolution (if needed)
   ↓
5. Apply Changes (Upload/Download)
   ↓
6. Update Local Database
```

**Detailed Flow**:

1. **Startup**: Load sync folders from database
2. **Initial Scan**: Compare local filesystem with database
3. **Detect Local Changes**: Filesystem watcher fires events
4. **Fetch Remote Changes**: Poll `/api/sync/changes?since={last_sync}`
5. **Conflict Check**: Compare `local_modified` vs `remote_modified`
6. **Resolve Conflicts**: Apply strategy (Last-Write-Wins, Keep Both, Manual)
7. **Execute Sync**:
   - Upload modified local files
   - Download modified remote files
   - Delete files marked for deletion
8. **Update Database**: Update `file_metadata` and `sync_state`

---

## IPC Protocol

### Message Format

```json
{
  "type": "message_type",
  "payload": { /* data */ }
}
```

### Frontend → Backend Messages

```typescript
// Add Sync Folder
{
  "type": "add_sync_folder",
  "payload": {
    "localPath": "/Users/john/Documents",
    "remotePath": "/Documents"
  }
}

// Remove Sync Folder
{
  "type": "remove_sync_folder",
  "payload": {
    "folderId": "abc123"
  }
}

// Pause/Resume Sync
{
  "type": "pause_sync",
  "payload": { "folderId": "abc123" }
}

{
  "type": "resume_sync",
  "payload": { "folderId": "abc123" }
}

// Get Sync State
{
  "type": "get_sync_state",
  "payload": {}
}

// Update Settings
{
  "type": "update_settings",
  "payload": {
    "bandwidthLimit": 1048576, // bytes/sec
    "conflictStrategy": "last_write_wins"
  }
}
```

### Backend → Frontend Messages

```typescript
// Sync State Update
{
  "type": "sync_state_update",
  "payload": {
    "status": "syncing", // idle, syncing, paused, error
    "uploadSpeed": 524288, // bytes/sec
    "downloadSpeed": 1048576,
    "lastSync": "2026-01-02T14:30:00Z",
    "folders": [
      {
        "id": "abc123",
        "localPath": "/Users/john/Documents",
        "status": "syncing",
        "pendingUploads": 5,
        "pendingDownloads": 2
      }
    ]
  }
}

// File Change Event
{
  "type": "file_change",
  "payload": {
    "path": "/Users/john/Documents/report.pdf",
    "action": "uploaded", // uploaded, downloaded, deleted
    "size": 1048576,
    "timestamp": "2026-01-02T14:35:00Z"
  }
}

// Conflict Detected
{
  "type": "conflict_detected",
  "payload": {
    "path": "/Users/john/Documents/data.xlsx",
    "localModified": "2026-01-02T14:30:00Z",
    "remoteModified": "2026-01-02T14:32:00Z",
    "requiresManualResolution": true
  }
}

// Error
{
  "type": "error",
  "payload": {
    "code": "AUTH_FAILED",
    "message": "Authentication failed. Please re-login.",
    "details": "Token expired"
  }
}
```

---

## Security Considerations

### Credential Storage

- **Windows**: Windows Credential Manager API
- **macOS**: Keychain Services API
- **Linux**: libsecret (GNOME Keyring, KWallet)

```cpp
class CredentialStore {
public:
  static void saveCredentials(const std::string& username, const std::string& token);
  static std::string loadToken(const std::string& username);
  static void deleteCredentials(const std::string& username);
};
```

### Secure Communication

- All HTTP requests use HTTPS (TLS 1.2+)
- Certificate validation enabled (can disable for self-signed)
- JWT token in Authorization header
- Token refresh before expiry

### IPC Security

- Renderer process is sandboxed
- No direct filesystem access from renderer
- All file operations go through IPC
- JSON schema validation on all messages

---

## Performance Optimizations

### 1. Chunked Upload/Download
```cpp
// Upload large files in 5MB chunks
const size_t CHUNK_SIZE = 5 * 1024 * 1024;

bool uploadFile(const std::string& path) {
  size_t fileSize = getFileSize(path);
  size_t chunks = (fileSize + CHUNK_SIZE - 1) / CHUNK_SIZE;
  
  for (size_t i = 0; i < chunks; ++i) {
    size_t offset = i * CHUNK_SIZE;
    size_t length = std::min(CHUNK_SIZE, fileSize - offset);
    uploadChunk(path, offset, length);
  }
}
```

### 2. Connection Pooling
```cpp
// Reuse CURL handles
std::vector<CURL*> curlPool_;
```

### 3. Batch Operations
```cpp
// Upload multiple small files in one request
std::vector<std::string> batchUpload(const std::vector<std::string>& files);
```

### 4. Database Indexing
```sql
CREATE INDEX idx_file_metadata_folder ON file_metadata(folder_id);
CREATE INDEX idx_file_metadata_status ON file_metadata(sync_status);
CREATE INDEX idx_conflicts_resolved ON conflicts(resolved_at);
```

---

## Error Handling

### Retry Strategy

```cpp
class RetryPolicy {
public:
  static constexpr int MAX_RETRIES = 3;
  static constexpr int BASE_DELAY_MS = 1000;
  
  bool shouldRetry(int attemptCount, const Error& error) {
    if (attemptCount >= MAX_RETRIES) return false;
    return error.isTransient(); // network errors, 5xx responses
  }
  
  int getDelayMs(int attemptCount) {
    return BASE_DELAY_MS * std::pow(2, attemptCount); // exponential backoff
  }
};
```

### Error Types

```cpp
enum class ErrorCode {
  // Network Errors
  NETWORK_UNREACHABLE,
  CONNECTION_TIMEOUT,
  DNS_RESOLUTION_FAILED,
  
  // Auth Errors
  AUTH_FAILED,
  TOKEN_EXPIRED,
  INSUFFICIENT_PERMISSIONS,
  
  // File Errors
  FILE_NOT_FOUND,
  FILE_ACCESS_DENIED,
  DISK_FULL,
  
  // Sync Errors
  CONFLICT_DETECTED,
  CHECKSUM_MISMATCH,
  QUOTA_EXCEEDED
};
```

---

## Testing Strategy

### C++ Unit Tests (Google Test)

```cpp
TEST(SyncEngineTest, DetectsLocalChanges) {
  SyncEngine engine;
  MockFileWatcher watcher;
  MockHttpClient client;
  
  engine.setFileWatcher(&watcher);
  engine.setHttpClient(&client);
  
  // Simulate file creation
  watcher.fireEvent(FileEvent{
    .path = "/test/file.txt",
    .action = FileAction::CREATED
  });
  
  // Assert upload was triggered
  EXPECT_TRUE(client.wasUploadCalled("/test/file.txt"));
}
```

### Electron E2E Tests (Playwright)

```typescript
test('user can add sync folder', async ({ page }) => {
  await page.click('[data-testid="add-folder-button"]');
  await page.fill('[data-testid="local-path"]', '/Users/test/Documents');
  await page.fill('[data-testid="remote-path"]', '/Documents');
  await page.click('[data-testid="submit-button"]');
  
  await expect(page.locator('[data-testid="folder-list"]')).toContainText('Documents');
});
```

---

## Future Enhancements

1. **Delta Sync**: Only transfer changed blocks (rsync-style)
2. **P2P Sync**: Direct device-to-device synchronization
3. **Version History**: Keep file versions (like Dropbox)
4. **Smart Sync**: Cloud-only files (download on demand)
5. **LAN Sync**: Faster sync when on same network
6. **Mobile Apps**: iOS/Android clients

---

**Last Updated**: January 2, 2026  
**Status**: 🔴 Planning Phase
