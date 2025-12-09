#!/usr/bin/env python3
"""Fix camera_backups table schema."""
import sqlite3

conn = sqlite3.connect('baluhost.db')

# Drop old table
conn.execute('DROP TABLE IF EXISTS camera_backups')

# Create new table with correct schema
conn.execute('''
CREATE TABLE camera_backups (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    quality TEXT NOT NULL DEFAULT 'original',
    wifi_only INTEGER NOT NULL DEFAULT 1,
    delete_after_upload INTEGER NOT NULL DEFAULT 0,
    video_backup INTEGER NOT NULL DEFAULT 1,
    max_video_size_mb INTEGER NOT NULL DEFAULT 500,
    last_backup DATETIME,
    total_photos INTEGER NOT NULL DEFAULT 0,
    total_videos INTEGER NOT NULL DEFAULT 0,
    pending_uploads INTEGER NOT NULL DEFAULT 0,
    failed_uploads INTEGER NOT NULL DEFAULT 0,
    storage_used_bytes INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME,
    FOREIGN KEY (device_id) REFERENCES mobile_devices (id) ON DELETE CASCADE
)
''')

conn.commit()
print('Table camera_backups recreated successfully!')
conn.close()
