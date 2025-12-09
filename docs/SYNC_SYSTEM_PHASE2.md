# Phase 2: Progressive Sync, Scheduling & Selective Sync

## Overview

Phase 2 adds sophisticated sync features for enterprise use:
- Chunked uploads for large files (resumable)
- Automatic scheduled syncs
- Selective folder synchronization
- Bandwidth throttling
- WebDAV network drive mounting

## Features Implemented

### ✅ Progressive/Chunked Uploads

**API Endpoints:**
- `POST /api/sync/upload/start` - Start chunked upload
- `POST /api/sync/upload/{upload_id}/chunk/{chunk_number}` - Upload chunk
- `GET /api/sync/upload/{upload_id}/progress` - Check progress
- `POST /api/sync/upload/{upload_id}/resume` - Resume paused upload
- `DELETE /api/sync/upload/{upload_id}` - Cancel upload

**Features:**
- 5MB default chunk size (configurable)
- SHA256 integrity verification per chunk
- Resume from any chunk
- Automatic cleanup of expired uploads (7 days)
- Progress tracking

### ✅ Bandwidth Management

**API Endpoints:**
- `POST /api/sync/bandwidth/limit` - Set speed limits
- `GET /api/sync/bandwidth/limit` - Get current limits

**Features:**
- Upload/download speed limits (bytes/sec)
- Time-based throttling windows
- Per-user configuration

### ✅ Scheduled Syncs

**API Endpoints:**
- `POST /api/sync/schedule/create` - Create sync schedule
- `GET /api/sync/schedule/list` - List schedules
- `POST /api/sync/schedule/{id}/disable` - Disable schedule

**Schedule Types:**
- Daily (at specific time)
- Weekly (day + time)
- Monthly (date + time)
- On Change (triggered by file changes)

**Configuration:**
- Automatic conflict resolution (keep_newest, keep_local, keep_server)
- Deletion sync option
- Next run prediction

### ✅ Selective Sync

**API Endpoints:**
- `POST /api/sync/selective/configure` - Set folders to sync
- `GET /api/sync/selective/list/{device_id}` - List config

**Features:**
- Per-folder enable/disable
- Include/exclude subfolders
- Per-device configuration
- Storage optimization

### ✅ Database Models

**ChunkedUpload**
```python
- upload_id: UUID
- file_metadata_id: FK
- total_size, uploaded_bytes
- completed_chunks / total_chunks
- resume_token
- expires_at (auto-cleanup)
```

**SyncBandwidthLimit**
```python
- user_id: FK
- upload_speed_limit (bytes/sec)
- download_speed_limit
- throttle_enabled
- throttle_start_hour, throttle_end_hour
```

**SyncSchedule**
```python
- user_id, device_id
- schedule_type (daily/weekly/monthly/on_change)
- time_of_day, day_of_week, day_of_month
- next_run_at, last_run_at
- resolve_conflicts strategy
```

**SelectiveSync**
```python
- user_id, device_id
- folder_path
- include_subfolders
- is_enabled
```

## API Examples

### Start Chunked Upload

```bash
curl -X POST http://localhost:8000/api/sync/upload/start \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "laptop-123",
    "file_path": "/Videos/large_movie.mp4",
    "file_name": "large_movie.mp4",
    "total_size": 2147483648,
    "chunk_size": 10485760
  }'

Response:
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_size": 10485760,
  "total_chunks": 205,
  "resume_token": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Upload Chunk

```bash
curl -X POST http://localhost:8000/api/sync/upload/{upload_id}/chunk/0 \
  -H "Authorization: Bearer {token}" \
  -F "chunk_file=@chunk_000000.bin" \
  -F "chunk_hash=abc123def456..."

Response:
{
  "chunk_number": 0,
  "completed_chunks": 1,
  "total_chunks": 205,
  "progress_percent": 0.49
}
```

### Create Daily Sync Schedule

```bash
curl -X POST http://localhost:8000/api/sync/schedule/create \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "iphone-12345",
    "schedule_type": "daily",
    "time_of_day": "02:00",
    "sync_deletions": true,
    "resolve_conflicts": "keep_newest"
  }'

