#!/usr/bin/env python3
"""Fix sync_folders table schema."""
import sqlite3

conn = sqlite3.connect('baluhost.db')

# Drop old table
conn.execute('DROP TABLE IF EXISTS sync_folders')

# Create new table with correct schema
conn.execute('''
CREATE TABLE sync_folders (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    local_path TEXT NOT NULL,
    remote_path TEXT NOT NULL,
    sync_type TEXT NOT NULL DEFAULT 'bidirectional',
    auto_sync INTEGER NOT NULL DEFAULT 1,
    last_sync DATETIME,
    status TEXT NOT NULL DEFAULT 'idle',
    error_message TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME,
    FOREIGN KEY (device_id) REFERENCES mobile_devices (id) ON DELETE CASCADE
)
''')

conn.commit()
print('Table sync_folders recreated successfully!')
conn.close()
