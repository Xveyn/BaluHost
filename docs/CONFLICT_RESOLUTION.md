# Conflict Resolution System

## Overview
The conflict resolution system provides intelligent detection and resolution of file conflicts during bidirectional synchronization. It follows Android and sync best practices with automatic and manual resolution strategies.

## Architecture

### Components

1. **ConflictDetectionService** (`domain/service/`)
   - Pure domain logic (no Android dependencies)
   - Immutable data structures
   - Timestamp and hash-based conflict detection
   - Automatic resolution strategies

2. **ConflictResolutionDialog** (`presentation/ui/components/`)
   - Material 3 glassmorphism design
   - Per-file and batch resolution
   - Visual comparison of local vs remote versions
   - Accessible UI with semantic colors

3. **FolderSyncWorker** (Enhanced)
   - Integrates ConflictDetectionService
   - Applies automatic resolutions
   - Stores manual conflicts for UI handling
   - Progress reporting during conflict analysis

4. **FolderSyncViewModel** (Enhanced)
   - Manages pending conflicts state
   - Handles conflict resolution actions
   - Triggers re-sync after resolution

## Conflict Detection Rules

### Detection Algorithm

The service analyzes three scenarios:

#### 1. File exists in both locations
```kotlin
when {
    hashes_match -> NO_ACTION
    both_modified_after_last_sync -> CONFLICT
    only_local_modified -> UPLOAD
    only_remote_modified -> DOWNLOAD
    neither_modified_but_different -> CONFLICT (edge case)
}
```

#### 2. File only exists locally
```kotlin
-> UPLOAD (new local file)
```

#### 3. File only exists remotely
```kotlin
-> DOWNLOAD (new remote file)
```

### Conflict Detection Flow

```
Local Files Scan
       ↓
Remote Files Fetch
       ↓
Create File Maps (by relativePath)
       ↓
For Each File:
  ├─ Compare Hashes
  ├─ Check Last Sync Time
  ├─ Compare Timestamps
  └─ Determine Action
       ↓
Group Results:
  ├─ To Upload
  ├─ To Download
  ├─ Conflicts
  └─ No Action
```

## Resolution Strategies

### 1. Keep Local (`ConflictResolution.KEEP_LOCAL`)
- **Action:** Upload local version to server
- **Use Case:** Local changes are authoritative
- **Behavior:** Overwrites server file

### 2. Keep Server (`ConflictResolution.KEEP_SERVER`)
- **Action:** Download server version to local
- **Use Case:** Server changes are authoritative
- **Behavior:** Overwrites local file

### 3. Keep Newest (`ConflictResolution.KEEP_NEWEST`)
- **Action:** Compare timestamps, keep newer file
- **Use Case:** Time-based resolution (default)
- **Behavior:** Automatic based on `modifiedAt`

### 4. Ask User (`ConflictResolution.ASK_USER`)
- **Action:** Present conflict dialog
- **Use Case:** Manual review required
- **Behavior:** Stores conflicts, shows UI

## Automatic Resolution

### Configuration
Each sync folder has a `conflictResolution` setting:

```kotlin
data class SyncFolderConfig(
    // ...
    val conflictResolution: ConflictResolution = ConflictResolution.KEEP_NEWEST
)
```

### Resolution Process

```kotlin
// Worker detects conflicts
val analysisResult = conflictDetectionService.analyzeConflicts(
    localFiles, remoteFiles, lastSyncTime
)

// Apply automatic resolution
if (folder.conflictResolution != ConflictResolution.ASK_USER) {
    analysisResult.conflicts.forEach { conflict ->
        val action = conflictDetectionService.resolveConflict(
            conflict, 
            folder.conflictResolution
        )
        // Execute upload or download
    }
}
```

### Example Scenarios

#### Scenario 1: Keep Newest (Default)
```
Local:  document.pdf  (modified: 2025-12-10 10:00, size: 500KB)
Remote: document.pdf  (modified: 2025-12-10 09:00, size: 450KB)

Resolution: UPLOAD (local is newer)
Action: Upload local → server
```

#### Scenario 2: Keep Local
```
Local:  config.json  (modified: 2025-12-10 08:00)
Remote: config.json  (modified: 2025-12-10 09:00)

Resolution: UPLOAD (always keep local)
Action: Upload local → server (even though older)
```

#### Scenario 3: Ask User
```
Local:  report.docx  (modified: 2025-12-10 10:00, size: 1.2MB)
Remote: report.docx  (modified: 2025-12-10 10:00, size: 1.5MB)

Resolution: CONFLICT (same timestamp, different content)
Action: Show ConflictResolutionDialog
```

## Manual Resolution UI

### ConflictResolutionDialog Features

