# Backup & Restore System

## Overview

The BaluHost NAS Manager includes a comprehensive backup and restore system that allows administrators to create full system backups and restore them when needed. This feature is essential for disaster recovery and data protection.

## Features

### ✅ Implemented

  - Database backup (SQLite)
  - File storage backup (all user files)
  - Compressed archives (tar.gz format)
  - Automatic retention management

  - Create backups on-demand
  - List all available backups
  - Download backup files
  - Delete old backups
  - Restore from backup

  - All backup operations logged
  - Success/failure tracking
  - User attribution

  - Configurable max backup count
  - Configurable retention days
  - Automatic cleanup of old backups

  - Settings page Backup tab
  - Create backup button
  - Backup list with status
  - Download/Restore/Delete actions
  - Confirmation dialogs

## Configuration

Backup settings are configured in `backend/app/core/config.py`:

```python
nas_backup_path: str = "./backups"  # Dev: ./dev-backups
nas_backup_retention_days: int = 30  # Keep backups for 30 days
nas_backup_max_count: int = 10  # Keep max 10 backups
```

## API Endpoints

All backup endpoints require **Admin role**.

### Create Backup
```
POST /api/backups
Content-Type: application/json

{
  "backup_type": "full",  // full | incremental | database_only | files_only
  "includes_database": true,
  "includes_files": true,
  "includes_config": false
}

Response: 201 Created
{
  "id": 1,
  "filename": "backup_20250101_120000.tar.gz",
  "size_mb": 123.45,
  "status": "completed",
  "created_at": "2025-01-01T12:00:00Z",
  ...
}
```

### List Backups
```
GET /api/backups

Response: 200 OK
{
  "backups": [...],
  "total_size_bytes": 1234567890,
  "total_size_mb": 1177.38
}
```

### Get Backup Details
```
GET /api/backups/{backup_id}

Response: 200 OK
{
  "id": 1,
  "filename": "backup_20250101_120000.tar.gz",
  ...
}
```

### Delete Backup
```
DELETE /api/backups/{backup_id}

Response: 204 No Content
```

### Restore Backup
```
POST /api/backups/{backup_id}/restore
Content-Type: application/json

{
  "backup_id": 1,
  "restore_database": true,
  "restore_files": true,
  "restore_config": false,
  "confirm": true  // Required!
}

Response: 200 OK
{
  "success": true,
  "message": "Backup restored successfully. Please restart the application.",
  "backup_id": 1,
  "restored_at": "2025-01-01T12:05:00Z"
}
```

### Download Backup
```
GET /api/backups/{backup_id}/download

Response: 200 OK
Content-Type: application/gzip
Content-Disposition: attachment; filename="backup_20250101_120000.tar.gz"
```

## Usage

### Creating a Backup (UI)

1. Login as admin
2. Navigate to **Settings → Backup** tab
3. Click **"Create Backup"** button
4. Wait for completion (status will show "completed")
5. Backup appears in the list

### Restoring a Backup (UI)

⚠️ **WARNING: This will overwrite all current data!**

1. Navigate to **Settings → Backup** tab
2. Find the backup you want to restore
3. Click the **Restore** icon (↻)
4. Type **"RESTORE"** in the confirmation dialog
5. Click **"Restore Backup"**
6. Wait for completion
7. **Reload the application** when prompted

### Downloading a Backup (UI)

1. Navigate to **Settings → Backup** tab
2. Find the backup you want to download
3. Click the **Download** icon (↓)
4. File will be downloaded to your browser's download folder

### Deleting a Backup (UI)

1. Navigate to **Settings → Backup** tab
2. Find the backup you want to delete
3. Click the **Delete** icon (🗑️)
4. Confirm deletion in the dialog

## Backup Contents

A full backup includes:

```
backup_YYYYMMDD_HHMMSS.tar.gz
└── backup/
    ├── database/
    │   ├── baluhost.db
    │   ├── baluhost.db-wal  (if exists)
    │   └── baluhost.db-shm  (if exists)
    └── files/
        └── [all user files from storage]
```

## Automatic Cleanup

Old backups are automatically cleaned up based on retention policy:


## Database Schema

### Backup Model

```python
class Backup:
    id: int
    filename: str
    filepath: str
    size_bytes: int
    backup_type: str  # full, incremental, database_only, files_only
    status: str  # in_progress, completed, failed
    created_at: datetime
    completed_at: datetime | None
    creator_id: int
    error_message: str | None
    includes_database: bool
    includes_files: bool
    includes_config: bool
```

## Security


## Testing

Run backup service tests:

```bash
cd backend
python -m pytest tests/test_backup.py -v
```

All 8 tests should pass:

## Future Enhancements

### Phase 2 (Not Implemented)


## Troubleshooting

### Backup Creation Fails

**Problem**: Backup status shows "failed"

**Solution**:
1. Check error message in backup details
2. Verify disk space available
3. Check file permissions on backup directory
4. Review audit logs for detailed error

### Restore Fails

**Problem**: Restore operation returns error

**Solution**:
1. Verify backup file exists and is not corrupted
2. Check database file permissions
3. Ensure no active connections to database
4. Check audit logs for detailed error

### Out of Disk Space

**Problem**: Cannot create backup due to insufficient space

**Solution**:
1. Delete old backups manually
2. Reduce `nas_backup_max_count` setting
3. Increase available disk space
4. Use external backup storage (future feature)

## Performance Considerations


## Best Practices

1. **Regular Backups**: Create backups before major system changes
2. **Test Restores**: Periodically test restore functionality
3. **Monitor Disk Space**: Ensure sufficient space for backups
4. **Retention Policy**: Adjust based on available storage
5. **Download Critical Backups**: Store important backups externally

## Related Documentation

