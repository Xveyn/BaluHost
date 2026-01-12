import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(__file__).resolve().parents[1] / 'baluhost.db'
print('Using DB:', DB)
con = sqlite3.connect(str(DB))
cur = con.cursor()

# Find a sync_state
cur.execute("SELECT id, user_id, device_id FROM sync_states LIMIT 1")
row = cur.fetchone()
if not row:
    print('No sync_state found, aborting')
    con.close()
    exit(1)

sync_state_id, user_id, device_id = row
print('Found SyncState:', sync_state_id, user_id, device_id)

# Ensure a file_metadata exists for this user
cur.execute("SELECT id, path FROM file_metadata WHERE owner_id = ? LIMIT 1", (user_id,))
fm = cur.fetchone()
if fm:
    fm_id, fm_path = fm
    print('Found existing FileMetadata:', fm_id, fm_path)
else:
    path = f"/test-sync/{device_id}-test.txt"
    name = f"{device_id}-test.txt"
    size_bytes = 123
    is_directory = 0
    cur.execute(
        "INSERT INTO file_metadata (path, name, owner_id, size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)",
        (path, name, user_id, size_bytes, is_directory)
    )
    fm_id = cur.lastrowid
    con.commit()
    print('Inserted FileMetadata id=', fm_id)

# Insert a SyncMetadata row
now = datetime.now(timezone.utc).isoformat(sep=' ')
content_hash = 'deadbeef'*8
file_size = 123
is_deleted = 0
conflict_detected = 0

cur.execute(
    "INSERT INTO sync_metadata (file_metadata_id, sync_state_id, content_hash, file_size, local_modified_at, server_modified_at, is_deleted, conflict_detected) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (fm_id, sync_state_id, content_hash, file_size, now, now, is_deleted, conflict_detected)
)
sm_id = cur.lastrowid
con.commit()
print('Inserted SyncMetadata id=', sm_id)

con.close()