Response:
{
  "schedule_id": 1,
  "device_id": "iphone-12345",
  "schedule_type": "daily",
  "next_run_at": "2025-01-06T02:00:00"
}
```

### Configure Selective Sync

```bash
curl -X POST http://localhost:8000/api/sync/selective/configure \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "laptop-123",
    "folders": [
      {
        "path": "/Documents",
        "enabled": true,
        "include_subfolders": true
      },
      {
        "path": "/Photos",
        "enabled": false,
        "include_subfolders": true
      },
      {
        "path": "/Projects/Active",
        "enabled": true,
        "include_subfolders": true
      }
    ]
  }'

Response:
{
  "device_id": "laptop-123",
  "folders_configured": 3
}
```

## Implementation Details

### Chunked Upload Flow

1. **Client initiates** - `POST /api/sync/upload/start`
2. **Receive upload_id + chunk_size**
3. **Loop over chunks:**
   - `POST /api/sync/upload/{upload_id}/chunk/{N}`
   - Client calculates SHA256(chunk)
   - Server verifies hash
   - Server stores chunk
4. **On last chunk:**
   - Server assembles chunks → final file
   - Update FileMetadata
   - Delete chunk directory
5. **Resume capability:**
   - `GET /api/sync/upload/{upload_id}/progress`
   - On resume: `POST /api/sync/upload/{upload_id}/resume`
   - Continue from `resume_from_chunk`

### Scheduled Sync Execution

- Background task checks `SyncSchedule.next_run_at` periodically
- Executes sync if due
- Updates `last_run_at` and recalculates `next_run_at`
- Logs execution in audit log

### Selective Sync Logic

- Client only syncs folders marked `is_enabled=true`
- Subfolders only included if `include_subfolders=true`
- Configuration per-device (different devices = different sync folders)
- Storage optimization: exclude large folders from smaller devices

### Bandwidth Throttling

```python
if throttle_enabled and in_throttle_window():
    bytes_to_send = min(
        remaining_data,
        speed_limit * elapsed_seconds
    )
    time.sleep(delay_time)
```

## Services

### ProgressiveSyncService
- Chunk management
- Upload resumption
- Bandwidth limiting

### SyncSchedulerService
- Schedule creation/management
- Next-run calculations
- Schedule execution

### WebDAV Integration
- Network drive mounting
- File operations via ASGI
- Cross-platform support

## Status

- ✅ Chunked upload models & service
- ✅ Progressive sync API endpoints
- ✅ Bandwidth limiting structure
- ✅ Sync scheduler service & API
- ✅ Selective sync configuration
- ⏳ Background task scheduler (APScheduler)
- ⏳ WebDAV ASGI integration
- ⏳ Client implementation
- ⏳ Integration tests

## Next Steps (Phase 3)

- [ ] Background task executor (APScheduler)
- [ ] WebDAV ASGI server
- [ ] Desktop client (Electron)
- [ ] Mobile client support
- [ ] File change watcher
- [ ] Sync conflict UI improvements
- [ ] Performance benchmarking

## Configuration

**Environment Variables:**
```bash
SYNC_CHUNK_SIZE=5242880          # 5MB
SYNC_CHUNK_CLEANUP_DAYS=7
SYNC_MAX_CONCURRENT_UPLOADS=10
SYNC_BANDWIDTH_MONITOR=true
```

## Performance Targets

- **Chunks:** 10-100MB files = 2-20 chunks
- **Large file:** 1GB file ≈ 200 chunks
- **Bandwidth:** 1MB/s upload = 8 hours for 1GB (with limits)
- **Scheduling:** Process 100 schedules < 1 second

## Security Notes

- ✅ Per-user bandwidth limits
- ✅ Device authentication required
- ✅ Chunk integrity verification
- ✅ Admin-only schedule management
- ⏳ Encrypted chunk transfer (TLS)
- ⏳ Rate limiting on uploads

