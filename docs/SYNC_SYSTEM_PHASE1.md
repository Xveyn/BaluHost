# Phase 1: Local Network File Sync & WebDAV

## Overview

Phase 1 enables local network file synchronization for BaluHost NAS. Clients can:
- Register devices for sync
- Detect file changes (delta sync)
- Handle conflicts automatically or manually
- Track file versions
- Access files via WebDAV as network drives

## Features Implemented

### ✅ Sync API Endpoints

- **POST /api/sync/register** - Register a device for synchronization
- **GET /api/sync/status/{device_id}** - Get sync status for a device
- **POST /api/sync/changes** - Detect changes with delta sync
- **POST /api/sync/conflicts/{file_path}/resolve** - Resolve file conflicts
- **GET /api/sync/history/{file_path}** - Get version history for a file

### ✅ Database Models

- **SyncState** - Track sync state for each device
- **SyncMetadata** - Store file-level sync metadata (hash, timestamps)
- **FileVersion** - Keep historical versions for rollback

### ✅ File Sync Service

- `calculate_file_hash()` - SHA256 content detection
- `register_device()` - Device registration
- `detect_changes()` - Delta sync with conflict detection
- `resolve_conflict()` - Multiple resolution strategies
- `_create_file_version()` - Version tracking

### ✅ WebDAV Provider (Partial)

- Basic WebDAV resource wrapper
- File operations (create, delete, list)
- Ready for mounting as network drive

## Database Schema

```sql
CREATE TABLE sync_states (
    id INTEGER PRIMARY KEY,
    user_id INTEGER FOREIGN KEY,
    device_id STRING UNIQUE,
    device_name STRING,
    last_sync DATETIME,
    last_change_token STRING,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE sync_metadata (
    id INTEGER PRIMARY KEY,
    file_metadata_id INTEGER FOREIGN KEY,
    sync_state_id INTEGER FOREIGN KEY,
    content_hash STRING,
    file_size INTEGER,
    local_modified_at DATETIME,
    sync_modified_at DATETIME,
    server_modified_at DATETIME,
    is_deleted BOOLEAN,
    conflict_detected BOOLEAN,
    conflict_resolution STRING,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE file_versions (
    id INTEGER PRIMARY KEY,
    file_metadata_id INTEGER FOREIGN KEY,
    version_number INTEGER,
    file_path STRING,
    file_size INTEGER,
    content_hash STRING,
    created_at DATETIME,
    created_by_id INTEGER FOREIGN KEY,
    change_reason STRING
);
```

## API Examples

### Register Device

```bash
curl -X POST http://localhost:8000/api/sync/register \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "iphone-12345",
    "device_name": "iPhone XS"
  }'

Response:
{
  "device_id": "iphone-12345",
  "device_name": "iPhone XS",
  "status": "registered",
  "change_token": "uuid-..."
}
```

### Detect Changes

```bash
curl -X POST http://localhost:8000/api/sync/changes \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "iphone-12345",
    "file_list": [
      {
        "path": "/Documents/file1.txt",
        "hash": "sha256abc123...",
        "size": 1024,
        "modified_at": "2025-01-01T12:00:00Z"
      }
    ]
  }'

Response:
{
  "to_download": [
    {
      "path": "/Documents/file2.txt",
      "action": "add",
      "size": 2048,
      "modified_at": "2025-01-01T13:00:00Z"
    }
  ],
  "to_delete": [
    {"path": "/Documents/old_file.txt"}
  ],
  "conflicts": [
    {
      "path": "/Documents/conflict.txt",
      "client_hash": "hash1...",
      "server_hash": "hash2...",
      "server_modified_at": "2025-01-01T14:00:00Z"
    }
  ],
  "change_token": "new-uuid-..."
}
```

### Resolve Conflict

```bash
curl -X POST http://localhost:8000/api/sync/conflicts/Documents%2Fconflict.txt/resolve \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/Documents/conflict.txt",
    "resolution": "create_version"
  }'

Response:
{
  "file_path": "/Documents/conflict.txt",
  "resolution": "create_version",
  "resolved": true
}
```

### Get File History

```bash
curl -X GET http://localhost:8000/api/sync/history/Documents%2Ffile.txt \
  -H "Authorization: Bearer {token}"

Response:
{
  "file_path": "/Documents/file.txt",
  "versions": [
    {
      "version_number": 3,
      "size": 2048,
      "hash": "sha256new...",
      "created_at": "2025-01-01T14:00:00Z",
      "reason": "conflict"
    },
    {
      "version_number": 2,
      "size": 1024,
      "hash": "sha256old...",
      "created_at": "2025-01-01T13:00:00Z",
      "reason": "sync"
    }
  ]
}
```

## Conflict Resolution Strategies

### 1. keep_server
Use the server version, discard client changes.

### 2. keep_local
Use the client version, overwrite server.

### 3. create_version
Keep both versions - server stays, old version saved in history.

## Implementation Details

### Delta Sync Algorithm

1. Client sends file list with SHA256 hashes
2. Server compares with database:
   - Files with newer hashes = to_download
   - Files not in client list = to_delete
   - Files with conflicting hashes = conflicts
3. Server returns change set with new change_token
4. Client applies changes and syncs back

### Change Detection

- Uses SHA256 content hashing
- Timestamps (local_modified_at vs server_modified_at)
- File size changes
- Deleted flag tracking

### Version Storage

Versions are stored with:
- Version number (auto-incrementing per file)
- Original file path
- Content hash and size
- Creation timestamp
- Change reason (sync, conflict, manual)

## Next Steps (Phase 2)

- [ ] WebDAV server mounting
- [ ] Progressive sync (large files)
- [ ] Bandwidth throttling
- [ ] Selective sync (sync specific folders)
- [ ] Scheduled automatic sync
- [ ] Conflict resolution UI

## Testing

Run sync tests:

```bash
cd backend
python -m pytest tests/test_sync.py -v
```

## Status

- ✅ API endpoints complete
- ✅ Database models & migrations
- ✅ Sync service (core logic)
- ⏳ WebDAV server (WIP)
- ⏳ Client implementation (next phase)
- ⏳ Integration tests

