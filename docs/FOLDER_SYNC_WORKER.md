# Folder Sync Worker Implementation

## Overview
The `FolderSyncWorker` provides robust background synchronization for Android app folders using WorkManager and follows Android best practices.

## Architecture

### Components
1. **FolderSyncWorker** - CoroutineWorker with Hilt injection
2. **LocalFolderScanner** - SAF-based file scanning with hash calculation
3. **SyncRepository** - API integration for chunked uploads/downloads
4. **FolderSyncViewModel** - UI integration and work scheduling

### Key Features
- ✅ **Chunked Upload**: 5MB chunks for large files with resume capability
- ✅ **Change Detection**: SHA-256 hash comparison for efficient sync
- ✅ **Progress Tracking**: Real-time progress updates via WorkManager Progress API
- ✅ **Retry Logic**: Exponential backoff with 3 retries for network failures
- ✅ **Battery Optimization**: Respects Android battery constraints
- ✅ **Bidirectional Sync**: Supports upload-only, download-only, and two-way sync

## Sync Types

### 1. Upload-Only (`SyncType.UPLOAD_ONLY`)
- Scans local folder for files
- Compares with server files using SHA-256 hashes
- Uploads new or modified files
- Skips files that match exclude patterns

### 2. Download-Only (`SyncType.DOWNLOAD_ONLY`)
- Fetches remote file list from server
- Compares with local files using hashes
- Downloads new or modified files to SAF folder

### 3. Bidirectional (`SyncType.BIDIRECTIONAL`)
- Performs upload sync first
- Then performs download sync
- Future: Will integrate conflict resolution

## WorkManager Configuration

### One-Time Sync (Manual Trigger)
```kotlin
val workRequest = FolderSyncWorker.createOneTimeRequest(
    folderId = 123L,
    isManual = true
)
workManager.enqueue(workRequest)
```

**Constraints:**
- Requires network connectivity
- Exponential backoff: 30 seconds initial delay
- Max retries: 3

### Periodic Sync (Auto-Sync)
```kotlin
val periodicWork = FolderSyncWorker.createPeriodicRequest(folderId = 123L)
workManager.enqueueUniquePeriodicWork(
    "folder_sync_work_123",
    ExistingPeriodicWorkPolicy.REPLACE,
    periodicWork
)
```

**Configuration:**
- Runs every 6 hours
- Flex interval: 15 minutes
- Requires battery not low
- Requires network connectivity

## Chunked Upload Implementation

### Small Files (< 5MB)
Direct upload in single request:
```
POST /mobile/upload/file/{folder_id}?remote_path=/path/to/file
Content-Type: multipart/form-data
```

### Large Files (>= 5MB)
Three-phase chunked upload:

#### Phase 1: Initiate
```
POST /mobile/upload/chunked/initiate
{
  "folder_id": 123,
  "remote_path": "/path/to/file",
  "file_size": 10485760,
  "file_hash": "abc123...",
  "total_chunks": 2
}
```

**Response:**
```json
{
  "upload_id": "upload_uuid",
  "total_chunks": 2,
  "chunk_size": 5242880
}
```

#### Phase 2: Upload Chunks
```
POST /mobile/upload/chunked/chunk
Content-Type: multipart/form-data

metadata: {
  "upload_id": "upload_uuid",
  "chunk_index": 0,
  "chunk_hash": "def456..."
}
chunk: <binary data>
```

#### Phase 3: Finalize
```
POST /mobile/upload/chunked/{upload_id}/finalize
```

### Error Handling
If any chunk fails:
```
DELETE /mobile/upload/chunked/{upload_id}/cancel
```

## Progress Tracking

The Worker reports progress using WorkManager Progress API:

```kotlin
setProgress(workDataOf(
    PROGRESS_STATUS to "Hochladen: 50%",
    PROGRESS_CURRENT to 5,
    PROGRESS_TOTAL to 10,
    PROGRESS_FILE to "document.pdf"
))
```

### Progress Keys
- `PROGRESS_STATUS` - Human-readable status (German)
- `PROGRESS_CURRENT` - Current file number
- `PROGRESS_TOTAL` - Total files to sync
- `PROGRESS_FILE` - Current filename

## File Scanning

### LocalFolderScanner Features
- **Recursive Scanning**: Traverses subdirectories
- **Hash Calculation**: SHA-256 for change detection
- **Exclude Patterns**: Filters system files (.tmp, .cache, etc.)
- **SAF Integration**: Uses DocumentFile API for Android 10+ compatibility

### Scan Process
1. Open folder using SAF content URI
2. Recursively list all files
3. Calculate SHA-256 hash for each file
4. Build FileInfo list with metadata
5. Return ScanResult with statistics

### Example Usage
```kotlin
val scanResult = folderScanner.scanFolder(
    folderUri = Uri.parse("content://..."),
    recursive = true,
    excludePatterns = listOf(".tmp", ".cache", "node_modules")
)

println("Total files: ${scanResult.totalFiles}")
println("Total size: ${formatBytes(scanResult.totalSize)}")
```

## Error Handling

### Retry Conditions
Worker retries on:
- `IOException` - Network errors
- `SocketException` - Connection failures

### Failure Conditions
Worker fails permanently on:
- Invalid folder configuration
- Missing SAF permissions
- Max retries exceeded (3)
- Non-network errors