1. **Conflict List**
   - Shows all conflicting files
   - File name, path, size, timestamp
   - Visual comparison cards

2. **Batch Actions**
   - "Alle Lokal" - Keep all local versions
   - "Alle Server" - Keep all server versions
   - "Alle Neuste" - Keep all newest versions

3. **Per-File Resolution**
   - Click local/remote version card
   - Shows size and timestamp
   - Visual selection indicator

4. **Resolution Chips**
   - "Neuste" strategy selector
   - Can be expanded with more strategies

### UI Components

```kotlin
ConflictResolutionDialog(
    conflicts: List<FileConflict>,
    onResolve: (Map<String, ConflictResolution>) -> Unit,
    onDismiss: () -> Unit
)
```

### Dialog Structure

```
┌─────────────────────────────────────┐
│ 🔀 Konflikte lösen                  │
│ 3 Dateien mit Konflikten            │
├─────────────────────────────────────┤
│ Alle Konflikte lösen:               │
│ [Lokal] [Server] [Neuste]           │
├─────────────────────────────────────┤
│ ┌─────────────────────────────────┐ │
│ │ 📄 document.pdf                 │ │
│ │ /Documents/work/document.pdf    │ │
│ │                                 │ │
│ │ [✓ Lokal]    [ Server]          │ │
│ │ 1.2 MB       1.5 MB             │ │
│ │ 10:00        09:30              │ │
│ │                                 │ │
│ │ Strategie: [✓ Neuste]           │ │
│ └─────────────────────────────────┘ │
│                                     │
│ (Scroll for more conflicts)         │
├─────────────────────────────────────┤
│          [Abbrechen]  [Lösen (3)]   │
└─────────────────────────────────────┘
```

## Data Flow

### 1. Conflict Detection (Worker)

```
Scan Local Files
     ↓
Fetch Remote Files
     ↓
ConflictDetectionService.analyzeConflicts()
     ↓
Apply Automatic Resolution
     ↓
Store Manual Conflicts → PreferencesManager
     ↓
Return Result to Worker
```

### 2. Manual Resolution (UI)

```
FolderSyncViewModel loads conflicts
     ↓
FolderSyncScreen shows badge/notification
     ↓
User opens ConflictResolutionDialog
     ↓
User selects resolutions
     ↓
ViewModel.resolveConflicts()
     ↓
Clear conflicts from storage
     ↓
Re-trigger sync with resolutions
```

### 3. Bidirectional Sync Flow

```
performBidirectionalSync()
     ↓
Analyze Conflicts
     ↓
┌─────────────────┐
│ Has Conflicts?  │
└─────┬───────────┘
      │
   Yes│    No
      ↓     ↓
   Auto │  Direct
   Resolve│ Sync
      ↓     │
   ┌─────────┐
   │ Can Auto│
   │ Resolve?│
   └────┬────┘
        │
     Yes│    No
        ↓     ↓
   Execute  Store
   Actions  Conflicts
        ↓     ↓
   Upload  Show
   Download Dialog
        ↓
   Complete
```

## Conflict Storage

### PreferencesManager Integration

```kotlin
// Save conflicts
suspend fun savePendingConflicts(
    folderId: Long, 
    conflicts: List<FileConflict>
)

// Load conflicts
fun getPendingConflicts(folderId: Long): Flow<List<FileConflict>>

// Clear conflicts
suspend fun clearPendingConflicts(folderId: Long)
```

### Storage Format

Conflicts stored as delimited string in DataStore:
```
id::relativePath::fileName::localSize::remoteSize::localModifiedAt::remoteModifiedAt::detectedAt|||...
```

Example:
```
123_/docs/file.pdf::/docs/file.pdf::file.pdf::1048576::2097152::1702119600000::1702119800000::1702120000000
```

## Testing

### Unit Tests

#### ConflictDetectionService Tests

```kotlin
@Test
fun `detect conflict when both modified after sync`() {
    val local = LocalFileInfo(
        relativePath = "test.txt",
        hash = "hash1",
        modifiedAt = 1000L
    )
    val remote = RemoteFileInfo(
        relativePath = "test.txt",
        hash = "hash2",
        modifiedAt = 1100L
    )
    val lastSync = 500L
    
    val result = service.analyzeConflicts(
        listOf(local), 
        listOf(remote), 
        lastSync
    )
    
    assertEquals(1, result.conflicts.size)
    assertEquals(SyncAction.CONFLICT, result.conflicts[0].action)
}
```

#### Resolution Strategy Tests

```kotlin
@Test
fun `keep newest resolves to newer file`() {
    val conflict = FileConflict(
        localModifiedAt = 1000L,
        remoteModifiedAt = 2000L,
        // ...
    )
    
    val action = service.resolveConflict(
        conflict, 
        ConflictResolution.KEEP_NEWEST
    )
    
    assertEquals(SyncAction.DOWNLOAD, action)
}
```

