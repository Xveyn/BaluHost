"""Run due sync schedules using raw sqlite (avoids SQLAlchemy mapper issues).

This script:
- Queries `sync_schedules` for due schedules
- Looks up `sync_states` and `sync_metadata` rows
- Builds a simple plan (to_download/to_delete/conflicts)
- Updates `sync_metadata.sync_modified_at`, `sync_states.last_sync` and `last_change_token`, and `sync_schedules.last_run_at` and `next_run_at`
- Prints the plan per schedule

Note: This is a test runner for local development only.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
import uuid

DB = Path(__file__).resolve().parents[1] / 'baluhost.db'
print('Using DB:', DB)
con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row
cur = con.cursor()

now = datetime.now(timezone.utc)
now_iso = now.isoformat(sep=' ')

# Find due schedules
cur.execute("""
SELECT * FROM sync_schedules
WHERE is_active = 1
  AND next_run_at IS NOT NULL
  AND datetime(next_run_at) <= datetime(?)
""", (now_iso,))
due = cur.fetchall()

if not due:
    print('No due schedules found')
    con.close()
    exit(0)

for s in due:
    sid = s['id']
    user_id = s['user_id']
    device_id = s['device_id']
    schedule_type = s['schedule_type']
    time_of_day = s['time_of_day']
    day_of_week = s['day_of_week']
    day_of_month = s['day_of_month']

    print(f"Processing schedule id={sid} device={device_id} user={user_id} next_run_at={s['next_run_at']}")

    # Find sync_state for device
    cur.execute("SELECT * FROM sync_states WHERE user_id=? AND device_id=? LIMIT 1", (user_id, device_id))
    ss = cur.fetchone()
    if not ss:
        print('  No SyncState registered for device, skipping')
        continue
    ss_id = ss['id']

    # Gather sync_metadata for this sync_state
    cur.execute("SELECT * FROM sync_metadata WHERE sync_state_id=?", (ss_id,))
    metas = cur.fetchall()

    plan = {"to_download": [], "to_delete": [], "conflicts": []}

    for m in metas:
        if m['conflict_detected']:
            plan['conflicts'].append({
                'id': m['id'],
                'file_metadata_id': m['file_metadata_id'],
                'local_modified_at': m['local_modified_at'],
                'server_modified_at': m['server_modified_at']
            })
        elif m['is_deleted']:
            plan['to_delete'].append({'id': m['id'], 'file_metadata_id': m['file_metadata_id']})
        else:
            plan['to_download'].append({
                'id': m['id'],
                'file_metadata_id': m['file_metadata_id'],
                'content_hash': m['content_hash'],
                'file_size': m['file_size'],
                'server_modified_at': m['server_modified_at']
            })

        # update sync_modified_at
        cur.execute("UPDATE sync_metadata SET sync_modified_at = ? WHERE id = ?", (now_iso, m['id']))

    # update sync_state last_sync and last_change_token
    token = str(uuid.uuid4())
    cur.execute("UPDATE sync_states SET last_sync = ?, last_change_token = ? WHERE id = ?", (now_iso, token, ss_id))

    # update schedule last_run_at and compute next_run_at similar to service
    cur.execute("UPDATE sync_schedules SET last_run_at = ? WHERE id = ?", (now_iso, sid))

    # compute next_run_at
    def compute_next_run(rt_type, time_of_day, day_of_week, day_of_month):
        now_local = datetime.now(timezone.utc)
        if rt_type == 'daily':
            hour, minute = map(int, (time_of_day or '02:00').split(':'))
            next_run = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now_local:
                next_run += timedelta(days=1)
            return next_run
        if rt_type == 'weekly':
            hour, minute = map(int, (time_of_day or '02:00').split(':'))
            target = int(day_of_week) if day_of_week is not None else 0
            next_run = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = target - now_local.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run += timedelta(days=days_ahead)
            return next_run
        if rt_type == 'monthly':
            hour, minute = map(int, (time_of_day or '02:00').split(':'))
            target = int(day_of_month) if day_of_month is not None else 1
            try:
                next_run = now_local.replace(day=target, hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
                # fallback to first of next month
                next_run = (now_local + timedelta(days=32)).replace(day=target, hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now_local:
                next_run = (next_run + timedelta(days=32)).replace(day=target)
            return next_run
        return None

    nr = compute_next_run(schedule_type, time_of_day, day_of_week, day_of_month)
    if nr:
        nr_iso = nr.isoformat(sep=' ')
        cur.execute("UPDATE sync_schedules SET next_run_at = ? WHERE id = ?", (nr_iso, sid))
    else:
        cur.execute("UPDATE sync_schedules SET next_run_at = NULL WHERE id = ?", (sid,))

    con.commit()

    print('  Plan:')
    print('   to_download:', len(plan['to_download']))
    print('   to_delete:', len(plan['to_delete']))
    print('   conflicts:', len(plan['conflicts']))

con.close()
print('Done')