### Error Reporting
```kotlin
Result.failure(
    workDataOf(
        "error" to "Error message",
        "stacktrace" to exception.stackTraceToString()
    )
)
```

## Integration with ViewModel

### Triggering Sync
```kotlin
viewModel.triggerSync(folderId = "123")
```

### Observing Progress
```kotlin
viewModel.snackbarMessage.collectLatest { message ->
    scaffoldState.snackbarHostState.showSnackbar(message)
}
```

### Scheduling Auto-Sync
Automatically scheduled when:
- Folder is created with `autoSync = true`
- Folder is updated to enable auto-sync

### Canceling Auto-Sync
```kotlin
viewModel.cancelPeriodicSync(folderId = "123")
```

## Performance Considerations

### Optimizations
1. **Parallel Hashing**: Future enhancement for multi-core devices
2. **Resume Capability**: Chunked uploads can resume after failure
3. **Incremental Sync**: Only uploads/downloads changed files
4. **Efficient Scanning**: SAF DocumentFile with streaming

### Resource Usage
- **Memory**: ~10MB for Worker + file buffers
- **Storage**: Temporary cache files (auto-cleaned)
- **Network**: Chunked for large transfers
- **Battery**: Uses WorkManager constraints

## Testing

### Test Scenarios
1. **Small File Upload** (< 5MB)
   - Single request path
   - Verify hash calculation
   
2. **Large File Upload** (> 5MB)
   - Chunked upload path
   - Verify chunk integrity
   - Test resume on failure
   
3. **Network Failure**
   - Verify retry logic
   - Check exponential backoff
   
4. **Battery Constraints**
   - Verify work deferred when battery low
   - Check resume on charge

### Mock Configuration
```kotlin
@Before
fun setup() {
    workManager = WorkManagerTestInitHelper
        .initializeTestWorkManager(context)
}

@Test
fun testSyncWorker() {
    val request = FolderSyncWorker.createOneTimeRequest(123L, true)
    workManager.enqueue(request).result.get()
    
    val workInfo = workManager.getWorkInfoById(request.id).get()
    assertEquals(WorkInfo.State.SUCCEEDED, workInfo.state)
}
```

## Future Enhancements

### Phase 3 (Next)
- Conflict resolution dialog integration
- Bidirectional sync with merge strategies
- User notification for conflicts

### Phase 4
- Sync history with timestamps
- Bandwidth throttling options
- Wi-Fi only sync mode
- Custom notification channels

### Phase 5
- Delta sync (binary diff for large files)
- Compression for text files
- Encryption for sensitive data
- Offline queue management

## API Endpoints

All endpoints documented in backend `mobile_routes.py`:

### Sync Folder Management
- `GET /mobile/sync/folders/{device_id}` - List folders
- `POST /mobile/sync/folders/{device_id}` - Create folder
- `PUT /mobile/sync/folders/{folder_id}` - Update folder
- `DELETE /mobile/sync/folders/{folder_id}` - Delete folder
- `POST /mobile/sync/folders/{folder_id}/trigger` - Trigger sync
- `GET /mobile/sync/folders/{folder_id}/status` - Get status
- `GET /mobile/sync/folders/{folder_id}/files` - List remote files

### File Upload
- `POST /mobile/upload/file/{folder_id}` - Upload small file
- `POST /mobile/upload/chunked/initiate` - Start chunked upload
- `POST /mobile/upload/chunked/chunk` - Upload chunk
- `POST /mobile/upload/chunked/{upload_id}/finalize` - Complete upload
- `DELETE /mobile/upload/chunked/{upload_id}/cancel` - Cancel upload

### File Download
- `GET /mobile/download/file/{folder_id}` - Download file

### Upload Queue
- `GET /mobile/upload/queue/{device_id}` - Get queue items
- `DELETE /mobile/upload/queue/{upload_id}` - Cancel upload
- `POST /mobile/upload/queue/{upload_id}/retry` - Retry failed upload

## Dependencies

```gradle
// WorkManager with Hilt support
implementation "androidx.work:work-runtime-ktx:2.9.1"
implementation "androidx.hilt:hilt-work:1.2.0"
kapt "androidx.hilt:hilt-compiler:1.2.0"

// Storage Access Framework
implementation "androidx.documentfile:documentfile:1.0.1"

// Networking
implementation "com.squareup.retrofit2:retrofit:2.9.0"
implementation "com.squareup.okhttp3:okhttp:4.12.0"
```

## Best Practices Applied

✅ **Hilt Dependency Injection** - Worker uses `@HiltWorker` annotation  
✅ **Coroutines** - All I/O on Dispatchers.IO  
✅ **Progress Reporting** - WorkManager Progress API  
✅ **Error Handling** - Try-catch with proper Result types  
✅ **Resource Cleanup** - Temporary files deleted in finally blocks  
✅ **Battery Optimization** - WorkManager constraints  
✅ **Network Efficiency** - Chunked uploads with resume  
✅ **Memory Management** - Streaming for large files  
✅ **SAF Integration** - Persistent URI permissions  
✅ **Type Safety** - Kotlin sealed classes and enums  

## Status

**Current Implementation:** ✅ Complete  
**Testing:** ⏳ Pending  
**Documentation:** ✅ Complete  
**Integration:** ✅ Complete