### Integration Tests

#### Worker Tests

```kotlin
@Test
fun `bidirectional sync resolves conflicts automatically`() {
    // Setup: Create local and remote files with conflicts
    // Configure folder with KEEP_NEWEST resolution
    
    val request = FolderSyncWorker.createOneTimeRequest(123L, true)
    workManager.enqueue(request)
    
    val workInfo = workManager.getWorkInfoById(request.id).get()
    
    assertEquals(WorkInfo.State.SUCCEEDED, workInfo.state)
    // Verify no pending conflicts
    val conflicts = preferencesManager.getPendingConflicts(123L).first()
    assertTrue(conflicts.isEmpty())
}
```

### UI Tests

```kotlin
@Test
fun `conflict dialog shows all conflicts`() {
    composeTestRule.setContent {
        ConflictResolutionDialog(
            conflicts = listOf(
                FileConflict(/* ... */),
                FileConflict(/* ... */)
            ),
            onResolve = {},
            onDismiss = {}
        )
    }
    
    composeTestRule.onNodeWithText("2 Dateien mit Konflikten").assertExists()
}
```

## Performance Considerations

### Optimizations

1. **Hash Comparison First**
   - Quick elimination of identical files
   - Avoids timestamp comparison overhead

2. **Map-Based Lookup**
   - O(1) file lookup by relativePath
   - Efficient for large folder scans

3. **Lazy Conflict Resolution**
   - Manual conflicts stored, not processed immediately
   - UI resolution only when needed

4. **Batch Operations**
   - Single transaction for multiple file actions
   - Reduces API calls

### Memory Usage

- **Conflict Data:** ~200 bytes per conflict
- **UI State:** ~1KB for dialog with 10 conflicts
- **Storage:** Text-based, minimal disk usage

### Network Efficiency

- **Hash-based Sync:** Only changed files transferred
- **Chunked Uploads:** Resume capability on failure
- **Parallel Downloads:** Configurable concurrency

## Best Practices Applied

✅ **Domain-Driven Design**
- ConflictDetectionService is pure domain logic
- No Android dependencies in service layer
- Testable without instrumentation

✅ **Immutability**
- All data classes are immutable
- No mutable state in service
- Thread-safe operations

✅ **Separation of Concerns**
- Detection logic separate from UI
- Resolution strategies independent
- Storage abstracted via repository

✅ **User Experience**
- Clear visual indicators
- Batch actions for efficiency
- Progress feedback during analysis
- Non-blocking UI (background processing)

✅ **Error Handling**
- Graceful fallback to manual resolution
- Conflict detection never blocks sync
- Clear error messages

✅ **Material 3 Design**
- Glassmorphism cards
- Semantic colors (Sky400, Green500, Orange500)
- Accessible touch targets
- Responsive layout

## Future Enhancements

### Phase 1 (Completed)
- ✅ Basic conflict detection
- ✅ Automatic resolution strategies
- ✅ Manual resolution UI
- ✅ Bidirectional sync integration

### Phase 2 (Planned)
- 🔄 Conflict history tracking
- 🔄 Smart conflict prediction
- 🔄 Merge strategies for text files
- 🔄 Three-way merge for Git-like resolution

### Phase 3 (Planned)
- 🔄 ML-based resolution suggestions
- 🔄 User preference learning
- 🔄 Collaborative conflict resolution
- 🔄 Real-time conflict notifications

## Troubleshooting

### Common Issues

**Issue:** Conflicts not detected
- Check `lastSync` timestamp is accurate
- Verify hash calculation is consistent
- Ensure clock synchronization

**Issue:** Automatic resolution fails
- Verify folder configuration
- Check network connectivity
- Review Worker logs

**Issue:** Dialog doesn't show
- Check `pendingConflicts` StateFlow
- Verify PreferencesManager storage
- Ensure LaunchedEffect triggers

## API Endpoints

No dedicated conflict API endpoints required. Uses existing sync endpoints:

- `GET /mobile/sync/folders/{folder_id}/files` - List remote files
- `POST /mobile/upload/file/{folder_id}` - Upload resolved file
- `GET /mobile/download/file/{folder_id}` - Download resolved file

## Dependencies

```gradle
// No additional dependencies required
// Uses existing:
// - Hilt for DI
// - Material 3 for UI
// - DataStore for storage
// - WorkManager for background processing
```

## Status

**Implementation:** ✅ Complete  
**Testing:** ⏳ Pending  
**Documentation:** ✅ Complete  
**Integration:** ✅ Complete
