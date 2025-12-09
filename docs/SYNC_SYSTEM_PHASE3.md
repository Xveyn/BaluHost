# Sync System Phase 3: Background Scheduler & UI

**Status:** ✅ **COMPLETE**  
**Date:** 2024  
**Phase:** 3/3

## Overview

Phase 3 completes the sync infrastructure with:
- ✅ **APScheduler Integration** - Background task execution
- ✅ **Automated Sync Execution** - Scheduled syncs run automatically
- ✅ **Expired Upload Cleanup** - Daily cleanup of abandoned chunks
- ✅ **Sync Settings UI** - React frontend for sync configuration

## Background Scheduler

### Service: `sync_background.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

class SyncBackgroundScheduler:
    """Background scheduler for automated sync operations."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        
    async def start(self):
        """Start the background scheduler."""
        # Check for due syncs every 5 minutes
        self.scheduler.add_job(
            self.check_and_run_due_syncs,
            trigger=IntervalTrigger(minutes=5),
            id='check_sync_schedules',
            replace_existing=True
        )
        
        # Cleanup expired uploads daily at 3 AM
        self.scheduler.add_job(
            self.cleanup_expired_uploads,
            trigger=CronTrigger(hour=3, minute=0),
            id='cleanup_uploads',
            replace_existing=True
        )
        
        self.scheduler.start()
```

### Automated Sync Execution

**check_and_run_due_syncs():**
- Runs every 5 minutes
- Queries `SyncSchedule` for `next_run_at <= now`
- Executes `execute_scheduled_sync()` for each due schedule
- Updates `next_run_at` using `_calculate_next_run()`
- Logs audit events for each execution

**Flow:**
1. Find all schedules with `next_run_at <= current_time`
2. For each schedule:
   - Load sync service with user's database session
   - Call `sync_service.detect_changes(device_id)`
   - Log "sync_schedule_execution" audit event
   - Calculate and update `next_run_at` + `last_run_at`

### Cleanup Job

**cleanup_expired_uploads():**
- Runs daily at 3:00 AM
- Deletes `ChunkedUpload` records older than 7 days
- Removes corresponding `.chunks` files from disk
- Prevents storage bloat from abandoned uploads

## Frontend Sync Settings UI

### Component: `SyncSettings.tsx`

**Location:** `client/src/components/SyncSettings.tsx`  
**Route:** `/sync`  
**Access:** All authenticated users

### Features

#### 1. Device Registration
```tsx
<input placeholder="Device ID (e.g., laptop-123)" />
<input placeholder="Device Name (e.g., My Laptop)" />
<button onClick={registerDevice}>Register</button>
```

- Calls `POST /api/sync/register`
- Displays success/error messages
- Clears form after registration

#### 2. Schedule Creation
```tsx
<input placeholder="Device ID" />
<select> {/* daily, weekly, monthly */} </select>
<input type="time" />
<button onClick={createSchedule}>Create Schedule</button>
```

- Calls `POST /api/sync/schedule/create`
- Configurable schedule types: daily, weekly, monthly
- Time picker for `time_of_day`
- Options for `sync_deletions` and `resolve_conflicts`

#### 3. Bandwidth Limits
```tsx
<input type="number" placeholder="Upload Limit (bytes/sec)" />
<input type="number" placeholder="Download Limit (bytes/sec)" />
<button onClick={saveBandwidthLimits}>Save Limits</button>
```

- Calls `POST /api/sync/bandwidth/limit`
- Sets `upload_speed_limit` and `download_speed_limit`
- Uses bytes per second (e.g., 1048576 for 1 MB/s)

#### 4. Active Schedules
```tsx
{schedules.map(schedule => (
  <div key={schedule.schedule_id}>
    <span>{schedule.device_id}</span>
    <span>{schedule.schedule_type}</span>
    <span>Next: {formatDate(schedule.next_run_at)}</span>
    <button onClick={() => disableSchedule(schedule.schedule_id)}>
      <Trash2 />
    </button>
  </div>
))}
```

- Lists all active schedules
- Shows next/last run times
- Disable button calls `POST /api/sync/schedule/{id}/disable`

## Integration

### App Lifecycle

**backend/app/main.py:**
```python
from app.services import sync_background

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await sync_background.start_sync_scheduler()
    yield
    # Shutdown
    await sync_background.stop_sync_scheduler()
```

### Navigation

**client/src/components/Layout.tsx:**
```tsx
const navIcon = {
  sync: (
    <svg viewBox="0 0 24 24">
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <circle cx="12" cy="12" r="2" fill="currentColor" />
    </svg>
  )
}

navItems = [
  { path: '/sync', label: 'Sync', description: 'File Sync', icon: navIcon.sync }
]
```

## Testing Schedule Execution

### 1. Register Device
```bash
curl -X POST http://localhost:8000/api/sync/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "test-laptop", "device_name": "Test Laptop"}'
```

### 2. Create Schedule (5 minutes from now)
```bash
# Get current time + 5 minutes
TIME=$(date -u -d '+5 minutes' '+%H:%M')

curl -X POST http://localhost:8000/api/sync/schedule/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"device_id\": \"test-laptop\",
    \"schedule_type\": \"daily\",
    \"time_of_day\": \"$TIME\",
    \"sync_deletions\": true,
    \"resolve_conflicts\": \"keep_newest\"
  }"
```

### 3. Monitor Logs
```bash
tail -f backend/tmp/audit/*.log
```

Expected output after 5 minutes:
```json
{
  "action": "sync_schedule_execution",
  "user_id": 1,
  "resource_type": "sync_schedule",
  "resource_id": "test-laptop",
  "details": {
    "schedule_id": 1,
    "device_id": "test-laptop",
    "changes_detected": 0
  }
}
```

## Performance Considerations

### Schedule Check Interval
- **Current:** 5 minutes
- **Trade-off:** Lower = more responsive, higher CPU usage
- **Recommendation:** 5 minutes for most use cases, 1 minute for high-frequency sync

### Cleanup Frequency
- **Current:** Daily at 3:00 AM
- **Retention:** 7 days for abandoned uploads
- **Disk Impact:** Each chunk = 5 MB, max ~100 concurrent uploads = 500 MB

### Database Queries
```sql
-- Optimized with index on next_run_at
SELECT * FROM sync_schedules 
WHERE next_run_at <= NOW() 
AND enabled = 1;
```

**Index Creation:**
```python
# In sync_progress.py model
__table_args__ = (
    Index('idx_sync_schedule_next_run', 'next_run_at'),
)
```

## Error Handling

### Failed Sync Execution
- **Behavior:** Log error, continue to next schedule
- **Recovery:** Next check (5 min) will retry if `next_run_at` still due
- **Notification:** Audit log with level "error"

### Scheduler Crash
- **Behavior:** App startup re-initializes scheduler
- **State:** Persistent in database, no sync loss
- **Recovery:** Missed syncs execute on next check

## Security

### User Isolation
- Each schedule runs in user's database session
- File access respects ownership and permissions
- Audit logs track user_id for all sync operations

### API Authentication
- All endpoints require JWT bearer token
- Device registration validates user identity
- Schedules tied to user account

## Next Steps

### Desktop Client (TODO)
- Python/TypeScript file watcher application
- `watchdog` integration for real-time file monitoring
- Auto-sync on file change detection
- Cross-platform support (Windows, macOS, Linux)

### Mobile Client (TODO)
- React Native or Flutter app
- Background sync with iOS/Android schedulers
- Photo/video auto-upload
- Selective folder sync

### WebDAV Integration (TODO)
- Complete `webdav_asgi.py` ASGI adapter
- Test mounting on Windows (Network Drive)
- Test mounting on macOS (Finder → Connect to Server)
- Test mounting on Linux (`mount.davfs`)

### Performance Testing (TODO)
- Load test: 100+ concurrent syncs
- Benchmark: Large file chunked uploads
- Monitor: Scheduler CPU/memory usage
- Optimize: Database query performance

## Dependencies

**Added in Phase 3:**
```toml
[tool.poetry.dependencies]
apscheduler = "^3.10.0"
watchdog = "^3.0.0"
```

**Install:**
```bash
cd backend
pip install apscheduler watchdog
```

## Files Modified

### Backend
- `backend/pyproject.toml` - Added dependencies
- `backend/app/services/sync_background.py` - **NEW** scheduler service
- `backend/app/main.py` - Integrated lifecycle hooks

### Frontend
- `client/src/components/SyncSettings.tsx` - **NEW** sync UI
- `client/src/App.tsx` - Added `/sync` route
- `client/src/components/Layout.tsx` - Added sync navigation

## Summary

Phase 3 completes the **automated sync infrastructure**:

✅ **Background Scheduler** - APScheduler with interval and cron triggers  
✅ **Automated Execution** - Syncs run every 5 minutes based on schedules  
✅ **Cleanup Jobs** - Daily removal of expired uploads  
✅ **Frontend UI** - Complete sync configuration interface  
✅ **App Integration** - Lifecycle management in FastAPI  
✅ **Navigation** - Sync page accessible from main menu  

**All three phases now complete:**
- Phase 1: Core sync infrastructure (API, models, services)
- Phase 2: Progressive features (chunked uploads, bandwidth, scheduling)
- Phase 3: Background automation & UI (scheduler, frontend)

**Ready for:**
- Desktop client development
- WebDAV network drive testing
- Performance benchmarking
- Production deployment
